import pytest
from app.db import AsyncSessionLocal, init_db
from app.models import Node, Source
from app.syncer import sync_single_source
from sqlalchemy import select


@pytest.mark.asyncio
async def test_incremental_sync_preserves_latency(monkeypatch):
    await init_db()

    # Disable background ping during sync test so it doesn't overwrite with real network measurement
    async def noop_ping(sid):
        pass
    monkeypatch.setattr("app.syncer.ping_source_nodes", noop_ping)

    # Step 1: Create a mock source
    async with AsyncSessionLocal() as session:
        src = Source(
            name="Test Singbox Source",
            url="local://test",
            raw_content='''{
                "outbounds": [
                    {
                        "type": "vless",
                        "tag": "US Node 1",
                        "server": "1.1.1.1",
                        "server_port": 443,
                        "uuid": "test-uuid-1"
                    }
                ]
            }''',
            source_type="local_yaml",
            is_shared=True
        )
        session.add(src)
        await session.commit()
        source_id = src.id

    # Step 2: Sync source once
    async with AsyncSessionLocal() as session:
        ok = await sync_single_source(source_id, session)
        assert ok is True

    # Step 3: Check node and inject fake latency
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Node).where(Node.source_id == source_id))
        nodes = res.scalars().all()
        assert len(nodes) == 1
        original_node_id = nodes[0].id
        nodes[0].latency = 123.4
        nodes[0].latency_status = "ok"
        await session.commit()

    # Step 4: Sync source again with updated content but same server/port
    async with AsyncSessionLocal() as session:
        src = await session.get(Source, source_id)
        src.raw_content = '''{
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "US Node 1 Renamed",
                    "server": "1.1.1.1",
                    "server_port": 443,
                    "uuid": "test-uuid-1"
                },
                {
                    "type": "vless",
                    "tag": "US Node 2 New",
                    "server": "2.2.2.2",
                    "server_port": 443,
                    "uuid": "test-uuid-2"
                }
            ]
        }'''
        await session.commit()

        ok = await sync_single_source(source_id, session)
        assert ok is True

    # Step 5: Verify original node ID and latency were preserved!
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Node).where(Node.source_id == source_id).order_by(Node.id))
        nodes = res.scalars().all()
        assert len(nodes) == 2

        # First node must keep original ID and original latency!
        assert nodes[0].id == original_node_id
        assert nodes[0].latency == 123.4
        assert nodes[0].latency_status == "ok"
        assert "Renamed" in nodes[0].original_name

        # Second node is newly inserted
        assert nodes[1].id != original_node_id
        assert nodes[1].server == "2.2.2.2"
        assert nodes[1].latency is None


@pytest.mark.asyncio
async def test_sync_corrects_country_and_preserves_node_identity(monkeypatch):
    await init_db()

    async def noop_ping(sid):
        pass

    monkeypatch.setattr("app.syncer.ping_source_nodes", noop_ping)
    async with AsyncSessionLocal() as session:
        source = Source(
            name="Country Test",
            url="local://country-test",
            source_type="local_yaml",
            is_shared=True,
            raw_content='''{"outbounds": [
                {"type":"vless", "tag":"🇺🇸 Australia-01", "server":"1.1.1.1", "server_port":443, "uuid":"test"},
                {"type":"vless", "tag":"🇺🇸 Russia-01", "server":"2.2.2.2", "server_port":443, "uuid":"test"}
            ]}''',
        )
        session.add(source)
        await session.flush()
        session.add(Node(source_id=source.id, original_name="🇺🇸 Australia-01", display_name="old",
                         server="1.1.1.1", port=443, node_type="vless", country_code="US",
                         country_flag="🇺🇸", latency=123.4, config_json={}))
        await session.commit()
        source_id = source.id
        old_node_id = (await session.execute(select(Node.id).where(Node.source_id == source_id))).scalar_one()

        assert await sync_single_source(source_id, session)
        nodes = (await session.execute(select(Node).where(Node.source_id == source_id))).scalars().all()
        by_name = {node.original_name: node for node in nodes}
        assert by_name["🇺🇸 Australia-01"].country_code == "AU"
        assert by_name["🇺🇸 Australia-01"].country_flag == "🇦🇺"
        assert by_name["🇺🇸 Australia-01"].id == old_node_id
        assert by_name["🇺🇸 Australia-01"].latency == 123.4
        assert by_name["🇺🇸 Russia-01"].country_code == "RU"
