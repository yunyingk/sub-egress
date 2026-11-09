import base64
import copy
import json
from typing import Any, Dict, List
import urllib.parse
import yaml

DEFAULT_DNS_CONFIG = {
    "enable": True,
    "ipv6": False,
    "enhanced-mode": "fake-ip",
    "fake-ip-range": "198.18.0.1/16",
    "use-hosts": True,
    "default-nameserver": ["223.5.5.5", "119.29.29.29"],
    "nameserver": ["223.5.5.5", "119.29.29.29", "114.114.114.114"],
    "fake-ip-filter": [
        "*.lan", "*.local", "*.localhost", "*.test",
        "+.stun.*", "+.msftncsi.com", "+.msftconnecttest.com"
    ]
}

DEFAULT_RULES = [
    "DOMAIN-SUFFIX,local,DIRECT",
    "DOMAIN-SUFFIX,localhost,DIRECT",
    "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,17.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
    "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
    "GEOIP,CN,DIRECT",
    "MATCH,PROXY"
]


def build_clash_config(raw_nodes: List[Dict[str, Any]]) -> str:
    """
    Builds a clean, single-selector Mihomo / ClashMeta YAML configuration.
    """
    if not raw_nodes:
        dummy_node = {"name": "DIRECT", "type": "direct"}
        config = {
            "mixed-port": 7890,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            "proxies": [dummy_node],
            "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": ["DIRECT"]}],
            "rules": ["MATCH,PROXY"]
        }
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    proxies_list: List[Dict[str, Any]] = []
    pass_through_names: List[str] = []
    japan_node_names: List[str] = []
    residential_node_names: List[str] = []

    for item in raw_nodes:
        node_cfg = copy.deepcopy(item.get("config_json", {}))
        display_name = item.get("display_name")
        country_code = item.get("country_code", "OTHER")
        is_res = item.get("is_residential", False)

        node_cfg["name"] = display_name
        proxies_list.append(node_cfg)
        pass_through_names.append(display_name)

        if country_code == "JP":
            japan_node_names.append(display_name)
        if is_res:
            residential_node_names.append(display_name)

    proxy_groups: List[Dict[str, Any]] = []
    dynamic_options: List[str] = []

    # 1. 动态·日区 (同国巡检，绝不换区)
    if japan_node_names:
        jp_dyn_name = "[动态·日区] 🇯🇵 日本最佳低延迟"
        proxy_groups.append({
            "name": jp_dyn_name,
            "type": "url-test",
            "proxies": list(japan_node_names),
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50
        })
        dynamic_options.append(jp_dyn_name)

    # 2. 动态·家宽 (仅限住宅IP主备，绝不换区)
    if residential_node_names:
        res_dyn_name = "[动态·家宽] 🇺🇸 美国住宅智能主备"
        proxy_groups.append({
            "name": res_dyn_name,
            "type": "fallback",
            "proxies": list(residential_node_names),
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300
        })
        dynamic_options.append(res_dyn_name)

    # 3. 动态·全局 (全网兜底容灾)
    global_dyn_name = "[动态·全局] 🌐 全网故障转移"
    proxy_groups.append({
        "name": global_dyn_name,
        "type": "url-test",
        "proxies": list(pass_through_names),
        "url": "http://www.gstatic.com/generate_204",
        "interval": 300,
        "tolerance": 100
    })
    dynamic_options.append(global_dyn_name)

    # 4. 主选择器 PROXY: 动态置顶 + 平铺全部透传节点
    main_selector_proxies = [*dynamic_options, *pass_through_names]
    main_selector = {
        "name": "PROXY",
        "type": "select",
        "proxies": main_selector_proxies
    }

    full_groups = [main_selector, *proxy_groups]

    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "strict",
        "dns": DEFAULT_DNS_CONFIG,
        "proxies": proxies_list,
        "proxy-groups": full_groups,
        "rules": DEFAULT_RULES
    }

    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)


def build_singbox_config(raw_nodes: List[Dict[str, Any]]) -> str:
    """
    Builds a complete, modern Sing-box JSON configuration with single-selector control.
    """
    outbounds: List[Dict[str, Any]] = []
    pass_through_tags: List[str] = []
    japan_tags: List[str] = []
    residential_tags: List[str] = []

    for item in raw_nodes:
        s = copy.deepcopy(item.get("config_json", {}))
        tag = item.get("display_name")
        country_code = item.get("country_code", "OTHER")
        is_res = item.get("is_residential", False)
        ntype = s.get("type", "").lower()

        outbound = None
        if ntype == "ss":
            outbound = {
                "type": "shadowsocks",
                "tag": tag,
                "server": s.get("server"),
                "server_port": int(s.get("port")),
                "method": s.get("cipher"),
                "password": s.get("password")
            }
        elif ntype == "trojan":
            outbound = {
                "type": "trojan",
                "tag": tag,
                "server": s.get("server"),
                "server_port": int(s.get("port")),
                "password": s.get("password"),
                "tls": {
                    "enabled": True,
                    "server_name": s.get("sni") or s.get("server"),
                    "insecure": bool(s.get("skip-cert-verify", False))
                }
            }
        elif ntype == "vless":
            outbound = {
                "type": "vless",
                "tag": tag,
                "server": s.get("server"),
                "server_port": int(s.get("port")),
                "uuid": s.get("uuid", ""),
                "flow": s.get("flow") or ""
            }
            if s.get("tls"):
                tls_cfg: Dict[str, Any] = {
                    "enabled": True,
                    "server_name": s.get("servername") or s.get("server"),
                    "insecure": bool(s.get("skip-cert-verify", False))
                }
                ropts = s.get("reality-opts")
                if ropts:
                    tls_cfg["reality"] = {
                        "enabled": True,
                        "public_key": ropts.get("public-key", ""),
                        "short_id": ropts.get("short-id", "")
                    }
                outbound["tls"] = tls_cfg
            if s.get("network") and s.get("network") != "tcp":
                outbound["transport"] = {"type": s.get("network")}
        elif ntype in ("hysteria2", "hy2"):
            outbound = {
                "type": "hysteria2",
                "tag": tag,
                "server": s.get("server"),
                "server_port": int(s.get("port")),
                "password": s.get("password", ""),
                "tls": {
                    "enabled": True,
                    "server_name": s.get("sni") or s.get("server"),
                    "insecure": bool(s.get("skip-cert-verify", False))
                }
            }

        if outbound:
            outbounds.append(outbound)
            pass_through_tags.append(tag)
            if country_code == "JP":
                japan_tags.append(tag)
            if is_res:
                residential_tags.append(tag)

    # 动态组
    group_outbounds: List[Dict[str, Any]] = []
    dyn_tags: List[str] = []

    if japan_tags:
        jp_dyn = "[动态·日区] 🇯🇵 日本最佳低延迟"
        group_outbounds.append({
            "type": "urltest",
            "tag": jp_dyn,
            "outbounds": japan_tags,
            "url": "http://www.gstatic.com/generate_204",
            "interval": "5m"
        })
        dyn_tags.append(jp_dyn)

    if residential_tags:
        res_dyn = "[动态·家宽] 🇺🇸 美国住宅智能主备"
        group_outbounds.append({
            "type": "urltest",
            "tag": res_dyn,
            "outbounds": residential_tags,
            "url": "http://www.gstatic.com/generate_204",
            "interval": "5m"
        })
        dyn_tags.append(res_dyn)

    if pass_through_tags:
        global_dyn = "[动态·全局] 🌐 全网故障转移"
        group_outbounds.append({
            "type": "urltest",
            "tag": global_dyn,
            "outbounds": pass_through_tags,
            "url": "http://www.gstatic.com/generate_204",
            "interval": "5m"
        })
        dyn_tags.append(global_dyn)

    # 主选择器 PROXY
    proxy_selector = {
        "type": "selector",
        "tag": "PROXY",
        "outbounds": [*dyn_tags, *pass_through_tags] if pass_through_tags else ["direct"],
        "default": dyn_tags[0] if dyn_tags else (pass_through_tags[0] if pass_through_tags else "direct")
    }

    # 基础出站
    system_outbounds = [
        {"type": "direct", "tag": "direct"},
        {"type": "dns", "tag": "dns-out"},
        {"type": "block", "tag": "block"}
    ]

    all_outbounds = [proxy_selector, *group_outbounds, *outbounds, *system_outbounds]

    singbox_config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "address": "tls://1.1.1.1",
                    "address_resolver": "dns-direct"
                },
                {
                    "tag": "dns-direct",
                    "address": "223.5.5.5",
                    "detour": "direct"
                },
                {
                    "tag": "dns-block",
                    "address": "rcode://success"
                }
            ],
            "rules": [
                {"outbound": "any", "server": "dns-direct"},
                {"geosite": "cn", "server": "dns-direct"}
            ],
            "independent_cache": True
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 7890
            }
        ],
        "outbounds": all_outbounds,
        "route": {
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"},
                {"geoip": "private", "outbound": "direct"},
                {"geoip": "cn", "outbound": "direct"},
                {"geosite": "cn", "outbound": "direct"}
            ],
            "auto_detect_interface": True,
            "final": "PROXY"
        }
    }

    return json.dumps(singbox_config, ensure_ascii=False, indent=2)


def build_base64_config(raw_nodes: List[Dict[str, Any]]) -> str:
    """
    Builds a standard Base64 URI subscription containing all valid node links.
    """
    uris: List[str] = []
    for item in raw_nodes:
        s = item.get("config_json", {})
        tag = item.get("display_name", "")
        ntype = s.get("type", "").lower()
        tag_encoded = urllib.parse.quote(tag)

        if ntype == "ss":
            userinfo = f"{s.get('cipher')}:{s.get('password')}@{s.get('server')}:{s.get('port')}"
            b64_user = base64.b64encode(userinfo.encode()).decode()
            uris.append(f"ss://{b64_user}#{tag_encoded}")
        elif ntype == "trojan":
            uris.append(f"trojan://{s.get('password')}@{s.get('server')}:{s.get('port')}?sni={s.get('sni') or s.get('server')}#{tag_encoded}")
        elif ntype == "vless":
            sec = "reality" if s.get("reality-opts") else ("tls" if s.get("tls") else "none")
            uris.append(f"vless://{s.get('uuid')}@{s.get('server')}:{s.get('port')}?security={sec}&sni={s.get('servername') or s.get('server')}#{tag_encoded}")
        elif ntype in ("hysteria2", "hy2"):
            uris.append(f"hy2://{s.get('password')}@{s.get('server')}:{s.get('port')}?sni={s.get('sni') or s.get('server')}#{tag_encoded}")

    text = "\n".join(uris)
    return base64.b64encode(text.encode()).decode()
