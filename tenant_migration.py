"""Safe, additive bootstrap migration for the original single-school VICORA database.

This is a compatibility bridge, not the completed multi-tenant security layer.
All existing rows are assigned to one immutable legacy school identity. New
rows created by old single-school code inherit that identity until each
write path is upgraded to supply an authenticated school_id explicitly.
"""
import secrets
import uuid

LEGACY_SCHOOL_TABLES = (
    "admins", "classes", "subjects", "students", "questions", "exams",
    "sessions", "messages", "answers", "theory_marks", "proctor_events",
    "android_host_devices", "android_sync_receipts", "android_sync_conflicts",
    "android_sync_outbox", "audit",
)


def migrate_legacy_school(connection):
    """Assign all pre-existing school records to one stable legacy tenant."""
    c = connection
    c.execute("SAVEPOINT vicora_legacy_school_bootstrap")
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS schools (
            school_id TEXT PRIMARY KEY,
            school_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'approved',
            is_legacy_default INTEGER NOT NULL DEFAULT 0,
            created_ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            approved_ts INTEGER
        )""")
        if not c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone():
            raise RuntimeError("settings table must exist before the school migration")

        def setting(key):
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row and row[0] else ""

        school_id = setting("vicora_legacy_school_id") or str(uuid.uuid4())
        school_code = setting("vicora_legacy_school_code") or (
            "VIC-" + secrets.token_hex(4).upper()
        )
        school_name = setting("school_name").strip() or "VICORA Legacy School"
        c.execute("""INSERT OR IGNORE INTO schools
            (school_id,school_code,name,status,is_legacy_default,approved_ts)
            VALUES(?,?,?,'approved',1,strftime('%s','now'))""",
            (school_id, school_code, school_name[:120]))
        existing = c.execute(
            "SELECT school_code FROM schools WHERE school_id=?", (school_id,)
        ).fetchone()
        if not existing:
            raise RuntimeError("Legacy school identity conflicts with an existing school")
        school_code = existing[0]
        settings_columns = {row[1] for row in c.execute("PRAGMA table_info(settings)")}
        if "school_id" in settings_columns:
            c.execute("INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('vicora_legacy_school_id',?,?)",
                      (school_id, school_id))
            c.execute("INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('vicora_legacy_school_code',?,?)",
                      (school_code, school_id))
        else:
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('vicora_legacy_school_id',?)",
                      (school_id,))
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('vicora_legacy_school_code',?)",
                      (school_code,))

        for table in LEGACY_SCHOOL_TABLES:
            if not c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                continue
            columns = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
            if "school_id" not in columns:
                c.execute(f"ALTER TABLE {table} ADD COLUMN school_id TEXT")
            c.execute(
                f"UPDATE {table} SET school_id=? WHERE school_id IS NULL OR school_id=''",
                (school_id,))
            c.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_school_id ON {table}(school_id)")
            trigger_name = f"trg_{table}_legacy_school_default"
            legacy_literal = "'" + school_id.replace("'", "''") + "'"
            c.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
            c.execute(f"""CREATE TRIGGER {trigger_name}
                AFTER INSERT ON {table}
                WHEN NEW.school_id IS NULL OR NEW.school_id=''
                BEGIN
                  UPDATE {table} SET school_id={legacy_literal} WHERE rowid=NEW.rowid;
                END""")
        c.execute("RELEASE SAVEPOINT vicora_legacy_school_bootstrap")
        return {"school_id": school_id, "school_code": school_code, "school_name": school_name}
    except Exception:
        c.execute("ROLLBACK TO SAVEPOINT vicora_legacy_school_bootstrap")
        c.execute("RELEASE SAVEPOINT vicora_legacy_school_bootstrap")
        raise
