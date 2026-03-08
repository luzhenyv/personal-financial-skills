# Database Schema

Three PostgreSQL tables. See `src/db/schema.sql` for full DDL.

## investment_theses

Core thesis record — one row per ticker.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | References companies.ticker |
| position | VARCHAR(10) | 'long' or 'short' |
| status | VARCHAR(20) | 'active', 'watching', 'closed' |
| core_thesis | TEXT | 1-2 sentence thesis statement |
| buy_reasons | JSONB | Array of reason objects |
| assumptions | JSONB | Array of {description, weight, kpi_metric, kpi_thresholds} |
| sell_conditions | JSONB | Array of condition strings |
| risk_factors | JSONB | Array of "where I might be wrong" items |
| target_price | NUMERIC(12,4) | Optional target price |
| stop_loss_price | NUMERIC(12,4) | Optional stop-loss trigger |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| closed_at | TIMESTAMP | When thesis was closed |
| close_reason | TEXT | Why the thesis was closed |

## thesis_updates

Append-only log of thesis-affecting events.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | |
| event_date | DATE | When the event happened |
| event_title | VARCHAR(255) | Short label |
| event_description | TEXT | What occurred |
| assumption_impacts | JSONB | {assumption_idx: {status, explanation}} |
| strength_change | VARCHAR(20) | 'strengthened', 'weakened', 'unchanged' |
| action_taken | VARCHAR(20) | 'hold', 'add', 'trim', 'exit' |
| conviction | VARCHAR(10) | 'high', 'medium', 'low' |
| notes | TEXT | |
| source | VARCHAR(50) | 'manual', 'earnings', 'catalyst' |
| created_at | TIMESTAMP | |

## thesis_health_checks

Point-in-time thesis evaluation snapshots.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | |
| check_date | DATE | |
| objective_score | NUMERIC(5,2) | 0-100, from quantitative KPIs |
| subjective_score | NUMERIC(5,2) | 0-100, from LLM judgment |
| composite_score | NUMERIC(5,2) | Weighted: 60% obj + 40% subj |
| assumption_scores | JSONB | Per-assumption breakdown |
| key_observations | JSONB | Array of observation strings |
| recommendation | VARCHAR(20) | 'hold', 'add', 'trim', 'exit' |
| recommendation_reasoning | TEXT | |
| created_at | TIMESTAMP | |
