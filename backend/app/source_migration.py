"""Upgrade legacy source ownership without guessing historical creators."""

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable

from .models import Source


async def migrate_source_ownership(conn):
    columns = await conn.run_sync(lambda sync: {c['name'] for c in inspect(sync).get_columns('sources')})
    if 'user_id' not in columns:
        return
    invalid = await conn.execute(text('''
        SELECT sources.id FROM sources LEFT JOIN users ON sources.user_id = users.id
        WHERE sources.is_shared IS NULL OR
              (sources.is_shared = false AND (sources.user_id IS NULL OR users.id IS NULL))
        ORDER BY sources.id
    '''))
    invalid_ids = [row[0] for row in invalid]
    if invalid_ids:
        raise RuntimeError(f"Cannot migrate sources with unknown ownership: {invalid_ids}")

    if conn.dialect.name == 'sqlite':
        foreign_keys = (await conn.execute(text('PRAGMA foreign_keys'))).scalar_one()
        if foreign_keys:
            raise RuntimeError('SQLite source migration requires foreign_keys disabled during migration')
        expected = {c.name for c in Source.__table__.columns} - {'owner_user_id', 'created_by_user_id', 'deleted_at', 'deleted_by_user_id'} | {'user_id'}
        extra = columns - expected
        if extra:
            raise RuntimeError(f"Cannot migrate sources with unrecognized columns: {sorted(extra)}")
        objects = await conn.execute(text("""
            SELECT type, name FROM sqlite_master
            WHERE tbl_name = 'sources' AND type IN ('index', 'trigger')
              AND name NOT LIKE 'sqlite_autoindex_%'
        """))
        known_indexes = {'ix_sources_id', 'ix_sources_name', 'ix_sources_user_id'}
        custom_objects = [(kind, name) for kind, name in objects if kind != 'index' or name not in known_indexes]
        if custom_objects:
            raise RuntimeError(f"Cannot migrate sources with unrecognized indexes or triggers: {custom_objects}")
        ddl = str(CreateTable(Source.__table__).compile(dialect=conn.dialect))
        ddl = ddl.replace('CREATE TABLE sources (', 'CREATE TABLE sources_migration (', 1)
        await conn.execute(text(ddl))
        names = [c.name for c in Source.__table__.columns if c.name not in {'owner_user_id', 'created_by_user_id', 'deleted_at', 'deleted_by_user_id'}]
        target = ', '.join(f'"{name}"' for name in names)
        await conn.execute(text(
            f'INSERT INTO sources_migration ({target}, owner_user_id, created_by_user_id) '  # noqa: S608 -- static ORM identifiers
            f'SELECT {target}, CASE WHEN is_shared THEN NULL ELSE user_id END, NULL FROM sources'  # noqa: S608 -- static ORM identifiers
        ))
        await conn.execute(text('DROP TABLE sources'))
        await conn.execute(text('ALTER TABLE sources_migration RENAME TO sources'))
        for index in Source.__table__.indexes:
            if index.name != 'ix_sources_deleted_at':
                await conn.run_sync(lambda sync, idx=index: idx.create(sync, checkfirst=True))
    else:
        await conn.execute(text('ALTER TABLE sources ADD COLUMN owner_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT'))
        await conn.execute(text('ALTER TABLE sources ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL'))
        await conn.execute(text('UPDATE sources SET owner_user_id = user_id WHERE NOT is_shared'))
        await conn.execute(text('ALTER TABLE sources DROP COLUMN user_id'))
        await conn.execute(text('ALTER TABLE sources ALTER COLUMN is_shared SET NOT NULL'))
        await conn.execute(text('ALTER TABLE sources ADD CONSTRAINT ck_sources_owner_scope CHECK ((is_shared AND owner_user_id IS NULL) OR (NOT is_shared AND owner_user_id IS NOT NULL))'))
        for index in Source.__table__.indexes:
            if index.name != 'ix_sources_deleted_at':
                await conn.run_sync(lambda sync, idx=index: idx.create(sync, checkfirst=True))
