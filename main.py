"""Entry point.

Local dev:   python main.py              -> http://127.0.0.1:8000 with auto-reload
Render/prod: uvicorn app.main:app --host 0.0.0.0 --port $PORT  (see render.yaml)
             `python main.py` also works there: it binds 0.0.0.0:$PORT without reload.
"""

import os

import uvicorn

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    on_server = "PORT" in os.environ or "RENDER" in os.environ
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0" if on_server else "127.0.0.1",
        port=int(os.environ.get("PORT", 8000)),
        reload=not on_server,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
