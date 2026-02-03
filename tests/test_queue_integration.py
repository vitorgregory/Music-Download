import os
import time
import threading
import sqlite3
import pytest

os.environ['DISABLE_QUEUE_WORKER'] = '1'

from app import queue_manager
from app.queue_manager import init_db, add_to_queue, get_db_connection, start_worker, WORKER_STOP_EVENT


class FakeDownloader:
    def __init__(self):
        self.running = False
        self.logs = []

    def start(self, link, args=None):
        def run_sim():
            self.running = True
            for p in ['10%', '50%', '100%']:
                self.logs.append(p)
                time.sleep(0.2)
            self.running = False

        t = threading.Thread(target=run_sim)
        t.start()
        return True


def test_queue_worker_processes_task(tmp_path):
    # Ensure DB in repo path
    init_db()

    # Swap real downloader for fake
    real_downloader = queue_manager.downloader
    queue_manager.downloader = FakeDownloader()

    try:
        # Add a task
        add_to_queue('https://music.apple.com/us/album/1', 'alac', 'Test Album')

        # Start worker
        start_worker()

        # Wait up to 10s for task to complete
        deadline = time.time() + 10
        status = None
        while time.time() < deadline:
            conn = get_db_connection()
            row = conn.execute("SELECT status FROM queue ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            if row:
                status = row['status']
                if status in ('completed', 'failed', 'cancelled'):
                    break
            time.sleep(0.2)

        assert status == 'completed', f"Task did not complete, final status: {status}"
    finally:
        # Signal worker to stop
        WORKER_STOP_EVENT.set()
        queue_manager.downloader = real_downloader