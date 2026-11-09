from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, unique=True)
    url = Column(Text, nullable=False)
    source_type = Column(String(32), default="auto")  # auto, remote_clash, remote_base64, local_yaml
    enabled = Column(Boolean, default=True, nullable=False)
    status = Column(String(32), default="pending")  # healthy, error, updating
    error_message = Column(Text, nullable=True)
    node_count = Column(Integer, default=0)
    traffic_used = Column(BigInteger, default=0)
    traffic_total = Column(BigInteger, default=0)
    expire_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    raw_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = relationship("Node", back_populates="source", cascade="all, delete-orphan")

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    original_name = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False, index=True)
    node_type = Column(String(32), nullable=False)
    server = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    country_code = Column(String(16), default="OTHER", index=True)
    country_flag = Column(String(8), default="🌐")
    is_residential = Column(Boolean, default=False, index=True)
    config_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="nodes")
