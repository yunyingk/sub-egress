import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .db import init_db
from .syncer import background_ping_worker, background_sync_worker
from .version import VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    await init_db()
    # Start background synchronization worker & ping worker
    sync_task = asyncio.create_task(background_sync_worker())
    ping_task = asyncio.create_task(background_ping_worker())
    try:
        yield
    finally:
        sync_task.cancel()
        ping_task.cancel()

app = FastAPI(
    title="sub-egress",
    description="出站网关与订阅聚合调度中枢",
    version=VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount frontend static directory & clean URL routing
frontend_dir = Path(os.getenv("FRONTEND_DIR", "/frontend"))
if not frontend_dir.exists():
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

@app.api_route("/login", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_login():
    login_file = frontend_dir / "login.html"
    if login_file.exists():
        return FileResponse(str(login_file))
    return RedirectResponse(url="/")

@app.api_route("/login.html", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_login_html():
    return RedirectResponse(url="/login", status_code=301)

@app.api_route("/index.html", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_index_html():
    return RedirectResponse(url="/", status_code=301)

@app.api_route("/admin", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/admin/", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/admin/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_admin_app(path: str = ""):
    return FileResponse(str(frontend_dir / "index.html"))

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

