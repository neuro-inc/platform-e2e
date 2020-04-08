from pathlib import Path
from uuid import uuid4

from yarl import URL

from platform_e2e import Helper


async def test_blob_storage_interaction(helper: Helper, tmp_path: Path) -> None:
    # Create directory for the test
    await helper.mkdir("data")

    fname = tmp_path / (str(uuid4()) + ".tmp")
    checksum = await helper.gen_random_file(fname, size=20_000_000)
    dst_file = tmp_path / ("out-" + str(fname.name))

    async with helper.create_tmp_bucket() as bucket_name:
        # Upload local file
        await helper.client.blob_storage.upload_file(
            URL(fname.as_uri()), URL(f"blob:{bucket_name}/data/foo")
        )

        await helper.client.blob_storage.download_file(
            URL(f"blob:{bucket_name}/data/foo"), URL(dst_file.as_uri()),
        )

    # confirm checksum
    assert checksum == await helper.calc_local_checksum(dst_file)
