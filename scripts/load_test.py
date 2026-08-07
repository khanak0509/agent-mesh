"""Async load test against the gateway.

Usage:
  python scripts/load_test.py --concurrency 20 --requests 100
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def one(client: httpx.AsyncClient, i: int, intent: str) -> tuple[bool, float, int]:
    payload = {
        "text": f"Explain photosynthesis briefly #{i}",
        "user_id": f"load-{i % 10}",
        "intent_hint": intent,
    }
    if intent == "quiz":
        payload = {
            "text": "quiz me on osmosis",
            "user_id": f"load-{i % 10}",
            "intent_hint": "quiz",
            "topic": "osmosis",
            "num_questions": 3,
        }
    t0 = time.perf_counter()
    try:
        r = await client.post("/api/message", json=payload)
        dt = time.perf_counter() - t0
        return r.status_code < 400, dt, r.status_code
    except Exception:
        return False, time.perf_counter() - t0, 0


async def run(args: argparse.Namespace) -> None:
    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    oks = 0
    fails = 0

    async with httpx.AsyncClient(base_url=args.base, timeout=60.0) as client:
        async def worker(i: int):
            nonlocal oks, fails
            async with sem:
                ok, dt, _ = await one(client, i, args.intent)
                latencies.append(dt)
                if ok:
                    oks += 1
                else:
                    fails += 1

        t0 = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - t0

    latencies.sort()
    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(p * (len(latencies) - 1)))
        return latencies[idx]

    print("--- load test ---")
    print(f"base:          {args.base}")
    print(f"requests:      {args.requests}")
    print(f"concurrency:   {args.concurrency}")
    print(f"intent:        {args.intent}")
    print(f"elapsed_s:     {elapsed:.2f}")
    print(f"rps:           {args.requests / elapsed:.2f}")
    print(f"ok:            {oks}")
    print(f"fail:          {fails}")
    print(f"error_rate:    {fails / max(args.requests, 1) * 100:.1f}%")
    print(f"latency_avg_s: {statistics.mean(latencies) if latencies else 0:.3f}")
    print(f"latency_p50_s: {pct(0.50):.3f}")
    print(f"latency_p95_s: {pct(0.95):.3f}")
    print(f"latency_p99_s: {pct(0.99):.3f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--requests", type=int, default=50)
    p.add_argument("--intent", default="study", choices=["study", "quiz", "progress"])
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
