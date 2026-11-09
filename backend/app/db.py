import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from .models import Base

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # 默认零门槛启动：未指定外部数据库时，自动使用轻量嵌入式 SQLite 数据库
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    if not data_dir.exists():
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{data_dir}/sub_egress.db"

# 兼容通用 postgres:// 与 postgresql:// 前缀
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine_kwargs = {"echo": False}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # 兼容已有数据库结构，平滑增补延迟字段
        if not DATABASE_URL.startswith("sqlite"):
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency DOUBLE PRECISION;"))
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency_status VARCHAR(32);"))
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency_updated_at TIMESTAMP;"))
        else:
            # SQLite 增补字段检测
            try:
                res = await conn.execute(text("PRAGMA table_info(nodes);"))
                cols = [row[1] for row in res.fetchall()]
                if "latency" not in cols:
                    await conn.execute(text("ALTER TABLE nodes ADD COLUMN latency REAL;"))
                if "latency_status" not in cols:
                    await conn.execute(text("ALTER TABLE nodes ADD COLUMN latency_status TEXT;"))
                if "latency_updated_at" not in cols:
                    await conn.execute(text("ALTER TABLE nodes ADD COLUMN latency_updated_at TIMESTAMP;"))
            except Exception:
                pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
