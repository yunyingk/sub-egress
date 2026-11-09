import asyncio
from datetime import datetime
import re
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

        # Insert new parsed nodes with standard prefixes
        for item in raw_nodes:
            orig_name = str(item.get("name", "")).strip()
            flag, code = detect_country(orig_name)
            is_res = is_residential_node(orig_name, item)
            
            # Format display name: [透传·{source.name}] {flag} {cleaned_name}
            # Remove duplicated country flag if already in orig_name to avoid 🇯🇵 🇯🇵
            display_base = orig_name.replace(flag, "").strip()
            display_name = f"[透传·{source.name}] {flag} {display_base}"

            node_rec = Node(
                source_id=source.id,
                original_name=orig_name,
                display_name=display_name,
                node_type=item.get("type", "unknown"),
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
