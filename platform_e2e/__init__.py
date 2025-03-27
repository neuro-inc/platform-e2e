import asyncio
import hashlib
import logging
import os
import re
import secrets
import subprocess
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from hashlib import sha1
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiohttp
from apolo_sdk import (
    CONFIG_ENV_NAME,
    Client,
    Container,
    HTTPPort,
    JobDescription,
    JobStatus,
    Resources,
    Volume,
    login_with_token,
)
from yarl import URL

JOB_OUTPUT_TIMEOUT = 60 * 5
JOB_OUTPUT_SLEEP_SECONDS = 2

log = logging.getLogger(__name__)


class Helper:
    def __init__(self, client: Client, tmp_path: Path, config_path: Path) -> None:
        self._client = client
        self._tmp_path = tmp_path
        self._config_path = config_path
        self._tmpstorage = URL.build(
            scheme="storage",
            host=client.cluster_name,
            path=f"/{client.config.project_name_or_raise}/{str(uuid4())}/",
        )
        self._has_root_storage = False

    @property
    def client(self) -> Client:
        return self._client

    @property
    def tmpstorage(self) -> URL:
        return self._tmpstorage

    @property
    def registry(self) -> URL:
        return self._client.config.registry_url

    @property
    def username(self) -> str:
        return self._client.username

    @property
    def cluster_name(self) -> str:
        return self._client.cluster_name

    @property
    def project_name(self) -> str:
        return self._client.config.project_name_or_raise

    @property
    def config_path(self) -> Path:
        return self._config_path

    async def close(self) -> None:
        if self._has_root_storage:
            await self.rm("")
            self._has_root_storage = False
        await self._client.close()

    async def run_job(
        self,
        image: str,
        command: str | None = None,
        *,
        description: str | None = None,
        wait_state: JobStatus = JobStatus.RUNNING,
        http: HTTPPort | None = None,
        resources: Resources | None = None,
        name: str | None = None,
        volumes: list[Volume] | None = None,
        schedule_timeout: float | None = None,
        wait_timeout: int = 180,
    ) -> JobDescription:
        if resources is None:
            resources = Resources(
                cpu=0.1,
                memory=128 * 10**6,
            )
        if volumes is None:
            volumes = []
        log.info("Submit job")
        remote_image = self.client.parse.remote_image(image)
        container = Container(
            image=remote_image,
            command=command,
            resources=resources,
            volumes=volumes,
            http=http,
        )
        job = await self.client.jobs.run(
            container=container,
            scheduler_enabled=False,
            description=description,
            name=name,
            schedule_timeout=schedule_timeout,
        )
        return await self._wait_job_state(job, wait_state, wait_timeout)

    async def _wait_job_state(
        self, job: JobDescription, wait_state: JobStatus, timeout: int = 180
    ) -> JobDescription:
        for i in range(timeout):
            log.info("Wait state %s: %s -> %s", wait_state, job.id, job.status)
            if job.status == wait_state:
                break
            if (wait_state != JobStatus.FAILED and job.status == JobStatus.FAILED) or (
                wait_state == JobStatus.FAILED and job.status == JobStatus.SUCCEEDED
            ):
                raise AssertionError(f"Wait for {wait_state} is failed: {job.status}")
            if wait_state == JobStatus.PENDING and job.status in (
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
            ):
                break
            await asyncio.sleep(1)
            job = await self.client.jobs.status(job.id)
        else:
            raise AssertionError(f"Cannot start job to {wait_state}: {job.status}")
        return job

    async def wait_job_state(
        self, job_id: str, wait_state: JobStatus
    ) -> JobDescription:
        job = await self.client.jobs.status(job_id)
        return await self._wait_job_state(job, wait_state)

    async def http_get(self, url: URL) -> str:
        """
        Try to fetch given url few times.
        """
        async with aiohttp.ClientSession() as session:
            for i in range(3):
                log.info("Probe %s", url)
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.text()
                await asyncio.sleep(5)
            else:
                raise aiohttp.ClientResponseError(
                    status=resp.status,
                    message=f"Server return {resp.status}",
                    history=tuple(),
                    request_info=resp.request_info,
                )

    async def check_job_output(
        self, job_id: str, expected: str, *, re_flags: int = 0
    ) -> None:
        """
        Wait until job output satisfies given regexp
        """
        started_at = time.monotonic()
        while time.monotonic() - started_at < JOB_OUTPUT_TIMEOUT:
            log.info("Monitor %s", job_id)
            chunks = []
            async with self.client.jobs.monitor(job_id) as it:
                async for chunk in it:
                    if not chunk:
                        break
                    chunks.append(chunk.decode())
                    if re.search(expected, "".join(chunks), re_flags):
                        return
                    if time.monotonic() - started_at > JOB_OUTPUT_TIMEOUT:
                        break
                    await asyncio.sleep(JOB_OUTPUT_SLEEP_SECONDS)

        raise AssertionError(
            f"Output of job {job_id} does not satisfy to expected regexp: {expected}"
        )

    async def mkdir(self, path: str) -> None:
        await self.ensure_root_storage()
        await self._client.storage.mkdir(
            self.tmpstorage / path, parents=True, exist_ok=True
        )

    async def rm(self, path: str) -> None:
        await self._client.storage.rm(self.tmpstorage / path)

    async def ensure_root_storage(self) -> None:
        if not self._has_root_storage:
            self._has_root_storage = True
            await self.mkdir("")

    async def gen_random_file(self, path: Path, size: int) -> str:
        hasher = hashlib.sha1()
        with path.open("wb") as file:
            generated = 0
            while generated < size:
                length = min(1024 * 1024, size - generated)
                data = os.urandom(length)
                file.write(data)
                hasher.update(data)
                generated += len(data)
        return hasher.hexdigest()

    async def calc_storage_checksum(self, path: str) -> str:
        tmp_file = self._tmp_path / (str(uuid4()) + ".tmp")
        await self._client.storage.download_file(
            self.tmpstorage / path, URL(tmp_file.as_uri())
        )
        return await self.calc_local_checksum(tmp_file)

    async def calc_local_checksum(self, path: Path) -> str:
        hasher = hashlib.sha1()
        with path.open("rb") as file:
            chunk = file.read(1024 * 1024)
            while chunk:
                hasher.update(chunk)
                chunk = file.read(1024 * 1024)
        return hasher.hexdigest()

    @contextmanager
    def docker_context(self, monkeypatch: Any) -> Iterator[None]:
        with monkeypatch.context() as context:
            # docker support
            context.setenv("DOCKER_CONFIG", f"{self._tmp_path}")

            # podman support
            docker_config = self._tmp_path / "config.json"
            monkeypatch.setenv("REGISTRY_AUTH_FILE", f"{docker_config}")

            monkeypatch.setenv(CONFIG_ENV_NAME, f"{self.config_path}")
            shell("neuro config docker")

            yield

            docker_config.unlink()

    async def create_bucket(self, name: str, *, wait: bool = False) -> None:
        await self.client.buckets.create(name)
        if wait:
            t0 = time.monotonic()
            delay = 1
            url = URL(f"blob:{name}")
            while time.monotonic() - t0 < 60:
                try:
                    async with self.client.buckets.list_blobs(url, limit=1) as it:
                        async for _ in it:
                            pass
                    return
                except Exception as e:
                    print(e)
                    delay = min(delay * 2, 10)
                    await asyncio.sleep(delay)
            raise RuntimeError(f"Bucket {name} doesn't available after the creation")

    async def delete_bucket(self, bucket_name_or_id: str) -> None:
        await self.client.buckets.rm(bucket_name_or_id)

    async def cleanup_bucket(self, bucket_name_or_id: str) -> None:
        # Each test needs a clean bucket state and we can't delete bucket until it's
        # cleaned
        async with self.client.buckets.list_blobs(
            URL(f"blob:{bucket_name_or_id}"), recursive=True
        ) as blobs_it:
            # XXX: We do assume we will not have tests that run 10000 of objects.
            # If we do, please add a semaphore here.
            tasks = []
            async for blob in blobs_it:
                log.info("Removing %s %s", bucket_name_or_id, blob.key)
                tasks.append(
                    self.client.buckets.delete_blob(bucket_name_or_id, key=blob.key)
                )
        await asyncio.gather(*tasks)

    @asynccontextmanager
    async def create_tmp_bucket(self) -> AsyncIterator[str]:
        name = f"neuro-e2e-{secrets.token_hex(10)}"
        await self.create_bucket(name, wait=True)
        yield name
        await self.cleanup_bucket(name)
        await self.delete_bucket(name)

    async def upload_blob(self, bucket_name: str, key: str, file: Path | str) -> None:
        await self.client.buckets.upload_file(
            URL("file:" + str(file)), URL(f"blob:{bucket_name}/{key}")
        )

    async def check_blob_size(self, bucket_name: str, key: str, size: int) -> None:
        blob = await self.client.buckets.head_blob(bucket_name, key)
        assert blob.size == size

    async def check_blob_checksum(
        self, bucket_name: str, key: str, checksum: str, tmp_path: Path
    ) -> None:
        await self.client.buckets.download_file(
            URL(f"blob:{bucket_name}/{key}"),
            URL("file:" + str(tmp_path)),
        )
        assert self.hash_hex(tmp_path) == checksum, "checksum test failed for {url}"

    def hash_hex(self, file: str | Path) -> str:
        _hash = sha1()
        with open(file, "rb") as f:
            for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
                _hash.update(block)

        return _hash.hexdigest()


async def ensure_config(
    token: str, url: URL, tmp_path_factory: Callable[[], Path]
) -> Path | None:
    if token is not None:
        log.info("Api URL: %s", str(url))
        log.info("Token: %s", token[:8] + "...")
        config_path = tmp_path_factory() / ".nmrc"
        await login_with_token(token=token, url=url, path=config_path)
        return config_path
    else:
        return None


def shell(cmd: str, timeout: float = 300) -> str:
    log.info(f"Run {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        timeout=timeout,
        capture_output=True,
    )
    if result.returncode != os.EX_OK:
        raise SystemError(
            f"Command `{cmd}` exits with code {result.returncode}, "
            f"Stderr: {result.stderr.decode('utf-8')},"
            f"Stdout: {result.stdout.decode('utf-8')}"
        )
    if result.stderr:
        log.warning(
            f"Command {cmd} write something to stderr: "
            f"{result.stderr.decode('utf-8')}"
        )
    return result.stdout.decode("utf-8")
