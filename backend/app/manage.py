"""
sub-egress CLI Management Tool
Usage:
    python -m app.manage reset-admin [new_password]
    python -m app.manage create-user <username> [password] [--admin]
    python -m app.manage list-users
"""
import asyncio
import os
import secrets
import sys
from sqlalchemy import select
from .db import AsyncSessionLocal, init_db
from .models import User
from .security import generate_secure_password, hash_password, validate_password, validate_username


async def cmd_reset_admin(args):
    await init_db()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.username == "admin")
        res = await session.execute(stmt)
        admin = res.scalar_one_or_none()
        if not admin:
            print("错误: 未找到 admin 用户。")
            return

        if len(args) > 0:
            new_pwd = args[0]
            valid, msg = validate_password(new_pwd)
            if not valid:
                print(f"错误: 密码不符合规范: {msg}")
                return
        else:
            new_pwd = generate_secure_password(32)

        admin.password_hash = hash_password(new_pwd)
        await session.commit()
        print("\n" + "=" * 60)
        print("管理员 admin 密码重置成功！")
        print(f"新密码: {new_pwd}")
        print("=" * 60 + "\n")


async def cmd_create_user(args):
    if not args:
        print("用法: python -m app.manage create-user <username> [password] [--admin]")
        return
    username = args[0]
    valid, msg = validate_username(username)
    if not valid:
        print(f"错误: 用户名不符合规范: {msg}")
        return

    is_admin = "--admin" in args
    filtered_args = [a for a in args[1:] if a != "--admin"]
    if filtered_args:
        pwd = filtered_args[0]
        p_valid, p_msg = validate_password(pwd)
        if not p_valid:
            print(f"错误: 密码不符合规范: {p_msg}")
            return
    else:
        pwd = generate_secure_password(32)

    await init_db()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.username == username)
        res = await session.execute(stmt)
        if res.scalar_one_or_none():
            print(f"错误: 用户 {username} 已存在！")
            return

        token = secrets.token_hex(24)
        user = User(
            username=username,
            password_hash=hash_password(pwd),
            role="admin" if is_admin else "user",
            is_active=True,
            sub_hash_token=token
        )
        session.add(user)
        await session.commit()
        print("\n" + "=" * 60)
        print(f"用户 {username} 创建成功！")
        print(f"角色: {'管理员 (admin)' if is_admin else '普通用户 (user)'}")
        print(f"密码: {pwd}")
        print(f"订阅令牌: {token}")
        print("=" * 60 + "\n")


async def cmd_list_users():
    await init_db()
    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(User.id)
        res = await session.execute(stmt)
        users = res.scalars().all()
        print("\n" + "=" * 80)
        print(f"{'ID':<4} {'用户名':<16} {'角色':<10} {'状态':<8} {'订阅令牌':<32}")
        print("-" * 80)
        for u in users:
            status = "已激活" if u.is_active else "已禁用"
            print(f"{u.id:<4} {u.username:<16} {u.role:<10} {status:<8} {u.sub_hash_token:<32}")
        print("=" * 80 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd in ("reset-admin", "reset_admin"):
        asyncio.run(cmd_reset_admin(args))
    elif cmd in ("create-user", "create_user"):
        asyncio.run(cmd_create_user(args))
    elif cmd in ("list-users", "list_users"):
        asyncio.run(cmd_list_users())
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
