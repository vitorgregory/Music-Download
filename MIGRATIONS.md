# Migrations & Notes

This file documents non-reversible or notable runtime schema/behavior changes introduced in recent refactors.

## Queue schema changes

The `queue` table gained two new columns to support retries and scheduling:

- `failed_attempts INTEGER DEFAULT 0` — counts how many times a task has failed.
- `next_try_at TIMESTAMP NULL` — when to attempt the task again (used for exponential backoff).

These columns are added non-destructively by `init_db()` using `ALTER TABLE` where supported. If you manage the DB outside this code (manual scripts, backups), ensure you add these columns to avoid `next_try_at` selection logic skipping all tasks.

## Runtime behavior changes

- Automatic retries: failed tasks are retried with exponential backoff (base `RETRY_BASE_SECONDS`, multiplier 2^attempts).
- Dead-letter: tasks are moved to `status = 'dead'` when they hit the `MAX_RETRIES` threshold or when a permanent error is detected (e.g., DRM, 401/unauthorized).
- Worker auto-start: set `DISABLE_QUEUE_WORKER=1` to avoid auto-starting the queue worker when importing `app.queue_manager` (useful for tests/CI).

## Recommended migration steps

1. Backup `data/queue.db`.
2. Stop any running service using the DB.
3. Start the app once with the updated code (it will run `init_db()` and perform non-destructive ALTERs).
4. Inspect the `queue` table and verify `failed_attempts` and `next_try_at` columns exist.

If your environment doesn't permit `ALTER TABLE`, manually add the columns using your preferred SQLite client:

```sql
ALTER TABLE queue ADD COLUMN failed_attempts INTEGER DEFAULT 0;
ALTER TABLE queue ADD COLUMN next_try_at TIMESTAMP NULL;
```

## Rollback

To rollback, restore your `data/queue.db` backup. There is no automated downgrade path provided.
