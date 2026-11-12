"""Home = Dashboard (generic; labels and metrics come from usecase.yaml). Run:  streamlit run app.py"""
import json

import pandas as pd
import streamlit as st

from core import db
from core.usecase import get_usecase
from ui.common import page_setup

uc = get_usecase()
page_setup("Dashboard", uc.app.icon)

st.title(f"{uc.app.icon} {uc.app.name}")
st.caption(uc.app.tagline)

records = db.list_records()
items = pd.DataFrame(db.all_items())
if not records or items.empty:
    st.info(f"No {uc.app.record_name_plural.lower()} yet. Open **Upload** in the sidebar and load a sample.")
    st.stop()

task = uc.task_section
open_tasks = items[(items.kind == task.key) & (items.status != "done")]

cols = st.columns(len(uc.sections) + 2)
cols[0].metric(uc.app.record_name_plural, len(records))
for col, sec in zip(cols[1:], uc.sections):
    col.metric(f"{sec.icon} {sec.label}", int((items.kind == sec.key).sum()))
unassigned = int(open_tasks.owner.isna().sum())
cols[-1].metric(f"Unassigned {task.label.lower()}", unassigned,
                delta=-unassigned if unassigned else None, delta_color="inverse")

left, right = st.columns(2)
with left:
    st.subheader(f"Open {task.label.lower()} by {task.owner_label.lower()}")
    if not open_tasks.empty:
        st.bar_chart(open_tasks.fillna({"owner": "Unassigned"}).groupby("owner").size().rename("count"))
with right:
    st.subheader("Items by section")
    labels = {s.key: s.label for s in uc.sections}
    st.bar_chart(items.assign(section=items.kind.map(labels)).groupby("section").size().rename("count"))

st.subheader(f"{task.icon} Open {task.label.lower()}")
if not open_tasks.empty:
    view = open_tasks.assign(**{a.name: open_tasks.attributes.map(lambda d, n=a.name: d.get(n, ""))
                                for a in task.attributes})
    st.dataframe(view[["text", "owner", "deadline", *[a.name for a in task.attributes], "status",
                       "record_title", "grounded"]]
                 .rename(columns={"text": task.label, "owner": task.owner_label,
                                  "record_title": uc.app.record_name, "grounded": "Verified"}),
                 hide_index=True, width="stretch")

for sec in uc.sections:
    if sec.key == task.key:
        continue
    sub = items[items.kind == sec.key]
    if not sub.empty:
        with st.expander(f"{sec.icon} Latest {sec.label.lower()} ({len(sub)})"):
            st.dataframe(sub[["text", "owner", "record_title"]].tail(15)
                         .rename(columns={"text": sec.label, "owner": sec.owner_label,
                                          "record_title": uc.app.record_name}), hide_index=True, width="stretch")

st.subheader(f"🗂️ Recent {uc.app.record_name_plural.lower()}")
st.dataframe(pd.DataFrame([{
    "ID": r["id"], "Title": r["title"], "Date": r["record_date"],
    **{(f.label or f.name): json.loads(r["insights_json"]).get("fields", {}).get(f.name, "") for f in uc.fields},
    "Reviewed": "✅" if r["approved"] else "⏳",
} for r in records[:15]]), hide_index=True, width="stretch")
