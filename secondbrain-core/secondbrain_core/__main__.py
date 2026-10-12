import os

import uvicorn

from .app import create_app

uvicorn.run(
    create_app(),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    proxy_headers=True,
    forwarded_allow_ips=os.environ.get("SB_TRUSTED_PROXY_IPS", ""),
)
