import re
from typing import Any

import aiohttp
import pytest
from neuromation.api import JobStatus

from platform_e2e import Helper


async def test_connectivity_job_with_http_port(secret_job: Any, helper: Helper) -> None:

    http_job = await secret_job(True)

    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")

    # external ingress test
    probe = await helper.http_get(ingress_secret_url)
    assert probe
    assert probe.strip() == http_job["secret"]

    # internal ingress test
    command = f"wget -q -T 15 {ingress_secret_url} -O -"
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.SUCCEEDED,
    )
    await helper.check_job_output(job.id, re.escape(http_job["secret"]))

    # internal network test
    internal_secret_url = f"http://{http_job['internal_hostname']}/secret.txt"
    command = f"wget -q -T 15 {internal_secret_url} -O -"
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret internal network fetcher ",
        wait_state=JobStatus.SUCCEEDED,
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
    command = f"wget -q -T 15 {ingress_secret_url} -O -"
    job = await helper.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.FAILED,
    )
    await helper.check_job_output(job.id, r"wget.+404.+Not Found")

    # internal network test
    # cannot be implemented now
    # because by default k8s will not register DNS name if pod
    # haven't any service
    # internal network test


async def test_check_isolation(secret_job: Any, helper_alt: Helper) -> None:
    http_job = await secret_job(True)

    ingress_secret_url = f"{http_job['ingress_url']}/secret.txt"
    ingress_secret_url

    # internal ingress test
    command = f"wget -q -T 15 {ingress_secret_url} -O -"
    job = await helper_alt.run_job(
        "alpine:latest",
        command,
        description="secret ingress fetcher ",
        wait_state=JobStatus.SUCCEEDED,
    )
    await helper_alt.check_job_output(job.id, re.escape(http_job["secret"]))

    # internal network test

    internal_secret_url = f"http://{http_job['internal_hostname']}/secret.txt"
    command = f"wget -q -T 15 {internal_secret_url} -O -"
    # This job must be failed,
    job = await helper_alt.run_job(
        "alpine:latest",
        command,
        description="secret internal network fetcher ",
        wait_state=JobStatus.FAILED,
    )

    await helper_alt.check_job_output(job.id, r"timed out")
