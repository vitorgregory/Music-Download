# Music-Download v6 - AI Coding Instructions

## Purpose
Provide actionable guidance for AI agents to be immediately productive in this Flask + Go + SQLite codebase.

## Big Picture

**Music-Download** is a Docker-first web application orchestrating Apple Music downloads in multiple formats (ALAC, AAC, Atmos). It acts as a controller for two external Go tools and manages a persistent download queue with retry logic.

### Architecture Overview
```
Frontend (Browser)
   ↓ HTTP/Socket.IO
Flask App + Queue Worker (Python)
   ├→ Wrapper Manager (spawns wrapper binary for login/2FA)
   ├→ Downloader Manager (spawns go run main.go for track downloads)
   └→ SQLite Queue DB (persistent state + retry scheduling)

External Services:
   - wrapper/wrapper binary (Apple Music authentication)
   - apple-music-downloader/main.go (track download logic)
```

### Key Components

#### 1. Process Management (`app/process_manager.py`)
Three manager classes orchestrate subprocess lifecycle:

**`WrapperManager`** — Apple Music login & 2FA
- `start(email, password)` — Spawns wrapper binary, captures credential prompts
- `_stream_logs()` — Daemon thread reading stdout line-by-line, detects "2fa" keyword
- `write_input(text)` — Sends 2FA codes via stdin
- **Pattern**: Thread-safe via `threading.Lock()` guarding running/needs_2fa state

**`DownloaderManager`** — Track downloads from Apple Music
- `start(link, args)` — Spawns `go run main.go --aac/--alac/--atmos link`
- `_stream_logs()` — Detects "select:" prompts, parses table/list of options
- `is_complete()` — **Fallback completion detector** (checks: exit code, timeout, success patterns)
- `_parse_options()` — Regex parser for multi-track selections (albums/artists)
- **Pattern**: Timestamp tracking (`last_output_at`) enables stall detection; logs stored in deque(maxlen=300)

**Global Singletons**: `wrapper` and `downloader` are module-level exports used by routes and queue_manager.

#### 2. Queue Management (`app/queue_manager.py`)
SQLite-backed task queue with exponential backoff:

**Schema**: `queue(id, link, format, status, title, progress, position, failed_attempts, next_try_at, created_at)`

**Statuses**: pending → processing → (completed | failed | cancelled | dead)

**`queue_worker()` Thread** — Runs continuously at import time (unless `DISABLE_QUEUE_WORKER=1`)
1. Pulls next pending task by position
2. Starts downloader via `downloader.start(link, args)`
3. **Main loop**: Extracts %, detects stalls, monitors for process exit
4. **Completion check (priority order)**:
   - Process exit code == 0? → success
   - `is_complete()` detected pattern? → success
   - Final percentage == 100%? → success
   - Else → failure, analyze error, retry or dead-letter

**Error Analysis** (`find_error_in_logs()`):
- Scans last 50 log lines for permanent patterns: "no codec found", "401", "geo restricted"
- Permanent errors → move to "dead" status (no retry)
- Transient errors → retry with backoff: 5s → 10s → 20s (configurable via `MAX_RETRIES`, `RETRY_BASE_SECONDS`)

#### 3. Frontend Integration (`app/routes.py` + Socket.IO + `app/static/script.js`)

**Unified API** (`GET /api/state`):
- Returns wrapper, downloader, queue status in one JSON payload
- Includes computed `downloader_stalled` flag (detects no output timeout)

**Socket.IO Events** (real-time selection prompts):
- Server emits `selection_required` when user selection detected in logs
- Client renders Bootstrap modal with parsed options
- User selects option → `POST /submit_selection` → sent to subprocess stdin

**Frontend Polling** (`script.js`):
- `fetchState()` runs every 1.5s via `setInterval`
- Renders queue as **Lidarr-style table** (not cards): ID | Title | Status | % | Format | Actions
- Status colors: pending (gray) | processing (yellow) | completed (green) | failed (red)
- Progress bar updates in real-time; stalled tasks show "Em espera..." warning

#### 4. UI Table Layout (`app/templates/index.html` + `style.css`)

Replaced card grid with responsive table:
- **Columns**: ID | Title | Status Badge | Progress Bar | Format | Action Buttons
- **Row indicators**: Left border color by status (green=success, yellow=processing, red=failed)
- **Responsive**: Mobile hides secondary columns, stacks inline
- **CSS Classes**: `.queue-table-container`, `.queue-row.status-*`, `.progress-bar`

## Critical Data Flows

### Download Workflow
```
1. User: POST /download {link, format}
   → add_to_queue(link, format, title)
   → status="pending"

2. queue_worker detects pending task
   → downloader.start(link, args) where args = ["--aac"|"--alac"|"--atmos"]
   → spawns: go run main.go [args] link

3. downloader._stream_logs() reads subprocess output line-by-line
   → Extracts % via regex: r'(\d{1,3})%'
   → Updates queue.progress every iteration
   → Detects "select:" keyword → parses_options() → emits Socket.IO event

4. Frontend receives selection_required event
   → Shows modal with checkboxes/buttons
   → User selects option

5. User: POST /submit_selection {choice}
   → downloader.write_input(choice)
   → sent to subprocess stdin

6. Subprocess completes, process.poll() returns exit code
   → queue_worker exits main loop
   → Checks: exit_code == 0 OR is_complete() OR final_perc == "100"
   → Mark completed or analyze failure

7. _handle_failure() decides retry vs dead-letter
```

### Why `is_complete()` Fallback Matters
- Go downloader may not flush stdout on success → readline() blocks indefinitely
- Solution: Fallback completion detector checks process exit + success patterns + timeout
- Prevents cards stuck in "processing" state

## Implementation Patterns & Conventions

### Thread Safety
- All manager state guarded by `threading.Lock()` (`self._lock`)
- Queue worker runs single thread (no concurrency)
- Frontend stateless (HTTP polling only)

### Naming
- Classes: `DownloaderManager`, `WrapperManager` (not "Processor")
- DB updates always use `update_status(task_id, status, title, progress)` helper
- ENV vars: `STALL_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_BASE_SECONDS`, `DISABLE_QUEUE_WORKER`

### Error Handling
- Permanent errors (DRM, 401, geo) → "dead" status (no retry)
- Transient errors (network, timeout) → retry with exponential backoff
- UI shows error in red badge with truncated message (from `progress` field)

### Testing
- Set `DISABLE_QUEUE_WORKER=1` env var to prevent auto-start in tests
- Import managers directly: `from app.process_manager import wrapper, downloader`
- Mock subprocess or use real Go binary for integration tests

## How to Modify This Codebase

### Adding a New Download Format
1. Update `DownloaderManager.start()` to accept new arg: `--myformat`
2. Update frontend quality radio options in `index.html`
3. Update `/download` route to validate format

### Adding a New Error Pattern
1. Add pattern to `find_error_in_logs()` in `queue_manager.py`
2. Decide if permanent (DRM-like) or transient (network-like)
3. Update `_is_permanent_error()` if needed

### Changing Queue Status Transitions
1. Modify SQL schema in `init_db()` (add columns, constraints)
2. Update worker loop in `queue_worker()` to handle new status
3. Update frontend table rendering in `renderQueueTable()` if new visual state

### Fixing Selection Modal Issues
- Edit `_parse_options()` regex in `process_manager.py` if output format changed
- Update modal HTML in `index.html` if styling needed
- Socket.IO event already wired; ensure it fires in `_stream_logs()`

## Common Pitfalls

❌ **Don't**:
- Extract completion status only from percentage (fragile, Go downloader may not output 100%)
- Block main thread if readline() fails to EOF
- Hardcode format flags; use args array
- Skip process.poll() checks before process.stdin.write()

✅ **Do**:
- Use `strip_ansi()` before regex matching on logs
- Emit Socket.IO events inside locks where state changes
- Check `process.returncode` after `process.poll() is not None`
- Use `is_complete()` as final fallback detector

## Key Files Reference

| File | Purpose |
|------|---------|
| [main.py](main.py) | Entry point; starts Flask + Socket.IO server |
| [app/__init__.py](app/__init__.py) | Flask app init, Socket.IO setup |
| [app/process_manager.py](app/process_manager.py) | Subprocess orchestration (wrapper + downloader) |
| [app/queue_manager.py](app/queue_manager.py) | Queue DB + worker thread + retry logic |
| [app/routes.py](app/routes.py) | Flask endpoints (login, download, selection, config) |
| [app/static/script.js](app/static/script.js) | Frontend polling + Socket.IO listener + table rendering |
| [app/templates/index.html](app/templates/index.html) | HTML (table markup for queue, modals) |
| [app/static/style.css](app/static/style.css) | Styling (queue-table-container, status colors) |
| [app/utils.py](app/utils.py) | Config handling, metadata scraping, helpers |
| [app/crypto.py](app/crypto.py) | Credential encryption (Fernet) |
| [requirements.txt](requirements.txt) | Python dependencies (Flask, Flask-SocketIO, etc.) |

## Developer Workflows

### Docker (Recommended)
```bash
docker-compose up --build
curl http://localhost:5000/health
```

### Local Development
```bash
python main.py
# Runs on 0.0.0.0:5000 with debug=False
```

### Running Tests
```bash
DISABLE_QUEUE_WORKER=1 pytest
```

### Inspecting Queue State
```bash
curl http://localhost:5000/api/state | jq '.queue'
```

## Important Runtime Facts

1. **Worker auto-start**: Queue worker thread starts at `import queue_manager` unless `DISABLE_QUEUE_WORKER=1` set
2. **Credential storage**: Encrypted via Fernet (see `crypto.py`), stored at `data/.credentials`
3. **Required paths**:
   - `apple-music-downloader/` (Go project root)
   - `wrapper/wrapper` (binary executable)
   - Changing these breaks subprocess start logic
4. **Logs capped**: ProcessManager stores max 300 entries; older entries discarded
5. **Selection parsing**: Depends on specific table/list format from Go downloader; format changes break modal

## Recent Changes (v7 - Latest)

✅ Task 1: Fixed "processing" card stuck issue (RESOLVED)
- Completely rewrote queue_worker (v4) with simple linear flow
- Removed dependency on unreliable `downloader.running` flag
- Loop now checks ONLY `process.poll() is not None` for exit detection
- Fixed deque slicing errors in `extract_percentage()` and `find_error_in_logs()`
- Cards now auto-transition to "Concluído" within seconds of download completion
- No manual stop button click needed

✅ Task 2: Restored selection modal for artist links (RESOLVED)
- Integrated Socket.IO for real-time selection events
- Server emits `selection_required` when user choice detected
- Expanded `selection_keywords` to catch variations: "please select", "select from", "options separated", "ranges supported"
- Frontend modal auto-shows with parsed options
- Works for single-track and artist/album selections

✅ Task 3: Refactored UI from cards to table layout (RESOLVED)
- Converted queue display to Lidarr-style table (ID | Title | Status | % | Format | Actions)
- Added status color indicators (left border: pending/processing/completed/failed)
- Table responsive on mobile, progress bar updates in real-time
- User confirmed: "very good, thanks, good work"

✅ Infrastructure Updates (v7)
- Added Flask-SocketIO and python-socketio to requirements.txt
- Updated main.py with `allow_unsafe_werkzeug=True` for containerized Socket.IO
- Deque-to-list conversion applied to all log processing functions
- Docker rebuild with `--no-cache` ensures fresh code deployment

## Integration Points

**External Binaries**:
- `wrapper/wrapper` — Apple Music login
- `apple-music-downloader/main.go` — Track downloading

**External Tools** (assumed in Docker image):
- ffmpeg, Bento4, sox (audio processing)

**Network**:
- `fetch_metadata()` uses HTTP to scrape Apple Music link info (timeout: 5s)
- Offline environments may need mocking

## Getting Started as AI Agent

1. **For bug fixes**: Read the relevant manager class + queue_worker logic
2. **For UI changes**: Modify table HTML + `renderQueueTable()` function
3. **For new features**: Identify which manager needs updating + routes.py endpoint
4. **For testing**: Set `DISABLE_QUEUE_WORKER=1`, import managers directly

If any section needs expansion or examples, ask for clarification on specific patterns or workflows.
