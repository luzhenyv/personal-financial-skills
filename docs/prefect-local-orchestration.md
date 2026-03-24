# Prefect — Orchestration Guide

## Core Concepts

Prefect is a Python-native workflow orchestration tool. It adds scheduling, retries, observability, and deployment management around ordinary Python functions without requiring you to change how your business logic is structured.

Four primitives cover almost everything you need to know:

**Flow** — a Python function decorated with `@flow`. This is the unit Prefect tracks, schedules, and displays in the UI. Every run gets a unique run ID, start/end timestamps, and a state (Completed, Failed, etc.).

**Task** — a Python function decorated with `@task`, called from inside a flow. Tasks get individual retry logic, caching, and their own state transitions. A flow can contain zero or many tasks.

**Deployment** — a server-side record that pairs a flow entrypoint with a schedule, parameters, and a work pool. Creating a deployment is what makes a flow schedulable and triggerable from the UI or CLI. The repo deployments are declared in `prefect.yaml`.

**Work Pool + Worker** — a work pool is a named queue; a worker is a process that polls that queue and executes deployment runs locally. The `process` work pool type (used here) runs flows as subprocesses directly from the local filesystem — no code packaging or remote upload involved.

The runtime rule worth internalizing:

| What is running | What you get |
|---|---|
| Server only | UI is accessible |
| Server + deployments registered | Flows appear in the Deployments page |
| Server + deployments + worker | Flows actually execute when triggered |

A run created in the UI without a running worker will sit in `Pending` forever.

## How This Repo Uses Prefect

Prefect handles three recurring mechanical jobs. Business logic stays in `pfs/` — Prefect is purely the scheduling and execution shell around it.

| Deployment | Entrypoint | Schedule |
|---|---|---|
| `price-sync/local-price-sync` | `prefect/flows/price_sync.py:price_sync` | Weekdays 17:30 ET |
| `filing-check/local-filing-check` | `prefect/flows/filing_check.py:filing_check` | Daily 06:00 ET |
| `data-validation/local-data-validation` | `prefect/flows/data_validation.py:data_validation` | Sunday 02:00 ET |

All three deployments target the `pfs-local-pool` work pool and are declared in `prefect.yaml` — the single source of truth for deployment configuration.

## Running Locally

You need three things running: the server, registered deployments, and a worker.

### Step 1 — Initial setup (once per machine)

```bash
uv sync
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

Setting `PREFECT_API_URL` permanently points the CLI at your local server instead of spawning a temporary ephemeral one for each command.

### Step 2 — Start the server (Terminal 1)

```bash
uv run prefect server start --host 127.0.0.1 --port 4200
```

Open the UI at http://localhost:4200.

### Step 3 — Create the work pool (once, Terminal 2)

```bash
uv run prefect work-pool inspect pfs-local-pool >/dev/null 2>&1 || \
uv run prefect work-pool create pfs-local-pool --type process
```

### Step 4 — Register deployments (Terminal 2)

```bash
uv run prefect deploy --no-prompt --all --prefect-file prefect.yaml
```

This reads `prefect.yaml` and registers all three deployments. Re-run this any time you change schedules or add a new deployment.

### Step 5 — Start the worker (Terminal 3)

```bash
uv run prefect worker start --pool pfs-local-pool
```

Leave this running. It polls `pfs-local-pool` and executes any triggered runs.

## Triggering a Flow Run

### From the UI

1. Open **Deployments** at http://localhost:4200/deployments.
2. Click on a deployment (e.g. `local-price-sync`).
3. Click **Run > Quick run** in the top-right corner.
4. Navigate to **Flow Runs** to watch state transitions and logs in real time.

The worker must be running (Step 5) for the run to leave `Pending` state.

### From the CLI

```bash
uv run prefect deployment run "price-sync/local-price-sync"
uv run prefect deployment run "filing-check/local-filing-check"
uv run prefect deployment run "data-validation/local-data-validation"
```

Inspect recent runs:

```bash
uv run prefect flow-run ls --limit 10
```

## Recreating Deployments from Scratch

If the server state is lost or you are on a new machine:

```bash
uv run prefect work-pool create pfs-local-pool --type process
uv run prefect deploy --no-prompt --all --prefect-file prefect.yaml
```

`prefect.yaml` encodes all deployment names, schedules, timezones, and work pool assignments — no manual flags needed.
