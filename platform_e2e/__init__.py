import asyncio
import hashlib
import logging
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from subprocess import PIPE, run
from typing import Any, AsyncIterator, Callable, Iterator, List, Optional
from uuid import uuid4

import aiohttp
import pytest
from yarl import URL

from neuro_sdk import (
    CONFIG_ENV_NAME,
    DEFAULT_CONFIG_PATH,
    Client,
    Container,
    HTTPPort,
    JobDescription,
    JobStatus,
    Resources,
    Volume,
    get,
    login_with_token,
)
from neuro_sdk.parsing_utils import _ImageNameParser


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


NETWORK_TIMEOUT = 60.0 * 3
CLIENT_TIMEOUT = aiohttp.ClientTimeout(None, None, NETWORK_TIMEOUT, NETWORK_TIMEOUT)
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
            path=f"/{client.username}/{str(uuid4())}/",
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
        command: Optional[str] = None,
        *,
        description: Optional[str] = None,
        wait_state: JobStatus = JobStatus.RUNNING,
        http: Optional[HTTPPort] = None,
        resources: Optional[Resources] = None,
        name: Optional[str] = None,
        volumes: Optional[List[Volume]] = None,
        schedule_timeout: Optional[float] = None,
        wait_timeout: int = 180,
    ) -> JobDescription:
        if resources is None:
            resources = Resources(
                cpu=0.1,
                gpu=None,
                gpu_model=None,
                memory_mb=20,
                shm=True,
                tpu_software_version=None,
                tpu_type=None,
            )
        if volumes is None:
            volumes = []
        log.info("Submit job")
        remote_image = _ImageNameParser(
            self.client.username,
            default_cluster=self.cluster_name,
            registry_url=self.client.config.registry_url,
        ).parse_remote(image)
        container = Container(
            image=remote_image,
            command=command,
            resources=resources,
            volumes=volumes,
            http=http,
        )
        job = await self.client.jobs.run(
            container=container,
            is_preemptible=False,
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
        loop = asyncio.get_event_loop()

        started_at = loop.time()
        chunks = []
        while loop.time() - started_at < JOB_OUTPUT_TIMEOUT:
            log.info("Monitor %s", job_id)
            async for chunk in self.client.jobs.monitor(job_id):
                if not chunk:
                    break
                chunks.append(chunk.decode())
                if re.search(expected, "".join(chunks), re_flags):
                    return
                if loop.time() - started_at < JOB_OUTPUT_TIMEOUT:
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
    def docker_context(
        self, monkeypatch: Any, shell: Callable[..., str]
    ) -> Iterator[None]:
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

    @asynccontextmanager
    async def create_tmp_bucket(self) -> AsyncIterator[str]:
        blob_storage = self.client.blob_storage
        name = "neuro-test-e2e-" + self.username
        available = [x.name for x in await blob_storage.list_buckets()]
        if name not in available:
            await blob_storage.create_bucket(name)
        yield name
        await self.cleanup_bucket(name)
        await blob_storage.delete_bucket(name)

    async def cleanup_bucket(self, bucket_name: str) -> None:
        blobs, _ = await self.client.blob_storage.list_blobs(
            bucket_name, recursive=True
        )
        if not blobs:
            return

        for blob in blobs:
            log.info("Removing %s %s", bucket_name, blob.key)
            await self.client.blob_storage.delete_blob(bucket_name, key=blob.key)


def ensure_config(
    token_env_name: str, uri_env_name: str, tmp_path_factory: Any
) -> Optional[Path]:
    token = os.environ.get(token_env_name)
    uri = os.environ.get(uri_env_name, "https://dev.neu.ro/api/v1")
    if token is not None:
        log.info("Used token from env %s: %s", token_env_name, token[:8] + "...")
        log.info("Api URL: %s", uri)
        config_path = tmp_path_factory.mktemp(token_env_name.lower()) / ".nmrc"
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            login_with_token(
                token=token, url=URL(uri), timeout=CLIENT_TIMEOUT, path=config_path
            )
        )
        loop.close()
        return config_path
    else:
        return None


@pytest.fixture(scope="session")
def config_path(tmp_path_factory: Any) -> Path:
    path = ensure_config(
        "CLIENT_TEST_E2E_USER_NAME", "CLIENT_TEST_E2E_URI", tmp_path_factory
    )

    if not path:
        path = Path(DEFAULT_CONFIG_PATH).expanduser()
        if not path.exists():
            raise RuntimeError(
                f"Neither config file({path}) exists "
                f"nor ENV variable(CLIENT_TEST_E2E_USER_NAME) set"
            )
        log.info("Default config used: %s", path)
    return path


@pytest.fixture(scope="session")
def config_path_alt(tmp_path_factory: Any) -> Path:
    path = ensure_config(
        "CLIENT_TEST_E2E_USER_NAME_ALT", "CLIENT_TEST_E2E_URI", tmp_path_factory
    )
    if path is None:
        # pytest.skip() actually raises an exception itself
        # raise statement is required for mypy checker
        raise pytest.skip("CLIENT_TEST_E2E_USER_NAME_ALT variable is not set")
    else:
        return path


@pytest.fixture()
async def helper(
    config_path: Path, loop: asyncio.AbstractEventLoop, tmp_path: Path
) -> AsyncIterator[Helper]:
    client = await get(timeout=CLIENT_TIMEOUT, path=config_path)
    print("API URL", client.config.api_url)
    yield Helper(client, tmp_path, config_path)
    await client.close()


@pytest.fixture()
async def helper_alt(
    config_path_alt: Path, loop: asyncio.AbstractEventLoop, tmp_path: Path
) -> AsyncIterator[Helper]:
    client = await get(timeout=CLIENT_TIMEOUT, path=config_path_alt)
    print("Alt API URL", client.config.api_url)
    yield Helper(client, tmp_path, config_path_alt)
    await client.close()


@pytest.fixture()
def shell() -> Callable[..., str]:
    def _shell(cmd: str, timeout: float = 300) -> str:
        log.info(f"Run {cmd}")
        result = run(cmd, shell=True, timeout=timeout, stdout=PIPE, stderr=PIPE)
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

    return _shell
