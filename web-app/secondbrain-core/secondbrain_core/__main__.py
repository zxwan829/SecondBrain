import os
import ipaddress

import uvicorn

from .app import create_app


def trusted_proxy_ips():
    values = [value.strip() for value in os.environ.get("SB_TRUSTED_PROXY_IPS", "").split(",") if value.strip()]
    # Uvicorn accepts wildcard/range values; this deployment intentionally trusts only
    # individually verified proxy peer addresses.
    try:
        for value in values:
            ipaddress.ip_address(value)
    except ValueError as exc:
        raise RuntimeError("SB_TRUSTED_PROXY_IPS must contain exact IP addresses only") from exc
    return ",".join(values)

uvicorn.run(
    create_app(),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    proxy_headers=True,
    forwarded_allow_ips=trusted_proxy_ips(),
)
