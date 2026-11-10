import base64
import urllib.parse
from typing import Any

from .clash import is_ad_node


def safe_b64decode(s: str) -> str:
    s = s.strip().replace(" ", "").replace("\n", "").replace("\r", "")
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    try:
        return base64.b64decode(s).decode("utf-8", errors="ignore")
    except Exception:
        try:
            return base64.urlsafe_b64decode(s).decode("utf-8", errors="ignore")
        except Exception:
            return ""

def parse_ss(url: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        name = urllib.parse.unquote(parsed.fragment) or "Shadowsocks"
        userinfo = parsed.netloc.split("@")[0] if "@" in parsed.netloc else parsed.netloc
        hostport = parsed.netloc.split("@")[1] if "@" in parsed.netloc else ""
        if not hostport:
            decoded = safe_b64decode(userinfo)
            if "@" in decoded:
                userinfo, hostport = decoded.split("@", 1)
        if ":" in userinfo and not hostport:
            pass
        elif not hostport and "@" in safe_b64decode(parsed.netloc):
            decoded = safe_b64decode(parsed.netloc)
            userinfo, hostport = decoded.split("@", 1)

        server, port_str = hostport.split(":")
        port = int(port_str)
        if ":" in userinfo:
            cipher, password = userinfo.split(":", 1)
        else:
            decoded = safe_b64decode(userinfo)
            cipher, password = decoded.split(":", 1)
        return {
            "name": name,
            "type": "ss",
            "server": server,
            "port": port,
            "cipher": cipher,
            "password": password,
            "udp": True,
        }
    except Exception:
        return None

def parse_vless(url: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        uuid = parsed.username or parsed.netloc.split("@")[0]
        hostport = parsed.netloc.split("@")[-1]
        server, port_str = hostport.split(":")
        port = int(port_str)
        qs = urllib.parse.parse_qs(parsed.query)
        name = urllib.parse.unquote(parsed.fragment) or "VLESS"
        
        flow = qs.get("flow", [None])[0]
        security = qs.get("security", ["none"])[0]
        sni = qs.get("sni", [None])[0] or qs.get("peer", [None])[0]
        net = qs.get("type", ["tcp"])[0]
        pbk = qs.get("pbk", [None])[0]
        sid = qs.get("sid", [None])[0]
        fp = qs.get("fp", ["chrome"])[0]

        proxy: dict[str, Any] = {
            "name": name,
            "type": "vless",
            "server": server,
            "port": port,
            "uuid": uuid,
            "udp": True,
            "network": net,
            "client-fingerprint": fp,
        }
        if flow:
            proxy["flow"] = flow
        if security in ("tls", "reality"):
            proxy["tls"] = True
            if sni:
                proxy["servername"] = sni
            if security == "reality" and pbk:
                proxy["reality-opts"] = {
                    "public-key": pbk,
                    "short-id": sid or "",
                }
        return proxy
    except Exception:
        return None

def parse_trojan(url: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        password = parsed.username or parsed.netloc.split("@")[0]
        hostport = parsed.netloc.split("@")[-1]
        server, port_str = hostport.split(":")
        port = int(port_str)
        qs = urllib.parse.parse_qs(parsed.query)
        name = urllib.parse.unquote(parsed.fragment) or "Trojan"
        sni = qs.get("sni", [None])[0] or qs.get("peer", [None])[0]
        return {
            "name": name,
            "type": "trojan",
            "server": server,
            "port": port,
            "password": password,
            "udp": True,
            "sni": sni or server,
            "skip-cert-verify": True,
        }
    except Exception:
        return None

def parse_hysteria2(url: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        password = parsed.username or parsed.netloc.split("@")[0]
        hostport = parsed.netloc.split("@")[-1]
        server, port_str = hostport.split(":")
        port = int(port_str)
        qs = urllib.parse.parse_qs(parsed.query)
        name = urllib.parse.unquote(parsed.fragment) or "Hysteria2"
        sni = qs.get("sni", [None])[0]
        return {
            "name": name,
            "type": "hysteria2",
            "server": server,
            "port": port,
            "password": password,
            "udp": True,
            "sni": sni or server,
            "skip-cert-verify": True,
        }
    except Exception:
        return None

def parse_anytls(url: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.hostname or not parsed.username:
            return None
        qs = urllib.parse.parse_qs(parsed.query)
        proxy: dict[str, Any] = {
            "name": urllib.parse.unquote(parsed.fragment) or "AnyTLS",
            "type": "anytls", "server": parsed.hostname, "port": parsed.port or 443,
            "password": urllib.parse.unquote(parsed.username), "udp": True,
        }
        if qs.get("sni"):
            proxy["sni"] = qs["sni"][0]
        if qs.get("insecure"):
            proxy["skip-cert-verify"] = qs["insecure"][0].lower() in ("1", "true")
        if qs.get("fp"):
            proxy["client-fingerprint"] = qs["fp"][0]
        if qs.get("alpn"):
            proxy["alpn"] = [value for value in qs["alpn"][0].split(",") if value]
        return proxy
    except (ValueError, TypeError):
        return None


def parse_uri(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith("ss://"):
        return parse_ss(line)
    elif line.startswith("vless://"):
        return parse_vless(line)
    elif line.startswith("trojan://"):
        return parse_trojan(line)
    elif line.startswith("hysteria2://") or line.startswith("hy2://"):
        return parse_hysteria2(line)
    elif line.startswith("anytls://"):
        return parse_anytls(line)
    return None

def parse_subscription_text(text: str) -> list[dict[str, Any]]:
    # Attempt base64 decode if lines look like base64 blob
    decoded = safe_b64decode(text)
    content = decoded if decoded and ("vmess://" in decoded or "vless://" in decoded or "ss://" in decoded or "trojan://" in decoded or "anytls://" in decoded) else text
    
    results = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        p = parse_uri(line)
        if p and not is_ad_node(p.get("name", "")):
            results.append(p)
    return results
