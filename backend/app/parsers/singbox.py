import json
import logging
from typing import Any

from .clash import is_ad_node

logger = logging.getLogger(__name__)

NON_PROXY_TYPES = {"selector", "urltest", "direct", "block", "dns"}


def parse_singbox_json(content: str) -> list[dict[str, Any]]:
    """解析 Sing-box JSON 格式的订阅配置，提取真实代理节点转为统一样式字典"""
    if not content or not content.strip():
        return []

    text = content.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return []

    try:
        data = json.loads(text)
    except Exception:
        return []

    outbounds: list[dict[str, Any]] = []
    if isinstance(data, dict):
        outbounds = data.get("outbounds", [])
    elif isinstance(data, list):
        outbounds = data

    if not isinstance(outbounds, list):
        return []

    proxies: list[dict[str, Any]] = []
    for ob in outbounds:
        if not isinstance(ob, dict):
            continue
        ob_type = str(ob.get("type", "")).lower()
        if not ob_type or ob_type in NON_PROXY_TYPES:
            continue

        tag = str(ob.get("tag", "")).strip()
        server = str(ob.get("server", "")).strip()
        port = int(ob.get("server_port") or ob.get("port") or 0)
        if not server or not port:
            continue

        if is_ad_node(tag):
            continue

        proxy_dict: dict[str, Any] = {
            "name": tag or f"Node-{server}:{port}",
            "server": server,
            "port": port,
            "udp": True,
        }

        tls_cfg = ob.get("tls", {}) if isinstance(ob.get("tls"), dict) else {}
        tls_enabled = bool(tls_cfg.get("enabled", False))

        transport_cfg = ob.get("transport", {}) if isinstance(ob.get("transport"), dict) else {}
        net_type = transport_cfg.get("type", "tcp")

        if ob_type == "vless":
            proxy_dict["type"] = "vless"
            proxy_dict["uuid"] = str(ob.get("uuid", ""))
            if ob.get("flow"):
                proxy_dict["flow"] = str(ob["flow"])
            if ob.get("packet_encoding"):
                proxy_dict["packet-encoding"] = str(ob["packet_encoding"])

            if net_type and net_type != "tcp":
                proxy_dict["network"] = net_type

            if tls_enabled:
                proxy_dict["tls"] = True
                sni = tls_cfg.get("server_name") or server
                proxy_dict["servername"] = sni
                if tls_cfg.get("insecure"):
                    proxy_dict["skip-cert-verify"] = True

                utls = tls_cfg.get("utls", {})
                if isinstance(utls, dict) and utls.get("fingerprint"):
                    proxy_dict["client-fingerprint"] = utls["fingerprint"]

                reality = tls_cfg.get("reality", {})
                if isinstance(reality, dict) and reality.get("enabled"):
                    proxy_dict["reality-opts"] = {
                        "public-key": reality.get("public_key", ""),
                        "short-id": reality.get("short_id", "")
                    }

        elif ob_type == "vmess":
            proxy_dict["type"] = "vmess"
            proxy_dict["uuid"] = str(ob.get("uuid", ""))
            proxy_dict["alterId"] = int(ob.get("alter_id", 0))
            proxy_dict["cipher"] = str(ob.get("security", "auto"))
            if net_type and net_type != "tcp":
                proxy_dict["network"] = net_type
            if tls_enabled:
                proxy_dict["tls"] = True
                proxy_dict["servername"] = tls_cfg.get("server_name") or server

        elif ob_type in ("shadowsocks", "ss"):
            proxy_dict["type"] = "ss"
            proxy_dict["cipher"] = str(ob.get("method", ""))
            proxy_dict["password"] = str(ob.get("password", ""))

        elif ob_type == "trojan":
            proxy_dict["type"] = "trojan"
            proxy_dict["password"] = str(ob.get("password", ""))
            if tls_enabled:
                proxy_dict["sni"] = tls_cfg.get("server_name") or server
                if tls_cfg.get("insecure"):
                    proxy_dict["skip-cert-verify"] = True

        elif ob_type in ("hysteria2", "hy2"):
            proxy_dict["type"] = "hysteria2"
            proxy_dict["password"] = str(ob.get("password", ""))
            if tls_enabled:
                proxy_dict["sni"] = tls_cfg.get("server_name") or server
                if tls_cfg.get("insecure"):
                    proxy_dict["skip-cert-verify"] = True

        else:
            # 未知或实验性协议暂不处理
            continue

        proxies.append(proxy_dict)

    return proxies
