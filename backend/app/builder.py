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
    "proxy-server-nameserver": [
        "223.5.5.5",
        "119.29.29.29",
        "https://doh.pub/dns-query"
    ],
    "nameserver": [
        "223.5.5.5",
        "119.29.29.29",
        "https://doh.pub/dns-query",
        "https://dns.alidns.com/dns-query"
    ],
    "nameserver-policy": {
        "geosite:cn": ["223.5.5.5", "119.29.29.29"]
    },
    "fake-ip-filter": [
        "*.lan", "*.local", "*.localhost", "*.test",
        "+.stun.*", "+.msftncsi.com", "+.msftconnecttest.com"
    ]
}

DEFAULT_SNIFFER_CONFIG = {
    "enable": True,
    "parse-pure-ip": True,
    "sniff": {
        "HTTP": {
            "ports": [80, "8080-8880"],
            "override-destination": True
        },
        "TLS": {
            "ports": [443, 8443],
            "override-destination": True
        }
    }
}

DEFAULT_RULES = [
    # 1. 基础广告过滤
    "GEOSITE,category-ads-all,REJECT",
    # 2. 阻断 UDP 443 (防 QUIC 降级与探测泄露)
    "AND,((NETWORK,udp),(DST-PORT,443)),REJECT",
    # 3. 阻断 WebRTC STUN 泄露
    "DOMAIN-KEYWORD,stun,REJECT",
    "AND,((NETWORK,udp),(DST-PORT,3478)),REJECT",
    # 4. 私网及局域网直连 (避免 fake-ip 劫持局域网通信)
    "DOMAIN-SUFFIX,local,DIRECT",
    "DOMAIN-SUFFIX,localhost,DIRECT",
    "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
    "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve",
    "IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
    "IP-CIDR6,::1/128,DIRECT,no-resolve",
    "IP-CIDR6,fc00::/7,DIRECT,no-resolve",
    "IP-CIDR6,fe80::/10,DIRECT,no-resolve",
    # 5. 常用邮件端口直连 (防代理拦截或账号风控)
    "DST-PORT,25,DIRECT",
    "DST-PORT,465,DIRECT",
    "DST-PORT,587,DIRECT",
    "DST-PORT,110,DIRECT",
    "DST-PORT,143,DIRECT",
    "DST-PORT,993,DIRECT",
    "DST-PORT,995,DIRECT",
    # 6. 重点 AI 域名与风控服务精准走主选择器
    "DOMAIN-SUFFIX,anthropic.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,claude.ai,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,claude.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,claudeusercontent.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,statsigapi.net,__MAIN_PROXY__",
    "IP-CIDR,160.79.104.0/21,__MAIN_PROXY__,no-resolve",
    "DOMAIN-SUFFIX,openai.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,chatgpt.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,oaistatic.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,oaiusercontent.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,arkoselabs.com,__MAIN_PROXY__",
    "DOMAIN-KEYWORD,arkose,__MAIN_PROXY__",
    "DOMAIN,challenges.cloudflare.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,statsig.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,featuregates.org,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,gemini.google.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,x.ai,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,grok.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,perplexity.ai,__MAIN_PROXY__",
    # 7. IP 与 DNS 泄露检测站点
    "DOMAIN-SUFFIX,browserleaks.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,ipleak.net,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,dnsleaktest.com,__MAIN_PROXY__",
    # 8. 中国大陆网站与 IP 直连
    "GEOSITE,cn,DIRECT",
    "GEOIP,CN,DIRECT",
    # 9. 全局兜底
    "MATCH,__MAIN_PROXY__"
]

DYNAMIC_REGIONS = [
    ("HK", "🇭🇰", "港区", "香港最佳低延迟"),
    ("JP", "🇯🇵", "日区", "日本最佳低延迟"),
    ("SG", "🇸🇬", "狮城", "新加坡最佳低延迟"),
    ("TW", "🇨🇳", "台区", "台湾最佳低延迟"),
    ("US", "🇺🇸", "美区", "美国最佳低延迟"),
    ("KR", "🇰🇷", "韩区", "韩国最佳低延迟"),
    ("GB", "🇬🇧", "英区", "英国最佳低延迟"),
    ("DE", "🇩🇪", "德区", "德国最佳低延迟"),
]


def sort_residential_nodes(names: List[str]) -> List[str]:
    """
    家宽住宅主备优先排序：
    1. 协议优先：AnyTLS (' A ' 或 'AnyTLS') 作为第一顺位主选，优于 VLESS (' V ')
    2. 线路优先：主线 ('01' / '主线') 优先于 备用 ('02' / '备用')
    """
    def key_fn(n: str):
        proto_score = 0 if (' A ' in n or 'AnyTLS' in n) else 1
        line_score = 0 if ('01' in n or '主线' in n) else 1
        return (proto_score, line_score, n)
    return sorted(names, key=key_fn)


def extract_dynamic_groups(raw_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据接入的可用物理节点，自动计算带边界的聚合动态策略组 (URL-Test / Fallback)。
    既用于下发配置文件生成，也用于提供给 Web 仪表盘清晰展示。
    """
    if not raw_nodes:
        return []

    pass_through_names = [item.get("display_name") or item.get("name") for item in raw_nodes if (item.get("display_name") or item.get("name"))]
    by_country: Dict[str, List[str]] = {}
    residential_names: List[str] = []

    for item in raw_nodes:
        name = item.get("display_name") or item.get("name")
        if not name:
            continue
        cc = (item.get("country_code") or "OTHER").upper()
        by_country.setdefault(cc, []).append(name)
        if item.get("is_residential"):
            residential_names.append(name)

    groups = []

    # 1. 重点地区同国巡检低延迟动态组 (绝不跨区乱跳)
    for code, flag, short_name, desc in DYNAMIC_REGIONS:
        node_names = by_country.get(code, [])
        if node_names:
            groups.append({
                "name": f"[动态·{short_name}] {flag} {desc}",
                "type": "url-test",
                "strategy": "同国低延迟自动优选",
                "country_code": code,
                "country_flag": flag,
                "node_count": len(node_names),
                "proxies": list(node_names),
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50
            })

    # 2. 纯净美国家宽住宅智能主备组 (绝不混入机房IP)
    if residential_names:
        sorted_res = sort_residential_nodes(residential_names)
        groups.append({
            "name": "[动态·家宽] 🇺🇸 美国住宅智能主备",
            "type": "fallback",
            "strategy": "纯净住宅IP主备容灾",
            "country_code": "US",
            "country_flag": "🇺🇸",
            "node_count": len(sorted_res),
            "proxies": sorted_res,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50
        })

    # 3. 全网全局兜底容灾组
    if pass_through_names:
        groups.append({
            "name": "[动态·全局] 🌐 全网故障转移",
            "type": "url-test",
            "strategy": "全网跨区故障转移兜底",
            "country_code": "ALL",
            "country_flag": "🌐",
            "node_count": len(pass_through_names),
            "proxies": list(pass_through_names),
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 100
        })

    return groups


def extract_source_groups(raw_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按供应商（根据节点前缀 [XX]）聚合生成供应商专属策略组。
    """
    import re
    by_source: Dict[str, List[str]] = {}
    for item in raw_nodes:
        name = item.get("display_name") or item.get("name")
        if not name:
            continue
        m = re.match(r'^\[([A-Za-z0-9]+)\]', name)
        code = m.group(1).upper() if m else "OTHER"
        by_source.setdefault(code, []).append(name)

    source_groups = []
    for code, n_names in by_source.items():
        if not n_names:
            continue
        if code == "RE":
            s_name = "[源·RE] 🇺🇸 RESIP 美国家宽专区"
            s_type = "fallback"
            s_flag = "🇺🇸"
            n_names = sort_residential_nodes(n_names)
        elif code == "SD":
            s_name = "[源·SD] 🌐 SDK 机场全节点专区"
            s_type = "url-test"
            s_flag = "🌐"
        else:
            s_name = f"[源·{code}] 🌐 供应商 {code} 专区"
            s_type = "url-test"
            s_flag = "🌐"
        
        source_groups.append({
            "name": s_name,
            "type": s_type,
            "country_flag": s_flag,
            "proxies": n_names,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50
        })
    return source_groups


def build_clash_config(
    raw_nodes: List[Dict[str, Any]],
    mixed_port: int = 7897,
    terminal_port: int = 7898,
    custom_direct_domains: List[str] = None,
    custom_nameserver_policy: Dict[str, Any] = None
) -> str:
    """
    Builds a clean, production-grade Mihomo / ClashMeta YAML configuration with:
    - Primary mixed port (default 7897) for general traffic & TUN bound to [{mixed_port}] 主出站
    - Secondary listeners mixed port (default 7898) directly bound to [{terminal_port}] 副出站 (px-7898)
    - Full four-layer pyramid hierarchy (Dual Ports -> Source Groups -> Dynamic Regions -> Physical Nodes)
    - 100% decoupled from personal/corporate domains with dynamic rule injection.
    """
    main_group_name = f"[{mixed_port}] 主出站"
    terminal_group_name = f"[{terminal_port}] 副出站"

    if not raw_nodes:
        dummy_node = {"name": "DIRECT", "type": "direct"}
        config = {
            "mixed-port": mixed_port,
            "allow-lan": True,
            "mode": "rule",
            "log-level": "info",
            "proxies": [dummy_node],
            "proxy-groups": [
                {"name": main_group_name, "type": "select", "proxies": ["DIRECT"]},
                {"name": terminal_group_name, "type": "select", "proxies": ["DIRECT"]}
            ],
            "rules": [f"MATCH,{main_group_name}"]
        }
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    proxies_list: List[Dict[str, Any]] = []
    pass_through_names: List[str] = []

    for item in raw_nodes:
        if "config_json" in item and isinstance(item["config_json"], dict):
            node_cfg = copy.deepcopy(item["config_json"])
        else:
            node_cfg = copy.deepcopy(item)
            # Remove helper metadata keys if any
            for k in ["display_name", "country_code", "country_flag", "is_residential"]:
                node_cfg.pop(k, None)

        display_name = item.get("display_name") or item.get("name")
        if not display_name:
            continue
        node_cfg["name"] = display_name
        proxies_list.append(node_cfg)
        pass_through_names.append(display_name)

    # 1. 地区低延迟智能动态组
    dyn_groups = extract_dynamic_groups(raw_nodes)
    dyn_names = [g["name"] for g in dyn_groups]

    # 2. 供应商专区组
    src_groups = extract_source_groups(raw_nodes)
    src_names = [g["name"] for g in src_groups]

    # 格式化所有辅助策略组
    sub_groups = []
    for g in [*src_groups, *dyn_groups]:
        grp = {
            "name": g["name"],
            "type": g["type"],
            "proxies": g["proxies"],
            "url": g["url"],
            "interval": g["interval"],
        }
        if "tolerance" in g:
            grp["tolerance"] = g["tolerance"]
        sub_groups.append(grp)

    # 默认预选探测：主出站默认优先家宽；副出站默认优先日区
    res_group_name = next((g["name"] for g in dyn_groups if "家宽" in g["name"]), None)
    jp_group_name = next((g["name"] for g in dyn_groups if g.get("country_code") == "JP"), None)

    # 构建主出站候选列表（美国家宽智能主备置顶）
    main_proxies = []
    if res_group_name:
        main_proxies.append(res_group_name)
    for name in [*src_names, *dyn_names, *pass_through_names]:
        if name not in main_proxies:
            main_proxies.append(name)

    main_selector = {
        "name": main_group_name,
        "type": "select",
        "proxies": main_proxies or ["DIRECT"]
    }

    # 构建副出站候选列表（日本最佳低延迟置顶）
    terminal_proxies = []
    if jp_group_name:
        terminal_proxies.append(jp_group_name)
    for name in [*src_names, *dyn_names, *pass_through_names]:
        if name not in terminal_proxies:
            terminal_proxies.append(name)

    terminal_selector = {
        "name": terminal_group_name,
        "type": "select",
        "proxies": terminal_proxies or ["DIRECT"]
    }

    full_groups = [main_selector, terminal_selector, *sub_groups]

    # 构造双端口监听器
    listeners = [
        {
            "name": f"terminal-port-{terminal_port}",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": terminal_port,
            "udp": False,
            "proxy": terminal_group_name
        }
    ]

    # 动态组装 DNS
    dns_cfg = copy.deepcopy(DEFAULT_DNS_CONFIG)
    if custom_direct_domains:
        for dom in custom_direct_domains:
            dom = dom.strip()
            if dom:
                dns_cfg["fake-ip-filter"].extend([f"*.{dom}", dom])

    if custom_nameserver_policy:
        dns_cfg["nameserver-policy"].update(custom_nameserver_policy)

    # 动态组装 Rules
    rules = []
    if custom_direct_domains:
        for dom in custom_direct_domains:
            dom = dom.strip()
            if dom:
                rules.append(f"DOMAIN-SUFFIX,{dom},DIRECT")

    for r in DEFAULT_RULES:
        rules.append(r.replace("__MAIN_PROXY__", main_group_name))

    config = {
        "mixed-port": mixed_port,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "strict",
        "profile": {"store-selected": True},
        "sniffer": DEFAULT_SNIFFER_CONFIG,
        "listeners": listeners,
        "dns": dns_cfg,
        "proxies": proxies_list,
        "proxy-groups": full_groups,
        "rules": rules
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

    # 动态组 (使用统一的 extract_dynamic_groups)
    dyn_groups = extract_dynamic_groups(raw_nodes)
    group_outbounds: List[Dict[str, Any]] = []
    dyn_tags: List[str] = []

    for g in dyn_groups:
        dyn_tags.append(g["name"])
        group_outbounds.append({
            "type": "urltest",
            "tag": g["name"],
            "outbounds": g["proxies"],
            "url": g["url"],
            "interval": "5m"
        })

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
