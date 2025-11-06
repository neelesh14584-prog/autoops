# agent.py
import time, json, os, threading, shutil
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Dict, Any
import math, datetime
import httpx

# Config
SIMULATOR_BASE = os.environ.get("SIMULATOR_BASE", "http://localhost:5001")
WORKFLOW_FILE = "workflow.json"
VERSIONS_DIR = "workflow_versions"
os.makedirs(VERSIONS_DIR, exist_ok=True)

app = FastAPI()

# Simple in-memory metrics store
METRICS = {
    "window": [],
    "error_count": 0,
    "total_count": 0
}

# Load workflow
def load_workflow():
    with open(WORKFLOW_FILE, "r") as f:
        return json.load(f)

def save_workflow(wf):
    with open(WORKFLOW_FILE, "w") as f:
        json.dump(wf, f, indent=2)

def snapshot_workflow(reason):
    """Save copy of workflow with timestamp and reason."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    src = WORKFLOW_FILE
    dest = os.path.join(VERSIONS_DIR, f"{ts}__{reason.replace(' ', '_')}.json")
    shutil.copyfile(src, dest)
    print("Snapshot saved:", dest)

# Simple anomaly detector (z-score on latency and error rate)
def analyze_metrics(window):
    # window: list of dicts {latency_ms, level}
    latencies = [w.get("metric", {}).get("latency_ms", 0) for w in window if "metric" in w]
    error_flags = [1 if w.get("state")=="crashed" or w.get("level")=="error" else 0 for w in window]
    if not latencies:
        return {"anomaly": False}
    mean = sum(latencies)/len(latencies)
    var = sum((x-mean)**2 for x in latencies)/len(latencies)
    std = math.sqrt(var)
    latest = latencies[-1]
    z = (latest - mean) / (std+1e-6)
    error_rate = sum(error_flags)/len(error_flags)
    anomaly = (z > 2.0) or (error_rate > 0.15)
    return {"anomaly": anomaly, "z": z, "error_rate": error_rate, "latest_latency": latest, "mean": mean, "std": std}

# Root cause analyzer (simple heuristic reasoning)
def root_cause_reasoning(analysis):
    if analysis["error_rate"] > 0.15:
        return "service_crash_or_high_error_rate"
    if analysis["z"] > 2.0:
        return "latency_spike"
    return "unknown"

# Action executor (safe)
def execute_action(action, params):
    # Two safe methods:
    # - http_restart: call simulator's /recover endpoint (safe demo)
    # - docker_restart: attempt to restart container via docker sdk (optional)
    method = params.get("method", "http_restart")
    if action == "action_restart_service":
        if method == "http_restart":
            try:
                r = httpx.get(f"{SIMULATOR_BASE}/recover", timeout=3.0)
                return {"ok": True, "detail": "called /recover", "status_code": r.status_code}
            except Exception as e:
                return {"ok": False, "detail": str(e)}
        else:
            # fallback simulated restart
            return {"ok": True, "detail": "simulated restart (no docker)"}
    return {"ok": False, "detail": "unknown action"}

# Post-check verification
def verify_recovery(params):
    check_endpoint = params.get("check_endpoint", "/")
    try:
        r = httpx.get(f"{SIMULATOR_BASE}{check_endpoint}", timeout=2.0)
        return {"ok": r.status_code == 200, "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Reflection & self-evolver: modify workflow if action failed or slow
def reflect_and_evolve(workflow, context):
    """
    Basic strategy: if we attempted restart and it failed (or slow recovery),
    change workflow params: lower latency threshold, add another step (e.g., deeper check).
    """
    reason = context.get("reason", "no_reason")
    success = context.get("success", True)
    if success:
        print("Reflection: fix succeeded. Slightly lower threshold to be less sensitive.")
        # adjust threshold to be more sensitive (reduce threshold)
        for step in workflow.get("steps", []):
            if step["type"] == "anomaly_detection":
                t = step["params"].get("latency_threshold_ms", 300)
                step["params"]["latency_threshold_ms"] = max(80, int(t * 0.95))
        snapshot_workflow("improved_after_success")
        save_workflow(workflow)
        return {"evolved": True, "note": "lowered latency threshold"}
    else:
        print("Reflection: fix failed. Increase remediation sophistication: add 'notify_admin' step.")
        # Add a new step if not present
        ids = [s["id"] for s in workflow.get("steps", [])]
        if "notify_admin" not in ids:
            workflow["steps"].append({
                "id": "notify_admin",
                "type": "action_notify",
                "params": {"channel":"console", "message":"AutoOps Evo: remediation failed, manual review required"}
            })
            snapshot_workflow("added_notify_after_failure")
            save_workflow(workflow)
            return {"evolved": True, "note": "added notify_admin step"}
    return {"evolved": False}

# API models
class LogEvent(BaseModel):
    service: str
    timestamp: float
    metric: Dict[str, Any] = {}
    message: str
    level: str
    state: str = "ok"

@app.post("/ingest_log")
async def ingest_log(event: LogEvent):
    # Append to window (sliding window)
    METRICS["window"].append(event.dict())
    METRICS["total_count"] += 1
    if event.level.lower() == "error" or event.state=="crashed":
        METRICS["error_count"] += 1
    # keep window small (last 30 events)
    if len(METRICS["window"]) > 30:
        METRICS["window"].pop(0)
    return {"received": True}

@app.post("/run_cycle")
async def run_cycle():
    """
    Force the agent to evaluate current metrics, detect anomaly, choose fix,
    execute, verify and reflect/evolve.
    """
    workflow = load_workflow()
    analysis = analyze_metrics(METRICS["window"])
    if not analysis.get("anomaly", False):
        return {"status":"no_anomaly", "analysis": analysis}
    rc = root_cause_reasoning(analysis)
    # choose action from workflow (simple mapping)
    action_taken = None
    action_detail = None
    for step in workflow.get("steps", []):
        if step["type"] == "action_restart_service":
            action_taken = step["id"]
            action_detail = execute_action(step["type"], step.get("params", {}))
            break
    # verify
    verified = verify_recovery(workflow.get("steps")[-1].get("params", {}))
    success = action_detail.get("ok", False) and verified.get("ok", False)
    # reflect and possibly evolve workflow
    evolve_result = reflect_and_evolve(workflow, {"reason": rc, "success": success})
    # create a human readable reasoning chain
    reasoning_chain = {
        "analysis": analysis,
        "root_cause": rc,
        "action_taken": action_taken,
        "action_detail": action_detail,
        "verification": verified,
        "evolve": evolve_result
    }
    # clear metrics after remediation attempt so repeated cycles are meaningful
    METRICS["window"].clear()
    METRICS["error_count"] = 0
    METRICS["total_count"] = 0
    return {"status":"remediation_ran", "reasoning": reasoning_chain}

@app.get("/status")
async def status():
    wf = load_workflow()
    return {"metrics": {"window_len": len(METRICS["window"])}, "workflow": wf}
