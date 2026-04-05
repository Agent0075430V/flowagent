from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.logging_config import configure_json_logging
from app.routes.auth import router as auth_router
from app.routes.flow import router as flow_router
from app.routes.tasks import router as tasks_router

settings = get_settings()
configure_json_logging(logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name)
static_dir = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()

    exempt_paths = {
        "/",
        "/health",
        "/auth/callback",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    if path.startswith("/static") or path in exempt_paths or method == "OPTIONS":
        return await call_next(request)

    protected_prefixes = ("/flow", "/users", "/auth")
    should_protect = any(path.startswith(prefix) for prefix in protected_prefixes)

    if settings.enable_api_key_auth and should_protect:
        presented = request.headers.get("X-API-Key", "")
        if not settings.app_api_key:
            logger.warning("API key auth enabled but APP_API_KEY is not configured")
            return JSONResponse(status_code=500, content={"detail": "Server API key is not configured."})
        if presented != settings.app_api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key."})

    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": settings.app_name, "env": settings.env}


@app.get("/")
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


app.include_router(auth_router)
app.include_router(flow_router)
app.include_router(tasks_router)
