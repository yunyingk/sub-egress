import json

from app.parsers.singbox import parse_singbox_json


def test_parse_singbox_vless_reality():
    payload = json.dumps({
        "outbounds": [
            {
                "type": "selector",
                "tag": "Proxy",
                "outbounds": ["vless-node"]
            },
            {
                "type": "vless",
                "tag": "美国 Grande&RCN 66.167.9.194 · 主线",
                "server": "p5.vimovox.com",
                "server_port": 443,
                "uuid": "a4e642b8-03ea-4bd8-bcb5-9483bd7e580b",
                "flow": "xtls-rprx-vision",
                "packet_encoding": "xudp",
                "tls": {
                    "enabled": True,
                    "server_name": "swdist.apple.com",
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "reality": {
                        "enabled": True,
                        "public_key": "mynAx1EWuAfqLW2uHPoynhdD19Q0MJFBSTKEGo5MuAk",
                        "short_id": "ab853926"
                    }
                }
            },
            {
                "type": "direct",
                "tag": "direct"
            }
        ]
    })

    nodes = parse_singbox_json(payload)
    assert len(nodes) == 1
    node = nodes[0]
    assert node["name"] == "美国 Grande&RCN 66.167.9.194 · 主线"
    assert node["type"] == "vless"
    assert node["server"] == "p5.vimovox.com"
    assert node["port"] == 443
    assert node["uuid"] == "a4e642b8-03ea-4bd8-bcb5-9483bd7e580b"
    assert node["flow"] == "xtls-rprx-vision"
    assert node["tls"] is True
    assert node["servername"] == "swdist.apple.com"
    assert node["client-fingerprint"] == "chrome"
    assert node["reality-opts"]["public-key"] == "mynAx1EWuAfqLW2uHPoynhdD19Q0MJFBSTKEGo5MuAk"
    assert node["reality-opts"]["short-id"] == "ab853926"


def test_parse_singbox_mixed_protocols():
    payload = json.dumps({
        "outbounds": [
            {
                "type": "shadowsocks",
                "tag": "SS-Node",
                "server": "1.2.3.4",
                "server_port": 8388,
                "method": "aes-256-gcm",
                "password": "secret_password"
            },
            {
                "type": "trojan",
                "tag": "Trojan-Node",
                "server": "trojan.test.com",
                "server_port": 443,
                "password": "trojan_secret",
                "tls": {
                    "enabled": True,
                    "server_name": "trojan.test.com"
                }
            }
        ]
    })

    nodes = parse_singbox_json(payload)
    assert len(nodes) == 2
    assert nodes[0]["type"] == "ss"
    assert nodes[0]["cipher"] == "aes-256-gcm"
    assert nodes[1]["type"] == "trojan"
    assert nodes[1]["sni"] == "trojan.test.com"
