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
        "geosite:cn": ["223.5.5.5", "119.29.29.29"],
        "+.hosecloud.com": ["223.5.5.5", "119.29.29.29"],
        "+.ekuaibao.com": ["223.5.5.5", "119.29.29.29"]
    },
    "fake-ip-filter": [
        "*.lan", "*.local", "*.localhost", "*.test",
        "+.stun.*", "+.msftncsi.com", "+.msftconnecttest.com",
        "*.ying-qing.cn", "ying-qing.cn"
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
    # 5. 个人域名与内网服务直连
    "DOMAIN-SUFFIX,ying-qing.cn,DIRECT",
    # 6. 常用邮件端口直连 (防代理拦截或账号风控)
    "DST-PORT,25,DIRECT",
    "DST-PORT,465,DIRECT",
    "DST-PORT,587,DIRECT",
    "DST-PORT,110,DIRECT",
    "DST-PORT,143,DIRECT",
    "DST-PORT,993,DIRECT",
    "DST-PORT,995,DIRECT",
    # 7. 重点 AI 域名与风控服务精准走 PROXY 主选择器
    "DOMAIN-SUFFIX,anthropic.com,PROXY",
    "DOMAIN-SUFFIX,claude.ai,PROXY",
    "DOMAIN-SUFFIX,claude.com,PROXY",
    "DOMAIN-SUFFIX,claudeusercontent.com,PROXY",
    "DOMAIN-SUFFIX,statsigapi.net,PROXY",
    "IP-CIDR,160.79.104.0/21,PROXY,no-resolve",
    "DOMAIN-SUFFIX,openai.com,PROXY",
    "DOMAIN-SUFFIX,chatgpt.com,PROXY",
    "DOMAIN-SUFFIX,oaistatic.com,PROXY",
    "DOMAIN-SUFFIX,oaiusercontent.com,PROXY",
    "DOMAIN-SUFFIX,arkoselabs.com,PROXY",
    "DOMAIN-KEYWORD,arkose,PROXY",
    "DOMAIN,challenges.cloudflare.com,PROXY",
    "DOMAIN-SUFFIX,statsig.com,PROXY",
    "DOMAIN-SUFFIX,featuregates.org,PROXY",
    "DOMAIN-SUFFIX,gemini.google.com,PROXY",
    "DOMAIN-SUFFIX,x.ai,PROXY",
    "DOMAIN-SUFFIX,grok.com,PROXY",
    "DOMAIN-SUFFIX,perplexity.ai,PROXY",
    # 8. IP 与 DNS 泄露检测站点
    "DOMAIN-SUFFIX,browserleaks.com,PROXY",
    "DOMAIN-SUFFIX,ipleak.net,PROXY",
    "DOMAIN-SUFFIX,dnsleaktest.com,PROXY",
    # 9. 中国大陆网站与 IP 直连
    "GEOSITE,cn,DIRECT",
    "GEOIP,CN,DIRECT",
    # 10. 全局兜底
    "MATCH,PROXY"
]

DYNAMIC_REGIONS = [
    ("HK", "🇭🇰", "港区", "香港最佳低延迟"),
    ("JP", "🇯🇵", "日区", "日本最佳低延迟"),
    ("SG", "🇸🇬", "狮城", "新加坡最佳低延迟"),
    ("TW", "🇹🇼", "台区", "台湾最佳低延迟"),
    ("US", "🇺🇸", "美区", "美国最佳低延迟"),
    ("KR", "🇰🇷", "韩区", "韩国最佳低延迟"),
    ("GB", "🇬🇧", "英区", "英国最佳低延迟"),
    ("DE", "🇩🇪", "德区", "德国最佳低延迟"),
]


def extract_dynamic_groups(raw_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据接入的可用物理节点，自动计算带边界的聚合动态策略组 (URL-Test / Fallback)。
    既用于下发配置文件生成，也用于提供给 Web 仪表盘清晰展示。
    """
    if not raw_nodes:
        return []

    pass_through_names = [item.get("display_name") for item in raw_nodes if item.get("display_name")]
    by_country: Dict[str, List[str]] = {}
    residential_names: List[str] = []

    for item in raw_nodes:
        name = item.get("display_name")
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
        groups.append({
            "name": "[动态·家宽] 🇺🇸 美国住宅智能主备",
            "type": "fallback",
            "strategy": "纯净住宅IP主备容灾",
            "country_code": "US",
            "country_flag": "🇺🇸",
            "node_count": len(residential_names),
            "proxies": list(residential_names),
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


def build_clash_config(
    raw_nodes: List[Dict[str, Any]],
    mixed_port: int = 7897,
    terminal_port: int = 7898
) -> str:
    """
    Builds a clean, production-grade Mihomo / ClashMeta YAML configuration with:
    - Primary mixed port (default 7897) for general traffic & TUN
    - Secondary listeners mixed port (default 7898) directly bound to '终端-日本' fallback group for terminal traffic (px-7898)
    - Full DNS fallback, pure-IP sniffer, anti-leak rules and single-selector PROXY control.
    """
    if not raw_nodes:
        dummy_node = {"name": "DIRECT", "type": "direct"}
        config = {
            "mixed-port": mixed_port,
            "allow-lan": True,
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

    for item in raw_nodes:
        node_cfg = copy.deepcopy(item.get("config_json", {}))
        display_name = item.get("display_name")
        node_cfg["name"] = display_name
        proxies_list.append(node_cfg)
        pass_through_names.append(display_name)
        if (item.get("country_code") or "").upper() == "JP":
            japan_node_names.append(display_name)

    dyn_groups = extract_dynamic_groups(raw_nodes)
    dynamic_options = [g["name"] for g in dyn_groups]
    proxy_groups = []
    for g in dyn_groups:
        grp = {
            "name": g["name"],
            "type": g["type"],
            "proxies": g["proxies"],
            "url": g["url"],
            "interval": g["interval"],
        }
        if "tolerance" in g:
            grp["tolerance"] = g["tolerance"]
        proxy_groups.append(grp)

    # 构造双端口机制专用的【终端-日本】策略组 (fallback)
    # 优先日本最佳低延迟动态组，备选平铺所有日本物理节点；若无日本节点则优雅回退 PROXY
    jp_dyn_group = next((g["name"] for g in dyn_groups if g.get("country_code") == "JP"), None)
    terminal_jp_proxies = []
    if jp_dyn_group:
        terminal_jp_proxies.append(jp_dyn_group)
    for jn in japan_node_names:
        if jn not in terminal_jp_proxies:
            terminal_jp_proxies.append(jn)
    if not terminal_jp_proxies:
        terminal_jp_proxies = ["PROXY"]

    terminal_group = {
        "name": "终端-日本",
        "type": "select",
        "proxies": terminal_jp_proxies
    }

    # 主选择器 PROXY: 终端-日本组 + 动态策略组置顶 + 全部透传节点平铺
    main_selector_proxies = ["终端-日本", *dynamic_options, *pass_through_names]
    main_selector = {
        "name": "PROXY",
        "type": "select",
        "proxies": main_selector_proxies
    }

    full_groups = [main_selector, terminal_group, *proxy_groups]

    listeners = [
        {
            "name": f"terminal-jp-{terminal_port}",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": terminal_port,
            "udp": False,
            "proxy": "终端-日本"
        }
    ]

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
