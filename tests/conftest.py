import asyncio
from typing import Any, Dict, Optional
from uuid import uuid4

import pytest
from neuromation.api import JobDescription

from platform_e2e import Helper


@pytest.fixture
def secret_job(helper: Helper, loop: asyncio.AbstractEventLoop) -> Any:
    async def go(
        http_port: bool, http_auth: bool = False, description: Optional[str] = None
    ) -> Dict[str, Any]:
        secret = str(uuid4())
        # Run http job
        command = (
            f"bash -c \"echo -n '{secret}' > /usr/share/nginx/html/secret.txt; "
            f"timeout 15m /usr/sbin/nginx -g 'daemon off;'\""
        )
        args = []
        if http_port:
            args += ["--http", "80"]
            if http_auth:
                args += ["--http-auth"]
            else:
                args += ["--no-http-auth"]
        if not description:
            description = "nginx with secret file"
            if http_port:
                description += " and forwarded http port"
                if http_auth:
                    description += " with authentication"
        args += ["-d", description]
        ["-m", "20M", "-c", "0.1", "-g", "0", "--non-preemptible"]
        status: JobDescription = await helper.run_job(
            "nginx:latest", command, description=description
        )
        return {
            "id": status.id,
            "secret": secret,
            "ingress_url": status.http_url,
            "internal_hostname": status.internal_hostname,
        }

    return go
