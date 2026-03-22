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

import glob
import logging
import os
import subprocess
import sys
import time

import yaml

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
SKILLS_DIR = os.path.join(PROJECT_DIR, "skills")


# ── Skill config loading ────────────────────────────────────────────────────


def load_skill_configs() -> dict[str, dict]:
    """Discover and load all ``config.yaml`` files under ``skills/``.

    Returns a dict keyed by skill name (e.g. ``"company-profile"``).
    """
    configs: dict[str, dict] = {}
    pattern = os.path.join(SKILLS_DIR, "*/config.yaml")
    for path in sorted(glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        if cfg and isinstance(cfg, dict) and "name" in cfg:
            configs[cfg["name"]] = cfg
            cfg["_dir"] = os.path.dirname(path)
            log.debug("Loaded skill config: %s from %s", cfg["name"], path)
    return configs


# Loaded once at startup, can be refreshed via SIGHUP or restart
SKILL_CONFIGS: dict[str, dict] = {}


def _discover_scripts(skill_dir: str) -> dict[str, str]:
    """Return a mapping of script basenames (minus .py) → full paths."""
    scripts_dir = os.path.join(skill_dir, "scripts")
    result: dict[str, str] = {}
    if os.path.isdir(scripts_dir):
        for fname in os.listdir(scripts_dir):
            if fname.endswith(".py"):
                result[fname[:-3]] = os.path.join(scripts_dir, fname)
    return result


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
    """Resolve a task to a script command + arguments using config.yaml.

    Discovery order:
    1. If the skill has a script matching the action name, use it directly.
    2. If the skill has a ``*_cli.py``-style unified CLI, use it with
       the action as a subcommand.
    3. If the skill has only one script and no CLI, run it without subcommands.
    """
    skill_name = task.get("skill", "")
    action = task.get("action", "").split()[0]  # strip flags like "check --all" → "check"
    cfg = SKILL_CONFIGS.get(skill_name)

    if not cfg:
        raise ValueError(f"Unknown skill: {skill_name!r} — no config.yaml found")

    skill_dir = cfg["_dir"]
    scripts = _discover_scripts(skill_dir)

    if not scripts:
        raise ValueError(f"Skill {skill_name!r} has no scripts in {skill_dir}/scripts/")

    # Strategy 1: exact match on action name (e.g. action="build_comps" → build_comps.py)
    if action in scripts:
        cmd = ["uv", "run", "python", scripts[action]]
        if task.get("ticker"):
            cmd.append(task["ticker"])
        return cmd

    # Strategy 2: unified CLI — a script with "cli" in the name takes subcommands
    cli_scripts = [s for s in scripts if "cli" in s]
    if cli_scripts:
        script_path = scripts[cli_scripts[0]]
        cmd = ["uv", "run", "python", script_path]
        if action:
            cmd.append(action)
        if task.get("ticker"):
            cmd.append(task["ticker"])
        return cmd

    # Strategy 3: single script — run it directly (no subcommand)
    if len(scripts) == 1:
        script_path = next(iter(scripts.values()))
        cmd = ["uv", "run", "python", script_path]
        if task.get("ticker"):
            cmd.append(task["ticker"])
        return cmd

    # Multiple scripts, no CLI, no action match
    raise ValueError(
        f"Cannot resolve action {action!r} for skill {skill_name!r}. "
        f"Available scripts: {list(scripts.keys())}"
    )


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

    # Determine intelligence requirement: task field > config.yaml > default True
    requires_intel = task.get("requires_intelligence")
    if requires_intel is None:
        cfg = SKILL_CONFIGS.get(skill, {})
        requires_intel = cfg.get("requires_intelligence", True)

    try:
        if requires_intel:
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


def match_event_to_skills(event: str, event_data: dict) -> list[dict]:
    """Given an event name and data, return matching skill+action pairs.

    Scans all loaded config.yaml triggers to find skills that should run.
    Returns a list of dicts with ``skill``, ``action``, and ``requires_intelligence``.
    """
    matches = []
    for name, cfg in SKILL_CONFIGS.items():
        for trigger in cfg.get("triggers", []):
            if trigger.get("event") != event:
                continue

            # Check filter criteria
            filt = trigger.get("filter", {})
            matched = True
            for key, expected in filt.items():
                actual = event_data.get(key)
                if isinstance(expected, list):
                    if actual not in expected:
                        matched = False
                elif isinstance(expected, str) and expected.startswith(">"):
                    threshold = float(expected[1:])
                    if not (isinstance(actual, (int, float)) and actual > threshold):
                        matched = False
                elif actual != expected:
                    matched = False

            if matched:
                matches.append({
                    "skill": name,
                    "action": trigger.get("action", ""),
                    "requires_intelligence": cfg.get("requires_intelligence", True),
                })
    return matches


def main():
    global SKILL_CONFIGS

    api_url = os.environ.get("PFS_API_URL")
    if not api_url:
        log.error("PFS_API_URL environment variable is required")
        sys.exit(1)

    # Load skill configs from config.yaml files
    SKILL_CONFIGS = load_skill_configs()
    log.info("Loaded %d skill configs: %s", len(SKILL_CONFIGS), list(SKILL_CONFIGS.keys()))

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
