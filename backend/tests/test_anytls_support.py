import base64
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from app.builder import build_base64_config, build_singbox_config
from app.parsers.singbox import parse_singbox_json
from app.parsers.uri import parse_subscription_text, parse_uri


def sample_node():
    return {
        'type': 'anytls', 'name': '测试节点', 'display_name': '测试节点',
        'server': '2001:db8::1', 'port': 443, 'password': 'test:@/密碼',
        'sni': 'front.example.test', 'skip-cert-verify': True,
        'client-fingerprint': 'chrome', 'alpn': ['h2', 'http/1.1'],
    }


def test_anytls_singbox_conversion_and_roundtrip():
    config = json.loads(build_singbox_config([sample_node()]))
    node = next(x for x in config['outbounds'] if x['type'] == 'anytls')
    assert node['server'] == '2001:db8::1' and node['server_port'] == 443
    assert node['password'] == 'test:@/密碼'
    assert node['tls'] == {'enabled': True, 'server_name': 'front.example.test', 'insecure': True,
                           'utls': {'enabled': True, 'fingerprint': 'chrome'}, 'alpn': ['h2', 'http/1.1']}
    restored = parse_singbox_json(json.dumps(config))
    assert len(restored) == 1
    assert restored[0]['password'] == 'test:@/密碼'
    assert restored[0]['client-fingerprint'] == 'chrome'
    assert restored[0]['alpn'] == ['h2', 'http/1.1']


def test_anytls_uri_encoding_base64_and_import():
    result = base64.b64decode(build_base64_config([sample_node()])).decode()
    uri = urlsplit(result)
    assert uri.scheme == 'anytls' and uri.hostname == '2001:db8::1' and uri.port == 443
    assert parse_qs(uri.query)['insecure'] == ['1']
    decoded = parse_uri(result)
    assert decoded['password'] == 'test:@/密碼'
    assert decoded['name'] == '测试节点'
    assert decoded['client-fingerprint'] == 'chrome'
    assert decoded['alpn'] == ['h2', 'http/1.1']
    assert parse_subscription_text(base64.b64encode(result.encode()).decode())[0] == decoded


def test_anytls_defaults_to_certificate_verification():
    uri = 'anytls://test-password@node.example.test/#node'
    parsed = parse_uri(uri)
    assert parsed['port'] == 443 and not parsed.get('skip-cert-verify', False)
    outbound = next(x for x in json.loads(build_singbox_config([parsed]))['outbounds'] if x['type'] == 'anytls')
    assert outbound['tls']['insecure'] is False


@pytest.mark.asyncio
async def test_anytls_export_from_database_filters_deleted_sources():
    from datetime import UTC, datetime

    from app.api import export_subscription
    from app.models import Base, Node, Source, User
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from starlette.requests import Request

    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(id=1, username='alice', sub_hash_token='alice-test-token')
        active = Source(id=1, name='active', url='local://active', is_shared=False, owner_user_id=1)
        deleted = Source(id=2, name='deleted', url='local://deleted', is_shared=False, owner_user_id=1, deleted_at=datetime.now(UTC))
        db.add_all([user, active, deleted])
        for sid in (1, 2):
            cfg = sample_node()
            cfg['server'] = f'node-{sid}.example.test'
            db.add(Node(id=sid, source_id=sid, original_name='node', display_name=f'node-{sid}',
                        node_type='anytls', server=cfg['server'], port=443, config_json=cfg))
        await db.commit()
        request = Request({'type': 'http', 'method': 'GET', 'path': '/feed', 'headers': [(b'host', b'example.test')], 'scheme': 'https', 'query_string': b''})
        for target in ('sing-box', 'base64'):
            response = await export_subscription(request=request, db=db, token=user.sub_hash_token,
                                                 target=target, type=None, name=None, title=None, t=None)
            if target == 'sing-box':
                nodes = [x for x in json.loads(response.body)['outbounds'] if x['type'] == 'anytls']
                assert [x['server'] for x in nodes] == ['node-1.example.test']
            else:
                links = base64.b64decode(response.body).decode().splitlines()
                assert len(links) == 1 and urlsplit(links[0]).hostname == 'node-1.example.test'
    await engine.dispose()


@pytest.mark.asyncio
async def test_standalone_anytls_link_can_be_probed_and_synced(monkeypatch):
    from app.api import ProbeSourcePayload, probe_subscription_source
    from app.models import Base, Node, Source, User
    from app.syncer import sync_single_source
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr('app.syncer.ping_source_nodes', noop)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(id=1, username='alice', sub_hash_token='test-token')
        uri = 'anytls://test-password@node.example.test:443/?sni=front.example.test#my-node'
        source = Source(id=1, name='my-source', url=uri, owner_user_id=1, is_shared=False)
        db.add_all([user, source])
        await db.commit()
        probe = await probe_subscription_source(ProbeSourcePayload(url=uri), user)
        assert probe['node_count'] == 1 and probe['source_type'] == 'uri'
        assert await sync_single_source(1, db)
        node = await db.scalar(select(Node).where(Node.source_id == 1))
        assert node and node.node_type == 'anytls' and node.config_json['sni'] == 'front.example.test'
    await engine.dispose()
