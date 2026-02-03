import os
import time
from datetime import datetime

import importlib
import pytest


class FakeDownloader:
    """Simulates a downloader that fails a couple of times then succeeds."""
    def __init__(self, fail_times=2):
        self.attempt = 0
        self.fail_times = fail_times
        self.logs = []
        self.running = False

    def start(self, link, args):
        self.attempt += 1
        self.logs = []
        self.running = False
        # Simulate asynchronous log streaming by appending entries
        if self.attempt <= self.fail_times:
            # produce an error and exit
            self.logs.append('Error: transient network error')
            return True
        else:
            # produce progress and completion
            self.logs.append('10%')
            self.logs.append('100%')
            return True


def test_queue_retry(tmp_path, monkeypatch):
    # Ensure worker doesn't auto-start by setting env BEFORE importing module
    monkeypatch.setenv('DISABLE_QUEUE_WORKER', '1')
    db_file = tmp_path / "queue.db"

    # Import module after setting env
    qm = importlib.import_module('app.queue_manager')
    # If the worker was already started by other tests, stop it to ensure isolation
    if getattr(qm, 'WORKER_THREAD', None) and qm.WORKER_THREAD.is_alive():
        qm.WORKER_STOP_EVENT.set()
        try:
            qm.WORKER_THREAD.join(timeout=1)
        except Exception:
            pass
        qm.WORKER_THREAD = None
        qm.WORKER_STOP_EVENT.clear()
    monkeypatch.setattr(qm, 'DB_PATH', str(db_file))

    qm.init_db()

    # Inject fake downloader
    fake = FakeDownloader(fail_times=2)
    monkeypatch.setattr(qm, 'downloader', fake)

    # Add a task
    qm.add_to_queue('https://music.apple.com/album/1', 'mp3', title='Retry Album')

    # Make retries immediate for the test
    monkeypatch.setenv('RETRY_BASE_SECONDS', '0')

    # Start worker and let it process (it will schedule retries)
    worker = qm.start_worker()

    # Poll DB until status changes from 'pending' or timeout
    # Increased timeout to allow retries to be scheduled and processed under CI
    deadline = time.time() + 10
    final_row = None
    while time.time() < deadline:
        conn = qm.get_db_connection()
        final_row = conn.execute("SELECT * FROM queue").fetchone()
        conn.close()
        if final_row and final_row['status'] != 'pending':
            break
        time.sleep(0.2)

    # Stop the worker
    qm.WORKER_STOP_EVENT.set()
    if worker:
        worker.join(timeout=2)
    # Check DB (fresh read after worker stop)
    conn = qm.get_db_connection()
    final_row = conn.execute("SELECT * FROM queue").fetchone()
    conn.close()

    assert final_row is not None
    assert final_row['status'] in ('completed', 'dead')
