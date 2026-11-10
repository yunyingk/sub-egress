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
