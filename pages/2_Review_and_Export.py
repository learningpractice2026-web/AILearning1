import pandas as pd
import streamlit as st

from core import db
from core.schemas import Item
from core.usecase import get_usecase
from services import exporter
from ui.common import can, page_setup

uc = get_usecase()
user = page_setup("Review and Export", "📚")
st.title(f"📚 {uc.app.record_name_plural}")

c1, c2 = st.columns([3, 1])
query = c1.text_input("🔎 Search titles, items, owners")
records = db.list_records(query)
cats = sorted({r["category"] or "-" for r in records})
fcat = c2.multiselect(uc.fields[0].label if uc.fields else "Category", cats)
if fcat:
    records = [r for r in records if (r["category"] or "-") in fcat]
if not records:
    st.info("Nothing found.")
    st.stop()

labels = {r["id"]: f"#{r['id']} · {r['title']} · {r['record_date'] or ''} {'✅' if r['approved'] else '⏳'}"
          for r in records}
ids = list(labels)
default = st.session_state.get("current_record")
rid = st.selectbox(uc.app.record_name, ids, index=ids.index(default) if default in ids else 0, format_func=labels.get)
rec = db.get_record(rid)
ins = rec["insights"]

st.subheader(rec["title"])
st.caption(" · ".join([f"{f.label or f.name}: {ins.fields.get(f.name, '-')}" for f in uc.fields]
                      + ["✅ human-reviewed" if rec["approved"] else "⏳ awaiting human review"]))
for f in rec["guardrail_flags"]:
    st.warning(f"🛡️ {f}")

t_sum, t_rev, t_src, t_exp, t_fb = st.tabs(["📝 Summary", "✏️ Review & approve", "📜 Source", "📤 Export", "👍 Feedback"])

with t_sum:
    st.write(ins.summary)
    if ins.highlights:
        st.markdown("**Highlights**\n" + "\n".join(f"- {p}" for p in ins.highlights))
    for sec in uc.sections:
        items = ins.sections.get(sec.key, [])
        with st.expander(f"{sec.icon} {sec.label} ({len(items)})", expanded=True):
            for it in items:
                tag = "" if it.grounded else " 🔶 *needs review (not found in source)*"
                who = f" — **{it.owner}**" if it.owner else ""
                due = f" · due *{it.deadline}*" if it.deadline else ""
                attrs = "".join(f" · `{k}: {v}`" for k, v in it.attributes.items() if v)
                st.markdown(f"- {it.text}{who}{due}{attrs}{tag}")
                if it.evidence:
                    st.caption(f"   ↳ evidence: “{it.evidence}”")

with t_rev:
    st.caption("Human-in-the-loop: fix values, delete wrong rows, add missing ones, then approve. "
               "Only approved output should leave the system.")
    new_title = st.text_input("Title", ins.title, disabled=not can("editor"))
    new_fields = {}
    if uc.fields:
        fcols = st.columns(len(uc.fields))
        for col, f in zip(fcols, uc.fields):
            cur = ins.fields.get(f.name, "")
            if f.options:
                new_fields[f.name] = col.selectbox(f.label or f.name, f.options,
                                                   index=f.options.index(cur) if cur in f.options else 0,
                                                   disabled=not can("editor"), key=f"f_{rid}_{f.name}")
            else:
                new_fields[f.name] = col.text_input(f.label or f.name, cur, disabled=not can("editor"),
                                                    key=f"f_{rid}_{f.name}")
    edited = {}
    for sec in uc.sections:
        attr_names = [a.name for a in sec.attributes]
        rows = [{"text": i.text, "owner": i.owner, "deadline": i.deadline,
                 **{a: i.attributes.get(a) for a in attr_names},
                 "status": i.status, "confidence": i.confidence, "grounded": i.grounded, "evidence": i.evidence}
                for i in ins.sections.get(sec.key, [])]
        cols = ["text", "owner", "deadline", *attr_names, "status", "confidence", "grounded", "evidence"]
        if not sec.has_deadline:
            cols.remove("deadline")
        cfg = {"text": st.column_config.TextColumn(sec.label, width="large"),
               "owner": st.column_config.TextColumn(sec.owner_label),
               "status": st.column_config.SelectboxColumn(options=["open", "in progress", "done"]),
               "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1),
               "grounded": st.column_config.CheckboxColumn("verified")}
        for a in sec.attributes:
            if a.options:
                cfg[a.name] = st.column_config.SelectboxColumn(a.name, options=a.options)
        st.markdown(f"**{sec.icon} {sec.label}**")
        edited[sec.key] = (sec, st.data_editor(pd.DataFrame(rows, columns=cols), key=f"ed_{rid}_{sec.key}",
                                               num_rows="dynamic", hide_index=True, width="stretch",
                                               disabled=not can("editor"), column_config=cfg))
    if can("editor") and st.button("💾 Save & approve", type="primary"):
        for key, (sec, df) in edited.items():
            items = []
            for r in df.dropna(subset=["text"]).to_dict("records"):
                r = {k: (None if (v is None or (isinstance(v, float) and pd.isna(v))) else v) for k, v in r.items()}
                items.append(Item(
                    text=str(r["text"]), owner=r.get("owner"), deadline=r.get("deadline"),
                    evidence=r.get("evidence") or "", confidence=r.get("confidence") or 1.0,
                    attributes={a.name: str(r[a.name]) for a in sec.attributes if r.get(a.name)},
                    grounded=True, status=r.get("status") or "open"))  # a human confirmed them
            ins.sections[key] = items
        ins.title, ins.fields = new_title, {**ins.fields, **new_fields}
        db.update_insights(rid, ins, approved=True, user=user)
        st.success("Saved and approved ✅")
        st.rerun()

with t_src:
    st.text_area("Cleaned source text (PII masked if enabled)", rec["content"], height=400, disabled=True)

with t_exp:
    if not rec["approved"]:
        st.info("Tip: approve first (Review tab) so only human-checked output is exported.")
    title, date = rec["title"], rec["record_date"] or ""
    safe = "".join(ch if ch.isalnum() else "_" for ch in title)[:40]
    c = st.columns(5)
    c[0].download_button("Markdown", exporter.to_markdown(title, date, ins), f"{safe}.md")
    c[1].download_button("Word", exporter.to_docx(title, date, ins), f"{safe}.docx")
    c[2].download_button("PDF", exporter.to_pdf(title, date, ins), f"{safe}.pdf")
    c[3].download_button("Jira CSV", exporter.to_jira_csv(title, ins), f"{safe}_jira.csv")
    c[4].download_button("JSON", ins.model_dump_json(indent=2), f"{safe}.json")
    st.text_area("📧 Email draft", exporter.to_email(title, date, ins), height=260)

with t_fb:
    st.write("Was this output accurate? Feedback feeds the eval set and prompt tuning.")
    rating = st.radio("Rating", [1, -1], format_func=lambda x: "👍 Useful" if x == 1 else "👎 Wrong / missing",
                      horizontal=True)
    comment = st.text_input("What was wrong or missing?")
    if st.button("Submit feedback"):
        db.add_feedback(user, rid, "summary", rating, comment)
        st.success("Thanks — recorded.")

if can("admin"):
    with st.expander("🗑️ Danger zone"):
        if st.button(f"Delete #{rid}"):
            db.delete_record(rid, user)
            st.session_state.pop("current_record", None)
            st.rerun()
