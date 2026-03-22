-- ============================================
-- AGENT OPS: Unified Task Registry
-- ============================================
-- Run after schema.sql (02-agent-ops.sql in Docker init).
-- Single source of truth for ALL scheduled work:
-- mechanical (Prefect), intelligent (OpenClaw), event-driven, user-requested.

CREATE SCHEMA IF NOT EXISTS agent_ops;

CREATE TABLE agent_ops.tasks (
    id              SERIAL PRIMARY KEY,

    -- What to do
    type            VARCHAR(20) NOT NULL
                    CHECK (type IN ('immediate','scheduled','recurring','event_triggered')),
    skill           VARCHAR(50) NOT NULL,
    action          VARCHAR(50),
    ticker          VARCHAR(10),
    params          JSONB DEFAULT '{}',

    -- Who runs this task
    executor        VARCHAR(20) NOT NULL DEFAULT 'dispatcher'
                    CHECK (executor IN ('prefect','openclaw','dispatcher','script')),

    -- Scheduling
    trigger_cron    VARCHAR(100),
    trigger_event   VARCHAR(100),
    scheduled_at    TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,

    -- Lifecycle
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending','running','completed','failed','cancelled')),
    priority        INTEGER DEFAULT 5
                    CHECK (priority BETWEEN 1 AND 9),
    retries_left    INTEGER DEFAULT 2,

    -- Execution context
    server          VARCHAR(20),
    requires_intelligence BOOLEAN DEFAULT TRUE,

    -- Audit
    created_by      VARCHAR(50) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    -- Results
    result_summary  TEXT,
    error_message   TEXT,
    artifacts       JSONB DEFAULT '[]',
    git_commit_sha  VARCHAR(40)
);

-- Dispatcher polling (Agent Server tasks)
CREATE INDEX idx_tasks_pending ON agent_ops.tasks(status, priority, created_at)
    WHERE status = 'pending' AND executor IN ('openclaw','dispatcher','script');

-- Prefect flow matching
CREATE INDEX idx_tasks_prefect ON agent_ops.tasks(skill, status)
    WHERE executor = 'prefect' AND type = 'recurring';

-- General lookups
CREATE INDEX idx_tasks_ticker ON agent_ops.tasks(ticker);

CREATE INDEX idx_tasks_next_run ON agent_ops.tasks(next_run_at)
    WHERE type = 'recurring' AND status != 'cancelled';
