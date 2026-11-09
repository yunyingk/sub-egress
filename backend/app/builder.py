import copy
from typing import Any, Dict, List
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
        # Fallback dummy config so client doesn't crash if node list is empty
        dummy_node = {
            "name": "DIRECT",
            "type": "direct"
        }
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
    
    # 组装完整配置
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
