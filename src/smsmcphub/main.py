from __future__ import annotations

import uvicorn

from smsmcphub.api.app import create_app

app = create_app()


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)
