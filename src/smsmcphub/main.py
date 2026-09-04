from __future__ import annotations

import uvicorn

from smsmcphub.api.app import create_app
from smsmcphub.config import AppSettings

app = create_app()


def run() -> None:
    settings = AppSettings.from_env()
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)
