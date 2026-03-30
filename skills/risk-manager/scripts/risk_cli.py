#!/usr/bin/env python3
"""Risk Manager CLI — portfolio-level risk monitoring and alerting.

Computes concentration, risk metrics, thesis health, and rule-based alerts
for the portfolio as a whole.  Adapts the TradingAgents multi-perspective
risk debate pattern into a structured data pipeline.

Usage::

    uv run python skills/risk-manager/scripts/risk_cli.py check             # Full risk report
    uv run python skills/risk-manager/scripts/risk_cli.py alerts            # Show active alerts
    uv run python skills/risk-manager/scripts/risk_cli.py rules             # Show risk rules
    uv run python skills/risk-manager/scripts/risk_cli.py rules --set key=val
    uv run python skills/risk-manager/scripts/risk_cli.py report            # Generate markdown
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Path setup ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30

# ── Default rules ────────────────────────────────────────────

DEFAULT_RULES: dict[str, float] = {
    "max_single_position_pct": 0.15,
    "max_sector_pct": 0.40,
    "max_portfolio_beta": 1.5,
    "min_thesis_health_score": 40,
    "max_drawdown_alert_pct": -0.10,
}

# ── I/O ──────────────────────────────────────────────────────

io = ArtifactIO("_portfolio", "risk")


def _get(client: httpx.Client, path: str, **params: object) -> dict | list | None:
    """GET helper — returns parsed JSON or None on error."""
    try:
        resp = client.get(path, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"  ⚠  {path} → {exc.response.status_code}", file=sys.stderr)
        return None
    except httpx.ConnectError:
        print(f"  ✗  Cannot reach API at {client.base_url}", file=sys.stderr)
        sys.exit(1)


def _post(client: httpx.Client, path: str, **params: object) -> dict | None:
    """POST helper (query-param based, no body)."""
    try:
        resp = client.post(path, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"  ⚠  {path} → {exc.response.status_code}", file=sys.stderr)
        return None
    except httpx.ConnectError:
        print(f"  ✗  Cannot reach API at {client.base_url}", file=sys.stderr)
        sys.exit(1)


def _load_rules() -> dict[str, float]:
    """Load rules from artifact, falling back to defaults."""
    data = io.read_json("rules.json")
    if data and "rules" in data:
        merged = {**DEFAULT_RULES, **data["rules"]}
        return merged
    return dict(DEFAULT_RULES)


def _save_rules(rules: dict[str, float]) -> None:
    io.write_json("rules.json", {"rules": rules})


# ── Concentration ────────────────────────────────────────────


def _compute_concentration(allocation: dict) -> dict:
    """Compute concentration metrics from allocation data."""
    by_position = allocation.get("by_position", [])
    by_sector = allocation.get("by_sector", [])

    weights = [p["weight"] / 100.0 for p in by_position]

    top_position_pct = weights[0] if weights else 0.0
    top3_pct = sum(weights[:3]) if len(weights) >= 3 else sum(weights)

    # HHI = sum of squared weights
    hhi = sum(w * w for w in weights) if weights else 0.0

    sector_weights = {
        s["sector"]: round(s["weight"] / 100.0, 4) for s in by_sector
    }

    return {
        "top_position_pct": round(top_position_pct, 4),
        "top3_positions_pct": round(top3_pct, 4),
        "sector_weights": sector_weights,
        "hhi_index": round(hhi, 4),
    }


# ── Thesis Health ────────────────────────────────────────────


def _collect_thesis_health(positions: list[dict]) -> dict:
    """Read thesis artifacts for each position and summarize health."""
    scores = []
    below_threshold = []
    without_thesis = []
    stale_checks = []
    rules = _load_rules()
    min_score = rules.get("min_thesis_health_score", 40)

    now = datetime.now(timezone.utc)

    for pos in positions:
        ticker = pos.get("ticker", "")
        if not ticker:
            continue

        thesis = read_artifact_json(ticker, "thesis", "thesis.json")
        health_checks = read_artifact_json(ticker, "thesis", "health_checks.json")

        if not thesis:
            without_thesis.append(ticker)
            continue

        if health_checks and health_checks.get("entries"):
            latest = health_checks["entries"][-1]
            score = latest.get("composite_score")
            if score is not None:
                scores.append(score)
                if score < min_score:
                    below_threshold.append(ticker)

            # Check staleness (> 30 days since last health check)
            check_date = latest.get("date")
            if check_date:
                try:
                    dt = datetime.fromisoformat(check_date.replace("Z", "+00:00"))
                    if (now - dt).days > 30:
                        stale_checks.append(ticker)
                except (ValueError, TypeError):
                    stale_checks.append(ticker)
            else:
                stale_checks.append(ticker)
        else:
            stale_checks.append(ticker)

    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "avg_health_score": avg_score,
        "positions_below_50": below_threshold,
        "positions_without_thesis": without_thesis,
        "stale_checks": stale_checks,
    }


# ── Alerts ───────────────────────────────────────────────────


def _evaluate_alerts(
    concentration: dict,
    risk_metrics: dict,
    thesis_health: dict,
    rules: dict[str, float],
) -> list[dict]:
    """Generate alerts by comparing metrics against rules."""
    alerts = []
    now = datetime.now(timezone.utc).isoformat()

    # Concentration: single position
    if concentration["top_position_pct"] > rules["max_single_position_pct"]:
        alerts.append({
            "type": "concentration",
            "severity": "warning",
            "message": (
                f"Top position at {concentration['top_position_pct']:.1%} "
                f"(limit: {rules['max_single_position_pct']:.0%})"
            ),
            "timestamp": now,
        })

    # Concentration: sector
    for sector, weight in concentration.get("sector_weights", {}).items():
        if weight > rules["max_sector_pct"]:
            alerts.append({
                "type": "concentration",
                "severity": "warning",
                "message": f"{sector} sector at {weight:.1%} (limit: {rules['max_sector_pct']:.0%})",
                "timestamp": now,
            })

    # Portfolio beta
    port_beta = risk_metrics.get("portfolio_beta")
    if port_beta is not None and port_beta > rules["max_portfolio_beta"]:
        alerts.append({
            "type": "risk",
            "severity": "warning",
            "message": f"Portfolio beta {port_beta:.2f} exceeds limit {rules['max_portfolio_beta']:.1f}",
            "timestamp": now,
        })

    # Drawdown
    max_dd = risk_metrics.get("max_drawdown_30d")
    if max_dd is not None and max_dd < rules["max_drawdown_alert_pct"]:
        alerts.append({
            "type": "drawdown",
            "severity": "critical",
            "message": (
                f"30-day max drawdown {max_dd:.2%} breached "
                f"alert threshold {rules['max_drawdown_alert_pct']:.0%}"
            ),
            "timestamp": now,
        })

    # Thesis health
    min_score = rules["min_thesis_health_score"]
    for ticker in thesis_health.get("positions_below_50", []):
        alerts.append({
            "type": "thesis_health",
            "severity": "critical",
            "message": f"{ticker} thesis score below {min_score:.0f} — review position",
            "timestamp": now,
        })

    for ticker in thesis_health.get("positions_without_thesis", []):
        alerts.append({
            "type": "thesis_health",
            "severity": "warning",
            "message": f"{ticker} has no investment thesis — create one",
            "timestamp": now,
        })

    return alerts


def _append_alerts(new_alerts: list[dict]) -> None:
    """Append alerts to the alerts.json history file."""
    existing = io.read_json("alerts.json") or {"entries": []}
    entries = existing.get("entries", [])
    entries.extend(new_alerts)
    io.write_json("alerts.json", {"entries": entries})


# ── CLI Commands ─────────────────────────────────────────────


def cmd_check(args: argparse.Namespace) -> None:
    """Full risk check — compute metrics, evaluate rules, write report."""
    api_url = args.api_url
    portfolio_id = args.portfolio_id

    rules = _load_rules()

    with httpx.Client(base_url=api_url) as client:
        # 1. Get positions and allocation
        print("Collecting portfolio data...")
        positions = _get(client, "/api/portfolio/positions", portfolio_id=portfolio_id)
        if positions is None:
            print("  ✗  Could not fetch positions. Is the API running?", file=sys.stderr)
            sys.exit(1)

        if not positions:
            print("  ⚠  Portfolio has no positions — nothing to analyze.")
            return

        allocation = _get(client, "/api/portfolio/allocation", portfolio_id=portfolio_id) or {}
        print(f"  ✓  {len(positions)} positions")

        # 2. Compute concentration
        print("Computing concentration metrics...")
        concentration = _compute_concentration(allocation)
        print(f"  ✓  HHI={concentration['hhi_index']:.3f}, top position={concentration['top_position_pct']:.1%}")

        # 3. Compute risk metrics via API
        print("Computing risk metrics (this may take a moment)...")
        risk_data = _post(
            client,
            "/api/analysis/risk/portfolio",
            portfolio_id=portfolio_id,
            benchmark="SPY",
        )
        if risk_data is None:
            print("  ⚠  Risk computation failed — using partial data", file=sys.stderr)
            risk_data = {}

        risk_metrics = {
            "portfolio_beta": risk_data.get("portfolio_beta"),
            "max_drawdown_30d": risk_data.get("max_drawdown_30d"),
            "sharpe_ratio_90d": risk_data.get("sharpe_ratio_90d"),
            "sortino_ratio_90d": risk_data.get("sortino_ratio_90d"),
            "var_95_1d": risk_data.get("var_95_1d"),
        }
        beta_str = f"{risk_metrics['portfolio_beta']:.2f}" if risk_metrics['portfolio_beta'] is not None else "N/A"
        print(f"  ✓  beta={beta_str}, VaR(95%)=${risk_metrics.get('var_95_1d', 'N/A')}")

    # 4. Thesis health
    print("Checking thesis health...")
    thesis_health = _collect_thesis_health(positions)
    score_str = f"{thesis_health['avg_health_score']:.0f}" if thesis_health['avg_health_score'] is not None else "N/A"
    print(f"  ✓  avg score={score_str}, without thesis={len(thesis_health['positions_without_thesis'])}")

    # 5. Evaluate alerts
    alerts = _evaluate_alerts(concentration, risk_metrics, thesis_health, rules)
    if alerts:
        _append_alerts(alerts)
        print(f"\n⚠  {len(alerts)} alert(s) generated:")
        for a in alerts:
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            print(f"  {icon} [{a['type']}] {a['message']}")
    else:
        print("\n✓  No alerts — all metrics within limits.")

    # 6. Write risk_report.json
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "concentration": concentration,
        "risk_metrics": risk_metrics,
        "risk_detail": {
            k: v for k, v in risk_data.items()
            if k not in ("portfolio_id", "benchmark", "error")
        } if risk_data else {},
        "thesis_health": thesis_health,
        "alerts": alerts,
        "rules": rules,
    }
    path = io.write_json("risk_report.json", report)
    print(f"\n✓  Risk report written to {path}")


def cmd_alerts(args: argparse.Namespace) -> None:
    """Show current alerts from alerts.json."""
    data = io.read_json("alerts.json")
    if not data or not data.get("entries"):
        print("No alerts recorded yet. Run 'check' first.")
        return

    entries = data["entries"]

    # Show last N alerts (default 20)
    limit = args.limit
    recent = entries[-limit:]

    print(f"Showing last {len(recent)} of {len(entries)} alerts:\n")
    for a in recent:
        icon = "🔴" if a.get("severity") == "critical" else "🟡"
        ts = a.get("timestamp", "")[:19]
        print(f"  {icon} [{ts}] [{a.get('type', '?')}] {a.get('message', '')}")


def cmd_rules(args: argparse.Namespace) -> None:
    """Show or update risk rules."""
    rules = _load_rules()

    if args.set:
        for kv in args.set:
            if "=" not in kv:
                print(f"  ✗  Invalid format '{kv}' — use key=value", file=sys.stderr)
                continue
            key, val = kv.split("=", 1)
            key = key.strip()
            if key not in DEFAULT_RULES:
                print(f"  ⚠  Unknown rule '{key}'. Valid: {', '.join(DEFAULT_RULES.keys())}")
                continue
            try:
                rules[key] = float(val)
                print(f"  ✓  {key} = {float(val)}")
            except ValueError:
                print(f"  ✗  Cannot parse '{val}' as float", file=sys.stderr)

        _save_rules(rules)
        print(f"\nRules saved to {io.path / 'rules.json'}")
    else:
        print("Current risk rules:\n")
        for k, v in sorted(rules.items()):
            default = DEFAULT_RULES.get(k, "?")
            marker = "" if v == default else f"  (default: {default})"
            if "pct" in k:
                print(f"  {k}: {v:.0%}{marker}")
            else:
                print(f"  {k}: {v}{marker}")

        print(f"\nEdit: risk_cli.py rules --set max_sector_pct=0.35")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate markdown narrative from risk_report.json."""
    data = io.read_json("risk_report.json")
    if not data:
        print("No risk report found. Run 'check' first.")
        return

    md = _render_markdown(data)
    path = io.write_text("risk_report.md", md)
    print(f"✓  Markdown report written to {path}")

    if args.persist:
        _persist_report(md, args.api_url)


def _persist_report(md: str, api_url: str) -> None:
    """POST the report to the analysis reports endpoint."""
    with httpx.Client(base_url=api_url) as client:
        try:
            resp = client.post(
                "/api/analysis/reports",
                json={
                    "ticker": "_PORTFOLIO",
                    "report_type": "risk_report",
                    "title": "Portfolio Risk Report",
                    "content_md": md,
                    "generated_by": "risk-manager",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            print("  ✓  Report persisted to database")
        except Exception as exc:
            print(f"  ⚠  Could not persist report: {exc}", file=sys.stderr)


def _render_markdown(data: dict) -> str:
    """Render a risk report dict into readable markdown."""
    lines = ["# Portfolio Risk Report", ""]
    lines.append(f"*Generated: {data.get('generated_at', 'unknown')[:19]}*")
    lines.append("")

    # Concentration
    conc = data.get("concentration", {})
    lines.append("## Concentration")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Top position | {conc.get('top_position_pct', 0):.1%} |")
    lines.append(f"| Top 3 positions | {conc.get('top3_positions_pct', 0):.1%} |")
    lines.append(f"| HHI index | {conc.get('hhi_index', 0):.3f} |")
    lines.append("")

    sector_weights = conc.get("sector_weights", {})
    if sector_weights:
        lines.append("### Sector Weights")
        lines.append("")
        lines.append("| Sector | Weight |")
        lines.append("|--------|--------|")
        for sector, w in sorted(sector_weights.items(), key=lambda x: -x[1]):
            lines.append(f"| {sector} | {w:.1%} |")
        lines.append("")

    # Risk Metrics
    rm = data.get("risk_metrics", {})
    lines.append("## Risk Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    def _fmt(v, fmt_str=".2f"):
        return f"{v:{fmt_str}}" if v is not None else "N/A"

    lines.append(f"| Portfolio beta | {_fmt(rm.get('portfolio_beta'))} |")
    lines.append(f"| 30-day max drawdown | {_fmt(rm.get('max_drawdown_30d'), '.2%')} |")
    lines.append(f"| 90-day Sharpe ratio | {_fmt(rm.get('sharpe_ratio_90d'))} |")
    lines.append(f"| 90-day Sortino ratio | {_fmt(rm.get('sortino_ratio_90d'))} |")
    lines.append(f"| 1-day VaR (95%) | ${_fmt(rm.get('var_95_1d'), ',.2f')} |")
    lines.append("")

    # Thesis Health
    th = data.get("thesis_health", {})
    lines.append("## Thesis Health")
    lines.append("")
    avg = th.get("avg_health_score")
    lines.append(f"- **Average health score**: {avg:.0f}" if avg else "- **Average health score**: N/A")
    below = th.get("positions_below_50", [])
    if below:
        lines.append(f"- **Below threshold**: {', '.join(below)}")
    no_thesis = th.get("positions_without_thesis", [])
    if no_thesis:
        lines.append(f"- **Without thesis**: {', '.join(no_thesis)}")
    stale = th.get("stale_checks", [])
    if stale:
        lines.append(f"- **Stale health checks (>30 days)**: {', '.join(stale)}")
    lines.append("")

    # Alerts
    alerts = data.get("alerts", [])
    lines.append("## Alerts")
    lines.append("")
    if alerts:
        for a in alerts:
            icon = "🔴" if a.get("severity") == "critical" else "🟡"
            lines.append(f"- {icon} **[{a.get('type', '?')}]** {a.get('message', '')}")
    else:
        lines.append("✅ No alerts — all metrics within limits.")
    lines.append("")

    # Rules
    rules = data.get("rules", {})
    if rules:
        lines.append("## Active Rules")
        lines.append("")
        lines.append("| Rule | Value |")
        lines.append("|------|-------|")
        for k, v in sorted(rules.items()):
            if "pct" in k:
                lines.append(f"| {k} | {v:.0%} |")
            else:
                lines.append(f"| {k} | {v} |")
        lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Risk Manager — portfolio-level risk monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-url", default=API_URL, help=f"API base URL (default: {API_URL})"
    )
    parser.add_argument(
        "--portfolio-id", type=int, default=1, help="Portfolio ID (default: 1)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # check
    sub.add_parser("check", help="Full risk check — compute metrics, alerts, write report")

    # alerts
    p_alerts = sub.add_parser("alerts", help="Show recent alerts")
    p_alerts.add_argument("--limit", type=int, default=20, help="Number of alerts to show")

    # rules
    p_rules = sub.add_parser("rules", help="Show or update risk rules")
    p_rules.add_argument("--set", nargs="+", metavar="KEY=VALUE", help="Set rule values")

    # report
    p_report = sub.add_parser("report", help="Generate markdown risk report")
    p_report.add_argument("--persist", action="store_true", help="Persist report to database")

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "alerts":
        cmd_alerts(args)
    elif args.command == "rules":
        cmd_rules(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
