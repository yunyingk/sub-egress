import base64
import json

import pytest
import yaml
from app.api import (
    SourceCreate,
    SourceUpdate,
    admin_create_source,
    admin_list_sources,
    admin_update_source,
    batch_ping_nodes,
    export_subscription,
    list_nodes,
    list_sources,
    ping_node_endpoint,
    toggle_shared_source_for_user,
)
from app.builder import (
    DYNAMIC_GLOBAL_GROUP_NAME,
    DYNAMIC_PREMIUM_GROUP_NAME,
    PREMIUM_GROUP_NAME,
    build_clash_config,
    build_singbox_config,
)
from app.models import Base, Node, Setting, Source, SourceUserGrant, User
from app.syncer import sync_single_source
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request


def _ss_node(display_name: str, server: str, country_code: str, source_tier: str) -> dict:
    return {
        "display_name": display_name,
        "country_code": country_code,
        "source_tier": source_tier,
        "is_residential": source_tier == "premium",
        "config_json": {
            "type": "ss",
            "name": display_name,
            "server": server,
            "port": 443,
            "cipher": "aes-128-gcm",
            "password": "test-only-password",
        },
    }


def _collect_group_members(groups_by_name: dict[str, dict], group_name: str, visited: set[str] | None = None) -> set[str]:
    visited = visited or set()
    if group_name in visited or group_name not in groups_by_name:
        return set()
    visited.add(group_name)
    members: set[str] = set()
    for item in groups_by_name[group_name].get("proxies", []):
        if item in groups_by_name:
            members.update(_collect_group_members(groups_by_name, item, visited))
        else:
            members.add(item)
    return members


@pytest.mark.asyncio
async def test_sync_uses_explicit_source_tier_not_keywords(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr("app.syncer.ping_source_nodes", noop)

    async with factory() as db:
        standard_src = Source(
            name="Standard Airport",
            code="ST",
            url="local://std",
            source_type="local_yaml",
            tier="standard",
            is_shared=True,
            raw_content=yaml.safe_dump({
                "proxies": [{
                    "name": "🇺🇸 美国家宽住宅-01",
                    "type": "ss",
                    "server": "std.example.test",
                    "port": 443,
                    "cipher": "aes-128-gcm",
                    "password": "test-only-password",
                }]
            }),
        )
        premium_src = Source(
            name="Clean Line",
            code="PR",
            url="local://prem",
            source_type="local_yaml",
            tier="premium",
            is_shared=True,
            raw_content=yaml.safe_dump({
                "proxies": [{
                    "name": "🇯🇵 东京普通线路",
                    "type": "ss",
                    "server": "prem.example.test",
                    "port": 443,
                    "cipher": "aes-128-gcm",
                    "password": "test-only-password",
                }]
            }),
        )
        db.add_all([standard_src, premium_src])
        await db.commit()

        assert await sync_single_source(standard_src.id, db)
        assert await sync_single_source(premium_src.id, db)

        std_node = await db.scalar(select(Node).where(Node.source_id == standard_src.id))
        prem_node = await db.scalar(select(Node).where(Node.source_id == premium_src.id))
        assert std_node.is_residential is False
        assert std_node.display_name == "[ST] 🇺🇸 美国家宽住宅-01"
        assert prem_node.is_residential is True
        assert prem_node.display_name == "[PR] 🇯🇵 东京普通线路"

    await engine.dispose()


def test_clash_routing_isolates_premium_and_locks_global():
    nodes = [
        _ss_node("[SD] 🇺🇸 美国日常", "std-us.example.test", "US", "standard"),
        _ss_node("[SD] 🇯🇵 日本日常", "std-jp.example.test", "JP", "standard"),
        _ss_node("[RE] 🇺🇸 美国-01 A", "prem-1.example.test", "US", "premium"),
        _ss_node("[RE] 🇺🇸 美国-02 V", "prem-2.example.test", "US", "premium"),
    ]
    config = yaml.safe_load(build_clash_config(
        nodes,
        mixed_port=7897,
        terminal_port=7898,
        custom_proxy_domains=["openai.com"],
        custom_premium_domains=["sora.com"],
        custom_rules=["DOMAIN-SUFFIX,work-ai.example,__PREMIUM_PROXY__"],
    ))
    groups = {g["name"]: g for g in config["proxy-groups"]}
    group_order = [g["name"] for g in config["proxy-groups"]]

    assert group_order[:4] == ["[7897] 主出站", PREMIUM_GROUP_NAME, "[7898] 副出站", "GLOBAL"]
    assert groups["GLOBAL"]["proxies"][0] == "[7897] 主出站"

    # Standard selectors & dynamic groups must never include premium nodes
    for std_group in ("[7897] 主出站", "[7898] 副出站", DYNAMIC_GLOBAL_GROUP_NAME, "[动态·美区] 🇺🇸 美国最佳低延迟", "[源·SD] 🌐 供应商 SD 专区"):
        members = _collect_group_members(groups, std_group)
        assert "[RE] 🇺🇸 美国-01 A" not in members
        assert "[RE] 🇺🇸 美国-02 V" not in members

    # Premium group defaults to premium fallback and includes AnyTLS first
    assert groups[PREMIUM_GROUP_NAME]["proxies"][0] == DYNAMIC_PREMIUM_GROUP_NAME
    assert groups[PREMIUM_GROUP_NAME]["proxies"][-1] == "[7897] 主出站"
    assert groups[DYNAMIC_PREMIUM_GROUP_NAME]["proxies"] == ["[RE] 🇺🇸 美国-01 A", "[RE] 🇺🇸 美国-02 V"]

    rules = config["rules"]
    assert "DOMAIN-SUFFIX,sora.com,精选高级" in rules
    assert "DOMAIN-SUFFIX,work-ai.example,精选高级" in rules
    assert "DOMAIN-SUFFIX,claude.ai,精选高级" in rules
    assert "DOMAIN-SUFFIX,gemini.google.com,精选高级" in rules
    assert "DOMAIN-SUFFIX,google.com,[7897] 主出站" in rules
    assert rules[-1] == "MATCH,[7897] 主出站"
    # custom_proxy_domains overrides built-in AI rule to cheap main proxy
    assert rules.index("DOMAIN-SUFFIX,openai.com,[7897] 主出站") < rules.index("DOMAIN-SUFFIX,openai.com,精选高级")


def test_clash_fallbacks_for_standard_only_and_premium_only():
    std_only = yaml.safe_load(build_clash_config([_ss_node("[SD] 🇯🇵 日本-01", "jp.example.test", "JP", "standard")]))
    std_groups = {g["name"]: g for g in std_only["proxy-groups"]}
    assert std_groups[PREMIUM_GROUP_NAME]["proxies"][0] == "[7897] 主出站"
    assert DYNAMIC_PREMIUM_GROUP_NAME not in std_groups

    prem_only = yaml.safe_load(build_clash_config([_ss_node("[RE] 🇺🇸 美国-01", "us.example.test", "US", "premium")]))
    prem_groups = {g["name"]: g for g in prem_only["proxy-groups"]}
    assert DYNAMIC_PREMIUM_GROUP_NAME in prem_groups["[7897] 主出站"]["proxies"]


def test_singbox_premium_routing_parity():
    nodes = [
        _ss_node("[SD] 🇯🇵 日本日常", "std-jp.example.test", "JP", "standard"),
        _ss_node("[RE] 🇺🇸 美国高级", "prem-us.example.test", "US", "premium"),
    ]
    config = json.loads(build_singbox_config(
        nodes,
        custom_premium_domains=["sora.com"],
        custom_rules=["DOMAIN-SUFFIX,custom-ai.test,__PREMIUM_PROXY__"],
    ))
    outbounds = {o["tag"]: o for o in config["outbounds"]}
    assert "[RE] 🇺🇸 美国高级" not in outbounds["PROXY"]["outbounds"]
    assert DYNAMIC_PREMIUM_GROUP_NAME not in outbounds["PROXY"]["outbounds"]
    assert outbounds["PREMIUM"]["default"] == DYNAMIC_PREMIUM_GROUP_NAME

    rules = config["route"]["rules"]
    assert {"domain_suffix": ["sora.com"], "outbound": "PREMIUM"} in rules
    assert {"domain_suffix": ["custom-ai.test"], "outbound": "PREMIUM"} in rules
    assert any(r.get("outbound") == "PREMIUM" and "claude.ai" in r.get("domain_suffix", []) for r in rules)


@pytest.mark.asyncio
async def test_shared_source_whitelist_acl_and_admin_tier_updates(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def noop_sync(source_id, db):
        return True

    async def fake_ping(host, port, ntype, timeout=2.5):
        return {"latency": 12.3, "status": "ok", "error": None}

    monkeypatch.setattr("app.api.sync_single_source", noop_sync)
    monkeypatch.setattr("app.api.ping_single_node", fake_ping)

    async with factory() as db:
        admin = User(id=1, username="admin", role="admin", sub_hash_token="admin-tok", is_active=True)
        sister = User(id=2, username="sister", role="user", sub_hash_token="sister-tok", is_active=True)
        friend = User(id=3, username="friend", role="user", sub_hash_token="friend-tok", is_active=True)
        db.add_all([admin, sister, friend])
        db.add(Setting(key="admin_premium_domains", value="sora.com"))
        await db.flush()

        create_res = await admin_create_source(
            SourceCreate(
                name="Cheap Airport",
                url="https://cheap.example.test/sub",
                tier="standard",
                share_scope="all",
            ),
            admin=admin,
            db=db,
        )
        cheap_id = create_res["id"]

        prem_res = await admin_create_source(
            SourceCreate(
                name="US Residential",
                url="https://res.example.test/sub",
                tier="premium",
                share_scope="selected",
                granted_user_ids=[1, 2],
            ),
            admin=admin,
            db=db,
        )
        prem_id = prem_res["id"]

        cheap_node = Node(
            id=101,
            source_id=cheap_id,
            original_name="JP-01",
            display_name="[CH] 🇯🇵 JP-01",
            node_type="ss",
            server="cheap.example.test",
            port=443,
            country_code="JP",
            is_residential=False,
            config_json={"type": "ss", "server": "cheap.example.test", "port": 443, "cipher": "aes-128-gcm", "password": "pw"},
        )
        prem_node = Node(
            id=102,
            source_id=prem_id,
            original_name="US-Res",
            display_name="[US] 🇺🇸 US-Res",
            node_type="ss",
            server="res.example.test",
            port=443,
            country_code="US",
            is_residential=True,
            config_json={"type": "ss", "server": "res.example.test", "port": 443, "cipher": "aes-128-gcm", "password": "pw"},
        )
        db.add_all([cheap_node, prem_node])
        await db.commit()

        # Sister sees both sources & nodes; friend sees only cheap
        sister_sources = await list_sources(user=sister, db=db)
        friend_sources = await list_sources(user=friend, db=db)
        assert {s["id"] for s in sister_sources} == {cheap_id, prem_id}
        assert {s["id"] for s in friend_sources} == {cheap_id}

        sister_nodes = await list_nodes(user=sister, db=db)
        friend_nodes = await list_nodes(user=friend, db=db)
        assert {n["id"] for n in sister_nodes["nodes"]} == {101, 102}
        assert {n["id"] for n in friend_nodes["nodes"]} == {101}

        # Friend cannot ping or toggle ungranted shared source
        with pytest.raises(HTTPException) as ping_err:
            await ping_node_endpoint(node_id=102, user=friend, db=db)
        assert ping_err.value.status_code == 404

        with pytest.raises(HTTPException) as toggle_err:
            await toggle_shared_source_for_user(source_id=prem_id, user=friend, db=db)
        assert toggle_err.value.status_code == 404

        friend_batch = await batch_ping_nodes(user=friend, db=db, payload=None)
        assert friend_batch["total"] == 1 and "101" in friend_batch["results"]

        # Export endpoints enforce ACL across all formats
        req = Request({"type": "http", "method": "GET", "path": "/c/tok", "headers": [(b"host", b"example.test")], "scheme": "https", "query_string": b""})
        sister_clash = yaml.safe_load((await export_subscription(req, db, sister.sub_hash_token, target="clash")).body)
        friend_clash = yaml.safe_load((await export_subscription(req, db, friend.sub_hash_token, target="clash")).body)
        assert {p["name"] for p in sister_clash["proxies"]} == {"[CH] 🇯🇵 JP-01", "[US] 🇺🇸 US-Res"}
        assert {p["name"] for p in friend_clash["proxies"]} == {"[CH] 🇯🇵 JP-01"}
        assert "DOMAIN-SUFFIX,sora.com,精选高级" in sister_clash["rules"]

        friend_sb = json.loads((await export_subscription(req, db, friend.sub_hash_token, target="sing-box")).body)
        assert not any(o.get("server") == "res.example.test" for o in friend_sb["outbounds"])

        friend_links = base64.b64decode((await export_subscription(req, db, friend.sub_hash_token, target="base64")).body).decode().splitlines()
        friend_ss_hosts = {
            base64.b64decode(link.removeprefix("ss://").split("#")[0]).decode().rsplit("@", 1)[1].rsplit(":", 1)[0]
            for link in friend_links
        }
        assert friend_ss_hosts == {"cheap.example.test"}

        # Admin listing includes whitelist metadata; updating tier updates existing nodes immediately
        admin_sources = await admin_list_sources(admin=admin, db=db, scope="shared")
        prem_meta = next(s for s in admin_sources if s["id"] == prem_id)
        assert prem_meta["tier"] == "premium"
        assert prem_meta["share_scope"] == "selected"
        assert prem_meta["granted_usernames"] == ["admin", "sister"]

        await admin_update_source(
            cheap_id,
            SourceUpdate(tier="premium"),
            admin=admin,
            db=db,
        )
        updated_cheap_node = await db.get(Node, 101)
        assert updated_cheap_node.is_residential is True

        # Switching share_scope back to "all" clears grant rows
        await admin_update_source(
            prem_id,
            SourceUpdate(share_scope="all"),
            admin=admin,
            db=db,
        )
        grants_left = (await db.execute(select(SourceUserGrant).where(SourceUserGrant.source_id == prem_id))).scalars().all()
        assert grants_left == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_db_init_adds_tier_and_share_scope_preserving_existing_residential(monkeypatch):
    from app import db as db_module

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(64) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                role VARCHAR(32) NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                sub_hash_token VARCHAR(64) NOT NULL UNIQUE,
                theme_mode VARCHAR(16) NOT NULL DEFAULT 'system',
                subscription_title VARCHAR(128) NOT NULL DEFAULT 'sub-egress',
                clash_mixed_port VARCHAR(16) NOT NULL DEFAULT '7897',
                clash_terminal_port VARCHAR(16) NOT NULL DEFAULT '7898',
                custom_direct_domains TEXT DEFAULT 'ying-qing.cn',
                custom_proxy_domains TEXT DEFAULT '',
                custom_rules TEXT DEFAULT '',
                disabled_shared_sources TEXT DEFAULT '',
                oauth_provider VARCHAR(32),
                oauth_id VARCHAR(128),
                last_login_at TIMESTAMP,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY,
                owner_user_id INTEGER,
                created_by_user_id INTEGER,
                is_shared BOOLEAN NOT NULL DEFAULT 1,
                name VARCHAR(64) NOT NULL,
                code VARCHAR(8),
                url TEXT NOT NULL,
                source_type VARCHAR(32),
                enabled BOOLEAN NOT NULL DEFAULT 1,
                status VARCHAR(32),
                error_message TEXT,
                node_count INTEGER,
                traffic_used BIGINT,
                traffic_total BIGINT,
                expire_at TIMESTAMP,
                last_sync_at TIMESTAMP,
                raw_content TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                node_type VARCHAR(32) NOT NULL,
                server VARCHAR(255) NOT NULL,
                port INTEGER NOT NULL,
                country_code VARCHAR(16),
                country_flag VARCHAR(8),
                is_residential BOOLEAN DEFAULT 0,
                config_json JSON NOT NULL,
                created_at TIMESTAMP
            )
        """))
        await conn.execute(text("INSERT INTO users (id, username, role, sub_hash_token) VALUES (1, 'admin', 'admin', 'tok')"))
        await conn.execute(text("INSERT INTO sources (id, is_shared, name, url) VALUES (1, 1, 'Res', 'local://1'), (2, 1, 'Std', 'local://2')"))
        await conn.execute(text("""
            INSERT INTO nodes (id, source_id, original_name, display_name, node_type, server, port, is_residential, config_json)
            VALUES
              (1, 1, 'us', 'us', 'ss', '1.1.1.1', 443, 1, '{}'),
              (2, 2, 'jp', 'jp', 'ss', '2.2.2.2', 443, 0, '{}')
        """))

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    await db_module.init_db()

    async with engine.begin() as conn:
        rows = (await conn.execute(text("SELECT id, tier, share_scope FROM sources ORDER BY id"))).all()
        assert rows == [(1, "premium", "all"), (2, "standard", "all")]

    await engine.dispose()
