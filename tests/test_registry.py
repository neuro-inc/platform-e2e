import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4 as uuid

import pytest

from neuromation.api import JobStatus, RemoteImage
from platform_e2e import Helper


log = logging.getLogger(__name__)


TEST_IMAGE_NAME = "e2e-echo-image"


def _generate_image(name: str, tag: str, shell: Callable[..., str]) -> str:
    dockerfile = Path(__file__).parent / "assets/Dockerfile.echo"
    image_name = f"{name}:{tag}"
    log.info(f"Build image {image_name}")
    # build can be failed with error like  next:
    #   error creating read-write layer with ID "xxx": operation not permitted
    # if node has docker engine with aufs storage driver
    # In this case platform-e2e image must be runned with --privileged switch
    shell(
        f"docker build -f {dockerfile} -t {image_name} --build-arg TAG={tag} "
        f"{dockerfile.parent}"
    )
    return image_name


@pytest.fixture(scope="session")
def tag() -> str:
    return str(uuid())


@pytest.fixture(scope="session")
def name() -> str:
    return TEST_IMAGE_NAME


@pytest.fixture()
def generated_image_name(
    name: str, tag: str, shell: Callable[..., str]
) -> Iterator[str]:
    image_name = _generate_image(name, tag, shell)
    yield image_name
    log.info(f"Remove image {image_name}")
    shell(f"docker rmi {image_name}")


@pytest.fixture()
def remote_image(name: str, tag: str, helper: Helper) -> RemoteImage:
    return RemoteImage(
        name=name,
        tag=tag,
        registry=helper.registry.host,
        owner=helper.username,
        cluster_name=helper.cluster_name,
    )


@pytest.fixture()
def image_with_repo(
    remote_image: RemoteImage, helper: Helper, shell: Callable[..., str]
) -> Iterator[str]:
    image_with_repo = (
        f"{remote_image.registry}/"
        f"{remote_image.owner}/"
        f"{remote_image.name}:{remote_image.tag}"
    )
    yield image_with_repo
    log.info(f"Remove image {image_with_repo}")
    shell(f"docker rmi {image_with_repo}")


@pytest.fixture
def generated_image_with_repo(
    tag: str, shell: Callable[..., str], generated_image_name: str, image_with_repo: str
) -> str:
    shell(f"docker tag {generated_image_name} {image_with_repo}")
    return image_with_repo


@pytest.mark.dependency(name="image_pushed")
def test_user_can_push_image(
    generated_image_with_repo: str,
    shell: Callable[..., str],
    helper: Helper,
    monkeypatch: Any,
) -> None:
    with helper.docker_context(monkeypatch, shell):
        shell(f"docker push {generated_image_with_repo}")


@pytest.mark.dependency(depends=["image_pushed"])
def test_user_can_pull_image(
    image_with_repo: str, shell: Callable[..., str], helper: Helper, monkeypatch: Any
) -> None:
    with helper.docker_context(monkeypatch, shell):
        shell(f"docker pull {image_with_repo}")


@pytest.mark.dependency(depends=["image_pushed"])
async def test_registry_is_accesible_by_k8s(
    helper: Helper, remote_image: RemoteImage, tag: str
) -> None:
    job = await helper.run_job(
        str(remote_image),
        wait_state=JobStatus.SUCCEEDED,
        schedule_timeout=240,
        wait_timeout=270,
    )
    await helper.check_job_output(job.id, re.escape(tag))


async def test_long_tags_list(
    generated_image_name: str,
    remote_image: RemoteImage,
    shell: Callable[..., str],
    helper: Helper,
    monkeypatch: Any,
) -> None:
    # default_output_lines = 5
    tag_count = 500
    local_image = helper.client.parse.local_image(generated_image_name)

    with helper.docker_context(monkeypatch, shell):
        for i in range(tag_count):
            await helper.client.images.push(
                local_image, replace(remote_image, tag=str(uuid()))
            )
            # shell(f"neuro image push {generated_image_name} {image_with_repo}")

        tags = await helper.client.images.tags(
            RemoteImage.new_neuro_image(
                name=remote_image.name,
                registry=str(remote_image.registry),
                owner=str(remote_image.owner),
                cluster_name=str(remote_image.cluster_name),
            )
        )
    # output = shell(f"neuro image tags {image_with_repo}")
    # assert len(output.splitlines()) == tag_count + default_output_lines
    assert len(tags) == tag_count
