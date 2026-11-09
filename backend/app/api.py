import asyncio
import base64
from datetime import datetime
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from .builder import build_base64_config, build_clash_config, build_singbox_config, extract_dynamic_groups
from .db import get_db
from .models import Node, Setting, Source
from .parsers.clash import extract_subscription_extra_info
from .syncer import ping_single_node, sync_single_source
from .version import VERSION

router = APIRouter()

DEFAULT_SETTINGS = {
    "sub_hash_token": "e699ffd91845385075b27d813b8590df40375c6af2c4eb77",
    "require_token": "false",
    "default_target": "clash",
    "update_interval": "12",
    "write_api_token": "sec_7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
    "subscription_title": "sub-egress",
    "clash_mixed_port": "7897",
    "clash_terminal_port": "7898",
    "custom_direct_domains": "ying-qing.cn",
    "custom_nameserver_policy": '{"geosite:cn": ["223.5.5.5", "119.29.29.29"], "+.hosecloud.com": ["223.5.5.5", "119.29.29.29"], "+.ekuaibao.com": ["223.5.5.5", "119.29.29.29"]}',
    "profile_web_url": ""
}

async def get_system_settings(db: AsyncSession) -> Dict[str, str]:
    stmt = select(Setting)
    res = await db.execute(stmt)
    db_settings = {s.key: s.value for s in res.scalars().all()}
    
    # Fill in any missing default settings
    merged = dict(DEFAULT_SETTINGS)
    missing = []
    for k, v in DEFAULT_SETTINGS.items():
        if k in db_settings:
            merged[k] = db_settings[k]
        else:
            missing.append(Setting(key=k, value=v))
    
    if missing:
        for s in missing:
            db.add(s)
        await db.commit()
    return merged

# ==================== 下游订阅分发端点 (供客户端直连与多内核分发) ====================

@router.api_route("/c/{token}", methods=["GET", "HEAD"], summary="基于安全令牌的统一订阅调度端点")
@router.api_route("/feed", methods=["GET", "HEAD"], summary="标准统一订阅调度端点")
async def export_subscription(
    request: Request,
    token: Optional[str] = None,
    target: Optional[str] = Query(None, description="目标客户端内核: clash, sing-box, base64"),
    type: Optional[str] = Query(None, description="别名目标内核: clash, sing-box, base64"),
    name: Optional[str] = Query(None, description="自定义订阅卡片名称 (显示在客户端)"),
    title: Optional[str] = Query(None, description="自定义订阅卡片名称 (别名)"),
    t: Optional[str] = Query(None, description="Query 传递的安全令牌 (用于 /feed)"),
    db: AsyncSession = Depends(get_db)
):
    settings = await get_system_settings(db)
    req_token = token or t
    
    # 读权限安全检查
    if settings.get("require_token", "false").lower() == "true":
        expected_token = settings.get("sub_hash_token", "")
        if not req_token or req_token != expected_token:
            raise HTTPException(
                status_code=403,
                detail="403 Forbidden: Invalid or missing subscription security hash token"
            )

    # 确定目标导出内核
    raw_target = (target or type or settings.get("default_target", "clash")).lower()
    if raw_target in ("sing-box", "singbox", "sb"):
        final_target = "sing-box"
    elif raw_target in ("base64", "uri", "txt"):
        final_target = "base64"
    else:
        final_target = "clash"

    # 提取所有启用的节点
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled == True)
        .order_by(Node.country_code, Node.id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    raw_nodes = []
    for node, source_name in rows:
        raw_nodes.append({
            "display_name": node.display_name,
            "country_code": node.country_code,
            "country_flag": node.country_flag,
            "is_residential": node.is_residential,
            "config_json": node.config_json
        })

    # 统计总流量与最早到期时间供客户端展示
    src_stmt = select(Source).where(Source.enabled == True)
    src_res = await db.execute(src_stmt)
    sources = src_res.scalars().all()

    total_used = sum(s.traffic_used for s in sources if s.traffic_used)
    total_max = sum(s.traffic_total for s in sources if s.traffic_total)
    earliest_expire = min((int(s.expire_at.timestamp()) for s in sources if s.expire_at), default=0)

    interval = settings.get("update_interval", "12")

    if final_target == "sing-box":
        content = build_singbox_config(raw_nodes)
        media_type = "application/json; charset=utf-8"
        filename = "sub-egress-singbox.json"
    elif final_target == "base64":
        content = build_base64_config(raw_nodes)
        media_type = "text/plain; charset=utf-8"
        filename = "sub-egress.txt"
    else:
        mixed_port = int(settings.get("clash_mixed_port", "7897") or 7897)
        terminal_port = int(settings.get("clash_terminal_port", "7898") or 7898)
        custom_direct_domains = [d.strip() for d in settings.get("custom_direct_domains", "").split(",") if d.strip()]
        try:
            custom_nameserver_policy = json.loads(settings.get("custom_nameserver_policy", "{}"))
        except Exception:
            custom_nameserver_policy = None

        content = build_clash_config(
            raw_nodes,
            mixed_port=mixed_port,
            terminal_port=terminal_port,
            custom_direct_domains=custom_direct_domains,
            custom_nameserver_policy=custom_nameserver_policy
        )
        media_type = "application/yaml; charset=utf-8"
        filename = "sub-egress-clash.yaml"

    sub_title = (name or title or settings.get("subscription_title") or "sub-egress").strip()
    b64_title = "base64:" + base64.b64encode(sub_title.encode("utf-8")).decode("utf-8")
    encoded_fn = urllib.parse.quote(sub_title)
    ascii_safe_title = sub_title.encode('ascii', 'ignore').decode('ascii').strip() or "sub-egress"

    req_host = request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    default_base_url = f"{proto}://{req_host}" if req_host else "https://sub.ying-qing.cn"
    profile_web_url = settings.get("profile_web_url") or default_base_url

    headers = {
        "Content-Type": media_type,
        "Content-Disposition": f'attachment; filename*=UTF-8\'\'{encoded_fn}; filename="{ascii_safe_title}"',
        "profile-title": b64_title,
        "Profile-Title": b64_title,
        "subscription-title": b64_title,
        "profile-update-interval": interval,
        "profile-web-page-url": profile_web_url,
    }
    if total_max > 0:
        headers["subscription-userinfo"] = f"upload=0; download={total_used}; total={total_max}; expire={earliest_expire}"

    return Response(content=content, media_type=media_type, headers=headers)


# ==================== 读写设置 API ====================

class SettingsPayload(BaseModel):
    sub_hash_token: Optional[str] = None
    require_token: Optional[bool] = None
    default_target: Optional[str] = None
    update_interval: Optional[str] = None
    write_api_token: Optional[str] = None
    subscription_title: Optional[str] = None
    clash_mixed_port: Optional[str] = None
    clash_terminal_port: Optional[str] = None

@router.get("/api/settings", summary="获取全局读写与安全设置")
async def get_settings(db: AsyncSession = Depends(get_db)):
    settings = await get_system_settings(db)
    return {
        "version": VERSION,
        "sub_hash_token": settings.get("sub_hash_token", ""),
        "require_token": settings.get("require_token", "false").lower() == "true",
        "default_target": settings.get("default_target", "clash"),
        "update_interval": settings.get("update_interval", "12"),
        "write_api_token": settings.get("write_api_token", ""),
        "subscription_title": settings.get("subscription_title", "sub-egress"),
        "clash_mixed_port": settings.get("clash_mixed_port", "7897"),
        "clash_terminal_port": settings.get("clash_terminal_port", "7898")
    }

@router.post("/api/settings", summary="保存全局读写设置")
async def update_settings(payload: SettingsPayload, db: AsyncSession = Depends(get_db)):
    updates = {}
    if payload.sub_hash_token is not None:
        updates["sub_hash_token"] = payload.sub_hash_token.strip()
    if payload.require_token is not None:
        updates["require_token"] = "true" if payload.require_token else "false"
    if payload.default_target is not None:
        updates["default_target"] = payload.default_target.strip().lower()
    if payload.update_interval is not None:
        updates["update_interval"] = payload.update_interval.strip()
    if payload.write_api_token is not None:
        updates["write_api_token"] = payload.write_api_token.strip()
    if payload.subscription_title is not None:
        updates["subscription_title"] = payload.subscription_title.strip()
    if payload.clash_mixed_port is not None:
        updates["clash_mixed_port"] = str(payload.clash_mixed_port).strip()
    if payload.clash_terminal_port is not None:
        updates["clash_terminal_port"] = str(payload.clash_terminal_port).strip()

    for k, v in updates.items():
        stmt = select(Setting).where(Setting.key == k)
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = v
        else:
            db.add(Setting(key=k, value=v))
    await db.commit()
    return {"status": "success", "message": "Settings updated"}

@router.post("/api/settings/regenerate-token", summary="重新生成安全哈希令牌")
async def regenerate_token(db: AsyncSession = Depends(get_db)):
    new_token = secrets.token_hex(24)
    stmt = select(Setting).where(Setting.key == "sub_hash_token")
    res = await db.execute(stmt)
    setting = res.scalar_one_or_none()
    if setting:
        setting.value = new_token
    else:
        db.add(Setting(key="sub_hash_token", value=new_token))
    await db.commit()
    return {"status": "success", "new_token": new_token}


# ==================== 上游源管理 API (供 Web 控制台) ====================

class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: Optional[str] = "auto"
    raw_content: Optional[str] = None

class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    raw_content: Optional[str] = None

@router.get("/api/sources", summary="获取上游源列表")
async def list_sources(db: AsyncSession = Depends(get_db)):
    stmt = select(Source).order_by(Source.id)
    res = await db.execute(stmt)
    sources = res.scalars().all()
    results = []
    for s in sources:
        extra = extract_subscription_extra_info(s.raw_content or "")
        results.append({
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "source_type": s.source_type,
            "enabled": s.enabled,
            "status": s.status,
            "error_message": s.error_message,
            "node_count": s.node_count,
            "traffic_used": s.traffic_used,
            "traffic_total": s.traffic_total,
            "expire_at": s.expire_at.isoformat() if s.expire_at else None,
            "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
            "reset_info": extra.get("reset_info"),
            "remaining_text": extra.get("remaining_text")
        })
    return results

@router.post("/api/sources", summary="新增上游源")
async def create_source(payload: SourceCreate, db: AsyncSession = Depends(get_db)):
    src = Source(
        name=payload.name.strip(),
        url=payload.url.strip(),
        source_type=payload.source_type or "auto",
        raw_content=payload.raw_content
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    # 异步触发首次同步
    await sync_single_source(src.id, db)
    return {"status": "success", "id": src.id}

@router.put("/api/sources/{source_id}", summary="编辑上游源")
async def update_source(source_id: int, payload: SourceUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.url is not None:
        src.url = payload.url.strip()
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.raw_content is not None:
        src.raw_content = payload.raw_content

    await db.commit()
    await sync_single_source(src.id, db)
    return {"status": "success"}

@router.delete("/api/sources/{source_id}", summary="删除上游源")
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Source).where(Source.id == source_id))
    await db.commit()
    return {"status": "success"}

@router.post("/api/sources/{source_id}/refresh", summary="手动刷新指定上游源")
async def refresh_source(source_id: int, db: AsyncSession = Depends(get_db)):
    success = await sync_single_source(source_id, db)
    if not success:
        stmt = select(Source).where(Source.id == source_id)
        res = await db.execute(stmt)
        src = res.scalar_one_or_none()
        err = src.error_message if src else "Unknown error"
        raise HTTPException(status_code=500, detail=f"Refresh failed: {err}")
    return {"status": "success"}


# ==================== 节点池大盘 API ====================

@router.get("/api/nodes", summary="获取合并后的节点池与聚合动态策略组")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .order_by(Node.country_code, Node.id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    nodes = []
    raw_nodes_for_dyn = []
    for n, s_name in rows:
        node_dict = {
            "id": n.id,
            "source_id": n.source_id,
            "source_name": s_name,
            "original_name": n.original_name,
            "display_name": n.display_name,
            "node_type": n.node_type,
            "server": n.server,
            "port": n.port,
            "country_code": n.country_code,
            "country_flag": n.country_flag,
            "is_residential": n.is_residential,
            "latency": n.latency,
            "latency_status": n.latency_status,
            "latency_updated_at": n.latency_updated_at.isoformat() if n.latency_updated_at else None
        }
        nodes.append(node_dict)
        raw_nodes_for_dyn.append(node_dict)

    dynamic_groups = extract_dynamic_groups(raw_nodes_for_dyn)

    return {
        "total": len(nodes),
        "dynamic_groups": dynamic_groups,
        "nodes": nodes
    }

# ==================== 节点延迟测速 API ====================

class BatchPingPayload(BaseModel):
    node_ids: Optional[List[int]] = None

@router.post("/api/nodes/{node_id}/ping", summary="测试单个节点网络握手延迟")
async def ping_node_endpoint(node_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Node).where(Node.id == node_id)
    res = await db.execute(stmt)
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    result = await ping_single_node(node.server, node.port, node.node_type)
    node.latency = result["latency"]
    node.latency_status = result["status"]
    node.latency_updated_at = datetime.utcnow()
    await db.commit()

    return {
        "node_id": node.id,
        "display_name": node.display_name,
        "server": node.server,
        "port": node.port,
        **result
    }

@router.post("/api/nodes/ping", summary="批量并发测试节点延迟")
async def batch_ping_nodes(payload: Optional[BatchPingPayload] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Node)
    if payload and payload.node_ids:
        stmt = stmt.where(Node.id.in_(payload.node_ids))
    res = await db.execute(stmt)
    nodes = res.scalars().all()

    sem = asyncio.Semaphore(20)

    async def worker(node: Node):
        async with sem:
            res = await ping_single_node(node.server, node.port, node.node_type, timeout=2.5)
            node.latency = res["latency"]
            node.latency_status = res["status"]
            node.latency_updated_at = datetime.utcnow()
            return node.id, res

    tasks = [worker(n) for n in nodes]
    results = await asyncio.gather(*tasks)
    await db.commit()

    return {
        "total": len(results),
        "results": {str(nid): ping_res for nid, ping_res in results}
    }

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "sub-egress", "version": VERSION, "timestamp": datetime.utcnow().isoformat()}

@router.get("/api/version", summary="获取服务版本号")
async def get_version():
    return {"version": VERSION}

@router.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    fav = Path(os.getenv("FRONTEND_DIR", "/frontend")) / "favicon.ico"
    if not fav.exists():
        fav = Path(__file__).resolve().parent.parent.parent / "frontend" / "favicon.ico"
    if fav.exists():
        return FileResponse(fav, media_type="image/x-icon")
    return Response(status_code=404)
