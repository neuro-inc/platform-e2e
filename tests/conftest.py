from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import pytest
from apolo_sdk import (
    DEFAULT_CONFIG_PATH,
    HTTPPort,
    JobStatus,
    ResourceNotFound,
    Resources,
    get,
)
from jose import jwt
from neuro_admin_client import AdminClient, ClusterUserRoleType
from neuro_auth_client import AuthClient
from yarl import URL

from platform_e2e import Helper, ensure_config

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def url() -> URL:
    return URL(os.environ.get("CLIENT_TEST_E2E_URI", "https://api.dev.apolo.us"))


@pytest.fixture(scope="session")
def auth_url(url: URL) -> URL:
    if "CLIENT_TEST_E2E_AUTH_URI" in os.environ:
        url = URL(os.environ["CLIENT_TEST_E2E_AUTH_URI"])
    return url


@pytest.fixture(scope="session")
async def auth_client(
    auth_url: URL, admin_token: str | None
) -> AsyncIterator[AuthClient]:
    async with AuthClient(auth_url, admin_token or "") as client:
        yield client


@pytest.fixture(scope="session")
def admin_url(url: URL) -> URL:
    if "CLIENT_TEST_E2E_ADMIN_URI" in os.environ:
        url = URL(os.environ["CLIENT_TEST_E2E_ADMIN_URI"])
    return url.with_path("apis/admin/v1")


@pytest.fixture(scope="session")
async def admin_client(
    admin_url: URL, admin_token: str | None
) -> AsyncIterator[AdminClient]:
    async with AdminClient(base_url=admin_url, service_token=admin_token) as client:
        yield client


@pytest.fixture(scope="session")
def api_url(url: URL) -> URL:
    if "CLIENT_TEST_E2E_API_URI" in os.environ:
        url = URL(os.environ["CLIENT_TEST_E2E_API_URI"])
    return url.with_path("api/v1")


@pytest.fixture(scope="session")
def admin_token() -> str | None:
    return os.environ.get("CLIENT_TEST_E2E_ADMIN_TOKEN")


class UserFactory(Protocol):
    async def __call__(self, name: str) -> str:
        pass


@pytest.fixture(scope="session")
def user_factory(admin_client: AdminClient, auth_client: AuthClient) -> UserFactory:
    async def _add_user(name: str) -> str:
        try:
            await admin_client.create_user(
                name, f"{name}@neu.ro", skip_auto_add_to_clusters=True
            )
        except Exception as ex:
            LOGGER.info("User %s creation failed: %s", name, ex)
            # Check user exists
            await admin_client.get_user(name)
        token = await auth_client.get_user_token(name)
        return token

    return _add_user


class ClusterUserFactory(Protocol):
    async def __call__(self, user_name: str) -> None:
        pass


@pytest.fixture(scope="session")
def cluster_user_factory(
    admin_client: AdminClient, cluster_name: str
) -> ClusterUserFactory:
    async def _add_cluster_user(user_name: str) -> None:
        try:
            await admin_client.create_cluster_user(
                cluster_name=cluster_name,
                user_name=user_name,
                role=ClusterUserRoleType.USER,
            )
        except Exception as ex:
            LOGGER.info("Cluster user %s creation failed: %s", user_name, ex)
            # Check cluster user exists
            await admin_client.get_cluster_user(
                cluster_name=cluster_name, user_name=user_name
            )

    return _add_cluster_user


@pytest.fixture(scope="session")
def cluster_name() -> str:
    return os.environ["CLUSTER_NAME"]


def _hash(value: str) -> str:
    hasher = hashlib.new("sha1")
    hasher.update(value.encode())
    return hasher.hexdigest()[:16]


def _get_user_name_from_token(token: str) -> str:
    claims = jwt.get_unverified_claims(token)
    return claims.get("https://platform.neuromation.io/user") or claims["identity"]


@pytest.fixture(scope="session")
def user_name(cluster_name: str) -> str:
    if "CLIENT_TEST_E2E_USER_TOKEN" in os.environ:
        token = os.environ["CLIENT_TEST_E2E_USER_TOKEN"]
        return _get_user_name_from_token(token)
    return f"neuro-{_hash(cluster_name)}-1"


@pytest.fixture(scope="session")
async def user_token(
    user_factory: UserFactory, cluster_user_factory: ClusterUserFactory, user_name: str
) -> str:
    if "CLIENT_TEST_E2E_USER_TOKEN" in os.environ:
        return os.environ["CLIENT_TEST_E2E_USER_TOKEN"]
    user_token = await user_factory(user_name)
    await cluster_user_factory(user_name)
    return user_token


@pytest.fixture(scope="session")
def user_name_alt(cluster_name: str) -> str:
    if "CLIENT_TEST_E2E_USER_TOKEN_ALT" in os.environ:
        token = os.environ["CLIENT_TEST_E2E_USER_TOKEN_ALT"]
        return _get_user_name_from_token(token)
    return f"neuro-{_hash(cluster_name)}-2"


@pytest.fixture(scope="session")
async def user_token_alt(
    user_factory: UserFactory,
    cluster_user_factory: ClusterUserFactory,
    user_name_alt: str,
) -> str:
    if "CLIENT_TEST_E2E_USER_TOKEN_ALT" in os.environ:
        return os.environ["CLIENT_TEST_E2E_USER_TOKEN_ALT"]
    user_token = await user_factory(user_name_alt)
    await cluster_user_factory(user_name_alt)
    return user_token


@pytest.fixture(scope="session")
async def config_path(
    tmp_path_factory: Any,
    api_url: URL,
    user_name: str,
    user_token: str,
) -> Path:
    path = await ensure_config(
        user_token, api_url, lambda: tmp_path_factory.mktemp(user_name)
    )
    if not path:
        LOGGER.info("User %s config file was not created", user_name)
        path = Path(DEFAULT_CONFIG_PATH).expanduser()
        if not path.exists():
            raise RuntimeError(f"Config file({path}) not found ")
        LOGGER.info("Default config used: %s", path)
    return path


@pytest.fixture(scope="session")
async def config_path_alt(
    tmp_path_factory: Any, api_url: URL, user_name_alt: str, user_token_alt: str
) -> Path:
    path = await ensure_config(
        user_token_alt, api_url, lambda: tmp_path_factory.mktemp(user_name_alt)
    )
    if path is None:
        # pytest.skip() actually raises an exception itself
        # raise statement is required for mypy checker
        raise pytest.skip(f"User {user_name_alt} config file was not created")
    else:
        return path


@pytest.fixture(scope="session")
async def helper(
    config_path: Path,
    tmp_path_factory: Any,
    cluster_name: str,
    user_name: str,
) -> AsyncIterator[Helper]:
    client = await get(path=config_path)
    print("API URL", client.config.api_url)
    await client.config.switch_cluster(cluster_name)
    project_name = f"{user_name}-default"
    try:
        await client._admin.create_project(
            project_name, cluster_name=cluster_name, org_name=None
        )
        await client.config.fetch()
    except Exception as ex:
        LOGGER.info("Project creation failed: %s", ex)
        # Check project exists
        await client._admin.get_project(
            project_name=project_name,
            cluster_name=cluster_name,
            org_name=None,
        )
    await client.config.switch_project(project_name)
    yield Helper(client, tmp_path_factory.mktemp("helper"), config_path)
    await client.close()


@pytest.fixture(scope="session")
async def helper_alt(
    config_path_alt: Path,
    tmp_path_factory: Any,
    cluster_name: str,
    user_name_alt: str,
) -> AsyncIterator[Helper]:
    client = await get(path=config_path_alt)
    print("Alt API URL", client.config.api_url)
    await client.config.switch_cluster(cluster_name)
    project_name = f"{user_name_alt}-default"
    try:
        await client._admin.create_project(
            project_name, cluster_name=cluster_name, org_name=None
        )
        await client.config.fetch()
    except Exception as ex:
        LOGGER.info("Project user %s creation failed: %s", user_name, ex)
        # Check project user exists
        await client._admin.get_project(
            project_name=project_name,
            cluster_name=cluster_name,
            org_name=None,
        )
    await client.config.switch_project(project_name)
    yield Helper(client, tmp_path_factory.mktemp("helper_alt"), config_path_alt)
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
) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def _run(
        http_port: bool,
        http_auth: bool = False,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        secret = str(uuid4())
        # Run http job
        command = (
            f"bash -c \"echo -n '{secret}' > /usr/share/nginx/html/secret.txt; "
            f"timeout 15m /usr/sbin/nginx -g 'daemon off;'\""
        )
        if http_port:
            http: HTTPPort | None = HTTPPort(80, http_auth)
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
            name=name,
            description=description,
            http=http,
            resources=Resources(
                cpu=0.1,
                memory=256 * 10**6,
                shm=True,
            ),
        )
        kill_later(job.id)
        return {
            "id": job.id,
            "secret": secret,
            "ingress_url": job.http_url,
            "internal_hostname": job.internal_hostname,
            "internal_hostname_named": job.internal_hostname_named,
        }

    return _run
