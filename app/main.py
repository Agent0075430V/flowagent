from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes.auth import router as auth_router
from app.routes.flow import router as flow_router
from app.routes.tasks import router as tasks_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
static_dir = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": settings.app_name, "env": settings.env}


@app.get("/")
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


app.include_router(auth_router)
app.include_router(flow_router)
app.include_router(tasks_router)
