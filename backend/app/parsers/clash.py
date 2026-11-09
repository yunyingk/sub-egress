from typing import Any, Dict, List, Tuple
import re
import yaml

AD_KEYWORDS = [
    "剩余流量", "流量", "重置", "套餐到期", "到期", "官网", "最新地址",
    "获取最新", "注意:", "通知", "TG群", "频道", "不推荐", "expire",
    "traffic", "reset", "website", "telegram", "notice", "info"
]

COUNTRY_PATTERNS: List[Tuple[str, str, str]] = [
    ("🇭🇰", "HK", r"香港|hongkong|hk"),
    ("🇯🇵", "JP", r"日本|japan|jp|tokyo|osaka"),
    ("🇹🇼", "TW", r"台湾|taiwan|tw|taipei"),
    ("🇸🇬", "SG", r"新加坡|singapore|sg"),
    ("🇺🇸", "US", r"美国|united states|usa|us|america|los angeles|new york"),
    ("🇰🇷", "KR", r"韩国|korea|kr|seoul"),
    ("🇬🇧", "GB", r"英国|united kingdom|uk|london"),
    ("🇩🇪", "DE", r"德国|germany|de|frankfurt"),
    ("🇫🇷", "FR", r"法国|france|fr|paris"),
    ("🇨🇦", "CA", r"加拿大|canada|ca"),
    ("🇦🇺", "AU", r"澳大利亚|australia|au|sydney"),
    ("🇷🇺", "RU", r"俄罗斯|russia|ru|moscow"),
    ("🇹🇷", "TR", r"土耳其|turkey|tr"),
    ("🇪🇸", "ES", r"西班牙|spain|es"),
    ("🇮🇹", "IT", r"意大利|italy|it"),
    ("🇲🇾", "MY", r"马来西亚|malaysia|my"),
    ("🇻🇳", "VN", r"越南|vietnam|vn"),
    ("🇵🇭", "PH", r"菲律宾|philippines|ph"),
    ("🇮🇩", "ID", r"印尼|indonesia|id"),
    ("🇹🇭", "TH", r"泰国|thailand|th"),
    ("🇮🇳", "IN", r"印度|india|in"),
    ("🇦🇪", "AE", r"迪拜|阿联酋|uae|dubai"),
    ("🇳🇬", "NG", r"尼日利亚|nigeria|ng"),
    ("🇧🇷", "BR", r"巴西|brazil|br"),
    ("🇦🇷", "AR", r"阿根廷|argentina|ar"),
    ("🇲🇽", "MX", r"墨西哥|mexico|mx"),
]

def is_ad_node(name: str) -> bool:
    if not name:
        return True
    lower = name.lower()
    return any(k.lower() in lower for k in AD_KEYWORDS)

def detect_country(name: str) -> Tuple[str, str]:
    if not name:
        return "🌐", "OTHER"
    for flag, code, pattern in COUNTRY_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE) or flag in name:
            return flag, code
    return "🌐", "OTHER"

def is_residential_node(name: str, proxy: Dict[str, Any]) -> bool:
    lower_name = (name or "").lower()
    if any(k in lower_name for k in ["家宽", "住宅", "residential", "resip", "rcn", "grande"]):
        return True
    server = str(proxy.get("server", "")).lower()
    if "vimovox" in server or "resip" in server:
        return True
    return False

def extract_subscription_extra_info(text: str) -> Dict[str, Any]:
    """
    Extract extra metadata embedded by airports (e.g. pseudo-node comments)
    such as reset countdown and remaining traffic.
    """
    info: Dict[str, Any] = {}
    if not text:
        return info
    
    # Check reset countdown: e.g. "距离下次重置剩余：29 天" or "下次重置: 29天"
    m_reset = re.search(r"重置[^\d\n]*(\d+)\s*天", text)
    if m_reset:
        info["reset_info"] = f"{m_reset.group(1)} 天后重置"
        
    # Check remaining traffic: e.g. "剩余流量：150 GB"
    m_remain = re.search(r"剩余流量[：:]\s*([\d\.]+\s*[GMK]B)", text, re.IGNORECASE)
    if m_remain:
        info["remaining_text"] = m_remain.group(1).strip()
        
    return info

def parse_clash_yaml(content: str) -> List[Dict[str, Any]]:
    try:
        data = yaml.safe_load(content)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    
    raw_proxies = data.get("proxies", [])
    if not isinstance(raw_proxies, list):
        return []
    
    result = []
    for item in raw_proxies:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or is_ad_node(name):
            continue
        if "type" not in item or "server" not in item or "port" not in item:
            continue
        result.append(item)
    return result
