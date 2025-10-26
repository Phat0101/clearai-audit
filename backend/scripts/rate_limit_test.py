#!/usr/bin/env python3
"""
Simple rate limit tester.

Sends many requests to the API to validate the global per-IP rate limit.

Defaults:
- URL: http://127.0.0.1:8000/api/openapi.json (cheap and covered by rate limiter)
- TOTAL_REQUESTS: 120
- CONCURRENCY: 40
- TOKEN: optional Bearer token (will be attached if provided)

Usage examples:
  uv run scripts/rate_limit_test.py
  uv run scripts/rate_limit_test.py --total 150 --concurrency 50 --url http://127.0.0.1:8000/api/openapi.json \
    --token CvBGWtfSCAifZ9wPcxHIXLfPlGMP1w
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Dict, Tuple

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rate limit test client")
    parser.add_argument("--url", default=os.getenv("TEST_URL", "http://127.0.0.1:8000/api/openapi.json"))
    parser.add_argument("--total", type=int, default=int(os.getenv("TEST_TOTAL", "120")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("TEST_CONCURRENCY", "40")))
    parser.add_argument("--token", default=os.getenv("TEST_TOKEN", ""))
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    headers = {"Accept": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    print(f"Target URL: {args.url}")
    print(f"Total requests: {args.total}, Concurrency: {args.concurrency}")
    if args.token:
        print("Authorization: Bearer <provided>")

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    timeout = httpx.Timeout(10.0)

    semaphore = asyncio.Semaphore(args.concurrency)
    results: Dict[int, int] = {}
    latencies: Dict[int, list[float]] = {}
    sample_headers: Dict[int, Dict[str, str]] = {}

    async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=False) as client:
        async def do_request() -> Tuple[int, float, Dict[str, str]]:
            async with semaphore:
                start = time.perf_counter()
                try:
                    r = await client.get(args.url, headers=headers)
                    elapsed = time.perf_counter() - start
                    return r.status_code, elapsed, {
                        k: v for k, v in r.headers.items()
                        if k.lower() in {"x-ratelimit-limit", "x-ratelimit-remaining", "retry-after"}
                    }
                except httpx.HTTPError:
                    elapsed = time.perf_counter() - start
                    return 0, elapsed, {}

        tasks = [asyncio.create_task(do_request()) for _ in range(args.total)]
        for coro in asyncio.as_completed(tasks):
            status, elapsed, hdrs = await coro
            results[status] = results.get(status, 0) + 1
            latencies.setdefault(status, []).append(elapsed)
            if status not in sample_headers and hdrs:
                sample_headers[status] = hdrs

    def fmt_ms(v: float) -> str:
        return f"{v*1000:.1f}ms"

    print("\nSummary:")
    for status in sorted(results.keys()):
        count = results[status]
        lats = latencies.get(status, [])
        avg = sum(lats) / len(lats) if lats else 0.0
        print(f"  {status}: {count} (avg {fmt_ms(avg)})")
        hdrs = sample_headers.get(status)
        if hdrs:
            print(f"    headers: {hdrs}")

    # Helpful expectation when RATE_LIMIT_MAX_REQUESTS=100: first ~100 → 200, remainder → 429
    if results.get(429, 0) > 0:
        print("\nRate limit triggered: received 429 responses as expected.")
    else:
        print("\nNo 429 responses observed. Either the limit wasn't reached, or another process used the budget.")


if __name__ == "__main__":
    asyncio.run(main())

# To tes, run:
# uv run scripts/rate_limit_test.py --total 120 --concurrency 120 --url http://127.0.0.1:8000/api/openapi.json --token CvBGWtfSCAifZ9wPcxHIXLfPlGMP1w