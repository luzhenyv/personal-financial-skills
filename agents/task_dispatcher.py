#!/usr/bin/env python3
"""Task dispatcher — runs on Agent Server, polls Data Server REST API.

NO pfs.db.*, NO sqlalchemy, NO psycopg2 — pure HTTP + subprocess.

Usage:
    PFS_API_URL=http://100.124.x.x:8000 uv run python agents/task_dispatcher.py

Environment variables:
    PFS_API_URL         — Data Server REST API base URL (required)
    PFS_POLL_INTERVAL   — Seconds between polls when idle (default: 60)
    PFS_PROJECT_DIR     — Project root on Agent Server (default: /opt/pfs)
    PFS_TASK_TIMEOUT    — Max seconds per task execution (default: 600)
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import time

# Add project root to path so we can import skills._lib
PROJECT_DIR = os.environ.get("PFS_PROJECT_DIR", "/opt/pfs")
sys.path.insert(0, PROJECT_DIR)

from skills._lib.task_client import TaskClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [dispatcher] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dispatcher")

POLL_INTERVAL = int(os.environ.get("PFS_POLL_INTERVAL", "60"))
TASK_TIMEOUT = int(os.environ.get("PFS_TASK_TIMEOUT", "600"))

# Skill → script mapping for non-intelligence tasks
SCRIPT_MAP: dict[str, str] = {
    "company-profile:build_comps": "skills/company-profile/scripts/build_comps.py",
    "company-profile:generate_report": "skills/company-profile/scripts/generate_report.py",
    "thesis-tracker:create": "skills/thesis-tracker/scripts/thesis_cli.py",
    "thesis-tracker:update": "skills/thesis-tracker/scripts/thesis_cli.py",
    "thesis-tracker:check": "skills/thesis-tracker/scripts/thesis_cli.py",
    "thesis-tracker:catalyst": "skills/thesis-tracker/scripts/thesis_cli.py",
    "thesis-tracker:report": "skills/thesis-tracker/scripts/thesis_cli.py",
    "etl-coverage:check": "skills/etl-coverage/scripts/check_coverage.py",
}


def build_prompt(task: dict) -> str:
    """Build an OpenClaw prompt from a task dict."""
    skill = task.get("skill", "")
    action = task.get("action", "")
    ticker = task.get("ticker", "")
    params = task.get("params", {})

    parts = [f"Run the {skill} skill"]
    if action:
        parts.append(f"with action '{action}'")
    if ticker:
        parts.append(f"for ticker {ticker}")
    if params.get("description"):
        parts.append(f"— {params['description']}")

    return " ".join(parts)


def resolve_script(task: dict) -> list[str]:
    """Resolve a task to a script command + arguments."""
    key = f"{task['skill']}:{task.get('action', '')}"
    script = SCRIPT_MAP.get(key)
    if not script:
        raise ValueError(f"No script mapping for task key: {key}")

    cmd = ["uv", "run", "python", script]

    # For thesis_cli, the action is the subcommand
    if "thesis_cli" in script:
        action = task.get("action", "")
        cmd.append(action)

    if task.get("ticker"):
        cmd.append(task["ticker"])

    return cmd


def commit_artifacts(task: dict) -> str | None:
    """Commit artifact changes and return the SHA, or None."""
    artifacts_dir = os.path.join(PROJECT_DIR, "data", "artifacts")
    if not os.path.isdir(os.path.join(artifacts_dir, ".git")):
        log.warning("Artifacts dir is not a git repo, skipping commit")
        return None

    # Stage all changes
    subprocess.run(["git", "add", "--all"], cwd=artifacts_dir, check=True)

    # Check if there's anything to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=artifacts_dir,
        capture_output=True,
    )
    if result.returncode == 0:
        log.info("No artifact changes to commit")
        return None

    skill = task.get("skill", "unknown")
    ticker = task.get("ticker", "")
    action = task.get("action", "")
    msg = f"[{skill}] {ticker}: {action}".strip(": ")

    subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=artifacts_dir,
        check=True,
        capture_output=True,
    )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=artifacts_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Push if remote is configured
    try:
        subprocess.run(
            ["git", "push", "--quiet"],
            cwd=artifacts_dir,
            check=True,
            capture_output=True,
            timeout=30,
        )
        log.info("Pushed artifacts to remote")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log.warning("Push to remote failed — will retry on next commit")

    return sha


def execute_task(client: TaskClient, task: dict) -> None:
    """Execute a single task: claim → run → commit artifacts → complete/fail."""
    task_id = task["id"]
    skill = task.get("skill", "?")
    ticker = task.get("ticker", "")
    log.info("Claiming task %d: %s %s", task_id, skill, ticker)

    try:
        client.claim_task(task_id)
    except Exception:
        log.warning("Task %d already claimed, skipping", task_id)
        return

    try:
        if task.get("requires_intelligence", True):
            # Send to OpenClaw via CLI
            prompt = build_prompt(task)
            log.info("Sending to OpenClaw: %s", prompt[:100])
            result = subprocess.run(
                ["openclaw", "run", "--prompt", prompt],
                capture_output=True,
                text=True,
                timeout=TASK_TIMEOUT,
                cwd=PROJECT_DIR,
            )
            output = result.stdout + result.stderr
            if result.returncode != 0:
                raise RuntimeError(f"OpenClaw exited {result.returncode}: {output[-500:]}")
        else:
            # Run Python script directly
            cmd = resolve_script(task)
            log.info("Running script: %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TASK_TIMEOUT,
                cwd=PROJECT_DIR,
            )
            output = result.stdout + result.stderr
            if result.returncode != 0:
                raise RuntimeError(f"Script exited {result.returncode}: {output[-500:]}")

        # Commit any artifact changes
        sha = commit_artifacts(task)

        client.complete_task(
            task_id,
            result_summary=output[:2000] if output else "OK",
            git_commit_sha=sha,
        )
        log.info("Task %d completed (sha=%s)", task_id, sha or "none")

    except Exception as e:
        error_msg = str(e)[:2000]
        log.error("Task %d failed: %s", task_id, error_msg)
        try:
            client.fail_task(task_id, error=error_msg)
        except Exception:
            log.exception("Failed to report task %d failure to API", task_id)


def main():
    api_url = os.environ.get("PFS_API_URL")
    if not api_url:
        log.error("PFS_API_URL environment variable is required")
        sys.exit(1)

    client = TaskClient(base_url=api_url)
    log.info("Dispatcher started — polling %s every %ds", api_url, POLL_INTERVAL)

    while True:
        try:
            task = client.next_task()
            if not task:
                time.sleep(POLL_INTERVAL)
                continue

            execute_task(client, task)

        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception:
            log.exception("Unexpected error in poll loop")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
