from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime, timezone

import httpx


def sh(cmd: list[str]) -> str:
    print("+", " ".join(cmd))
    out = subprocess.check_output(cmd, text=True)
    return out.strip()


def health(url: str) -> bool:
    try:
        r = httpx.get(url, timeout=2.0)
        return r.status_code == 200
    except Exception as e:
        print("health check failed:", e)
        return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--service", default="quiz-agent")
    p.add_argument("--compose", default="infra/docker-compose.yml")
    p.add_argument("--project-dir", default="infra")
    p.add_argument("--gateway", default="http://localhost:8000/health")
    p.add_argument("--target-health", default="")
    args = p.parse_args()

    health_map = {
        "quiz-agent": "http://localhost:8003/health",
        "study-agent": "http://localhost:8002/health",
        "router": "http://localhost:8001/health",
        "progress": "http://localhost:8004/health",
        "gateway": "http://localhost:8000/health",
    }
    target = args.target_health or health_map.get(args.service, args.gateway)

    print(f"[{utcnow()}] killing {args.service}")
    t0 = time.perf_counter()
    sh(["docker", "compose", "-f", args.compose, "stop", args.service])

    dead_at = None
    for _ in range(60):
        if not health(target):
            dead_at = time.perf_counter()
            break
        time.sleep(0.5)
    if dead_at is None:
        print("huh, service never went down")
        return

    downtime_detect = dead_at - t0
    print(f"[{utcnow()}] dead after {downtime_detect:.2f}s")

    errors = 0
    attempts = 20
    with httpx.Client(timeout=5.0) as client:
        for i in range(attempts):
            try:
                r = client.post(
                    "http://localhost:8000/api/message",
                    json={
                        "text": f"chaos probe {i}",
                        "user_id": "chaos-user",
                        "intent_hint": "study",
                    },
                )
                if r.status_code >= 400:
                    errors += 1
            except Exception as e:
                print("probe failed:", e)
                errors += 1
            time.sleep(0.2)

    print(f"[{utcnow()}] while down: {errors}/{attempts} probes failed")

    print(f"[{utcnow()}] bringing {args.service} back")
    restart_t0 = time.perf_counter()
    sh(["docker", "compose", "-f", args.compose, "start", args.service])

    recovered_at = None
    for _ in range(120):
        if health(target):
            recovered_at = time.perf_counter()
            break
        time.sleep(0.5)

    if recovered_at is None:
        print("never came back")
        raise SystemExit(1)

    recovery = recovered_at - restart_t0
    total = recovered_at - t0
    print("--- chaos ---")
    print(f"service  {args.service}")
    print(f"noticed  {downtime_detect:.2f}s")
    print(f"errors   {errors}/{attempts} ({errors/attempts*100:.0f}%)")
    print(f"recover  {recovery:.2f}s")
    print(f"total    {total:.2f}s")
    print(f"gateway  {'up' if health(args.gateway) else 'down'}")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


if __name__ == "__main__":
    main()
