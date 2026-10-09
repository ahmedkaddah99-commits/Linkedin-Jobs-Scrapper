"""Read publication head and checkpoints from the actual VPS database binding."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def check_catalog(env_path):
    checked_at = datetime.now(timezone.utc).isoformat()
    connection = None
    try:
        from dotenv import dotenv_values
        env = dotenv_values(env_path)
        overlay = Path('/etc/runr/acquisition-catalog.env')
        if overlay.is_file():
            env.update(dotenv_values(overlay))
        for key in ("DATABASE_BACKEND", "RUNR_ENV", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
            if env.get(key) is not None:
                os.environ[key] = str(env[key])
        # Never accidentally inspect/create an empty local DB and call it Turso.
        if not os.environ.get("TURSO_DATABASE_URL"):
            return {"checked_at": checked_at, "access_ok": False, "error": "remote_binding_missing"}
        sys.path.insert(0, "/opt/runr")
        from backend.database.connection import connect_database
        connection = connect_database(Path('/var/lib/runr/acquisition-data/runr.sqlite3'))
        head = connection.execute('SELECT h.publication_id,h.updated_at,p.status FROM acquisition_publication_head h LEFT JOIN acquisition_publications p ON p.publication_id=h.publication_id WHERE h.head_id=1').fetchone()
        count = connection.execute('SELECT COUNT(*) AS jobs FROM acquisition_publication_jobs pj JOIN acquisition_publication_head h ON h.publication_id=pj.publication_id AND h.head_id=1').fetchone()
        checkpoints = connection.execute('SELECT source,source_rowid,source_watermark,bootstrap_complete,updated_at FROM acquisition_publisher_checkpoints ORDER BY source LIMIT 3').fetchall()
        cycle = connection.execute('SELECT cycle_id,status,started_at,completed_at,updated_at,jobs_observed,jobs_new,jobs_rejected,jobs_published,error_code FROM acquisition_cycles ORDER BY scheduled_at DESC LIMIT 1').fetchone()
        tasks = connection.execute('SELECT status,COUNT(*) AS count FROM acquisition_tasks WHERE cycle_id=? GROUP BY status', (cycle['cycle_id'] if cycle else '',)).fetchall()
        return {"checked_at": checked_at, "access_ok": True, "binding": "vps_configured_turso",
                "head": dict(head) if head else {}, "head_jobs": int(count['jobs']),
                "checkpoints": [dict(row) for row in checkpoints],
                "latest_cycle": dict(cycle) if cycle else {},
                "tasks": [dict(row) for row in tasks]}
    except Exception as error:
        # Driver exception text can contain credential URLs; expose class only.
        return {"checked_at": checked_at, "access_ok": False, "error": type(error).__name__}
    finally:
        if connection is not None:
            connection.close()
