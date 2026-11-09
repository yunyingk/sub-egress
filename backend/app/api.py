from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from .builder import build_clash_config
from .db import get_db
from .models import Node, Source
from .syncer import sync_single_source

router = APIRouter()

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

# ==================== 下游订阅分发端点 (供客户端直连) ====================

@router.get("/clash", summary="获取合并后的完整 ClashMeta 配置")
@router.get("/download/clash")
async def export_clash_config(db: AsyncSession = Depends(get_db)):
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

    yaml_text = build_clash_config(raw_nodes)

    # 统计总流量与最早到期时间供客户端展示
    src_stmt = select(Source).where(Source.enabled == True)
    src_res = await db.execute(src_stmt)
    sources = src_res.scalars().all()

    total_used = sum(s.traffic_used for s in sources if s.traffic_used)
    total_max = sum(s.traffic_total for s in sources if s.traffic_total)
    earliest_expire = min((int(s.expire_at.timestamp()) for s in sources if s.expire_at), default=0)

    headers = {
        "Content-Type": "application/yaml; charset=utf-8",
        "Content-Disposition": 'inline; filename="sub-egress.yaml"',
        "profile-update-interval": "12",
    }
    if total_max > 0:
        headers["subscription-userinfo"] = f"upload=0; download={total_used}; total={total_max}; expire={earliest_expire}"

    return Response(content=yaml_text, media_type="application/yaml", headers=headers)


# ==================== 上游源管理 API (供 Web 控制台) ====================

@router.get("/api/sources", summary="获取上游源列表")
async def list_sources(db: AsyncSession = Depends(get_db)):
    stmt = select(Source).order_by(Source.id)
    res = await db.execute(stmt)
    sources = res.scalars().all()
    return [{
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
    } for s in sources]

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

@router.get("/api/nodes", summary="获取合并后的节点池列表")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .order_by(Node.country_code, Node.id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    nodes = []
    for n, s_name in rows:
        nodes.append({
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
            "is_residential": n.is_residential
        })
    return {"total": len(nodes), "nodes": nodes}

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "sub-egress", "timestamp": datetime.utcnow().isoformat()}
