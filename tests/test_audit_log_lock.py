"""Two connections appending to the audit log at once never take the same seq."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from core.db import apply_schema, connect
from core.review import audit_log


def test_concurrent_appends_keep_the_chain(tmp_path):
    db = tmp_path / "case.db"
    conn = connect(db)
    apply_schema(conn)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.commit()
    errors: list[BaseException] = []

    def writer(name: str) -> None:
        c = connect(db)
        try:
            for i in range(40):
                with c:
                    audit_log.append(c, datetime.now(UTC), name, "test.view", {"i": i})
        except BaseException as err:  # noqa: BLE001
            errors.append(err)
        finally:
            c.close()

    threads = [threading.Thread(target=writer, args=(f"expert:{n}",)) for n in "ab"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 80
    assert audit_log.verify_chain(conn)
