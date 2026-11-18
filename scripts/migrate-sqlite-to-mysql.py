#!/usr/bin/env python3
"""Import a verified, standalone ANKA SQLite snapshot into an EMPTY MySQL database.

Requires: pip install mysql-connector-python
Example (PowerShell):
  $env:ANKA_MYSQL_PASSWORD = Read-Host "MySQL migration password"
  python scripts/migrate-sqlite-to-mysql.py --sqlite-snapshot D:\AnkaBackups\anka-...\anka.db --host 127.0.0.1 --database anka --user anka_migrator
  python scripts/migrate-sqlite-to-mysql.py ... --apply

Never pass the live IIS App_Data/anka.db as input. Never put credentials in source control.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from contextlib import closing

TABLES = (
    "books", "anka_users", "anka_works", "anka_editions",
    "anka_user_shelves", "anka_book_access", "anka_manual_entitlements",
    "anka_publisher_requests", "anka_book_moderation", "anka_publisher_submissions",
)
# Expected schema matches sql/mysql-schema.sql, and blocks silent loss of new fields.
COLUMNS = {
    "books": ("id","title","author","language","original_script","filename","bytes","created_utc"),
    "anka_users": ("id","email","display_name","password_hash","role","disabled","created_utc"),
    "anka_works": ("id","title","author","description","category","created_utc"),
    "anka_editions": ("book_id","work_id","language","script","translator","content_status","publisher_name","price_minor","currency"),
    "anka_user_shelves": ("user_id","book_id","added_utc"),
    "anka_book_access": ("book_id","access_mode","updated_utc"),
    "anka_manual_entitlements": ("user_id","book_id","granted_by","reason","granted_utc"),
    "anka_publisher_requests": ("user_id","statement","state","requested_utc","reviewed_utc"),
    "anka_book_moderation": ("book_id","uploader_id","rights_statement","state","reviewed_by","created_utc","reviewed_utc"),
    "anka_publisher_submissions": ("id","user_id","book_id","status","rights_statement","submitted_utc","reviewed_utc"),
}

def fingerprint(rows):
    """Order-independent full row digest, including nulls, UTF-8 content and primary keys."""
    digests = []
    for row in rows:
        encoded = json.dumps(row, ensure_ascii=False, separators=(",",":"), default=str).encode("utf-8")
        digests.append(hashlib.sha256(encoded).digest())
    h = hashlib.sha256()
    for digest in sorted(digests):
        h.update(digest)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-snapshot", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--apply", action="store_true", help="Copy records only after validating empty target.")
    args = parser.parse_args()
    dbfile = args.sqlite_snapshot.resolve(strict=True)
    if dbfile.name.lower() != "anka.db" or "app_data" in [x.lower() for x in dbfile.parts]:
        parser.error("Input must be an isolated anka.db backup, NEVER live App_Data.")
    if any(Path(str(dbfile)+s).exists() for s in ("-wal","-shm","-journal")):
        parser.error("Snapshot contains SQLite sidecars; create a consistent standalone backup first.")
    if not os.environ.get("ANKA_MYSQL_PASSWORD"):
        parser.error("ANKA_MYSQL_PASSWORD environment variable is required.")
    try:
        import mysql.connector
    except ImportError as exc:
        raise SystemExit("Install mysql-connector-python before migration.") from exc

    # Immutable read-only mode prevents accidental sidecar creation and modifications.
    source_uri = dbfile.as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite source integrity check failed.")
        source.row_factory = sqlite3.Row
        source_tables = {r[0] for r in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        contents = {}
        for table in TABLES:
            if table not in source_tables:
                contents[table] = []
                continue
            actual = [r[1] for r in source.execute("PRAGMA table_info(" + table + ")")]
            if set(actual) != set(COLUMNS[table]):
                raise RuntimeError("Unexpected columns in "+table+": "+str(actual)+
                                   "; update the migration schema before proceeding.")
            contents[table] = [tuple(row[col] for col in COLUMNS[table])
                               for row in source.execute("SELECT * FROM "+table)]

    conn = mysql.connector.connect(host=args.host, port=args.port,
        database=args.database, user=args.user,
        password=os.environ["ANKA_MYSQL_PASSWORD"], charset="utf8mb4",
        use_unicode=True, autocommit=False)
    try:
        with closing(conn.cursor()) as cur:
            schema_path = Path(__file__).resolve().parents[1] / "sql" / "mysql-schema.sql"
            for statement in schema_path.read_text(encoding="utf-8").split(";"):
                if "CREATE TABLE" in statement.upper():
                    cur.execute(statement)
            conn.commit()  # DDL commits implicitly; only the fresh empty target is allowed.
            for table in TABLES:
                cur.execute("SELECT COUNT(*) FROM "+table)
                if cur.fetchone()[0]:
                    raise RuntimeError("MySQL target is NOT empty: "+table+
                                       ". Refusing to overwrite existing data.")
            print("Source verified. Table counts:")
            for table in TABLES:
                print("  {:<28} {}".format(table, len(contents[table])))
            if not args.apply:
                print("DRY RUN only. Re-run with --apply after reviewing counts.")
                return
            for table in TABLES:
                rows=contents[table]
                if not rows:
                    continue
                columns=COLUMNS[table]
                sql="INSERT INTO "+table+" ("+",".join("["+c+"]" for c in columns)+") VALUES ("+",".join(["%s"]*len(columns))+")"
                # MySQL identifiers use backticks; allowlisted names are not user input.
                sql=sql.replace("[","\x60").replace("]","\x60")
                cur.executemany(sql, rows)
            for table in TABLES:
                cur.execute("SELECT "+",".join("\x60"+c+"\x60" for c in COLUMNS[table])+" FROM "+table)
                expected = fingerprint(contents[table])
                actual = fingerprint(cur.fetchall())
                if expected != actual:
                    raise RuntimeError("MySQL verification failed on "+table+
                                       "; rolling back imported rows.")
            conn.commit()
            print("SUCCESS: all "+str(len(TABLES))+
                  " tables matched full SHA-256 row fingerprints. MySQL committed.")
            print("Original SQLite snapshot and EPUB files were not modified.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("MIGRATION BLOCKED:",str(exc),file=sys.stderr)
        sys.exit(1)
