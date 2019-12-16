import re
from typing import Any

import aiohttp
import pytest
from neuromation.api import JobStatus, Resources

from platform_e2e import Helper


# Clusters created during Platform Infra CI are configured with
# letsencrypt staging certificates. So we need to install them into
# pod container before sending requests to job urls.
CERTIFICATE_URL = "https://letsencrypt.org/certs/fakelerootx1.pem"
CERTIFICATES_DIR = "/usr/local/share/ca-certificates"
INSTALL_CERTIFICATE_COMMAND = (
    "apk add -q --update --no-cache ca-certificates "
    "&& rm /etc/ssl/cert.pem "
    "&& ln -s /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem "
    f"&& mkdir -p {CERTIFICATES_DIR} "
    f"&& wget -q -O {CERTIFICATES_DIR}/fakelerootx1.pem {CERTIFICATE_URL} "
    "&& update-ca-certificates "
    '&& echo "Letsencrypt staging certificate installed"'
)
JOB_RESOURCES = Resources(
    cpu=0.1,
    memory_mb=100,  # increase memory for certificate installation
    gpu=None,
    gpu_model=None,
    shm=True,
    tpu_software_version=None,
    tpu_type=None,
)


async def test_connectivity_job_with_http_port(secret_job: Any, helper: Helper) -> None:

    http_job = await secret_job(True)

    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")

    # external ingress test
    probe = await helper.http_get(ingress_secret_url)
    assert probe
    assert probe.strip() == http_job["secret"]

    # internal ingress test
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} "
        f"&& wget -q -T 15 {ingress_secret_url} -O -'"
    )
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.SUCCEEDED,
        resources=JOB_RESOURCES,
    )
    await helper.check_job_output(job.id, re.escape(http_job["secret"]))

    # internal network test
    internal_secret_url = f"http://{http_job['internal_hostname']}/secret.txt"
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} "
        f"&& wget -q -T 15 {internal_secret_url} -O -'"
    )
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret internal network fetcher ",
        wait_state=JobStatus.SUCCEEDED,
        resources=JOB_RESOURCES,
    )
    await helper.check_job_output(job.id, re.escape(http_job["secret"]))


async def test_connectivity_job_without_http_port(
    secret_job: Any, helper: Helper
) -> None:
    # run http job for getting url
    http_job = await secret_job(True)
    await helper.client.jobs.kill(http_job["id"])
    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")

    # Run another job without shared http port
    no_http_job = await secret_job(False)

    # Let's emulate external url
    ingress_secret_url = str(ingress_secret_url).replace(
        http_job["id"], no_http_job["id"]
    )

    # external ingress test
    # it will take ~1 min, because we need to wait while nginx started
    with pytest.raises(aiohttp.ClientResponseError):
        await helper.http_get(ingress_secret_url)

    # internal ingress test
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} "
        f"&& wget -q -T 15 {ingress_secret_url} -O -'"
    )
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.FAILED,
        resources=JOB_RESOURCES,
    )
    await helper.check_job_output(job.id, r"wget.+404.+Not Found")

    # internal network test
    # cannot be implemented now
    # because by default k8s will not register DNS name if pod
    # haven't any service
    # internal network test


@pytest.mark.network_isolation
async def test_check_isolation(secret_job: Any, helper_alt: Helper) -> None:
    http_job = await secret_job(True)

    ingress_secret_url = f"{http_job['ingress_url']}/secret.txt"
    ingress_secret_url

    # internal ingress test
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} "
        f"&& wget -q -T 15 {ingress_secret_url} -O -'"
    )
    job = await helper_alt.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.SUCCEEDED,
        resources=JOB_RESOURCES,
    )
    await helper_alt.check_job_output(job.id, re.escape(http_job["secret"]))

    # internal network test

    internal_secret_url = f"http://{http_job['internal_hostname']}/secret.txt"
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} && "
        f"wget -q -T 15 {internal_secret_url} -O -'"
    )
    # This job must be failed,
    job = await helper_alt.run_job(
        "alpine:latest",
        command,
        description="secret internal network fetcher ",
        wait_state=JobStatus.FAILED,
        resources=JOB_RESOURCES,
    )

    await helper_alt.check_job_output(job.id, r"timed out")
