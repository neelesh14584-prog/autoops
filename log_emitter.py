# log_emitter.py
import requests, time, random
AGENT = "http://localhost:8000/ingest_log"
SIM = "http://localhost:5001"

def send_event(level="info", state="ok", latency=100):
    payload = {
        "service": "sim-service",
        "timestamp": time.time(),
        "metric": {"latency_ms": latency},
        "message": "synthetic",
        "level": level,
        "state": state
    }
    try:
        r = requests.post(AGENT, json=payload, timeout=1.0)
        print("sent", payload, "->", r.status_code)
    except Exception as e:
        print("err", e)

if __name__ == "__main__":
    # send normal events
    for i in range(10):
        send_event(level="info", state="ok", latency=100 + random.randint(0,10))
        time.sleep(0.2)
    # simulate crash events
    send_event(level="error", state="crashed", latency=1200)
    send_event(level="error", state="crashed", latency=1400)
    print("Trigger agent run_cycle to perform remediation:")
    import requests
    try:
        r = requests.post("http://localhost:8000/run_cycle", timeout=5.0)
        print("run_cycle ->", r.json())
    except Exception as e:
        print("run_cycle err", e)
