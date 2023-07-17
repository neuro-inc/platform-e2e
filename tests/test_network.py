import re
import uuid
from typing import Any

import pytest
from neuro_sdk import JobStatus, Resources

from platform_e2e import Helper

# Clusters created during Platform Infra CI are configured with
# letsencrypt staging certificates. So we need to install them into
# pod container before sending requests to job urls.
ROOT_CERT_URL = "https://letsencrypt.org/certs/staging/letsencrypt-stg-root-x1.pem"
CERTIFICATES_DIR = "/usr/local/share/ca-certificates"
INSTALL_CERTIFICATE_COMMAND = (
    "apk add -q --update --no-cache ca-certificates "
    "&& rm /etc/ssl/cert.pem "
    "&& ln -s /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem "
    f"&& mkdir -p {CERTIFICATES_DIR} "
    f"&& wget -q -O {CERTIFICATES_DIR}/letsencrypt-stg.pem {ROOT_CERT_URL} "
    "&& update-ca-certificates "
    '&& echo "Letsencrypt staging certificate installed"'
)
JOB_RESOURCES = Resources(
    cpu=0.1,
    memory=128 * 10**6,  # increase memory for certificate installation
    gpu=None,
    gpu_model=None,
    shm=True,
    tpu_software_version=None,
    tpu_type=None,
)


async def run_fetch_secret_job(
    helper: Helper,
    secret_job_url: str,
    fetch_output: str,
    fetch_wait_state: JobStatus = JobStatus.SUCCEEDED,
) -> None:
    internal_secret_url = f"{secret_job_url}/secret.txt"
    command = (
        f"sh -c '{INSTALL_CERTIFICATE_COMMAND} "
        f"&& wget -q -T 15 {internal_secret_url} -O -'"
    )
    fetch_job = await helper.run_job(
        "ghcr.io/neuro-inc/alpine:latest",
        command,
        description="e2e tests: fetch secret job",
        wait_state=fetch_wait_state,
        resources=JOB_RESOURCES,
    )

    await helper.check_job_output(fetch_job.id, re.escape(fetch_output))


async def test_job_internal_connectivity(secret_job: Any, helper: Helper) -> None:
    http_job = await secret_job(False, name=f"secret-{str(uuid.uuid4())[:8]}")

    await run_fetch_secret_job(
        helper, f"http://{http_job['internal_hostname']}", http_job["secret"]
    )
    await run_fetch_secret_job(
        helper, f"http://{http_job['internal_hostname_named']}", http_job["secret"]
    )


async def test_job_with_http_port_external_connectivity(
    secret_job: Any, helper: Helper
) -> None:
    http_job = await secret_job(True)

    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")

    # external ingress test
    probe = await helper.http_get(ingress_secret_url)
    assert probe
    assert probe.strip() == http_job["secret"]

    # internal ingress test
    await run_fetch_secret_job(helper, http_job["ingress_url"], http_job["secret"])


async def test_job_without_http_port_external_connectivity(
    secret_job: Any, helper: Helper
) -> None:
    # run http job for getting url
    http_job = await secret_job(True)
    await helper.client.jobs.kill(http_job["id"])
    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")
    internal_secret_url = f"http://{http_job['internal_hostname']}/secret.txt"

    # Run another job without shared http port
    no_http_job = await secret_job(False)

    # Let's emulate external and internal url
    ingress_secret_url = str(ingress_secret_url).replace(
        http_job["id"], no_http_job["id"]
    )
    internal_secret_url = str(internal_secret_url).replace(
        http_job["id"], no_http_job["id"]
    )

    # external ingress test
    # should receive fallback html page
    probe = await helper.http_get(ingress_secret_url)
    assert probe
    assert probe.strip() != no_http_job["secret"]


@pytest.mark.network_isolation
async def test_job_isolation(secret_job: Any, helper_alt: Helper) -> None:
    http_job = await secret_job(True)

    # internal ingress test
    await run_fetch_secret_job(helper_alt, http_job["ingress_url"], http_job["secret"])

    # internal network test
    await run_fetch_secret_job(
        helper_alt,
        f"http://{http_job['internal_hostname']}",
        "timed out",
        fetch_wait_state=JobStatus.FAILED,
    )
