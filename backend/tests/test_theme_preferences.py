import pytest
from app.api import UserSettingsPayload, auth_me, update_user_settings
from app.models import Base, User
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_theme_default_validation_and_user_isolation():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        alice = User(username='alice', sub_hash_token='alice-test-token')
        bob = User(username='bob', sub_hash_token='bob-test-token')
        session.add_all([alice, bob])
        await session.commit()
        assert (await auth_me(alice, session))['theme_mode'] == 'system'
        await update_user_settings(UserSettingsPayload(theme_mode='dark'), alice, session)
        await session.refresh(bob)
        assert (await auth_me(alice, session))['theme_mode'] == 'dark'
        assert (await auth_me(bob, session))['theme_mode'] == 'system'
        with pytest.raises(ValidationError):
            UserSettingsPayload(theme_mode='invalid')
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_existing_users_receive_system_default(monkeypatch):
    from app import db as db_module

    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text('ALTER TABLE users DROP COLUMN theme_mode'))
        await conn.execute(text("INSERT INTO users (id, username, role, is_active, sub_hash_token, subscription_title, clash_mixed_port, clash_terminal_port) VALUES (1, 'admin', 'admin', 1, 'token', 'test', '7897', '7898')"))
    monkeypatch.setattr(db_module, 'engine', engine)
    monkeypatch.setattr(db_module, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(db_module, 'DATABASE_URL', 'sqlite+aiosqlite:///:memory:')
    await db_module.init_db()
    async with factory() as session:
        assert (await session.get(User, 1)).theme_mode == 'system'
    await engine.dispose()
