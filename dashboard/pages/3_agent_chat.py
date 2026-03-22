"""Chatbot Widget — send commands to the AI agent via the Task API.

Users type natural language like "update NVDA thesis with Q4 beat"
→ creates a task → dispatcher picks it up → OpenClaw runs skill → dashboard reloads.

Phase 5b of the migration plan.
"""

import os
import re
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dashboard.components.styles import inject_css

st.set_page_config(page_title="Agent Chat", page_icon="💬", layout="wide")
inject_css()

st.title("💬 Agent Chat")
st.markdown("Send commands to the AI agent. Tasks are queued and executed by the dispatcher.")

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

API_URL = os.environ.get("PFS_API_URL", "http://127.0.0.1:8000")

# ──────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


def _get_task_client():
    from skills._lib.task_client import TaskClient
    return TaskClient(base_url=API_URL)


# ──────────────────────────────────────────────
# Intent parsing — extract skill + ticker + action from natural language
# ──────────────────────────────────────────────

_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")

_INTENT_MAP = [
    # (pattern, skill, action)
    (re.compile(r"generate\s+profile", re.I), "company-profile", "generate_report"),
    (re.compile(r"build\s+(?:comp|peer)", re.I), "company-profile", "build_comps"),
    (re.compile(r"create\s+thesis", re.I), "thesis-tracker", "create"),
    (re.compile(r"update\s+thesis", re.I), "thesis-tracker", "update"),
    (re.compile(r"health\s*check", re.I), "thesis-tracker", "check"),
    (re.compile(r"add\s+catalyst", re.I), "thesis-tracker", "catalyst"),
    (re.compile(r"thesis\s+report", re.I), "thesis-tracker", "report"),
    (re.compile(r"check\s+coverage", re.I), "etl-coverage", "check"),
    (re.compile(r"coverage\s+report", re.I), "etl-coverage", "check"),
]

# Common words that look like tickers but aren't
_TICKER_STOPWORDS = {
    "AI", "DO", "FOR", "THE", "AND", "NOT", "ALL", "CEO", "ETL",
    "API", "RUN", "ADD", "NEW", "SET", "GET",
}


def parse_intent(text: str) -> dict | None:
    """Parse user message into a task dict, or None if not understood."""
    # Find skill + action
    skill = action = None
    for pattern, s, a in _INTENT_MAP:
        if pattern.search(text):
            skill, action = s, a
            break

    if not skill:
        return None

    # Find ticker
    tickers = [
        m.group(1)
        for m in _TICKER_PATTERN.finditer(text)
        if m.group(1) not in _TICKER_STOPWORDS
    ]
    ticker = tickers[0] if tickers else None

    return {
        "skill": skill,
        "action": action,
        "ticker": ticker,
        "description": text.strip(),
        "requires_intelligence": True,
        "priority": 5,
    }


# ──────────────────────────────────────────────
# Chat display
# ──────────────────────────────────────────────

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ──────────────────────────────────────────────
# User input
# ──────────────────────────────────────────────

if prompt := st.chat_input("e.g. 'update NVDA thesis with Q4 beat'"):
    # Show user message
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Parse intent
    intent = parse_intent(prompt)

    if intent is None:
        reply = (
            "I didn't understand that command. Try one of these:\n\n"
            "- **generate profile for NVDA**\n"
            "- **create thesis for AAPL**\n"
            "- **update thesis for NVDA**\n"
            "- **health check TSLA**\n"
            "- **add catalyst for MSFT**\n"
            "- **thesis report for GOOGL**\n"
            "- **check coverage for AMD**\n"
        )
    elif not intent.get("ticker"):
        reply = (
            f"I understood the command (*{intent['skill']}* → *{intent['action']}*), "
            f"but couldn't find a ticker symbol. Please include a ticker, e.g. "
            f"\"*{intent['action']} for NVDA*\"."
        )
    else:
        # Submit task
        try:
            client = _get_task_client()
            result = client.create_task(
                skill=intent["skill"],
                action=intent["action"],
                ticker=intent["ticker"],
                params={"description": intent["description"]},
                requires_intelligence=intent["requires_intelligence"],
                priority=intent["priority"],
            )
            task_id = result.get("id", "?")
            reply = (
                f"✅ Task created (ID: **{task_id}**)\n\n"
                f"- **Skill:** {intent['skill']}\n"
                f"- **Action:** {intent['action']}\n"
                f"- **Ticker:** {intent['ticker']}\n\n"
                f"The dispatcher will pick this up shortly. "
                f"Check the Task Queue below for status."
            )
        except Exception as e:
            reply = (
                f"⚠️ Could not submit task — the API may be offline.\n\n"
                f"**Error:** {e}\n\n"
                f"You can run manually:\n"
                f"```\nuv run python skills/{intent['skill']}/scripts/*_cli.py "
                f"{intent['action']} {intent['ticker']}\n```"
            )

    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)

# ──────────────────────────────────────────────
# Task queue view
# ──────────────────────────────────────────────

st.markdown("---")
st.subheader("📋 Recent Tasks")

try:
    client = _get_task_client()
    tasks = client.list_tasks(limit=20)

    if tasks:
        import pandas as pd

        rows = []
        for t in tasks:
            rows.append({
                "ID": t.get("id", ""),
                "Skill": t.get("skill", ""),
                "Ticker": t.get("ticker", ""),
                "Action": t.get("action", ""),
                "Status": t.get("status", ""),
                "Created": str(t.get("created_at", ""))[:19],
            })
        df = pd.DataFrame(rows)

        # Color-code status
        def _color_status(val):
            colors = {
                "completed": "color: #10b981",
                "running": "color: #f59e0b",
                "failed": "color: #ef4444",
                "pending": "color: #64748b",
            }
            return colors.get(val, "")

        st.dataframe(
            df.style.map(_color_status, subset=["Status"]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No tasks in queue.")
except Exception:
    st.info(
        "Task API unavailable. Start the API server with:\n\n"
        "```\nuv run uvicorn pfs.api.app:app --reload\n```"
    )

# ──────────────────────────────────────────────
# Quick-action buttons
# ──────────────────────────────────────────────

st.markdown("---")
st.subheader("⚡ Quick Actions")
st.caption("Click to pre-fill common commands.")

col1, col2, col3, col4 = st.columns(4)

_QUICK_ACTIONS = [
    ("🏢 Generate Profile", "generate profile for "),
    ("📝 Create Thesis", "create thesis for "),
    ("🔄 Update Thesis", "update thesis for "),
    ("🩺 Health Check", "health check "),
]

for col, (label, prefix) in zip([col1, col2, col3, col4], _QUICK_ACTIONS):
    with col:
        if st.button(label, use_container_width=True):
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"Type a ticker after: **{prefix}**"}
            )
            st.rerun()

st.caption("Tasks are dispatched to the AI agent via the REST API.")
