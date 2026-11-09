from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(32), default="user", nullable=False)  # admin / user
    is_active = Column(Boolean, default=True, nullable=False)
    sub_hash_token = Column(String(64), nullable=False, unique=True, index=True)
    subscription_title = Column(String(128), default="sub-egress", nullable=False)
    clash_mixed_port = Column(String(16), default="7897", nullable=False)
    clash_terminal_port = Column(String(16), default="7898", nullable=False)
    custom_direct_domains = Column(Text, default="ying-qing.cn", nullable=True)
    custom_proxy_domains = Column(Text, default="", nullable=True)
    custom_rules = Column(Text, default="", nullable=True)
    oauth_provider = Column(String(32), nullable=True)  # authentik / etc.
    oauth_id = Column(String(128), nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    passkeys = relationship("PasskeyCredential", back_populates="user", cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="user")


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(255), nullable=False, unique=True, index=True)
    public_key = Column(Text, nullable=False)
    sign_count = Column(Integer, default=0, nullable=False)
    name = Column(String(64), default="我的通行密钥", nullable=False)
    transports = Column(String(128), default="internal", nullable=True)
    aaguid = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="passkeys")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_shared = Column(Boolean, default=True, nullable=False)
    name = Column(String(64), nullable=False, unique=True)
    code = Column(String(8), default="", nullable=True)
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
    user = relationship("User", back_populates="sources")


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
    latency = Column(Float, nullable=True)
    latency_status = Column(String(32), nullable=True)
    latency_updated_at = Column(DateTime, nullable=True)
    config_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="nodes")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
