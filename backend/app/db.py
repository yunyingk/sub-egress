import os
import secrets
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Setting, User
from .security import generate_secure_password, hash_password, validate_password
from .source_migration import migrate_source_ownership

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
        if DATABASE_URL.startswith("sqlite"):
            await conn.execute(text("BEGIN"))
        await conn.run_sync(Base.metadata.create_all)
        
        source_columns = await conn.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("sources")}
        )
        if "owner_user_id" not in source_columns and "user_id" not in source_columns:
            await conn.execute(text("ALTER TABLE sources ADD COLUMN user_id INTEGER"))

        # 兼容已有数据库结构，平滑增补字段
        if not DATABASE_URL.startswith("sqlite"):
            old_timestamps = await conn.execute(text("""
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN ('users', 'passkey_credentials', 'sources', 'nodes', 'settings')
                  AND data_type = 'timestamp without time zone'
            """))
            if old_timestamps.first():
                raise RuntimeError("Database timestamps require UTC migration before startup; see documentation")
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency DOUBLE PRECISION;"))
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency_status VARCHAR(32);"))
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS latency_updated_at TIMESTAMP WITH TIME ZONE;"))
            await conn.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS code VARCHAR(8);"))
            await conn.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS is_shared BOOLEAN DEFAULT TRUE;"))
            await conn.execute(text("ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_name_key;"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS theme_mode VARCHAR(16) NOT NULL DEFAULT 'system';"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_direct_domains TEXT DEFAULT 'ying-qing.cn';"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_proxy_domains TEXT DEFAULT '';"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_rules TEXT DEFAULT '';"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS disabled_shared_sources TEXT DEFAULT '';"))
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
                
                s_res = await conn.execute(text("PRAGMA table_info(sources);"))
                s_cols = [row[1] for row in s_res.fetchall()]
                if "code" not in s_cols:
                    await conn.execute(text("ALTER TABLE sources ADD COLUMN code TEXT;"))
                if "is_shared" not in s_cols:
                    await conn.execute(text("ALTER TABLE sources ADD COLUMN is_shared BOOLEAN DEFAULT 1;"))

                u_res = await conn.execute(text("PRAGMA table_info(users);"))
                u_cols = [row[1] for row in u_res.fetchall()]
                if "theme_mode" not in u_cols:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN theme_mode VARCHAR(16) NOT NULL DEFAULT 'system';"))
                if "custom_direct_domains" not in u_cols:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN custom_direct_domains TEXT DEFAULT 'ying-qing.cn';"))
                if "custom_proxy_domains" not in u_cols:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN custom_proxy_domains TEXT DEFAULT '';"))
                if "custom_rules" not in u_cols:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN custom_rules TEXT DEFAULT '';"))
                if "disabled_shared_sources" not in u_cols:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN disabled_shared_sources TEXT DEFAULT '';"))
            except Exception as exc:
                raise RuntimeError("SQLite schema initialization failed") from exc

        await migrate_source_ownership(conn)
        source_columns = await conn.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("sources")}
        )
        if "deleted_at" not in source_columns:
            timestamp_type = "TIMESTAMP" if DATABASE_URL.startswith("sqlite") else "TIMESTAMP WITH TIME ZONE"
            await conn.execute(text(f"ALTER TABLE sources ADD COLUMN deleted_at {timestamp_type}"))  # noqa: S608
        if "deleted_by_user_id" not in source_columns:
            await conn.execute(text("ALTER TABLE sources ADD COLUMN deleted_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sources_deleted_at ON sources (deleted_at)"))

    # 管理员初始化与忘记密码检查
    async with AsyncSessionLocal() as session:
        try:
            # 1. 检查是否存在 admin 用户
            stmt = select(User).where(User.username == "admin")
            res = await session.execute(stmt)
            admin_user = res.scalar_one_or_none()

            # 读取现有的 sub_hash_token 设置以保持无缝兼容
            set_stmt = select(Setting).where(Setting.key == "sub_hash_token")
            set_res = await session.execute(set_stmt)
            existing_token_setting = set_res.scalar_one_or_none()
            inherited_token = existing_token_setting.value if existing_token_setting and not admin_user else secrets.token_hex(24)
            if not admin_user and existing_token_setting:
                collision = await session.scalar(select(User.id).where(User.sub_hash_token == inherited_token))
                if collision is not None:
                    raise RuntimeError("Legacy subscription token already belongs to a user; cannot assign it to admin")

            if not admin_user:
                # 首次启动：自动生成 32 位全小写强随机密码
                init_admin_pwd = generate_secure_password(32)
                admin_user = User(
                    username="admin",
                    password_hash=hash_password(init_admin_pwd),
                    role="admin",
                    is_active=True,
                    sub_hash_token=inherited_token,
                    subscription_title="sub-egress",
                    clash_mixed_port="7897",
                    clash_terminal_port="7898"
                )
                session.add(admin_user)
                await session.commit()

                print("\n" + "=" * 70)
                print("[sub-egress] 首次启动：成功创建初始管理员账号 (ADMIN INITIALIZED)")
                print("用户名 (Username)   : admin")
                print(f"初始密码 (Password) : {init_admin_pwd}")
                print(f"订阅令牌 (Token)    : {inherited_token}")
                print("说明: 密码符合全小写规范 (禁止大写字母)，请妥善保管。")
                print("如忘记密码，可通过重启容器配置环境变量 RESET_ADMIN_PASSWORD 或 CLI 重置。")
                print("=" * 70 + "\n")
            else:
                # 确保 admin 用户拥有 sub_hash_token
                if not admin_user.sub_hash_token:
                    admin_user.sub_hash_token = inherited_token
                    await session.commit()

            if existing_token_setting:
                await session.delete(existing_token_setting)
                await session.commit()

            # 2. 检查环境变量 RESET_ADMIN_PASSWORD（管理员忘记密码通过重启服务器重置）
            env_reset_pwd = os.getenv("RESET_ADMIN_PASSWORD", "").strip()
            if env_reset_pwd and admin_user:
                valid, msg = validate_password(env_reset_pwd)
                if valid:
                    admin_user.password_hash = hash_password(env_reset_pwd)
                    await session.commit()
                    print("\n" + "*" * 70)
                    print("[sub-egress] 已通过环境变量 RESET_ADMIN_PASSWORD 成功重置管理员 admin 密码！")
                    print("*" * 70 + "\n")
                else:
                    print(f"\n[sub-egress 警告] 环境变量 RESET_ADMIN_PASSWORD 格式不符合规范: {msg}，密码未变更。\n")
        except Exception as e:
            raise RuntimeError("Failed to initialize admin or migrate legacy subscription token") from e

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
