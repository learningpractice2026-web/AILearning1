import datetime as dt

import streamlit as st

from core.config import get_settings
from core.usecase import get_usecase
from services import ingest
from services.pipeline import process_text
from ui.common import page_setup

uc = get_usecase()
user = page_setup("Upload", "📤", min_role="editor")
st.title(f"📤 New {uc.app.record_name.lower()}")

c1, c2 = st.columns([2, 1])
title = c1.text_input("Title (optional — AI will infer one)")
date = c2.date_input("Date", dt.date.today())

types = [e.lstrip(".") for e in ingest.SUPPORTED if uc.app.accepts_audio or e not in ingest.AUDIO_EXT]
st.caption("Accepts text, Word, PDF (digital or scanned), images" + (", audio" if uc.app.accepts_audio else "")
           + ". Large documents are split into chunks and processed in parallel automatically.")
tab_file, tab_paste, tab_sample = st.tabs(["📁 Upload file", f"📝 Paste {uc.app.input_label.lower()}", "🧪 Sample data"])
with tab_file:
    up = st.file_uploader(f"{uc.app.input_label} ({', '.join(types)})", type=types)
with tab_paste:
    pasted = st.text_area(uc.app.input_label, height=220, help=uc.app.input_help)
    if uc.app.input_help:
        st.caption(uc.app.input_help)
with tab_sample:
    samples = sorted(p.name for p in uc.samples_dir.glob("*.txt")) if uc.samples_dir.exists() else []
    sample = st.selectbox("Synthetic sample", ["—"] + samples)
    if sample != "—":
        st.code((uc.samples_dir / sample).read_text(encoding="utf-8")[:2000], language=None)

mask = st.toggle("Mask PII before sending to the AI (emails, phones, IDs)", value=get_settings().mask_pii_default)

if st.button("🚀 Analyse with AI", type="primary"):
    raw, source = None, None
    try:
        if up is not None:
            with st.spinner("Reading file (images / scanned PDFs use the vision model, audio uses Whisper)…"):
                raw, ingest_meta = ingest.read_upload_with_meta(up.name, up.getvalue())
                source = up.name
            st.caption(f"📥 Input type: {ingest_meta.get('modality')}"
                       + (f" · ⚠️ {ingest_meta['warning']}" if ingest_meta.get("warning") else ""))
        elif pasted.strip():
            raw, source = pasted, "pasted"
        elif sample != "—":
            raw, source = (uc.samples_dir / sample).read_text(encoding="utf-8"), sample
        if not raw:
            st.warning("Upload a file, paste text or choose a sample first.")
            st.stop()
        with st.status("Processing…", expanded=True) as status:
            rep = process_text(raw, title, str(date), source, mask, user, on_step=st.write)
            status.update(label=f"Done in {rep.seconds}s", state="complete")
    except Exception as e:  # friendly error, keep the app alive
        st.error(f"Processing failed: {e}")
        st.stop()

    st.session_state.current_record = rep.record_id
    m = rep.meta
    cols = st.columns(4)
    cols[0].metric("Grounding rate", f"{m.get('grounding_rate', 1) * 100:.0f}%")
    cols[1].metric("Items extracted", m.get("items_total", 0))
    cols[2].metric("Flagged for review", m.get("items_flagged", 0))
    cols[3].metric("Engine", m.get("provider", "?") + (" ↩ fallback" if m.get("fallback_used") else ""))
    if rep.pii_counts:
        st.info(f"🛡️ PII masked before AI processing: {rep.pii_counts}")
    for ev in rep.guard_events:
        st.warning(f"🛡️ Output guardrail: {ev}")
    st.caption(f"⚙️ Orchestration: **{rep.engine}** · path: {' → '.join(rep.trace)}")
    if rep.injection_hits:
        st.warning("🚨 Possible prompt-injection text found. It was treated as data, not as instructions:\n\n"
                   + "\n".join(f"- `{h}`" for h in rep.injection_hits))
    ins = rep.insights
    st.subheader(ins.title)
    if ins.fields:
        st.caption(" · ".join(f"{f.label or f.name}: **{ins.fields.get(f.name, '-')}**" for f in uc.fields))
    st.write(ins.summary)
    cols = st.columns(min(len(uc.sections), 2))
    for i, sec in enumerate(uc.sections):
        items = ins.sections.get(sec.key, [])
        lines = [f"- {x.text}" + (f" — *{x.owner}*" if x.owner else "") + (f" ({x.deadline})" if x.deadline else "")
                 for x in items] or ["- none"]
        cols[i % len(cols)].markdown(f"**{sec.icon} {sec.label}**\n" + "\n".join(lines))
    st.success(f"Saved as #{rep.record_id}. Open **Review and Export** to edit, approve and export.")
