import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import aiohttp
import pytest
from neuromation.api import (
    DEFAULT_CONFIG_PATH,
    Client,
    Image,
    JobDescription,
    JobStatus,
    NetworkPortForwarding,
    Resources,
    get,
    login_with_token,
)
from neuromation.utils import run
from yarl import URL


NETWORK_TIMEOUT = 60.0 * 3
CLIENT_TIMEOUT = aiohttp.ClientTimeout(None, None, NETWORK_TIMEOUT, NETWORK_TIMEOUT)
JOB_OUTPUT_TIMEOUT = 60 * 5
JOB_OUTPUT_SLEEP_SECONDS = 2

log = logging.getLogger(__name__)


class Helper:
    def __init__(self, client: Client) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client

    async def close(self) -> None:
        await self._client.close()

    async def run_job(
        self,
        image: str,
        command: str,
        *,
        description: Optional[str] = None,
        wait_state: JobStatus = JobStatus.RUNNING,
        network: Optional[NetworkPortForwarding] = None,
        resources: Optional[Resources] = None,
        name: Optional[str] = None,
    ) -> JobDescription:
        if resources is None:
            resources = Resources(
                cpu=0.1, gpu=None, gpu_model=None, memory_mb=20, shm=True
            )
        log.info("Submit job")
        job = await self.client.jobs.submit(
            image=Image(image, command=command),
            resources=resources,
            network=network,
            is_preemptible=False,
            volumes=None,
            description=description,
            name=name,
        )
        return await self._wait_job_state(job, wait_state)

    async def _wait_job_state(
        self, job: JobDescription, wait_state: JobStatus
    ) -> JobDescription:
        for i in range(60):
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
            raise AssertionError("Cannot start job to {wait_state}: {job.status}")
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


async def ensure_config(env_name: str, tmp_path_factory: Any) -> Optional[Path]:
    token = os.environ.get(env_name)
    if token is not None:
        config_path = tmp_path_factory.mktemp(env_name.lower()) / ".nmrc"
        await login_with_token(
            token=token,
            url=URL("https://dev.neu.ro/api/v1"),
            timeout=CLIENT_TIMEOUT,
            path=config_path,
        )
        await asyncio.sleep(3)
        return config_path
    else:
        return None


@pytest.fixture(scope="session")
def config_path(tmp_path_factory: Any) -> Path:
    path = run(ensure_config("CLIENT_TEST_E2E_USER_NAME", tmp_path_factory))
    if path is None:
        return Path(DEFAULT_CONFIG_PATH)
    else:
        return path


@pytest.fixture(scope="session")
def config_path_alt(tmp_path_factory: Any) -> Path:
    path = run(ensure_config("CLIENT_TEST_E2E_USER_NAME_ALT", tmp_path_factory))
    if path is None:
        # pytest.skip() actually raises an exception itself
        # raise statement is required for mypy checker
        raise pytest.skip("CLIENT_TEST_E2E_USER_NAME_ALT variable is not set")
    else:
        return path


@pytest.fixture()
async def helper(
    config_path: Path, loop: asyncio.AbstractEventLoop
) -> AsyncIterator[Helper]:
    client = await get(timeout=CLIENT_TIMEOUT, path=config_path)
    yield Helper(client)
    await client.close()


@pytest.fixture()
async def helper_alt(
    config_path_alt: Path, loop: asyncio.AbstractEventLoop
) -> AsyncIterator[Helper]:
    client = await get(timeout=CLIENT_TIMEOUT, path=config_path_alt)
    yield Helper(client)
    await client.close()
