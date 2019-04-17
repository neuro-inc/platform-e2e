import asyncio
from typing import Any, Dict, Optional
from uuid import uuid4

import pytest
from neuromation.api import JobDescription, NetworkPortForwarding

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
        if http_port:
            network = NetworkPortForwarding.from_cli(80, http_auth)
        else:
            network = None
        if not description:
            description = "nginx with secret file"
            if http_port:
                description += " and forwarded http port"
                if http_auth:
                    description += " with authentication"
        status: JobDescription = await helper.run_job(
            "nginx:latest", command, description=description, network=network
        )
        return {
            "id": status.id,
            "secret": secret,
            "ingress_url": status.http_url,
            "internal_hostname": status.internal_hostname,
        }

    return go
