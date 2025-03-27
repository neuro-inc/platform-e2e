import logging
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4 as uuid

import pytest
from apolo_sdk import JobStatus, RemoteImage, ResourceNotFound

from platform_e2e import Helper, shell

log = logging.getLogger(__name__)


@contextmanager
def _build_image(image: RemoteImage) -> Iterator[None]:
    dockerfile = Path(__file__).parent / "assets/Dockerfile.echo"
    image_url = image.as_docker_url()
    log.info(f"Build image {image_url}")
    # build can be failed with error like  next:
    #   error creating read-write layer with ID "xxx": operation not permitted
    # if node has docker engine with aufs storage driver
    # In this case platform-e2e image must be runned with --privileged switch
    shell(
        f"docker build -f {dockerfile} -t {image_url} --build-arg TAG={image.tag} "
        f"{dockerfile.parent}"
    )
    yield
    log.info(f"Remove image {image_url}")
    shell(f"docker rmi {image_url}")


@pytest.fixture(scope="session")
async def image(helper: Helper) -> AsyncIterator[RemoteImage]:
    image = RemoteImage(
        name="platform-e2e",
        tag=str(uuid()),
        registry=helper.registry.host,
        cluster_name=helper.cluster_name,
        project_name=helper.project_name,
    )
    with _build_image(image):
        yield image
        try:
            digest = await helper.client.images.digest(image)
            await helper.client.images.rm(image, digest)
        except ResourceNotFound:
            pass


@pytest.mark.dependency(name="image_pushed")
def test_user_can_push_image(
    helper: Helper, image: RemoteImage, monkeypatch: Any
) -> None:
    with helper.docker_context(monkeypatch):
        shell(f"docker push {image.as_docker_url()}")


@pytest.mark.dependency(name="pull_tested", depends=["image_pushed"])
def test_user_can_pull_image(
    helper: Helper, image: RemoteImage, monkeypatch: Any
) -> None:
    with helper.docker_context(monkeypatch):
        shell(f"docker pull {image.as_docker_url()}")


@pytest.mark.dependency(name="k8s_access_tested", depends=["image_pushed"])
async def test_registry_is_accessible_by_k8s(
    helper: Helper, image: RemoteImage
) -> None:
    job = await helper.run_job(
        str(image),
        wait_state=JobStatus.SUCCEEDED,
        schedule_timeout=240,
        wait_timeout=270,
    )
    assert image.tag
    await helper.check_job_output(job.id, re.escape(image.tag))


@pytest.mark.dependency(depends=["pull_tested", "k8s_access_tested"])
async def test_user_can_remove_image(helper: Helper, image: RemoteImage) -> None:
    digest = await helper.client.images.digest(image)
    await helper.client.images.rm(image, digest)
