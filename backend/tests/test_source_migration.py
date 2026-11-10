import pytest
from app.source_migration import migrate_source_ownership
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def legacy_schema(conn, invalid=False):
    await conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
    await conn.execute(text('INSERT INTO users VALUES (1)'))
    await conn.execute(text('''CREATE TABLE sources (
        id INTEGER PRIMARY KEY, user_id INTEGER, is_shared BOOLEAN,
        name VARCHAR(64) NOT NULL, code VARCHAR(8), url TEXT NOT NULL,
        source_type VARCHAR(32), enabled BOOLEAN, status VARCHAR(32), error_message TEXT,
        node_count INTEGER, traffic_used BIGINT, traffic_total BIGINT,
        expire_at DATETIME, last_sync_at DATETIME, raw_content TEXT,
        created_at DATETIME, updated_at DATETIME
    )'''))
    await conn.execute(text('CREATE TABLE nodes (id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id))'))
    await conn.execute(text("INSERT INTO sources (id, user_id, is_shared, name, url, enabled) VALUES (1, 1, 1, 'shared', 'local', 1), (2, :owner, 0, 'private', 'local', 1)"), {'owner': None if invalid else 1})
    await conn.execute(text('INSERT INTO nodes VALUES (42, 2)'))


@pytest.mark.asyncio
async def test_legacy_source_migration_preserves_nodes_and_scope():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await legacy_schema(conn)
        await migrate_source_ownership(conn)
        rows = (await conn.execute(text('SELECT id, owner_user_id, created_by_user_id FROM sources ORDER BY id'))).all()
        assert rows == [(1, None, None), (2, 1, None)]
        assert (await conn.execute(text('SELECT source_id FROM nodes WHERE id=42'))).scalar_one() == 2
        assert 'user_id' not in {row[1] for row in (await conn.execute(text('PRAGMA table_info(sources)'))).all()}
        await migrate_source_ownership(conn)
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_source_migration_rejects_unknown_private_owner():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await legacy_schema(conn, invalid=True)
        with pytest.raises(RuntimeError, match='unknown ownership'):
            await migrate_source_ownership(conn)
        assert (await conn.execute(text('SELECT count(*) FROM sources'))).scalar_one() == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_token_preserved_and_legacy_setting_removed(monkeypatch):
    from app import db as db_module
    from app.models import Base, Setting, User
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add_all([User(username='admin', role='admin', sub_hash_token='current-admin-token'), Setting(key='sub_hash_token', value='old-global-token')])
        await session.commit()
    monkeypatch.setattr(db_module, 'engine', engine)
    monkeypatch.setattr(db_module, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(db_module, 'DATABASE_URL', 'sqlite+aiosqlite:///:memory:')
    await db_module.init_db()
    async with factory() as session:
        admin = await session.get(User, 1)
        assert admin.sub_hash_token == 'current-admin-token'
        assert await session.get(Setting, 'sub_hash_token') is None
    await engine.dispose()
