from pathlib import Path
from uuid import uuid4

import pytest

from platform_e2e import Helper


pytestmark = pytest.mark.blob_storage


async def test_e2e_blob_storage_upload_download(
    tmp_path: Path,
    helper: Helper,
) -> None:
    fname = tmp_path / (str(uuid4()) + ".tmp")
    checksum = await helper.gen_random_file(fname, size=20_000)
    key = "folder/foo"

    async with helper.create_tmp_bucket() as tmp_bucket:

        # Upload local file
        await helper.upload_blob(bucket_name=tmp_bucket, key=key, file=fname)

        # Confirm file has been uploaded
        await helper.check_blob_size(tmp_bucket, key, 20_000)

        # Download into local file and confirm checksum
        await helper.check_blob_checksum(tmp_bucket, key, checksum, tmp_path / "bar")
