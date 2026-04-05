from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.logging_config import configure_json_logging
from app.routes.auth import router as auth_router
from app.routes.flow import router as flow_router
from app.routes.tasks import router as tasks_router

settings = get_settings()
configure_json_logging(logging.INFO)
app = FastAPI(title=settings.app_name)
static_dir = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def disable_browser_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": settings.app_name, "env": settings.env}


@app.get("/")
def root() -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


app.include_router(auth_router)
app.include_router(flow_router)
app.include_router(tasks_router)
