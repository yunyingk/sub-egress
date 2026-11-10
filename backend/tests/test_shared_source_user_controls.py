from contextlib import asynccontextmanager

import pytest
from app.api import (
    ProbeSourcePayload,
    delete_source,
    list_nodes,
    list_sources,
    probe_subscription_source,
    refresh_source,
    toggle_shared_source_for_user,
)
from app.models import Base, Node, Source, User
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


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
            session.add_all([admin, alice])

            shared_src = Source(
                id=10,
                name="Platform Shared Global",
                url="local://shared",
                is_shared=True,
                user_id=1,  # Created by admin
                enabled=True
            )
            session.add(shared_src)

            node = Node(
                id=100,
                source_id=10,
                original_name="Shared-HK",
                display_name="[PL] 🇭🇰 香港-01",
                node_type="vless",
                server="1.2.3.4",
                port=443,
                config_json={"name": "Shared-HK", "type": "vless"}
            )
            session.add(node)
            await session.commit()
        yield session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_source_protection_in_user_dashboard():
    async with create_test_env() as session_factory:
        # Admin visits user dashboard /api/sources
        async with session_factory() as db:
            admin = await db.get(User, 1)
            sources = await list_sources(user=admin, db=db)
            target = next(s for s in sources if s["id"] == 10)
            assert target["is_shared"] is True
            # In user dashboard, EVEN FOR ADMIN, shared sources must have can_manage = False!
            assert target["can_manage"] is False
            assert target["is_enabled_for_user"] is True

        # Admin tries to delete shared source via user dashboard endpoint -> 403 Forbidden!
        async with session_factory() as db:
            admin = await db.get(User, 1)
            with pytest.raises(HTTPException) as exc_info:
                await delete_source(source_id=10, user=admin, db=db)
            assert exc_info.value.status_code == 403
            assert "平台公共共享源不可在个人视图中删除" in exc_info.value.detail

        # Admin tries to refresh shared source via user dashboard endpoint -> 403 Forbidden!
        async with session_factory() as db:
            admin = await db.get(User, 1)
            with pytest.raises(HTTPException) as exc_info:
                await refresh_source(source_id=10, user=admin, db=db)
            assert exc_info.value.status_code == 403
            assert "平台共享源由系统自动调度同步" in exc_info.value.detail


@pytest.mark.asyncio
async def test_user_toggle_shared_source_isolates_nodes():
    async with create_test_env() as session_factory:
        # 1. Initially, Alice sees the node from shared source
        async with session_factory() as db:
            alice = await db.get(User, 2)
            node_res = await list_nodes(user=alice, db=db)
            assert any(n["display_name"] == "[PL] 🇭🇰 香港-01" for n in node_res["nodes"])

        # 2. Alice disables the shared source for herself
        async with session_factory() as db:
            alice = await db.get(User, 2)
            toggle_res = await toggle_shared_source_for_user(source_id=10, user=alice, db=db)
            assert toggle_res["status"] == "success"
            assert toggle_res["is_enabled_for_user"] is False

        # 3. Alice's source list reflects is_enabled_for_user = False
        async with session_factory() as db:
            alice = await db.get(User, 2)
            sources = await list_sources(user=alice, db=db)
            target = next(s for s in sources if s["id"] == 10)
            assert target["is_enabled_for_user"] is False

        # 4. The shared node is now EXCLUDED from Alice's nodes!
        async with session_factory() as db:
            alice = await db.get(User, 2)
            node_res = await list_nodes(user=alice, db=db)
            assert not any(n["display_name"] == "[PL] 🇭🇰 香港-01" for n in node_res["nodes"])

        # 5. Admin still sees the node (isolation verification)
        async with session_factory() as db:
            admin = await db.get(User, 1)
            node_res = await list_nodes(user=admin, db=db)
            assert any(n["display_name"] == "[PL] 🇭🇰 香港-01" for n in node_res["nodes"])

        # 6. Alice toggles it back on
        async with session_factory() as db:
            alice = await db.get(User, 2)
            toggle_res = await toggle_shared_source_for_user(source_id=10, user=alice, db=db)
            assert toggle_res["is_enabled_for_user"] is True

        # 7. The node reappears for Alice
        async with session_factory() as db:
            alice = await db.get(User, 2)
            node_res = await list_nodes(user=alice, db=db)
            assert any(n["display_name"] == "[PL] 🇭🇰 香港-01" for n in node_res["nodes"])


@pytest.mark.asyncio
async def test_probe_subscription_source():
    user = User(id=1, username="probe_user", role="user")
    # Empty url -> 400
    with pytest.raises(HTTPException):
        await probe_subscription_source(ProbeSourcePayload(url=""), user=user)

    # Valid domain fallback test
    res = await probe_subscription_source(ProbeSourcePayload(url="https://sub.resip.cc/test"), user=user)
    assert res["success"] is True
    assert res["suggested_name"] == "RESIP"
