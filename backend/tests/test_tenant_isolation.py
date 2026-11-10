from contextlib import asynccontextmanager

import pytest
from app.api import (
    SourceCreate,
    SourceUpdate,
    admin_create_source,
    admin_delete_source,
    admin_list_sources,
    admin_update_source,
    create_source,
    delete_source,
    list_nodes,
    list_sources,
    ping_node_endpoint,
    refresh_source,
    update_source,
)
from app.models import Base, Node, Source, User
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _mock_sync(sid, db):
    return True


@asynccontextmanager
async def create_test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            admin = User(id=1, username="admin", role="admin", sub_hash_token="admin-token", is_active=True)
            alice = User(id=2, username="alice", role="user", sub_hash_token="alice-token", is_active=True)
            bob = User(id=3, username="bob", role="user", sub_hash_token="bob-token", is_active=True)
            session.add_all([admin, alice, bob])
            await session.flush()

            shared_src = Source(
                id=10, name="公共优质节点", url="https://example.com/shared.yaml",
                user_id=1, is_shared=True, enabled=True
            )
            alice_src = Source(
                id=20, name="Alice住宅宽带", url="https://example.com/alice.yaml",
                user_id=2, is_shared=False, enabled=True
            )
            bob_src = Source(
                id=30, name="Bob游戏专线", url="https://example.com/bob.yaml",
                user_id=3, is_shared=False, enabled=True
            )
            session.add_all([shared_src, alice_src, bob_src])
            await session.flush()

            session.add(Node(id=101, source_id=10, original_name="shared-01", display_name="[SH] 节点1",
                             node_type="ss", server="1.1.1.1", port=443, config_json={}))
            session.add(Node(id=201, source_id=20, original_name="alice-01", display_name="[AL] Alice节点",
                             node_type="ss", server="2.2.2.2", port=443, config_json={}))
            session.add(Node(id=301, source_id=30, original_name="bob-01", display_name="[BO] Bob节点",
                             node_type="ss", server="3.3.3.3", port=443, config_json={}))
            await session.commit()

            yield session, admin, alice, bob
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sources_list_tenant_isolation():
    async with create_test_env() as (db, admin, alice, bob):
        alice_sources = await list_sources(user=alice, db=db)
        alice_names = [s["name"] for s in alice_sources]
        assert "公共优质节点" in alice_names
        assert "Alice住宅宽带" in alice_names
        assert "Bob游戏专线" not in alice_names

        for s in alice_sources:
            if s["id"] == 10:
                assert s["is_shared"] is True
                assert s["can_manage"] is False
            elif s["id"] == 20:
                assert s["is_shared"] is False
                assert s["can_manage"] is True

        bob_sources = await list_sources(user=bob, db=db)
        bob_names = [s["name"] for s in bob_sources]
        assert "公共优质节点" in bob_names
        assert "Bob游戏专线" in bob_names
        assert "Alice住宅宽带" not in bob_names


@pytest.mark.asyncio
async def test_nodes_list_tenant_isolation():
    async with create_test_env() as (db, admin, alice, bob):
        alice_nodes = await list_nodes(user=alice, db=db)
        alice_disp = [n["display_name"] for n in alice_nodes["nodes"]]
        assert "[SH] 节点1" in alice_disp
        assert "[AL] Alice节点" in alice_disp
        assert "[BO] Bob节点" not in alice_disp

        bob_nodes = await list_nodes(user=bob, db=db)
        bob_disp = [n["display_name"] for n in bob_nodes["nodes"]]
        assert "[SH] 节点1" in bob_disp
        assert "[BO] Bob节点" in bob_disp
        assert "[AL] Alice节点" not in bob_disp


@pytest.mark.asyncio
async def test_cross_tenant_source_mutation_forbidden(monkeypatch):
    async with create_test_env() as (db, admin, alice, bob):
        monkeypatch.setattr("app.api.sync_single_source", _mock_sync)

        with pytest.raises(HTTPException) as exc_info:
            await update_source(source_id=30, payload=SourceUpdate(name="Hacked Name"), user=alice, db=db)
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            await delete_source(source_id=30, user=alice, db=db)
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            await update_source(source_id=10, payload=SourceUpdate(name="New Shared Name"), user=alice, db=db)
        assert exc_info.value.status_code == 403
        assert "管理员控制台" in exc_info.value.detail

        with pytest.raises(HTTPException) as exc_info:
            await delete_source(source_id=10, user=alice, db=db)
        assert exc_info.value.status_code == 403
        assert "管理员控制台" in exc_info.value.detail

        with pytest.raises(HTTPException) as exc_info:
            await refresh_source(source_id=30, user=alice, db=db)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_user_source_creation_always_private(monkeypatch):
    async with create_test_env() as (db, admin, alice, bob):
        monkeypatch.setattr("app.api.sync_single_source", _mock_sync)

        res = await create_source(
            payload=SourceCreate(name="Alice的新源", url="https://example.com/a.yaml", is_shared=True),
            user=alice,
            db=db
        )
        assert res["status"] == "success"

        new_src = await db.get(Source, res["id"])
        assert new_src.user_id == alice.id
        assert new_src.is_shared is False

        res_admin = await create_source(
            payload=SourceCreate(name="Admin个人测试源", url="https://example.com/adm.yaml", is_shared=True),
            user=admin,
            db=db
        )
        admin_src = await db.get(Source, res_admin["id"])
        assert admin_src.user_id == admin.id
        assert admin_src.is_shared is False


@pytest.mark.asyncio
async def test_same_source_name_allowed_across_users(monkeypatch):
    async with create_test_env() as (db, admin, alice, bob):
        monkeypatch.setattr("app.api.sync_single_source", _mock_sync)

        res1 = await create_source(
            payload=SourceCreate(name="主力机场", url="https://example.com/main.yaml"),
            user=alice,
            db=db
        )
        assert res1["status"] == "success"

        res2 = await create_source(
            payload=SourceCreate(name="主力机场", url="https://example.com/bob-main.yaml"),
            user=bob,
            db=db
        )
        assert res2["status"] == "success"
        assert res1["id"] != res2["id"]


@pytest.mark.asyncio
async def test_admin_shared_sources_management(monkeypatch):
    async with create_test_env() as (db, admin, alice, bob):
        monkeypatch.setattr("app.api.sync_single_source", _mock_sync)

        res = await admin_create_source(
            payload=SourceCreate(name="全新平台共享机场", url="https://example.com/global.yaml"),
            admin=admin,
            db=db
        )
        shared_id = res["id"]
        shared_src = await db.get(Source, shared_id)
        assert shared_src.is_shared is True

        # 管理员可以列出所有共享源
        shared_list = await admin_list_sources(admin=admin, db=db, scope="shared")
        assert any(s["id"] == shared_id for s in shared_list)

        # 管理员在审计模式下可以列出全量源（包含租户私有源）
        all_list = await admin_list_sources(admin=admin, db=db, scope="all")
        assert any(s["name"] == "Alice住宅宽带" for s in all_list)

        alice_sources = await list_sources(user=alice, db=db)
        assert any(s["id"] == shared_id and s["is_shared"] is True for s in alice_sources)

        await admin_update_source(
            source_id=shared_id,
            payload=SourceUpdate(name="更新后的共享机场名称"),
            admin=admin,
            db=db
        )
        updated = await db.get(Source, shared_id)
        assert updated.name == "更新后的共享机场名称"

        await admin_delete_source(source_id=shared_id, admin=admin, db=db)
        assert (await db.get(Source, shared_id)) is None


@pytest.mark.asyncio
async def test_node_ping_tenant_isolation(monkeypatch):
    async with create_test_env() as (db, admin, alice, bob):
        async def mock_ping(h, p, t):
            return {"latency": 45.0, "status": "ok", "error": None}
        monkeypatch.setattr("app.api.ping_single_node", mock_ping)

        r1 = await ping_node_endpoint(node_id=101, user=alice, db=db)
        assert r1["node_id"] == 101

        r2 = await ping_node_endpoint(node_id=201, user=alice, db=db)
        assert r2["node_id"] == 201

        with pytest.raises(HTTPException) as exc_info:
            await ping_node_endpoint(node_id=301, user=alice, db=db)
        assert exc_info.value.status_code == 404
