import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Node, Source, User


@pytest.mark.asyncio
async def test_node_list_respects_source_visibility(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.api import list_nodes

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            user = User(id=1, username="alice", role="user", sub_hash_token="alice-token")
            session.add_all([
                user,
                User(id=2, username="other", role="user", sub_hash_token="other-token"),
            ])
            await session.flush()
            for name, owner, shared, enabled in (
                ("shared", 2, True, True),
                ("own", 1, False, True),
                ("other-private", 2, False, True),
                ("disabled", 1, True, False),
            ):
                source = Source(name=name, url="https://example.test/", user_id=owner,
                                is_shared=shared, enabled=enabled)
                session.add(source)
                await session.flush()
                session.add(Node(source_id=source.id, original_name=name, display_name=name,
                                 node_type="ss", server="example.test", port=443,
                                 config_json={}))
            await session.commit()

            result = await list_nodes(user=user, db=session)
            assert {node["display_name"] for node in result["nodes"]} == {"shared", "own"}
            assert result["total"] == 2
    finally:
        await engine.dispose()
