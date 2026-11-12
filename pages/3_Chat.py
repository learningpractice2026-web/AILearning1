import streamlit as st

from core import db
from core.usecase import get_usecase
from services import rag
from ui.common import page_setup

uc = get_usecase()
user = page_setup("Chat", "💬")
st.title(f"💬 Chat with your {uc.app.record_name_plural.lower()}")
st.caption("Answers come only from stored content, with citations like [R2#1] = record 2, chunk 1.")

if not uc.chat.enabled:
    st.info("Chat is disabled for this use case (chat.enabled: false in usecase.yaml).")
    st.stop()
records = db.list_records()
if not records:
    st.info("Process something on the Upload page first.")
    st.stop()
opts = {r["id"]: f"#{r['id']} {r['title']}" for r in records}
scope = st.multiselect(f"Scope (empty = all {uc.app.record_name_plural.lower()})", list(opts), format_func=opts.get)
if uc.chat.examples:
    with st.expander("Try these"):
        st.markdown("\n".join(f"- {q}" for q in uc.chat.examples))

st.session_state.setdefault("chat", [])
for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("hits"):
            with st.expander("Sources"):
                for h in msg["hits"]:
                    st.markdown(f"**[{h['cite']}] {h['title']}** · score {h['score']:.2f}")
                    st.code(h["text"], language=None)

if q := st.chat_input("Ask a question…"):
    st.session_state.chat.append({"role": "user", "content": q})
    with st.spinner("Searching…"):
        ans = rag.ask(q, scope or None)
    hits = [{"cite": h.cite, "title": h.title, "text": h.text, "score": h.score} for h in ans.hits]
    content = ans.text + (f"\n\n<sub>engine: {ans.provider}</sub>" if ans.provider else "")
    st.session_state.chat.append({"role": "assistant", "content": content, "hits": hits, "q": q})
    db.audit(user, "chat.ask", q[:200])
    st.rerun()

if st.session_state.chat and st.session_state.chat[-1]["role"] == "assistant":
    c1, c2, c3 = st.columns([1, 1, 6])
    last = st.session_state.chat[-1]
    if c1.button("👍"):
        db.add_feedback(user, None, f"chat: {last.get('q', '')[:200]}", 1)
        st.toast("Thanks!")
    if c2.button("👎"):
        db.add_feedback(user, None, f"chat: {last.get('q', '')[:200]}", -1)
        st.toast("Logged — used to improve retrieval.")
    if c3.button("Clear chat"):
        st.session_state.chat = []
        st.rerun()
