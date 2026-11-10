import asyncio
from contextlib import asynccontextmanager

import pytest
from app.api import (
    admin_delete_source,
    admin_list_sources,
    delete_source,
    list_nodes,
    list_sources,
    ping_node_endpoint,
)
from app.models import Base, Node, Source, User
from app.syncer import sync_single_source
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@asynccontextmanager
async def env(db_url):
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all([User(id=1, username='admin', role='admin', sub_hash_token='admin-token'),
                    User(id=2, username='alice', sub_hash_token='alice-token'),
                    User(id=3, username='bob', sub_hash_token='bob-token')])
        db.add_all([Source(id=1, name='private', url='https://example.test/', owner_user_id=2, is_shared=False),
                    Source(id=2, name='shared', url='https://example.test/', is_shared=True)])
        for sid in (1, 2):
            db.add(Node(id=sid, source_id=sid, original_name='node', display_name=f'node-{sid}', node_type='ss',
                        server='example.test', port=443, config_json={'type': 'ss', 'server': 'example.test', 'port': 443}))
        await db.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deletion_preserves_database_rows_but_hides_everywhere():
    async with env('sqlite+aiosqlite:///:memory:') as factory:
        async with factory() as db:
            admin, alice, bob = [await db.get(User, i) for i in (1, 2, 3)]
            with pytest.raises(HTTPException) as e:
                await delete_source(1, bob, db)
            assert e.value.status_code == 403
            await delete_source(1, alice, db)
            await admin_delete_source(2, admin, db)
            for sid, uid in ((1, 2), (2, 1)):
                source = await db.get(Source, sid)
                assert source.deleted_at is not None and source.deleted_by_user_id == uid
                assert await db.get(Node, sid) is not None
            assert await list_sources(alice, db) == []
            assert (await list_nodes(alice, db))['nodes'] == []
            assert await admin_list_sources(admin, db, scope='all') == []
            with pytest.raises(HTTPException) as e:
                await ping_node_endpoint(1, alice, db)
            assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_deleting_during_fetch_cannot_update_or_remove_nodes(tmp_path, monkeypatch):
    async with env(f'sqlite+aiosqlite:///{tmp_path / "test.db"}') as factory:
        started, proceed = asyncio.Event(), asyncio.Event()
        class Response:
            status_code = 200
            text = 'proxies: [{name: replacement, type: ss, server: example.test, port: 443}]'
            headers = {}
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs):
                started.set()
                await proceed.wait()
                return Response()
        monkeypatch.setattr('app.syncer.httpx.AsyncClient', Client)
        async with factory() as syncing, factory() as deleting:
            task = asyncio.create_task(sync_single_source(1, syncing))
            await asyncio.wait_for(started.wait(), timeout=5)
            alice = await deleting.get(User, 2)
            await delete_source(1, alice, deleting)
            proceed.set()
            assert await task is False
        async with factory() as db:
            assert (await db.get(Source, 1)).deleted_at is not None
            nodes = (await db.execute(select(Node).where(Node.source_id == 1))).scalars().all()
            assert len(nodes) == 1 and nodes[0].display_name == 'node-1'


@pytest.mark.asyncio
async def test_existing_sqlite_database_receives_delete_columns(monkeypatch):
    from app import db as db_module
    from sqlalchemy import text

    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy.schema import CreateTable

        ddl = str(CreateTable(Source.__table__).compile(dialect=conn.dialect))
        ddl = ddl.replace('\tdeleted_at DATETIME, \n', '').replace('\tdeleted_by_user_id INTEGER, \n', '')
        ddl = ddl.replace(', \n\tFOREIGN KEY(deleted_by_user_id) REFERENCES users (id) ON DELETE SET NULL', '')
        await conn.execute(text('DROP TABLE sources'))
        await conn.execute(text(ddl))
        await conn.execute(text("INSERT INTO users (id, username, role, is_active, sub_hash_token, subscription_title, clash_mixed_port, clash_terminal_port) VALUES (1, 'admin', 'admin', 1, 'admin-token', 'test', '7897', '7898')"))
        await conn.execute(text("INSERT INTO sources (id, is_shared, name, url, enabled) VALUES (1, 1, 'shared', 'local://shared', 1)"))
    monkeypatch.setattr(db_module, 'engine', engine)
    monkeypatch.setattr(db_module, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(db_module, 'DATABASE_URL', 'sqlite+aiosqlite:///:memory:')
    await db_module.init_db()
    async with factory() as db:
        source = await db.get(Source, 1)
        assert source and source.deleted_at is None and source.deleted_by_user_id is None
    await engine.dispose()
