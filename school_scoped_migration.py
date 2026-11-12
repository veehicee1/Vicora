"""School-scoped natural-key migration for VICORA's SQLite database.

This migration replaces four legacy global UNIQUE constraints with composite
school-scoped unique indexes. It preserves row IDs, all existing columns,
child-table foreign keys, explicit indexes and triggers. It must run only after
the legacy-school bootstrap has assigned school_id to every existing row.
"""
import re
import sqlite3

SCOPED_UNIQUE_COLUMNS = {
    "admins": "username",
    "classes": "name",
    "subjects": "name",
    "students": "reg_no",
}


def _table_exists(connection, table):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _rebuild_without_global_unique(connection, table, column):
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"Required table {table} is missing its CREATE TABLE definition")

    original_sql = row[0]
    scoped_index = f"ux_{table}_school_{column}"
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (scoped_index,),
    ).fetchone():
        return
    # Capture user-created indexes and triggers. SQLite's implicit UNIQUE
    # auto-index is intentionally not copied; it is replaced below.
    objects = connection.execute(
        """SELECT type, name, sql FROM sqlite_master
           WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL
           ORDER BY CASE type WHEN 'index' THEN 0 ELSE 1 END, name""",
        (table,),
    ).fetchall()

    temp_table = f"__vicora_rebuild_{table}"
    if _table_exists(connection, temp_table):
        raise RuntimeError(f"Temporary migration table {temp_table} already exists")

    create_sql = re.sub(
        rf"^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(['\"]?){re.escape(table)}\2",
        rf"\1{temp_table}",
        original_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if create_sql == original_sql:
        raise RuntimeError(f"Could not safely prepare table definition for {table}")

    # Remove only the known inline UNIQUE marker, leaving type, NULL rules,
    # defaults, checks, collations and all other column definitions intact.
    pattern = rf"(\b{re.escape(column)}\s+[^,\n]*?)\s+UNIQUE\b"
    create_sql, replacements = re.subn(pattern, r"\1", create_sql, count=1, flags=re.IGNORECASE)
    if replacements != 1:
        raise RuntimeError(f"Expected one global UNIQUE constraint on {table}.{column}")

    connection.execute(create_sql)
    columns = [item[1] for item in connection.execute(f"PRAGMA table_info({table})")]
    names = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
    connection.execute(
        f"INSERT INTO {temp_table} ({names}) SELECT {names} FROM {table}"
    )
    connection.execute(f"DROP TABLE {table}")
    connection.execute(f"ALTER TABLE {temp_table} RENAME TO {table}")

    for obj_type, _name, sql in objects:
        connection.execute(sql)

    index_name = f"ux_{table}_school_{column}"
    connection.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
        f'ON "{table}" (school_id, "{column}")'
    )


def migrate_school_scoped_unique_keys(connection):
    """Atomically scope legacy usernames/names/registration numbers by school."""
    c = connection
    missing = [
        table for table in SCOPED_UNIQUE_COLUMNS
        if not _table_exists(c, table)
    ]
    if missing:
        raise RuntimeError("Cannot scope uniqueness; missing tables: " + ", ".join(missing))

    for table in SCOPED_UNIQUE_COLUMNS:
        columns = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
        if "school_id" not in columns:
            raise RuntimeError(
                f"Cannot scope {table}; run the legacy-school migration first"
            )
        if c.execute(
            f"SELECT 1 FROM {table} WHERE school_id IS NULL OR school_id='' LIMIT 1"
        ).fetchone():
            raise RuntimeError(
                f"Cannot scope {table}; rows without school_id must be resolved first"
            )

    # PRAGMA foreign_keys cannot be toggled inside a transaction.
    was_foreign_keys = c.execute("PRAGMA foreign_keys").fetchone()[0]
    c.commit()
    if was_foreign_keys:
        c.execute("PRAGMA foreign_keys=OFF")
    c.execute("PRAGMA legacy_alter_table=ON")
    try:
        c.execute("BEGIN IMMEDIATE")
        for table, column in SCOPED_UNIQUE_COLUMNS.items():
            _rebuild_without_global_unique(c, table, column)
        violations = c.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Foreign-key validation failed after school-scoped migration: "
                + repr([tuple(row) for row in violations[:10]])
            )
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.execute("PRAGMA legacy_alter_table=OFF")
        if was_foreign_keys:
            c.execute("PRAGMA foreign_keys=ON")

    return {"tables": tuple(SCOPED_UNIQUE_COLUMNS)}
