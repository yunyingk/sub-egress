import base64
import json

import pytest
from app.api import export_subscription
from app.builder import build_base64_config, build_singbox_config
from app.models import Base, Node, Source, User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request


def shadowsocks(server):
    return {'type': 'ss', 'name': server, 'server': server, 'port': 443,
            'cipher': 'aes-128-gcm', 'password': 'test-only-password'}


def hosts_from_response(response, target):
    if target == 'sing-box':
        config = json.loads(response.body)
        return {item['server'] for item in config['outbounds'] if item['type'] == 'shadowsocks'}
    links = base64.b64decode(response.body).decode().splitlines()
    return {base64.b64decode(link.removeprefix('ss://').split('#')[0]).decode().rsplit('@', 1)[1].rsplit(':', 1)[0] for link in links}


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['sing-box', 'base64'])
async def test_export_formats_respect_ownership_and_both_shared_switches(target):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        alice = User(id=1, username='alice', sub_hash_token='alice-test-token', disabled_shared_sources='2')
        bob = User(id=2, username='bob', sub_hash_token='bob-test-token')
        db.add_all([alice, bob])
        sources = [
            Source(id=1, name='active', url='local://1', is_shared=True, enabled=True),
            Source(id=2, name='user-disabled', url='local://2', is_shared=True, enabled=True),
            Source(id=3, name='globally-disabled', url='local://3', is_shared=True, enabled=False),
            Source(id=4, name='alice-private', url='local://4', is_shared=False, owner_user_id=1, enabled=True),
            Source(id=5, name='bob-private', url='local://5', is_shared=False, owner_user_id=2, enabled=True),
        ]
        db.add_all(sources)
        for source in sources:
            server = f'{source.name}.example.test'
            db.add(Node(source_id=source.id, original_name=source.name, display_name=source.name,
                        node_type='ss', server=server, port=443, config_json=shadowsocks(server)))
        await db.commit()
        request = Request({'type': 'http', 'method': 'GET', 'path': '/feed',
                           'headers': [(b'host', b'example.test')], 'scheme': 'https', 'query_string': b''})
        response = await export_subscription(request=request, db=db, token=alice.sub_hash_token,
                                             target=target, type=None, name=None, title=None, t=None)
        assert response.status_code == 200
        assert hosts_from_response(response, target) == {'active.example.test', 'alice-private.example.test'}
        alice.disabled_shared_sources = ''
        await db.commit()
        response = await export_subscription(request=request, db=db, token=alice.sub_hash_token,
                                             target=target, type=None, name=None, title=None, t=None)
        assert hosts_from_response(response, target) == {
            'active.example.test', 'user-disabled.example.test', 'alice-private.example.test'
        }
    await engine.dispose()


def test_generators_keep_nested_node_compatibility():
    node = {'display_name': 'nested', 'config_json': shadowsocks('nested.example.test')}
    result = json.loads(build_singbox_config([node]))
    assert any(item.get('server') == 'nested.example.test' for item in result['outbounds'])
    assert 'nested.example.test' in base64.b64decode(base64.b64decode(build_base64_config([node])).decode().split('#')[0][5:]).decode()


@pytest.mark.parametrize(('node_type', 'singbox_type', 'uri_scheme'), [
    ('ss', 'shadowsocks', 'ss://'),
    ('trojan', 'trojan', 'trojan://'),
    ('vless', 'vless', 'vless://'),
    ('hysteria2', 'hysteria2', 'hy2://'),
])
@pytest.mark.parametrize('nested', [False, True])
def test_supported_protocols_for_flat_and_nested_nodes(node_type, singbox_type, uri_scheme, nested):
    config = {'type': node_type, 'server': 'proxy.example.test', 'port': 443,
              'cipher': 'aes-128-gcm', 'password': 'test-only-password',
              'uuid': '00000000-0000-4000-8000-000000000000'}
    node = {'display_name': 'test-node', 'config_json': config} if nested else {**config, 'display_name': 'test-node'}
    outbounds = json.loads(build_singbox_config([node]))['outbounds']
    outbound = next(x for x in outbounds if x.get('tag') == 'test-node')
    assert outbound['type'] == singbox_type
    assert outbound['server'] == 'proxy.example.test'
    assert base64.b64decode(build_base64_config([node])).decode().startswith(uri_scheme)
