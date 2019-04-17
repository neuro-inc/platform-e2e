import asyncio

from neuromation.api import JobStatus, Resources


async def test_unschedulable_job_lifecycle(helper):
    # Remember original running jobs
    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    job = await helper.run_job(
        "ubuntu:latest",
        command,
        resources=Resources.create(0.1, None, None, "200000000000", True),
        wait_state=JobStatus.PENDING,
    )

    jobs = await helper.client.jobs.list({"running", "pending"})
    jobs_updated = [j.id for j in jobs]

    assert job.id in jobs_updated
    for i in range(10):
        job = await helper.client.jobs.status(job.id)
        if job.history.reason == "Cluster doesn't have resources to fulfill request.":
            break
        else:
            await asyncio.sleep(5)
    else:
        raise AssertionError(f"Timeout {job.id}: {job.status}")

    # Kill the job
    await helper.client.jobs.kill(job.id)

    for i in range(10):
        job = await helper.client.jobs.status(job.id)
        # ASvetlov: hmm, should the status be FAILED?
        if job.status == JobStatus.SUCCEEDED:
            break
        else:
            await asyncio.sleep(5)
    else:
        raise AssertionError(f"Timeout {job.id}: {job.status}")

    # Check that it is not in a running job list anymore
    jobs = await helper.client.jobs.list({"running", "pending"})
    job_ids = [j.id for j in jobs]
    assert job.id not in job_ids


async def test_two_jobs_at_once(helper):
    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    first_job = await helper.run_job("ubuntu:latest", command)
    second_job = await helper.run_job("ubuntu:latest", command)

    # Check it is in a running,pending job list now
    jobs = await helper.client.jobs.list({"running", "pending"})
    job_ids = [j.id for j in jobs]
    assert first_job.id in job_ids
    assert second_job.id in job_ids

    # Kill the job
    await helper.client.jobs.kill(first_job.id)
    await helper.client.jobs.kill(second_job.id)

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    await helper.wait_job_state(first_job.id, JobStatus.SUCCEEDED)
    await helper.wait_job_state(second_job.id, JobStatus.SUCCEEDED)

    # Check that it is not in a running job list anymore
    jobs = await helper.client.jobs.list({"running", "pending"})
    job_ids = [j.id for j in jobs]
    assert first_job.id not in job_ids
    assert second_job.id not in job_ids
