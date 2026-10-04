"""Create the Tiger Data schema. Safe to re-run. Run from backend/:  python scripts/init_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

if not db.init_pool():
    sys.exit("Could not connect. Check DATABASE_URL in backend/.env")
db.apply_schema()
with db._pool.connection() as conn:
    tables = conn.execute(
        "SELECT hypertable_name FROM timescaledb_information.hypertables ORDER BY 1"
    ).fetchall()
print("hypertables:", [t[0] for t in tables])
db.close_pool()
