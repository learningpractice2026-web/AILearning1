"""Shared Streamlit helpers: bootstrap, login + role-based access, sidebar status."""
from __future__ import annotations

import hashlib
import hmac

import streamlit as st

from core import db
from core.config import get_settings
from core.llm import get_llm
from core.usecase import get_usecase

ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


@st.cache_resource
def _bootstrap() -> bool:
    db.init_db()
    return True


def _users() -> dict[str, tuple[str, str]]:
    out = {}
    for entry in get_settings().app_users.split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            u, p, r = parts
            out[u] = (hashlib.sha256(p.encode()).hexdigest(), r)
    return out


def page_setup(title: str, icon: str = "🧠", min_role: str = "viewer") -> str:
    """Call at the top of every page. Returns the current username (stops the page if not allowed)."""
    st.set_page_config(page_title=f"{title} · {get_usecase().app.name}", page_icon=icon, layout="wide")
    _bootstrap()
    s = get_settings()

    if s.auth_enabled and "user" not in st.session_state:
        st.title("🔐 Sign in")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary"):
                rec = _users().get(u)
                if rec and hmac.compare_digest(rec[0], hashlib.sha256(p.encode()).hexdigest()):
                    st.session_state.user, st.session_state.role = u, rec[1]
                    db.audit(u, "login")
                    st.rerun()
                st.error("Invalid credentials")
        st.caption("Demo users are configured in APP_USERS (.env).")
        st.stop()
    if not s.auth_enabled:
        st.session_state.setdefault("user", "demo")
        st.session_state.setdefault("role", "admin")

    with st.sidebar:
        st.markdown(f"**👤 {st.session_state.user}** · `{st.session_state.role}`")
        llm = get_llm()
        badge = "🟡" if llm.provider == "mock" else "🟢"
        st.caption(f"{badge} LLM: {llm.label}")
        st.caption(f"📁 Use case: `{get_usecase().slug}`")
        if s.auth_enabled and st.button("Sign out"):
            for k in ("user", "role"):
                st.session_state.pop(k, None)
            st.rerun()

    if ROLE_RANK.get(st.session_state.role, 0) < ROLE_RANK[min_role]:
        st.error(f"This page needs the '{min_role}' role.")
        st.stop()
    return st.session_state.user


def can(role: str) -> bool:
    return ROLE_RANK.get(st.session_state.get("role", "viewer"), 0) >= ROLE_RANK[role]
