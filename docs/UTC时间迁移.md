# UTC 时间迁移

新版使用带时区的 UTC 时间。旧版 PostgreSQL 中的时间列是 `timestamp without time zone`；新版检测到这类列时会拒绝启动，避免误读或错误写入。SQLite 的历史时间按 UTC 解释，读取时补充 UTC 时区；如果旧环境使用过其他本地时区，必须先确定数据含义并设计单独迁移。

生产迁移前确认所有历史值的原始时区、数据库连接目标和所有写入方，备份并验证恢复方式。当前 WSL K3s 运行环境的系统时区检查结果为 UTC，但这不能证明所有历史写入都来自 UTC 环境。未经确认不要使用 `--assume-utc`。

使用新版代码、指向目标库的 `DATABASE_URL` 和 Python 3.14 环境，先只读检查：

```bash
uv run --locked python -m app.migrate_utc
```

确认备份、原始时区及停写窗口后，显式执行：

```bash
uv run --locked python -m app.migrate_utc --apply --assume-utc
```

迁移在事务中处理已知列，逐列执行 `AT TIME ZONE 'UTC'`；遇到未知的时间戳列会报错并回滚。已经是 `timestamp with time zone` 的列会跳过。迁移成功后再部署新版，检查服务、登录及订阅时间。若需要回退旧版，先停止写入并按预先验证的数据库备份恢复方案处理；旧版不能假定可直接读取新版时区列。
