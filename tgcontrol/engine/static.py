"""
Serves the frontend/index.html at http://localhost:PORT/
alongside the FastAPI backend.
This is auto-imported by server.py — no need to run separately.
"""

from fastapi.responses import HTMLResponse
from pathlib import Path

def mount_frontend(app):
    frontend_html = Path(__file__).parent.parent / "frontend" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        return HTMLResponse(frontend_html.read_text(encoding="utf-8"))

    @app.get("/config.js")
    async def serve_config():
        from fastapi.responses import PlainTextResponse
        cfg = Path(__file__).parent.parent / "config.js"
        return PlainTextResponse(cfg.read_text(encoding="utf-8"),
                                  media_type="application/javascript")
