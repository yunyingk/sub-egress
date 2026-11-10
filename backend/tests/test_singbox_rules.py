import json

from app.builder import build_singbox_config


def test_singbox_converts_shared_rule_subset_in_priority_order():
    config = json.loads(build_singbox_config(
        [],
        custom_direct_domains=["internal.example"],
        custom_proxy_domains=["remote.example"],
        custom_rules=[
            "DOMAIN-SUFFIX,admin.example,DIRECT",
            "DOMAIN-KEYWORD,github,PROXY",
            "UNSUPPORTED,ignored,DIRECT",
        ],
    ))
    rules = config["route"]["rules"]
    assert rules[2] == {"domain_suffix": ["internal.example"], "outbound": "direct"}
    assert rules[3] == {"domain_suffix": ["remote.example"], "outbound": "PROXY"}
    assert rules[4] == {"domain_suffix": ["admin.example"], "outbound": "direct"}
    assert rules[5] == {"domain_keyword": ["github"], "outbound": "PROXY"}


def test_reality_has_utls_and_unsupported_xhttp_is_not_referenced():
    nodes = [
        {'type': 'vless', 'server': 'example.test', 'port': 443,
         'uuid': '00000000-0000-4000-8000-000000000000', 'tls': True,
         'reality-opts': {'public-key': 'test-only-key', 'short-id': '1234'},
         'display_name': 'reality-node', 'country_code': 'US'},
        {'type': 'vless', 'server': 'example.test', 'port': 443,
         'network': 'xhttp', 'display_name': 'unsupported-node', 'country_code': 'US'},
    ]
    config = json.loads(build_singbox_config(nodes))
    reality = next(x for x in config['outbounds'] if x.get('tag') == 'reality-node')
    assert reality['tls']['utls'] == {'enabled': True, 'fingerprint': 'chrome'}
    assert all(x.get('tag') != 'unsupported-node' and 'unsupported-node' not in x.get('outbounds', []) for x in config['outbounds'])
