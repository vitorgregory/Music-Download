## Purpose
Provide compact, actionable guidance so AI coding agents are immediately productive in this repository.

## Big picture
- This project is a Docker-first Flask web UI that wraps an external Go-based Apple Music downloader. The web backend orchestrates two long-running subprocess types: the `wrapper` binary (login/2FA) and the Go downloader (invoked via `go run main.go`). See [main.py](main.py#L1-L3) and the Flask app in [app/routes.py](app/routes.py#L1-L20).
- Background queue processing runs in-process: `queue_worker()` in [app/queue_manager.py](app/queue_manager.py#L1-L20) starts a daemon thread on import and manages an SQLite queue at `data/queue.db`.

## Key components & responsibilities
- `app/process_manager.py`: implements `ProcessManager`, `WrapperManager`, and `DownloaderManager`. These classes handle subprocess lifecycle, log streaming, and user input collection (2FA / selection). Inspect parsing/regex logic for selection detection and table parsing. ([app/process_manager.py](app/process_manager.py#L1-L40)).
- `app/queue_manager.py`: persistent queue logic, status transitions, error heuristics and the worker loop. Changing DB schema, error heuristics, or worker behavior affects runtime behavior immediately because it runs on import. ([app/queue_manager.py](app/queue_manager.py#L1-L40)).
- `app/utils.py`: config handling (YAML at `apple-music-downloader/config.yaml`), metadata scraping, and helper regexes. Many behaviors (playlist generation, folder names) read this config. ([app/utils.py](app/utils.py#L1-L40)).
- `app/routes.py`: single-page UI endpoints and unified `/api/state` polling endpoint used by the frontend for logs, queue state and selection prompts. Use these endpoints when integrating frontend changes. ([app/routes.py](app/routes.py#L1-L40)).

## Important runtime facts / gotchas
- The queue worker thread starts automatically at import time. Avoid importing `app.queue_manager` in contexts where you don't want the background thread to run (tests, one-off scripts) unless you intend to run it. See `threading.Thread(... daemon=True).start()` at the end of [app/queue_manager.py](app/queue_manager.py#L340-L360).
- Credentials are stored base64-encoded in `data/.credentials` via `save_creds`/`load_creds` in [app/routes.py](app/routes.py#L1-L40).
- The downloader expects the `apple-music-downloader` folder to exist at repo root and the wrapper binary to be at `wrapper/wrapper` (see start logic in `WrapperManager.start` and `DownloaderManager.start`). Do not rename those paths unless you update the code.
- Logs are capped (ProcessManager keeps ~300 entries). Selection parsing relies on specific table/list formats produced by the Go downloader—changes to that output break selection parsing.

## How to run / developer workflows
- Docker (recommended):
```bash
docker-compose up --build -d
```
This is the canonical runtime (see `Dockerfile` and `docker-compose.yml`). The README contains the Docker-first guidance. ([README.md](README.md#L1-L5))
- Local development without Docker: run the Flask app directly:
```bash
python main.py
```
This launches Flask on `0.0.0.0:5000` with `debug=True` (see [main.py](main.py#L1-L3)).

## Common edit patterns for AI agents
- If you modify selection parsing, update both `_parse_options` in `DownloaderManager` and tests (if added). See regexes and parsing helpers in [app/process_manager.py](app/process_manager.py#L1-L80).
- When changing queue state semantics, update `queue_worker()` and SQL schema migration code in `init_db()` inside [app/queue_manager.py](app/queue_manager.py#L1-L40).
- Config keys are explicitly enumerated in `app/utils.py` (`STRING_CONFIG_KEYS`, `BOOL_CONFIG_KEYS`); adding a new config requires updating those sets and handling defaults.

## Integration points / external dependencies
- Externally required binaries & folders:
  - `apple-music-downloader/` (Go project with `main.go`) — used by `DownloaderManager.start`.
  - `wrapper/wrapper` (binary) — used by `WrapperManager.start`.
  - `ffmpeg`, `Bento4`, and other compiled tools are expected in Docker image (handled by `Dockerfile`).
- Network: metadata scraping uses direct HTTP requests (`requests.get`) in `fetch_metadata` (short timeout). Keep this in mind for offline tests or CI.

## Small examples (use when making edits)
- To reproduce a selection prompt locally: run the Go downloader against an album link and observe the console output format; the agent should then adapt `_parse_options` in `DownloaderManager` accordingly. Relevant code: [app/process_manager.py](app/process_manager.py#L120-L220).
- To inspect queue state via API: `GET /api/state` returns the unified JSON the frontend expects. Modify only if you update UI or polling behavior. ([app/routes.py](app/routes.py#L1-L40)).

## What not to change without discussion
- Do not silently change the import-time side effects in `queue_manager.py` (thread start). Tests and CI assume the current behavior.
- Avoid renaming the `apple-music-downloader` or `wrapper` directories without updating process start paths.

---
If any section is unclear or you want me to expand examples (e.g., exact request payloads, or adding minimal tests), tell me which parts to iterate on.
