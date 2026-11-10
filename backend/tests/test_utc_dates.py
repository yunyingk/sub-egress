from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.models import Base, User
from sqlalchemy import text
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_utc_dates_round_trip_and_reject_naive_values():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            original = datetime(2026, 11, 10, 8, tzinfo=timezone(timedelta(hours=8)))
            user = User(username="alice", sub_hash_token="test-token", last_login_at=original)
            session.add(user)
            await session.commit()
            session.expire(user)
            await session.refresh(user)
            assert user.last_login_at == datetime(2026, 11, 10, 0, tzinfo=UTC)
            assert user.last_login_at.tzinfo is UTC
            user.last_login_at = datetime(2026, 11, 10)
            with pytest.raises(StatementError, match="must include a timezone"):
                await session.flush()
            await session.rollback()
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE users SET last_login_at = '2026-11-10 00:00:00'"))
        async with sessions() as session:
            existing = await session.get(User, 1)
            assert existing.last_login_at == datetime(2026, 11, 10, 0, tzinfo=UTC)
    finally:
        await engine.dispose()
