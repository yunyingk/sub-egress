import json

import yaml
from app.builder import (
    DEFAULT_GOOGLE_PROXY_DOMAINS,
    build_clash_config,
    build_singbox_config,
)


def _sample_node():
    return {
        "display_name": "[RE] 🇺🇸 US-01",
        "country_code": "US",
        "is_residential": True,
        "config_json": {
            "type": "ss",
            "name": "us-01",
            "server": "us.example.test",
            "port": 443,
            "cipher": "aes-128-gcm",
            "password": "test-only-password",
        },
    }


def test_clash_default_google_rules_order_and_port_binding():
    rendered = build_clash_config(
        [_sample_node()],
        mixed_port=8897,
        custom_direct_domains=["corp.example.test"],
    )
    config = yaml.safe_load(rendered)
    rules = config["rules"]
    main_group = "[8897] 主出站"

    direct_idx = rules.index("DOMAIN-SUFFIX,corp.example.test,DIRECT")
    ads_idx = rules.index("GEOSITE,category-ads-all,REJECT")
    quic_idx = rules.index("AND,((NETWORK,udp),(DST-PORT,443)),REJECT")
    stun_idx = rules.index("DOMAIN-KEYWORD,stun,REJECT")
    geosite_cn_idx = rules.index("GEOSITE,cn,DIRECT")
    geoip_cn_idx = rules.index("GEOIP,CN,DIRECT")

    for domain in DEFAULT_GOOGLE_PROXY_DOMAINS:
        rule = f"DOMAIN-SUFFIX,{domain},{main_group}"
        assert rule in rules
        idx = rules.index(rule)
        assert direct_idx < ads_idx < quic_idx < stun_idx < idx < geosite_cn_idx < geoip_cn_idx

    # Spot-check key domains needed for Chrome / Gemini region consistency
    for required in ("google.com", "googleapis.com", "gstatic.com", "google", "ai.google.dev"):
        assert f"DOMAIN-SUFFIX,{required},{main_group}" in rules


def test_singbox_default_google_rules_precede_cn_direct_without_remote_google_ruleset():
    rendered = build_singbox_config(
        [_sample_node()],
        custom_direct_domains=["corp.example.test"],
        custom_rules=["DOMAIN-SUFFIX,custom.example.test,PROXY"],
    )
    config = json.loads(rendered)
    rules = config["route"]["rules"]

    direct_idx = rules.index({"domain_suffix": ["corp.example.test"], "outbound": "direct"})
    custom_idx = rules.index({"domain_suffix": ["custom.example.test"], "outbound": "PROXY"})
    google_idx = next(
        i
        for i, rule in enumerate(rules)
        if rule.get("outbound") == "PROXY"
        and set(DEFAULT_GOOGLE_PROXY_DOMAINS).issubset(set(rule.get("domain_suffix", [])))
    )
    geoip_cn_idx = rules.index({"rule_set": ["geoip-cn"], "outbound": "direct"})
    geosite_cn_idx = rules.index({"rule_set": ["geosite-cn"], "outbound": "direct"})

    assert direct_idx < custom_idx < google_idx < geoip_cn_idx < geosite_cn_idx

    ruleset_tags = {item["tag"] for item in config["route"]["rule_set"]}
    assert "geosite-google" not in ruleset_tags
