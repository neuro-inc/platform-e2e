import asyncio
import logging
import re
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4 as uuid

import aiodocker
import pytest
from neuromation.api import JobStatus, LocalImage, RemoteImage

from platform_e2e import Helper


log = logging.getLogger(__name__)


TEST_IMAGE_NAME = "e2e-echo-image"


@pytest.fixture()
async def docker(loop: asyncio.AbstractEventLoop) -> AsyncIterator[aiodocker.Docker]:
    client = aiodocker.Docker()
    yield client
    await client.close()


@pytest.fixture(scope="session")
def tag() -> str:
    return str(uuid())


async def generate_image(docker: aiodocker.Docker, name: str, tag: str) -> None:
    image_archive = Path(__file__).parent / "assets/echo-tag.tar"
    image_name = f"{name}:{tag}"
    log.info(f"Build image {image_name}")
    with image_archive.open(mode="r+b") as fileobj:
        await docker.images.build(
            fileobj=fileobj, tag=image_name, buildargs={"TAG": tag}, encoding="identity"
        )


@pytest.fixture()
async def local_image(
    loop: asyncio.AbstractEventLoop, docker: aiodocker.Docker, tag: str
) -> AsyncIterator[LocalImage]:
    name = TEST_IMAGE_NAME

    await generate_image(docker, name, tag)
    image = LocalImage(name=name, tag=tag)
    yield image
    log.info(f"Remove image {image}")
    await docker.images.delete(str(image), force=True)


@pytest.fixture()
async def remote_image(tag: str, helper: Helper) -> RemoteImage:
    return RemoteImage(
        name=TEST_IMAGE_NAME,
        tag=tag,
        registry=helper.registry.host,
        owner=helper.username,
    )


@pytest.fixture()
async def local_image_for_pull(
    tag: str, helper: Helper, docker: aiodocker.Docker
) -> AsyncIterator[LocalImage]:
    image = LocalImage(name=TEST_IMAGE_NAME, tag=f"{tag}-pull")
    yield image
    log.info(f"Remove image {image}")
    await docker.images.delete(str(image), force=True)


@pytest.mark.dependency(name="push_image")
async def test_push(
    helper: Helper, local_image: LocalImage, remote_image: RemoteImage
) -> None:
    await helper.client.images.push(local_image, remote_image)


@pytest.mark.dependency(depends=["push_image"])
async def test_pull(
    helper: Helper, remote_image: RemoteImage, local_image_for_pull: LocalImage
) -> None:
    await helper.client.images.pull(remote_image, local_image_for_pull)


@pytest.mark.dependency(depends=["push_image"])
async def test_run_container(
    helper: Helper, remote_image: RemoteImage, tag: str
) -> None:
    job = await helper.run_job(str(remote_image), wait_state=JobStatus.SUCCEEDED)
    await helper.check_job_output(job.id, re.escape(tag))
