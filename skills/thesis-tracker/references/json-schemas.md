# JSON Schemas

All thesis artifacts live in `data/artifacts/{TICKER}/thesis/`. Every JSON file must include `"schema_version": "1.0"`.

## Guidelines

- Use MCP tools (`get_financial_metrics`, `get_income_statements`, `get_company`) as the primary data source for KPI baselines
- Source qualitative content from company-profile artifacts when available
- Buy reasons and assumptions must be specific and falsifiable
- Assumption weights must sum to 100%
- Never overwrite update or health check history — always append

---

## `thesis.json`

Core thesis record — one per ticker.

```json
{
  "schema_version": "1.0",
  "ticker": "NVDA",
  "position": "long",
  "status": "active",
  "core_thesis": "NVDA is the picks-and-shovels play for AI infrastructure — dominant platform with durable CUDA moat",
  "buy_reasons": [
    {
      "title": "Dominant AI accelerator platform",
      "description": "70-80% market share in AI training GPUs with CUDA ecosystem creating massive switching costs"
    },
    {
      "title": "Exceptional profitability",
      "description": "55%+ net margins and 70%+ ROIC demonstrate pricing power and operating leverage"
    },
    {
      "title": "Expanding TAM through AI adoption",
      "description": "Enterprise, sovereign AI, and edge deployments broadening addressable market beyond hyperscalers"
    }
  ],
  "assumptions": [
    {
      "description": "Data Center revenue growth stays above 30% YoY",
      "weight": 0.40,
      "kpi_metric": "revenue_growth",
      "kpi_thresholds": {
        "excellent": 0.50,
        "good": 0.30,
        "warning": 0.15,
        "critical": 0.05
      }
    },
    {
      "description": "Gross margins remain above 65%",
      "weight": 0.30,
      "kpi_metric": "gross_margin",
      "kpi_thresholds": {
        "excellent": 0.72,
        "good": 0.65,
        "warning": 0.58,
        "critical": 0.50
      }
    },
    {
      "description": "No credible competitive threat erodes market share significantly",
      "weight": 0.30,
      "kpi_metric": null,
      "kpi_thresholds": null
    }
  ],
  "sell_conditions": [
    "Gross margins fall below 55% for two consecutive quarters",
    "A major CSP announces full shift away from NVIDIA GPUs",
    "Revenue growth turns negative YoY"
  ],
  "risk_factors": [
    "Custom silicon from hyperscalers (Google TPU, AWS Trainium) gains significant share",
    "Export controls expand to block sales to additional major markets",
    "AI investment cycle slows materially as ROI questioned"
  ],
  "target_price": 250.00,
  "stop_loss_price": 120.00,
  "created_at": "2025-11-01T12:00:00Z",
  "updated_at": "2025-11-01T12:00:00Z"
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | ✓ | Always `"1.0"` |
| `ticker` | string | ✓ | Upper-case ticker symbol |
| `position` | string | ✓ | `"long"` or `"short"` |
| `status` | string | ✓ | `"active"`, `"watching"`, or `"closed"` |
| `core_thesis` | string | ✓ | 1-2 sentence falsifiable thesis statement |
| `buy_reasons` | array | ✓ | 3-5 objects with `title` and `description` |
| `assumptions` | array | ✓ | 3-5 objects with `description`, `weight`, `kpi_metric`, `kpi_thresholds` |
| `sell_conditions` | array | ✓ | Specific, actionable exit triggers |
| `risk_factors` | array | ✓ | Bear case arguments |
| `target_price` | number | | Optional target price |
| `stop_loss_price` | number | | Optional stop-loss trigger |
| `created_at` | string | ✓ | ISO 8601 timestamp |
| `updated_at` | string | ✓ | ISO 8601 timestamp, updated on any change |

---

## `updates.json`

Append-only log of thesis-affecting events.

```json
{
  "schema_version": "1.0",
  "ticker": "NVDA",
  "updates": [
    {
      "event_date": "2025-11-20",
      "event_title": "Q3 FY2026 earnings beat",
      "event_description": "Revenue $35.1B vs $33.2B expected. Data Center +94% YoY. Gross margin 74.6%.",
      "assumption_impacts": {
        "0": {"status": "✓", "explanation": "DC revenue growth 94% — well above 30% threshold"},
        "1": {"status": "✓", "explanation": "Gross margin 74.6% — above 72% excellent threshold"},
        "2": {"status": "—", "explanation": "No change in competitive dynamics"}
      },
      "strength_change": "strengthened",
      "action_taken": "hold",
      "conviction": "high",
      "notes": "Blackwell ramp ahead of schedule. Guide implies continued strong growth.",
      "source": "earnings",
      "created_at": "2025-11-20T20:00:00Z"
    }
  ]
}
```

### Update Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_date` | string | ✓ | Date the event occurred (YYYY-MM-DD) |
| `event_title` | string | ✓ | Short label for the event |
| `event_description` | string | | What occurred — specific data points |
| `assumption_impacts` | object | | Map of assumption index → `{status, explanation}`. Status: `✓` / `⚠️` / `✗` / `—` |
| `strength_change` | string | ✓ | `"strengthened"`, `"weakened"`, or `"unchanged"` |
| `action_taken` | string | ✓ | `"hold"`, `"add"`, `"trim"`, or `"exit"` |
| `conviction` | string | ✓ | `"high"`, `"medium"`, or `"low"` |
| `notes` | string | | Additional context |
| `source` | string | | `"manual"`, `"earnings"`, `"catalyst"`, `"news"` |
| `created_at` | string | ✓ | ISO 8601 timestamp |

---

## `health_checks.json`

Point-in-time thesis evaluation snapshots.

```json
{
  "schema_version": "1.0",
  "ticker": "NVDA",
  "health_checks": [
    {
      "check_date": "2025-12-01",
      "objective_score": 85.0,
      "subjective_score": 78.0,
      "composite_score": 82.2,
      "assumption_scores": [
        {
          "assumption_idx": 0,
          "description": "Data Center revenue growth stays above 30% YoY",
          "weight": 0.40,
          "objective": 100.0,
          "subjective": 85.0,
          "combined": 94.0,
          "status": "✓ Intact"
        },
        {
          "assumption_idx": 1,
          "description": "Gross margins remain above 65%",
          "weight": 0.30,
          "objective": 80.0,
          "subjective": 75.0,
          "combined": 78.0,
          "status": "✓ Intact"
        },
        {
          "assumption_idx": 2,
          "description": "No credible competitive threat",
          "weight": 0.30,
          "objective": 50.0,
          "subjective": 70.0,
          "combined": 58.0,
          "status": "⚠️ Watch"
        }
      ],
      "key_observations": [
        "✓ Data Center revenue growth 94% — well above threshold",
        "✓ Gross margins holding at 74.6%",
        "⚠️ Custom silicon efforts from hyperscalers accelerating — monitor share trends"
      ],
      "recommendation": "hold",
      "recommendation_reasoning": "Thesis remains strong. Two of three assumptions intact, third warrants monitoring.",
      "created_at": "2025-12-01T10:00:00Z"
    }
  ]
}
```

### Health Check Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `check_date` | string | ✓ | Date of the evaluation (YYYY-MM-DD) |
| `objective_score` | number | ✓ | 0-100, from quantitative KPI data |
| `subjective_score` | number | ✓ | 0-100, from LLM qualitative judgment |
| `composite_score` | number | ✓ | 60% objective + 40% subjective |
| `assumption_scores` | array | ✓ | Per-assumption breakdown with objective, subjective, combined, status |
| `key_observations` | array | ✓ | What strengthened, weakened, and what to monitor |
| `recommendation` | string | ✓ | `"hold"`, `"add"`, `"trim"`, or `"exit"` |
| `recommendation_reasoning` | string | ✓ | 1-2 sentence justification |
| `created_at` | string | ✓ | ISO 8601 timestamp |

---

## `catalysts.json`

Upcoming events that could prove or disprove the thesis.

```json
{
  "schema_version": "1.0",
  "ticker": "NVDA",
  "catalysts": [
    {
      "id": 1,
      "event": "Q4 FY2026 Earnings",
      "expected_date": "2026-02-26",
      "expected_impact": "positive",
      "affected_assumptions": [0, 1],
      "notes": "Key test of Blackwell full-quarter revenue contribution and margin trajectory",
      "status": "pending",
      "resolved_date": null,
      "outcome": null,
      "created_at": "2025-11-20T20:00:00Z"
    },
    {
      "id": 2,
      "event": "US export control policy update",
      "expected_date": "2026-Q1",
      "expected_impact": "negative",
      "affected_assumptions": [2],
      "notes": "Potential expansion of chip export restrictions to additional countries",
      "status": "pending",
      "resolved_date": null,
      "outcome": null,
      "created_at": "2025-11-20T20:00:00Z"
    }
  ]
}
```

### Catalyst Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | number | ✓ | Sequential ID within the file |
| `event` | string | ✓ | Description of the event |
| `expected_date` | string | ✓ | Date or quarter (YYYY-MM-DD or YYYY-QN) |
| `expected_impact` | string | ✓ | `"positive"`, `"negative"`, or `"neutral"` |
| `affected_assumptions` | array | | Indices of assumptions this catalyst affects |
| `notes` | string | | Additional context |
| `status` | string | ✓ | `"pending"`, `"resolved"`, or `"expired"` |
| `resolved_date` | string | | Date resolved (YYYY-MM-DD), null if pending |
| `outcome` | string | | What actually happened, null if pending |
| `created_at` | string | ✓ | ISO 8601 timestamp |
