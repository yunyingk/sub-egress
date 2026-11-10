from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """Store instants as UTC and restore timezone information on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.utcoffset() is None:
                raise ValueError("Datetime values must include a timezone")
            return value.astimezone(UTC)
        return None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.utcoffset() is None else value.astimezone(UTC)


def utc_now():
    return datetime.now(UTC)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(32), default="user", nullable=False)  # admin / user
    is_active = Column(Boolean, default=True, nullable=False)
    sub_hash_token = Column(String(64), nullable=False, unique=True, index=True)
    theme_mode = Column(String(16), default="system", server_default="system", nullable=False)
    subscription_title = Column(String(128), default="sub-egress", nullable=False)
    clash_mixed_port = Column(String(16), default="7897", nullable=False)
    clash_terminal_port = Column(String(16), default="7898", nullable=False)
    custom_direct_domains = Column(Text, default="ying-qing.cn", nullable=True)
    custom_proxy_domains = Column(Text, default="", nullable=True)
    custom_rules = Column(Text, default="", nullable=True)
    disabled_shared_sources = Column(Text, default="", nullable=True)
    oauth_provider = Column(String(32), nullable=True)  # authentik / etc.
    oauth_id = Column(String(128), nullable=True)
    last_login_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, default=utc_now)
    updated_at = Column(UTCDateTime, default=utc_now, onupdate=utc_now)

    passkeys = relationship("PasskeyCredential", back_populates="user", cascade="all, delete-orphan")
    identities = relationship("OAuthIdentity", back_populates="user", cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="owner", foreign_keys="Source.owner_user_id")

    def get_disabled_shared_source_ids(self) -> set[int]:
        if not self.disabled_shared_sources:
            return set()
        return {int(x.strip()) for x in self.disabled_shared_sources.split(",") if x.strip().isdigit()}


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
    created_at = Column(UTCDateTime, default=utc_now)
    last_used_at = Column(UTCDateTime, nullable=True)

    user = relationship("User", back_populates="passkeys")


class OAuthIdentity(Base):
    """A verified external identity; one local account may link many providers."""
    __tablename__ = "oauth_identities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    issuer = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    created_at = Column(UTCDateTime, default=utc_now, nullable=False)
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_oauth_identity_issuer_subject"),)
    user = relationship("User", back_populates="identities")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_shared = Column(Boolean, default=True, nullable=False)
    name = Column(String(64), nullable=False, index=True)
    code = Column(String(8), default="", nullable=True)
    url = Column(Text, nullable=False)
    source_type = Column(String(32), default="auto")  # auto, remote_clash, remote_base64, local_yaml
    enabled = Column(Boolean, default=True, nullable=False)
    status = Column(String(32), default="pending")  # healthy, error, updating
    error_message = Column(Text, nullable=True)
    node_count = Column(Integer, default=0)
    traffic_used = Column(BigInteger, default=0)
    traffic_total = Column(BigInteger, default=0)
    expire_at = Column(UTCDateTime, nullable=True)
    last_sync_at = Column(UTCDateTime, nullable=True)
    raw_content = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, default=utc_now)
    updated_at = Column(UTCDateTime, default=utc_now, onupdate=utc_now)

    nodes = relationship("Node", back_populates="source", cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("(is_shared AND owner_user_id IS NULL) OR (NOT is_shared AND owner_user_id IS NOT NULL)", name="ck_sources_owner_scope"),)
    owner = relationship("User", back_populates="sources", foreign_keys=[owner_user_id])
    creator = relationship("User", foreign_keys=[created_by_user_id])


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
    latency_updated_at = Column(UTCDateTime, nullable=True)
    config_json = Column(JSON, nullable=False)
    created_at = Column(UTCDateTime, default=utc_now)

    source = relationship("Source", back_populates="nodes")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(UTCDateTime, default=utc_now, onupdate=utc_now)
