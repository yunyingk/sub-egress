import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api import router
from .db import init_db
from .syncer import background_sync_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    await init_db()
    # Start background synchronization worker
    worker_task = asyncio.create_task(background_sync_worker())
    try:
        yield
    finally:
        worker_task.cancel()

app = FastAPI(
    title="sub-egress",
    description="出站网关与订阅聚合调度中枢",
    version="0.2.9",
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

# Mount frontend static directory
frontend_dir = Path(os.getenv("FRONTEND_DIR", "/frontend"))
if not frontend_dir.exists():
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

