import pandas as pd
import streamlit as st

from core import db
from core.config import get_settings
from ui.common import page_setup

page_setup("Admin & Observability", "🛡️", min_role="admin")
st.title("🛡️ Admin, cost & observability")
s = get_settings()

calls = pd.DataFrame(db.llm_calls())
c = st.columns(5)
if calls.empty:
    st.info("No AI calls logged yet.")
else:
    real = calls[calls.cached == 0]
    c[0].metric("AI calls", len(calls))
    c[1].metric("Cache hit rate", f"{(calls.cached == 1).mean() * 100:.0f}%")
    c[2].metric("Avg latency", f"{real.latency_ms.mean():.0f} ms" if not real.empty else "-")
    c[3].metric("Cost (USD)", f"${calls.cost_usd.fillna(0).sum():.4f}")
    c[4].metric("Errors", int((calls.status == "error").sum()))
    used = db.tokens_used_today()
    st.progress(min(used / max(s.daily_token_budget, 1), 1.0),
                text=f"Daily token budget: {used:,} / {s.daily_token_budget:,} (auto-fallback to offline engine when exceeded)")
    st.subheader("Calls by task / model")
    st.dataframe(calls.groupby(["task", "provider", "model"]).agg(
        calls=("id", "count"), tokens_in=("prompt_tokens", "sum"), tokens_out=("completion_tokens", "sum"),
        avg_ms=("latency_ms", "mean"), cost=("cost_usd", "sum")).reset_index(), hide_index=True, width="stretch")
    st.subheader("Recent calls")
    st.dataframe(calls.head(50), hide_index=True, width="stretch")

st.subheader("👍 User feedback")
fb = pd.DataFrame(db.feedback_rows())
if fb.empty:
    st.caption("No feedback yet.")
else:
    st.metric("Positive feedback", f"{(fb.rating > 0).mean() * 100:.0f}%", help=f"{len(fb)} ratings")
    st.dataframe(fb, hide_index=True, width="stretch")

st.subheader("📜 Audit log")
st.dataframe(pd.DataFrame(db.audit_rows()), hide_index=True, width="stretch")

st.subheader("🧭 Pipeline graph (LangGraph)")
try:
    from services.graph import get_graph
    g = get_graph().get_graph()
    dot = ["digraph G { rankdir=LR; node [shape=box, style=rounded];"]
    for e in g.edges:
        style = ' [style=dashed, label="conditional"]' if e.conditional else ""
        dot.append(f'"{e.source}" -> "{e.target}"{style};')
    st.graphviz_chart("\n".join(dot) + "}")
    st.caption("Dashed = conditional edges: validate → extract is the self-repair loop, validate → fallback "
               "uses the offline engine, guard_output → __end__ skips storage during evaluation.")
except Exception as e:  # noqa: BLE001
    st.caption(f"Graph not available: {e}")

with st.expander("⚙️ Effective configuration (secrets hidden)"):
    st.json({k: ("***" if any(x in k for x in ("key", "users", "headers")) else v) for k, v in s.__dict__.items()})
