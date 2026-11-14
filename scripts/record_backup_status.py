"""Called only after backup verification AND successful artifact upload."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storage import connect, remote_enabled
from datetime import datetime, timezone
if not remote_enabled():raise SystemExit('Remote database configuration required')
c=connect('unused')
try:
    with c:
        c.execute("INSERT OR IGNORE INTO admin_operations VALUES ('backup',?,'verified_uploaded')",(datetime.now(timezone.utc).isoformat(),))
        c.execute("UPDATE admin_operations SET checked_at=?,status='verified_uploaded' WHERE name='backup'",(datetime.now(timezone.utc).isoformat(),))
finally:c.close()
