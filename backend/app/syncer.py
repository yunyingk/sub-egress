import asyncio
from datetime import datetime
import re
import time
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from .db import AsyncSessionLocal
from .models import Node, Source
from .parsers.clash import detect_country, is_residential_node, parse_clash_yaml
from .parsers.uri import parse_subscription_text

DEFAULT_UA = "clash.meta/v1.19.29"

def parse_userinfo_header(header_val: str) -> Dict[str, Optional[int]]:
    info: Dict[str, Optional[int]] = {
        "upload": 0,
        "download": 0,
        "total": 0,
        "expire": None
    }
    if not header_val:
        return info
    for part in header_val.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().lower()
            try:
                val = int(v.strip())
                if k in info:
                    info[k] = val
            except ValueError:
                pass
    return info

def clean_node_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip()
    return cleaned

def extract_source_code(source_name: str, explicit_code: Optional[str] = None) -> str:
    if explicit_code and explicit_code.strip():
        return explicit_code.strip().upper()[:4]
    letters = re.findall(r'[A-Za-z]', source_name or "")
    if len(letters) >= 2:
        return (letters[0] + letters[1]).upper()
    elif len(letters) == 1:
        return (letters[0] + 'X').upper()
    return "MY"

def strip_all_flags(text: str) -> str:
    """清理字符串中已有的所有国旗 emoji，避免重复出现两面旗帜"""
    clean = re.sub(r'[\U0001F1E6-\U0001F1FF]{2}', '', text)
    clean = clean.replace('🌐', '').strip()
    return clean

def format_clean_node_name(source_code: str, orig_name: str, flag: str, is_res: bool, idx: int, protocol_type: str) -> str:
    base = strip_all_flags(orig_name).strip()
    p_char = protocol_type[0].upper() if protocol_type else "S"
    
    # 针对美国家庭宽带节点的规范化
    if is_res:
        if "主线" in base:
            return f"[{source_code}] {flag} 美国-01 {p_char} 住宅主线"
        elif "备用" in base:
            return f"[{source_code}] {flag} 美国-02 {p_char} 住宅备用"
        else:
            return f"[{source_code}] {flag} 美国-{idx:02d} {p_char} 住宅节点"
            
    # 针对普通机场节点，去除多余空白和前导符号
    base = re.sub(r'^\s*[-_·]\s*', '', base)
    return f"[{source_code}] {flag} {base}"

async def sync_single_source(source_id: int, session: AsyncSession) -> bool:
    stmt = select(Source).where(Source.id == source_id)
    result = await session.execute(stmt)
    source = result.scalar_one_or_none()
    if not source:
        return False

    source.status = "updating"
    await session.commit()

    content = ""
    raw_nodes: List[Dict[str, Any]] = []

    try:
        if source.source_type == "local_yaml" or source.url.startswith("local://"):
            content = source.raw_content or ""
        else:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(source.url, headers={"User-Agent": DEFAULT_UA})
                if resp.status_code != 200:
                    raise ValueError(f"HTTP Status {resp.status_code}")
                content = resp.text
                
                # Check subscription traffic info header
                userinfo_header = resp.headers.get("subscription-userinfo") or resp.headers.get("Subscription-Userinfo")
                if userinfo_header:
                    uinfo = parse_userinfo_header(userinfo_header)
                    upload = uinfo.get("upload") or 0
                    download = uinfo.get("download") or 0
                    source.traffic_used = upload + download
                    source.traffic_total = uinfo.get("total") or 0
                    if uinfo.get("expire"):
                        source.expire_at = datetime.fromtimestamp(uinfo["expire"])

        # Try Clash YAML first
        raw_nodes = parse_clash_yaml(content)
        if not raw_nodes:
            raw_nodes = parse_subscription_text(content)

        if not raw_nodes:
            raise ValueError("No valid proxy nodes extracted from payload")

        # Delete existing nodes for this source
        await session.execute(delete(Node).where(Node.source_id == source.id))

        # Insert new parsed nodes with clean concise prefixes [XX]
        source_code = getattr(source, "code", None) or extract_source_code(source.name)
        source.code = source_code

        for idx, item in enumerate(raw_nodes, 1):
            orig_name = str(item.get("name", "")).strip()
            flag, code = detect_country(orig_name)
            is_res = is_residential_node(orig_name, item)
            ntype = str(item.get("type", "unknown"))
            
            display_name = format_clean_node_name(source_code, orig_name, flag, is_res, idx, ntype)

            node_rec = Node(
                source_id=source.id,
                original_name=orig_name,
                display_name=display_name,
                node_type=ntype,
                server=str(item.get("server", "")),
                port=int(item.get("port", 0)),
                country_code=code,
                country_flag=flag,
                is_residential=is_res,
                config_json=item
            )
            session.add(node_rec)

        source.status = "healthy"
        source.error_message = None
        source.node_count = len(raw_nodes)
        source.last_sync_at = datetime.utcnow()
        source.raw_content = content
        await session.commit()
        return True

    except Exception as e:
        source.status = "error"
        source.error_message = str(e)
        source.last_sync_at = datetime.utcnow()
        await session.commit()
        return False

async def sync_all_sources():
    async with AsyncSessionLocal() as session:
        stmt = select(Source.id).where(Source.enabled == True)
        result = await session.execute(stmt)
        source_ids = result.scalars().all()
        for sid in source_ids:
            try:
                await sync_single_source(sid, session)
            except Exception:
                pass

async def background_sync_worker():
    while True:
        try:
            await sync_all_sources()
        except Exception:
            pass
        # Refresh every 30 minutes
        await asyncio.sleep(1800)


# ==================== 后端定时巡检与延迟测速工作者 ====================

async def ping_single_node(host: str, port: int, node_type: str, timeout: float = 2.5) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        rtt = (time.perf_counter() - t0) * 1000.0
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {"latency": round(rtt, 1), "status": "ok", "error": None}
    except ConnectionRefusedError:
        rtt = (time.perf_counter() - t0) * 1000.0
        if node_type == "hysteria2":
            return {"latency": round(rtt, 1), "status": "ok", "error": None}
        return {"latency": round(rtt, 1), "status": "refused", "error": "Connection refused"}
    except asyncio.TimeoutError:
        return {"latency": None, "status": "timeout", "error": "Connection timed out"}
    except Exception as e:
        return {"latency": None, "status": "error", "error": str(e)}

async def ping_all_nodes(timeout: float = 2.5, concurrency: int = 20):
    async with AsyncSessionLocal() as session:
        stmt = select(Node)
        res = await session.execute(stmt)
        nodes = res.scalars().all()
        if not nodes:
            return

        sem = asyncio.Semaphore(concurrency)

        async def worker(node: Node):
            async with sem:
                res = await ping_single_node(node.server, node.port, node.node_type, timeout=timeout)
                node.latency = res["latency"]
                node.latency_status = res["status"]
                node.latency_updated_at = datetime.utcnow()

        await asyncio.gather(*(worker(n) for n in nodes))
        await session.commit()

async def background_ping_worker():
    # 启动等待 5 秒后执行首次全节点测速巡检，随后每 5 分钟 (300秒) 定时持续更新数据库
    await asyncio.sleep(5)
    while True:
        try:
            await ping_all_nodes()
        except Exception:
            pass
        await asyncio.sleep(300)
