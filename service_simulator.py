# service_simulator.py
from flask import Flask, jsonify
import threading, time, requests, os

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8000/ingest_log")
app = Flask(__name__)

healthy = {"state": "ok"}

def emit_heartbeat():
    """Emit periodic log events to the agent."""
    i = 0
    while True:
        payload = {
            "service": "sim-service",
            "timestamp": time.time(),
            "metric": {
                "cpu": 20 + (i % 5),
                "latency_ms": 100 + (i % 20),
            },
            "message": "heartbeat",
            "level": "info",
            "state": healthy["state"]
        }
        try:
            requests.post(AGENT_URL, json=payload, timeout=1.0)
        except Exception as e:
            # agent may be down during dev — ignore
            pass
        i += 1
        time.sleep(1.0)

@app.route("/")
def home():
    return jsonify({"status": healthy["state"]})

@app.route("/work")
def work():
    # simulate occasional error
    if healthy["state"] == "crashed":
        return ("Service unavailable", 503)
    # sometimes simulate high latency
    return jsonify({"result":"ok", "latency_ms": 120})

@app.route("/crash")
def crash():
    healthy["state"] = "crashed"
    return jsonify({"status":"crashed"})

@app.route("/recover")
def recover():
    healthy["state"] = "ok"
    return jsonify({"status":"recovered"})

if __name__ == "__main__":
    t = threading.Thread(target=emit_heartbeat, daemon=True)
    t.start()
    app.run(port=5001)
