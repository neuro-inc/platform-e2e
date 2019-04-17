import asyncio
from uuid import uuid4

from neuromation.api import JobStatus, Resources

from platform_e2e import Helper


async def test_unschedulable_job_lifecycle(helper: Helper) -> None:
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


async def test_two_jobs_at_once(helper: Helper) -> None:
    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    first_job = await helper.run_job(
        "ubuntu:latest", command, wait_state=JobStatus.PENDING
    )
    second_job = await helper.run_job(
        "ubuntu:latest", command, wait_state=JobStatus.PENDING
    )

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


async def test_job_list_filtered_by_status(helper: Helper) -> None:
    N_JOBS = 5

    # submit N jobs
    jobs = set()
    for _ in range(N_JOBS):
        command = "sleep 10m"
        job = await helper.run_job(
            "ubuntu:latest", command, wait_state=JobStatus.PENDING
        )
        jobs.add(job.id)

    for job_id in jobs:
        await helper.wait_job_state(job_id, JobStatus.RUNNING)

    # test no status filters (same as pending+running)
    ret = await helper.client.jobs.list()
    jobs_ls_no_arg = set(j.id for j in ret)
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_no_arg >= jobs

    # test single status filter
    ret = await helper.client.jobs.list({"running"})
    jobs_ls_running = set(j.id for j in ret)
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_running >= jobs

    # test multiple status filters
    ret = await helper.client.jobs.list({"running", "failed"})
    jobs_ls_running = set(j.id for j in ret)
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_running >= jobs

    # status "all" is the same as pending+running+failed+succeeded
    ret = await helper.client.jobs.list({"pending", "running", "failed", "succeeded"})
    jobs_ls_all_explicit = set(j.id for j in ret)
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_all_explicit >= jobs


async def test_job_list_filtered_by_status_and_name(helper: Helper) -> None:
    N_JOBS = 5
    jobs_name_map = dict()
    name_0 = None
    command = "sleep 10m"
    for i in range(N_JOBS):
        name = f"my-job-{uuid4()}"
        if not name_0:
            name_0 = name
        job = await helper.run_job(
            "ubuntu:latest", command, name=name, wait_state=JobStatus.PENDING
        )
        jobs_name_map[name] = job.id

    assert name_0 is not None

    for job_id in jobs_name_map.values():
        await helper.wait_job_state(job_id, JobStatus.RUNNING)

    # test filtering by name only
    ret = await helper.client.jobs.list(name=name_0)
    jobs_ls = set(j.id for j in ret)
    assert jobs_ls == {jobs_name_map[name_0]}

    # test filtering by name and single status
    ret = await helper.client.jobs.list({"running"}, name=name_0)
    jobs_ls = set(j.id for j in ret)
    assert jobs_ls == {jobs_name_map[name_0]}

    # test filtering by name and 2 statuses - no jobs found
    ret = await helper.client.jobs.list({"failed", "succeeded"}, name=name_0)
    assert not ret
