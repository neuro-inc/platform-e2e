import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional
from uuid import uuid4

import pytest
import pytest_asyncio

from neuro_sdk import DEFAULT_CONFIG_PATH, HTTPPort, JobStatus, ResourceNotFound, get
from platform_e2e import Helper, ensure_config


log = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_event_loop()


@pytest_asyncio.fixture(scope="session")
async def config_path(tmp_path_factory: Any) -> Path:
    path = await ensure_config(
        "CLIENT_TEST_E2E_USER_NAME", "CLIENT_TEST_E2E_API_URI", tmp_path_factory
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


@pytest_asyncio.fixture(scope="session")
async def config_path_alt(tmp_path_factory: Any) -> Path:
    path = await ensure_config(
        "CLIENT_TEST_E2E_USER_NAME_ALT", "CLIENT_TEST_E2E_API_URI", tmp_path_factory
    )
    if path is None:
        # pytest.skip() actually raises an exception itself
        # raise statement is required for mypy checker
        raise pytest.skip("CLIENT_TEST_E2E_USER_NAME_ALT variable is not set")
    else:
        return path


@pytest_asyncio.fixture(scope="session")
async def helper(config_path: Path, tmp_path_factory: Any) -> AsyncIterator[Helper]:
    client = await get(path=config_path)
    print("API URL", client.config.api_url)
    yield Helper(client, tmp_path_factory.mktemp("helper"), config_path)
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def helper_alt(
    config_path_alt: Path, tmp_path_factory: Any
) -> AsyncIterator[Helper]:
    client = await get(path=config_path_alt)
    print("Alt API URL", client.config.api_url)
    yield Helper(client, tmp_path_factory.mktemp("helper"), config_path_alt)
    await client.close()


@pytest.fixture
async def kill_later(helper: Helper) -> AsyncIterator[Callable[[str], None]]:
    job_ids = []

    def _kill_later(job_id: str) -> None:
        job_ids.append(job_id)

    yield _kill_later

    for job_id in job_ids:
        try:
            await helper.client.jobs.kill(job_id)
        except ResourceNotFound:
            pass

    for job_id in job_ids:
        await helper.wait_job_state(job_id, JobStatus.CANCELLED)


@pytest.fixture
def secret_job(
    helper: Helper, kill_later: Callable[[str], None]
) -> Callable[..., Awaitable[Dict[str, Any]]]:
    async def _run(
        http_port: bool, http_auth: bool = False, description: Optional[str] = None
    ) -> Dict[str, Any]:
        secret = str(uuid4())
        # Run http job
        command = (
            f"bash -c \"echo -n '{secret}' > /usr/share/nginx/html/secret.txt; "
            f"timeout 15m /usr/sbin/nginx -g 'daemon off;'\""
        )
        if http_port:
            http: Optional[HTTPPort] = HTTPPort(80, http_auth)
        else:
            http = None
        if not description:
            description = "nginx with secret file"
            if http_port:
                description += " and forwarded http port"
                if http_auth:
                    description += " with authentication"
        job = await helper.run_job(
            "ghcr.io/neuro-inc/nginx:latest",
            command,
            description=description,
            http=http,
        )
        kill_later(job.id)
        return {
            "id": job.id,
            "secret": secret,
            "ingress_url": job.http_url,
            "internal_hostname": job.internal_hostname,
        }

    return _run
