"""Apply services/agent/database/migrations/*.sql to the configured database, in order.

Applied filenames are recorded in a `schema_migrations` ledger the runner owns. A
migration whose first created table already exists is recorded without running —
"baselined" — which absorbs databases whose early migrations were applied by hand.
Each migration runs inside its own transaction, so the DDL and its ledger row land
(or fail) together.

Run with the agent service's interpreter, e.g.
    services/agent/.venv/bin/python infra/apply-migrations.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The agent service isn't an installed package; put its root on the path so its
# database modules import exactly as they do when the service runs. In the agent
# container this script sits inside the service root itself, so fall back to that.
_HERE = Path(__file__).resolve()
_REPO_AGENT = _HERE.parents[1] / "services" / "agent"
AGENT_ROOT = _REPO_AGENT if _REPO_AGENT.exists() else _HERE.parent
sys.path.insert(0, str(AGENT_ROOT))

from sqlalchemy import text  # noqa: E402

from database.connection import get_engine  # noqa: E402

MIGRATIONS_DIR = AGENT_ROOT / "database" / "migrations"

LEDGER_DDL = """\
create table if not exists schema_migrations (
    filename text primary key,
    applied_at timestamptz not null default now()
)"""


def _first_created_table(sql: str) -> str | None:
    match = re.search(r"create table (\w+)", sql, re.IGNORECASE)
    return match.group(1) if match else None


def _is_applied(conn, filename: str) -> bool:
    stmt = text("select 1 from schema_migrations where filename = :f")
    return conn.execute(stmt, {"f": filename}).first() is not None


def _table_exists(conn, table: str) -> bool:
    stmt = text("select to_regclass('public.' || :t) is not null")
    return bool(conn.execute(stmt, {"t": table}).scalar())


def _record(conn, filename: str) -> None:
    conn.execute(text("insert into schema_migrations (filename) values (:f)"), {"f": filename})


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(LEDGER_DDL))

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        with engine.begin() as conn:
            if _is_applied(conn, path.name):
                print(f"{path.name}: already applied")
                continue
            sql = path.read_text()
            table = _first_created_table(sql)
            if table is not None and _table_exists(conn, table):
                # Applied by hand before the ledger existed; record it, don't re-run it.
                _record(conn, path.name)
                print(f"{path.name}: baselined ({table} already exists)")
                continue
            # exec_driver_sql: multi-statement DDL needs the driver's simple query
            # protocol, and the file's `:` sequences must not parse as bind params.
            conn.exec_driver_sql(sql)
            _record(conn, path.name)
            print(f"{path.name}: applied")


if __name__ == "__main__":
    main()
