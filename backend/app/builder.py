import base64
import copy
import json
import re
import urllib.parse
from typing import Any

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

PREMIUM_GROUP_NAME = "精选高级"
DYNAMIC_PREMIUM_GROUP_NAME = "[动态·精选高级] ⭐ 精选高级主备"
DYNAMIC_GLOBAL_GROUP_NAME = "[动态·全局] 🌐 日常全网优选"

DEFAULT_AI_PROXY_DOMAINS = (
    "anthropic.com",
    "claude.ai",
    "claude.com",
    "claudeusercontent.com",
    "statsigapi.net",
    "openai.com",
    "chatgpt.com",
    "oaistatic.com",
    "oaiusercontent.com",
    "arkoselabs.com",
    "statsig.com",
    "featuregates.org",
    "x.ai",
    "grok.com",
    "perplexity.ai",
    "gemini.google.com",
    "aistudio.google.com",
    "ai.google.dev",
    "generativelanguage.googleapis.com",
    "makersuite.google.com",
    "alkalimakersuite-pa.clients6.google.com",
    "deepmind.com",
    "deepmind.google",
    "notebooklm.google.com",
    "notebooklm.google",
    "labs.google",
    "cursor.sh",
    "cursor.com",
    "cursorapi.com",
    "copilot.github.com",
    "api.githubcopilot.com",
    "windsurf.com",
    "codeium.com",
)
DEFAULT_AI_EXACT_DOMAINS = ("challenges.cloudflare.com",)
DEFAULT_AI_DOMAIN_KEYWORDS = ("arkose",)
DEFAULT_AI_IP_CIDRS = ("160.79.104.0/21",)

DEFAULT_GOOGLE_PROXY_DOMAINS = (
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
    "gvt1.com",
    "gvt2.com",
    "withgoogle.com",
    "ggpht.com",
    "google",
    "g.co",
    "goo.gl",
)

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
    # 6. 重点 AI 与高风控域名精准走精选高级组
    *[f"DOMAIN-SUFFIX,{domain},__PREMIUM_PROXY__" for domain in DEFAULT_AI_PROXY_DOMAINS],
    *[f"DOMAIN,{domain},__PREMIUM_PROXY__" for domain in DEFAULT_AI_EXACT_DOMAINS],
    *[f"DOMAIN-KEYWORD,{kw},__PREMIUM_PROXY__" for kw in DEFAULT_AI_DOMAIN_KEYWORDS],
    *[f"IP-CIDR,{cidr},__PREMIUM_PROXY__,no-resolve" for cidr in DEFAULT_AI_IP_CIDRS],
    # 7. Google 常规服务走主出站 (置于 GEOSITE/GEOIP,CN 之前，防止解析到国内节点直连泄露)
    *[f"DOMAIN-SUFFIX,{domain},__MAIN_PROXY__" for domain in DEFAULT_GOOGLE_PROXY_DOMAINS],
    # 8. IP 与 DNS 泄露检测站点
    "DOMAIN-SUFFIX,browserleaks.com,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,ipleak.net,__MAIN_PROXY__",
    "DOMAIN-SUFFIX,dnsleaktest.com,__MAIN_PROXY__",
    # 9. 中国大陆网站与 IP 直连
    "GEOSITE,cn,DIRECT",
    "GEOIP,CN,DIRECT",
    # 10. 全局兜底
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


def sort_residential_nodes(names: list[str]) -> list[str]:
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


def _is_premium_node(item: dict[str, Any]) -> bool:
    tier = item.get("source_tier")
    if tier is not None:
        return tier == "premium"
    return bool(item.get("is_residential"))


def _dedupe_names(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in items:
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def extract_dynamic_groups(raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    根据接入的可用物理节点，自动计算带边界的聚合动态策略组 (URL-Test / Fallback)。
    普通日常组与精选高级组严格隔离，既用于下发配置生成，也用于 Web 仪表盘展示。
    """
    if not raw_nodes:
        return []

    by_country: dict[str, list[str]] = {}
    standard_names: list[str] = []
    premium_names: list[str] = []

    for item in raw_nodes:
        name = item.get("display_name") or item.get("name")
        if not name:
            continue
        if _is_premium_node(item):
            premium_names.append(name)
        else:
            cc = (item.get("country_code") or "OTHER").upper()
            by_country.setdefault(cc, []).append(name)
            standard_names.append(name)

    groups = []

    # 1. 重点地区同国巡检低延迟动态组 (仅纳入普通日常节点，绝不混入精选高级)
    for code, flag, short_name, desc in DYNAMIC_REGIONS:
        node_names = by_country.get(code, [])
        if node_names:
            groups.append({
                "name": f"[动态·{short_name}] {flag} {desc}",
                "type": "url-test",
                "strategy": "同国低延迟自动优选",
                "country_code": code,
                "country_flag": flag,
                "is_premium": False,
                "node_count": len(node_names),
                "proxies": list(node_names),
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50
            })

    # 2. 精选高级主备组 (仅纳入显式标记为精选高级的节点)
    if premium_names:
        sorted_res = sort_residential_nodes(premium_names)
        groups.append({
            "name": DYNAMIC_PREMIUM_GROUP_NAME,
            "type": "fallback",
            "strategy": "精选高级节点主备容灾",
            "country_code": "PREMIUM",
            "country_flag": "⭐",
            "is_premium": True,
            "node_count": len(sorted_res),
            "proxies": sorted_res,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50
        })

    # 3. 日常全网全局优选兜底组 (仅纳入普通日常节点)
    if standard_names:
        groups.append({
            "name": DYNAMIC_GLOBAL_GROUP_NAME,
            "type": "url-test",
            "strategy": "日常普通节点全网低延迟优选",
            "country_code": "ALL",
            "country_flag": "🌐",
            "is_premium": False,
            "node_count": len(standard_names),
            "proxies": list(standard_names),
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 100
        })

    return groups


def extract_source_groups(raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    按供应商前缀 [XX] 与节点等级聚合生成供应商专属策略组。
    """
    by_source: dict[tuple[str, bool], list[str]] = {}
    for item in raw_nodes:
        name = item.get("display_name") or item.get("name")
        if not name:
            continue
        m = re.match(r'^\[([A-Za-z0-9]+)\]', name)
        code = m.group(1).upper() if m else "OTHER"
        by_source.setdefault((code, _is_premium_node(item)), []).append(name)

    source_groups = []
    for (code, is_prem), n_names in by_source.items():
        if not n_names:
            continue
        if is_prem:
            s_name = f"[源·{code}] ⭐ {code} 精选高级专区"
            s_type = "fallback"
            s_flag = "⭐"
            n_names = sort_residential_nodes(n_names)
        else:
            s_name = f"[源·{code}] 🌐 供应商 {code} 专区"
            s_type = "url-test"
            s_flag = "🌐"

        source_groups.append({
            "name": s_name,
            "type": s_type,
            "country_flag": s_flag,
            "is_premium": is_prem,
            "proxies": n_names,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50
        })
    return source_groups


def build_clash_config(
    raw_nodes: list[dict[str, Any]],
    mixed_port: int = 7897,
    terminal_port: int = 7898,
    custom_direct_domains: list[str] = None,
    custom_proxy_domains: list[str] = None,
    custom_rules: list[str] = None,
    custom_nameserver_policy: dict[str, Any] = None,
    custom_premium_domains: list[str] = None,
) -> str:
    """
    Builds a clean, production-grade Mihomo / ClashMeta YAML configuration with:
    - Primary mixed port (default 7897) for general traffic & TUN bound to [{mixed_port}] 主出站 (standard nodes)
    - Dedicated 精选高级 selector for AI & high-risk domains (premium nodes)
    - Secondary listeners mixed port (default 7898) directly bound to [{terminal_port}] 副出站 (standard nodes)
    - Explicit GLOBAL selector defaulting to [{mixed_port}] 主出站 to avoid accidental premium burn in global mode
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
                {"name": PREMIUM_GROUP_NAME, "type": "select", "proxies": [main_group_name, "DIRECT"]},
                {"name": terminal_group_name, "type": "select", "proxies": ["DIRECT"]},
                {"name": "GLOBAL", "type": "select", "proxies": [main_group_name, PREMIUM_GROUP_NAME, terminal_group_name, "DIRECT"]},
            ],
            "rules": [f"MATCH,{main_group_name}"]
        }
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    proxies_list: list[dict[str, Any]] = []
    standard_names: list[str] = []
    premium_names: list[str] = []

    for item in raw_nodes:
        if "config_json" in item and isinstance(item["config_json"], dict):
            node_cfg = copy.deepcopy(item["config_json"])
        else:
            node_cfg = copy.deepcopy(item)
            # Remove helper metadata keys if any
            for k in ["display_name", "country_code", "country_flag", "is_residential", "source_name", "source_tier"]:
                node_cfg.pop(k, None)

        display_name = item.get("display_name") or item.get("name")
        if not display_name:
            continue
        node_cfg["name"] = display_name
        proxies_list.append(node_cfg)
        if _is_premium_node(item):
            premium_names.append(display_name)
        else:
            standard_names.append(display_name)

    # 1. 地区低延迟智能动态组与精选高级主备组
    dyn_groups = extract_dynamic_groups(raw_nodes)
    standard_dyn_names = [g["name"] for g in dyn_groups if not g.get("is_premium")]
    premium_dyn_names = [g["name"] for g in dyn_groups if g.get("is_premium")]

    # 2. 供应商专区组
    src_groups = extract_source_groups(raw_nodes)
    standard_src_names = [g["name"] for g in src_groups if not g.get("is_premium")]
    premium_src_names = [g["name"] for g in src_groups if g.get("is_premium")]

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

    jp_group_name = next((g["name"] for g in dyn_groups if not g.get("is_premium") and g.get("country_code") == "JP"), None)

    # 构建主出站候选列表（仅普通节点；极端情况全为高级节点时才兜底）
    if standard_names:
        main_proxies = _dedupe_names([
            *([DYNAMIC_GLOBAL_GROUP_NAME] if DYNAMIC_GLOBAL_GROUP_NAME in standard_dyn_names else []),
            *standard_src_names,
            *standard_dyn_names,
            *standard_names,
        ])
    else:
        main_proxies = _dedupe_names([
            *([DYNAMIC_PREMIUM_GROUP_NAME] if DYNAMIC_PREMIUM_GROUP_NAME in premium_dyn_names else []),
            *premium_src_names,
            *premium_dyn_names,
            *premium_names,
        ])

    main_selector = {
        "name": main_group_name,
        "type": "select",
        "proxies": main_proxies or ["DIRECT"]
    }

    # 构建精选高级出站（有高级节点则默认选中高级主备，末尾附主出站用于手动应急；无高级节点则指向主出站）
    if premium_names:
        premium_proxies = _dedupe_names([
            *premium_dyn_names,
            *premium_src_names,
            *premium_names,
            main_group_name,
        ])
    else:
        premium_proxies = _dedupe_names([
            main_group_name,
            *standard_dyn_names,
            *standard_src_names,
            *standard_names,
        ])

    premium_selector = {
        "name": PREMIUM_GROUP_NAME,
        "type": "select",
        "proxies": premium_proxies or ["DIRECT"]
    }

    # 构建副出站候选列表（单一出口，日本普通低延迟置顶，严格排除高级节点）
    if standard_names:
        terminal_proxies = _dedupe_names([
            *([jp_group_name] if jp_group_name else []),
            *standard_src_names,
            *standard_dyn_names,
            *standard_names,
        ])
    else:
        terminal_proxies = _dedupe_names([
            *premium_src_names,
            *premium_dyn_names,
            *premium_names,
        ])

    terminal_selector = {
        "name": terminal_group_name,
        "type": "select",
        "proxies": terminal_proxies or ["DIRECT"]
    }

    # 显式 GLOBAL 组：全局模式默认落到主出站（便宜节点），避免误烧高级流量
    global_selector = {
        "name": "GLOBAL",
        "type": "select",
        "proxies": _dedupe_names([
            main_group_name,
            PREMIUM_GROUP_NAME,
            terminal_group_name,
            *standard_dyn_names,
            *standard_src_names,
            "DIRECT",
        ])
    }

    full_groups = [main_selector, premium_selector, terminal_selector, global_selector, *sub_groups]

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

    def _expand_rule_targets(rule_text: str) -> str:
        return (
            rule_text
            .replace("__MAIN_PROXY__", main_group_name)
            .replace("__PREMIUM_PROXY__", PREMIUM_GROUP_NAME)
            .replace("__AI_PROXY__", PREMIUM_GROUP_NAME)
        )

    # 动态组装 Rules
    rules = []
    # 1. 用户级/全局直连域名规则 (优先级最高，置顶免代理且免 fake-ip 劫持)
    if custom_direct_domains:
        for dom in custom_direct_domains:
            dom = dom.strip()
            if dom:
                rules.append(f"DOMAIN-SUFFIX,{dom},DIRECT")

    # 2. 用户级/全局强制走主代理域名规则（可覆盖内置规则回退至便宜节点）
    if custom_proxy_domains:
        for dom in custom_proxy_domains:
            dom = dom.strip()
            if dom:
                rules.append(f"DOMAIN-SUFFIX,{dom},{main_group_name}")

    # 3. 管理员/全局精选高级域名规则
    if custom_premium_domains:
        for dom in custom_premium_domains:
            dom = dom.strip()
            if dom:
                rules.append(f"DOMAIN-SUFFIX,{dom},{PREMIUM_GROUP_NAME}")

    # 4. 用户级/管理员自定义分流规则注入
    if custom_rules:
        for r in custom_rules:
            r = r.strip()
            if r and not r.startswith("#"):
                rules.append(_expand_rule_targets(r))

    for r in DEFAULT_RULES:
        rules.append(_expand_rule_targets(r))

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


def build_singbox_config(
    raw_nodes: list[dict[str, Any]],
    custom_direct_domains: list[str] = None,
    custom_proxy_domains: list[str] = None,
    custom_rules: list[str] = None,
    custom_premium_domains: list[str] = None,
) -> str:
    """
    Builds a complete, modern Sing-box JSON configuration with PROXY & PREMIUM separation.
    """
    outbounds: list[dict[str, Any]] = []
    standard_tags: list[str] = []
    premium_tags: list[str] = []
    supported_nodes: list[dict[str, Any]] = []

    for item in raw_nodes:
        config = item.get("config_json")
        s = copy.deepcopy(config if isinstance(config, dict) else item)
        tag = item.get("display_name")
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
            # Official sing-box has no XHTTP transport; exclude it rather than emit an invalid outbound.
            if s.get("network") in ("xhttp", "splithttp"):
                continue
            outbound = {
                "type": "vless",
                "tag": tag,
                "server": s.get("server"),
                "server_port": int(s.get("port")),
                "uuid": s.get("uuid", ""),
                "flow": s.get("flow") or ""
            }
            if s.get("tls"):
                tls_cfg: dict[str, Any] = {
                    "enabled": True,
                    "server_name": s.get("servername") or s.get("server"),
                    "insecure": bool(s.get("skip-cert-verify", False))
                }
                ropts = s.get("reality-opts")
                if s.get("client-fingerprint") or ropts:
                    tls_cfg["utls"] = {"enabled": True, "fingerprint": s.get("client-fingerprint") or "chrome"}
                if ropts:
                    tls_cfg["reality"] = {
                        "enabled": True,
                        "public_key": ropts.get("public-key", ""),
                        "short_id": ropts.get("short-id", "")
                    }
                outbound["tls"] = tls_cfg
            if s.get("network") and s.get("network") != "tcp":
                outbound["transport"] = {"type": s.get("network")}
        elif ntype == "anytls":
            tls_cfg = {
                "enabled": True,
                "server_name": s.get("sni") or s.get("server"),
                "insecure": bool(s.get("skip-cert-verify", False)),
            }
            if s.get("alpn"):
                tls_cfg["alpn"] = s["alpn"]
            if s.get("client-fingerprint"):
                tls_cfg["utls"] = {"enabled": True, "fingerprint": s["client-fingerprint"]}
            outbound = {
                "type": "anytls", "tag": tag, "server": s.get("server"),
                "server_port": int(s.get("port")), "password": s.get("password", ""), "tls": tls_cfg,
            }
            for clash_key, sing_key in (("idle-session-check-interval", "idle_session_check_interval"), ("idle-session-timeout", "idle_session_timeout"), ("min-idle-session", "min_idle_session")):
                if clash_key in s:
                    outbound[sing_key] = s[clash_key]
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
            supported_nodes.append(item)
            if _is_premium_node(item):
                premium_tags.append(tag)
            else:
                standard_tags.append(tag)

    # 动态组 (使用统一的 extract_dynamic_groups)
    dyn_groups = extract_dynamic_groups(supported_nodes)
    group_outbounds: list[dict[str, Any]] = []
    standard_dyn_tags: list[str] = []
    premium_dyn_tags: list[str] = []

    for g in dyn_groups:
        if g.get("is_premium"):
            premium_dyn_tags.append(g["name"])
        else:
            standard_dyn_tags.append(g["name"])
        group_outbounds.append({
            "type": "urltest",
            "tag": g["name"],
            "outbounds": g["proxies"],
            "url": g["url"],
            "interval": "5m"
        })

    # 主选择器 PROXY（严格仅含普通日常节点；无普通节点时才兜底高级节点）
    if standard_tags:
        proxy_candidates = _dedupe_names([
            *([DYNAMIC_GLOBAL_GROUP_NAME] if DYNAMIC_GLOBAL_GROUP_NAME in standard_dyn_tags else []),
            *standard_dyn_tags,
            *standard_tags,
        ])
    elif premium_tags:
        proxy_candidates = _dedupe_names([*premium_dyn_tags, *premium_tags])
    else:
        proxy_candidates = ["direct"]

    proxy_selector = {
        "type": "selector",
        "tag": "PROXY",
        "outbounds": proxy_candidates,
        "default": proxy_candidates[0]
    }

    # 精选高级选择器 PREMIUM（对齐 Clash 的 精选高级）
    if premium_tags:
        premium_candidates = _dedupe_names([*premium_dyn_tags, *premium_tags, "PROXY"])
    else:
        premium_candidates = ["PROXY"]

    premium_selector = {
        "type": "selector",
        "tag": "PREMIUM",
        "outbounds": premium_candidates,
        "default": premium_candidates[0]
    }

    # 基础出站
    system_outbounds = [{"type": "direct", "tag": "direct"}]
    all_outbounds = [proxy_selector, premium_selector, *group_outbounds, *outbounds, *system_outbounds]

    rule_sets: dict[str, dict[str, str]] = {}

    def add_rule_set(kind: str, value: str) -> str | None:
        name = value.lower()
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            return None
        tag = f"{kind}-{name}"
        rule_sets[tag] = {
            "type": "remote", "tag": tag, "format": "binary",
            "url": f"https://cdn.jsdelivr.net/gh/SagerNet/sing-{kind}@rule-set/{tag}.srs",
            "download_detour": "PROXY",
        }
        return tag

    route_rules: list[dict[str, Any]] = [
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "outbound": "direct"},
    ]
    if custom_direct_domains:
        domains = [domain.strip() for domain in custom_direct_domains if domain.strip()]
        if domains:
            route_rules.append({"domain_suffix": domains, "outbound": "direct"})
    if custom_proxy_domains:
        domains = [domain.strip() for domain in custom_proxy_domains if domain.strip()]
        if domains:
            route_rules.append({"domain_suffix": domains, "outbound": "PROXY"})
    if custom_premium_domains:
        domains = [domain.strip() for domain in custom_premium_domains if domain.strip()]
        if domains:
            route_rules.append({"domain_suffix": domains, "outbound": "PREMIUM"})
    type_map = {"DOMAIN": "domain", "DOMAIN-SUFFIX": "domain_suffix", "DOMAIN-KEYWORD": "domain_keyword", "IP-CIDR": "ip_cidr", "IP-CIDR6": "ip_cidr", "GEOIP": "rule_set", "GEOSITE": "rule_set"}
    target_map = {
        "DIRECT": "direct",
        "PROXY": "PROXY",
        "__MAIN_PROXY__": "PROXY",
        "PREMIUM": "PREMIUM",
        "__PREMIUM_PROXY__": "PREMIUM",
        "__AI_PROXY__": "PREMIUM",
        PREMIUM_GROUP_NAME: "PREMIUM",
    }
    for raw_rule in custom_rules or []:
        parts = [part.strip() for part in raw_rule.split(",")]
        if len(parts) < 3 or parts[0].upper() not in type_map:
            continue
        rule_type, value, target = parts[0].upper(), parts[1], parts[2]
        if rule_type in ("GEOIP", "GEOSITE"):
            if rule_type == "GEOIP" and value.lower() == "private":
                match = {"ip_is_private": True}
            else:
                tag = add_rule_set(rule_type.lower(), value)
                if not tag:
                    continue
                match = {"rule_set": [tag]}
        else:
            match = {type_map[rule_type]: [value]}
        target_key = target.upper()
        if target_key == "REJECT":
            match["action"] = "reject"
        else:
            match["outbound"] = target_map.get(target_key, target_map.get(target, target))
        route_rules.append(match)

    route_rules.extend([
        {"domain_suffix": list(DEFAULT_AI_PROXY_DOMAINS), "outbound": "PREMIUM"},
        {"domain": list(DEFAULT_AI_EXACT_DOMAINS), "outbound": "PREMIUM"},
        {"domain_keyword": list(DEFAULT_AI_DOMAIN_KEYWORDS), "outbound": "PREMIUM"},
        {"ip_cidr": list(DEFAULT_AI_IP_CIDRS), "outbound": "PREMIUM"},
        {"domain_suffix": list(DEFAULT_GOOGLE_PROXY_DOMAINS), "outbound": "PROXY"},
    ])

    geoip_cn = add_rule_set("geoip", "cn")
    geosite_cn = add_rule_set("geosite", "cn")
    route_rules.extend([
        {"rule_set": [geoip_cn], "outbound": "direct"},
        {"rule_set": [geosite_cn], "outbound": "direct"},
    ])

    singbox_config = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [{"type": "udp", "tag": "dns-direct", "server": "223.5.5.5"}],
            "final": "dns-direct",
        },
        "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 7890}],
        "outbounds": all_outbounds,
        "route": {
            "rules": route_rules,
            "rule_set": list(rule_sets.values()),
            "auto_detect_interface": True,
            "default_domain_resolver": "dns-direct",
            "final": "PROXY",
        },
        "experimental": {"cache_file": {"enabled": True}},
    }

    return json.dumps(singbox_config, ensure_ascii=False, indent=2)


def build_base64_config(raw_nodes: list[dict[str, Any]]) -> str:
    """
    Builds a standard Base64 URI subscription containing all valid node links.
    """
    uris: list[str] = []
    for item in raw_nodes:
        config = item.get("config_json")
        s = config if isinstance(config, dict) else item
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
            if s.get("network") in ("xhttp", "splithttp"):
                continue
            sec = "reality" if s.get("reality-opts") else ("tls" if s.get("tls") else "none")
            uris.append(f"vless://{s.get('uuid')}@{s.get('server')}:{s.get('port')}?security={sec}&sni={s.get('servername') or s.get('server')}#{tag_encoded}")
        elif ntype == "anytls":
            server = str(s.get("server", ""))
            host = f"[{server}]" if ":" in server and not server.startswith("[") else server
            password = urllib.parse.quote(str(s.get("password", "")), safe="")
            params = {}
            if s.get("sni"):
                params["sni"] = s["sni"]
            if s.get("skip-cert-verify"):
                params["insecure"] = "1"
            # fp and alpn are widely used extensions to the AnyTLS base URI.
            if s.get("client-fingerprint"):
                params["fp"] = s["client-fingerprint"]
            if s.get("alpn"):
                params["alpn"] = ",".join(s["alpn"])
            query = urllib.parse.urlencode(params)
            uris.append(f"anytls://{password}@{host}:{s.get('port')}/?{query}#{tag_encoded}")
        elif ntype in ("hysteria2", "hy2"):
            uris.append(f"hy2://{s.get('password')}@{s.get('server')}:{s.get('port')}?sni={s.get('sni') or s.get('server')}#{tag_encoded}")

    text = "\n".join(uris)
    return base64.b64encode(text.encode()).decode()
