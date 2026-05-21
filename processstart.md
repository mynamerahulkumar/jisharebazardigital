# Bot process control: design and logic

This document explains how **`start.py`**, **`run_bot_once.py`**, **`stop.py`**, and **`status.py`** work together so you can reuse the same pattern in another algorithm / trading project.

## Mental model

| Script | Role |
|--------|------|
| `start.py` | **Foreground application entry**: runs the real bot (`main.main()`), while mirroring stdout/stderr into `logs/cli.log`. |
| `run_bot_once.py` | **Orchestrator for “bring up + peek”**: ensures at most one bot instance for this repo; if none, starts `start.py` **detached**; then tails `cli.log` for a short window and exits (it does **not** keep the bot alive). |
| `stop.py` | **Graceful shutdown**: finds bot processes for this repo and sends **SIGTERM**, waiting up to a timeout per PID. |
| `status.py` | **Observability**: reports running/stopped, **uptime**, recent log tails, optional live follow. |

The bot’s long-running workload lives in **`main.py`** (`TradingBot` and `main()`). `start.py` is a thin CLI/logging wrapper around that entrypoint.

---

## Shared idea: “is this process *our* bot?”

Several scripts duplicate the same **process-discovery** primitives so CLI tools stay self-contained:

1. **`REPO_ROOT`** – directory containing the script (the project root).
2. **`ENTRYPOINTS`** – tuple of launcher names, here `("start.py", "main.py")`. A process “belongs” to this project if its command line references one of these in a way that ties it to **`REPO_ROOT`**.

Concrete checks (with small variations per script):

- Parse `ps` output into `(pid, command)` or `(pid, elapsed, command)`.
- Resolve **absolute paths** for `REPO_ROOT/start.py` and `REPO_ROOT/main.py`. If any token in the command equals one of those paths → **match** (strong signal).
- Else, if the command’s tokens include a basename in `ENTRYPOINTS` (`start.py` / `main.py`), resolve the process **current working directory** (`cwd`) and require **`cwd == REPO_ROOT`** so you do not kill another project’s `main.py`.
- **`cwd` resolution**: prefer Linux-style `/proc/<pid>/cwd`; on macOS (no `/proc`), fall back to `lsof -a -p <pid> -d cwd -Fn`.
- Exclude the **current** tool PID so `ps` does not match the CLI itself.
- **`run_bot_once.py`** and **`status.py`** also ignore processes whose command mentions **`run_bot_once.py`**, **`status.py`**, or **`stop.py`** so helper CLIs are never classified as the bot.
- **`stop.py`** uses a slightly looser path check (substring of full command contains absolute script path) plus the same basename + `cwd` rule; it does not filter on `stop.py` / `status.py` in the same way, but typically those commands are short-lived.

**Porting tip:** In a new repo, keep **`ENTRYPOINTS`** aligned with how you actually launch the bot (e.g. `start.py` + whatever module runs the loop). If you rename files, update the tuple everywhere or centralize it in one small module.

---

## `start.py`

**Purpose:** Run the bot with **tee’d** console output for debugging and for `run_bot_once` / `status` to read from disk.

**Logic:**

1. Ensure `logs/` exists.
2. Open `logs/cli.log` in append mode.
3. Replace `sys.stdout` and `sys.stderr` with a **`TeeStream`** that writes to both the real terminal and the log file (with flush on write so tailers see output quickly).
4. Call `main()` from `main.py` and exit with its return code (`raise SystemExit(main())`).

**When to use:** Interactive runs, or as the **child** of `run_bot_once.py` when starting detached.

---

## `run_bot_once.py`

**Purpose:** **Idempotent start** + **brief log follow**; the parent process exits after `--seconds` (default **30**).

**Logic:**

1. **`find_bot_processes()`** – same family of rules as above; if any match → bot already running.
2. If **running:** print that it is reusing the existing process and print PID + command lines.
3. If **not running:** **`start_bot_detached()`**:
   - `subprocess.Popen([sys.executable, REPO_ROOT / "start.py"], cwd=REPO_ROOT, ...)`
   - `stdin` and `stdout`/`stderr` attached to **`os.devnull`** so the child is fully backgrounded.
   - `start_new_session=True` (and `close_fds=True`) so the bot is not tied to the parent’s TTY session.
4. **`follow_cli_log(seconds)`** – from the current end of `logs/cli.log`, poll every **0.25s** and print **new** bytes until the deadline. This gives immediate feedback after a fresh start without keeping a long-lived parent.

**CLI:** `--seconds <float>` (must be ≥ 0).

**Porting tip:** This script **does not** implement a supervisor (no restart on crash). For production you might add systemd, launchd, or a process manager; this pattern is “single instance + quick visibility.”

---

## `stop.py`

**Purpose:** Find all matching bot PIDs for this repo and stop them with **SIGTERM**.

**Logic:**

1. Build the same style of match list (excluding current PID).
2. If **no matches:** print that nothing is running; exit **0**.
3. For each match: `os.kill(pid, signal.SIGTERM)`, then **`wait_for_exit`** polling **`os.kill(pid, 0)`** every **0.25s** for up to **10s** per PID.
4. Exit **0** if every stop succeeded; **1** if any permission error or timeout (stderr explains which).

**Porting tip:** If your bot traps SIGTERM and needs longer to drain connections, increase **`STOP_TIMEOUT_SECONDS`** or send a different signal only after careful review.

---

## `status.py`

**Purpose:** Human-friendly **health + logs** in one command.

**Logic:**

1. **`find_bot_processes()`** using `ps` with **`etime`** so you can show **uptime** (e.g. `01-02:03:04` or `MM:SS`).
2. **`print_status`** – `STOPPED` vs `RUNNING`, list PID / uptime / full command string.
3. **`current_run_started_at`** – approximate **start time** of the current run: from `etime`, convert to seconds and subtract from “now”; if multiple PIDs, use the **minimum** (oldest) start among matches.
4. **Log tails** – predefined files under `logs/`:

   | Label | Path |
   |-------|------|
   | CLI | `logs/cli.log` |
   | SYSTEM | `logs/system.log` |
   | TRADING | `logs/trading.log` |
   | ERROR | `logs/error.log` |

   Default **`--lines`** (default **40**) tails each selected file.

5. **`latest_logged_start_at`** – fallback when process-based start time is unavailable: scans the last ~300 lines of `system.log` for **`Connecting websocket:`** and parses IST timestamps like `[YYYY-MM-DD HH:MM:SS IST]` from the start of lines.
6. **ERROR log scoping** – when a current-run start time is known, **`tail_error_lines_for_current_run`** groups error log lines into blocks keyed by IST timestamps and only keeps blocks **on or after** that start, so stale errors from prior runs are less noisy.

**CLI:**

- `--lines N`
- `--no-app-logs` – only **CLI** log (not system/trading/error)
- `--follow` – poll log files every **1s**, print new lines prefixed with `[CLI]`, `[SYSTEM]`, etc., until Ctrl+C

---

## Typical usage flow

1. **`python run_bot_once.py`** – start if needed, watch `cli.log` briefly.
2. **`python status.py`** – confirm RUNNING + uptime + recent logs; **`python status.py --follow`** for a poor man’s log aggregator.
3. **`python stop.py`** – graceful stop.
4. **`python start.py`** – run attached in a terminal with tee to `logs/cli.log` (no detach).

---

## Porting checklist (another algo project)

1. Copy or reimplement the four scripts with your **`ENTRYPOINTS`** and **log paths**.
2. Keep **`start.py`** as the single place that tees to **`logs/cli.log`** (or rename consistently).
3. Point **`run_bot_once.py`**’s detached child at that start script path.
4. Align **`status.py`**’s `LOG_FILES` and **websocket / timestamp** heuristics with how *your* app logs “session start.”
5. Verify **`ps`** column flags match your OS (`ps -axo` is common on macOS/BSD; adjust if Linux differs in your environment).
6. Test **two clones** of the repo side by side: `cwd` + absolute path logic should only ever match **one** tree.

This process layer stays intentionally small: **one logical bot per working copy**, easy **start / stop / status** from cron, SSH, or a wrapper, without binding to a specific exchange or strategy implementation.
