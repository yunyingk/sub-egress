import asyncio
from contextlib import asynccontextmanager
import os
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
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

@app.get("/login", include_in_schema=False)
async def serve_login():
    login_file = frontend_dir / "login.html"
    if login_file.exists():
        return FileResponse(str(login_file))
    return RedirectResponse(url="/")

@app.get("/login.html", include_in_schema=False)
async def redirect_login_html():
    return RedirectResponse(url="/login", status_code=301)

@app.get("/index.html", include_in_schema=False)
async def redirect_index_html():
    return RedirectResponse(url="/", status_code=301)

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

