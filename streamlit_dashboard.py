# streamlit_dashboard.py
import streamlit as st
import requests, json, os, glob, time

AGENT = "http://localhost:8000"

st.title("AutoOps Evo — Demo Dashboard")

if st.button("Refresh Status"):
    r = requests.get(f"{AGENT}/status").json()
    st.subheader("Workflow")
    st.json(r.get("workflow"))
    st.subheader("Metrics")
    st.write(r.get("metrics"))

if st.button("Trigger Run Cycle (Detect & Remediate)"):
    r = requests.post(f"{AGENT}/run_cycle", timeout=20.0)
    st.write(r.json())

st.markdown("### Workflow Versions")
files = sorted(glob.glob("workflow_versions/*.json"), reverse=True)
if files:
    for f in files[:10]:
        st.write(f)
        with open(f) as fh:
            st.json(json.load(fh))
else:
    st.write("No versions yet. Workflow will be snapshotted after evolve events.")
