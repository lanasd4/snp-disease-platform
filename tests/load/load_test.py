"""
Load test against a running Streamlit server, using the same WebSocket
protocol as a browser.

Usage (server must be running):
python -m streamlit run app/main.py --server.port 8511 --server.headless true
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from urllib.parse import quote

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from tornado.websocket import websocket_connect

SCENARIOS = {
    "home": "",
    "disease_search": "q=" + quote("السكري"),
    "snp_search": "q=rs429358",
    "gene_search": "q=APOE&mode=gene",
    "ranking": "page=ranking",
}
TIMEOUT_S = 120


async def _run_once(ws, query_string: str) -> tuple:
    """Ask the server to run the app once; return (ok, seconds, elements, error)."""
    started = time.perf_counter()
    msg = BackMsg()
    msg.rerun_script.query_string = query_string
    msg.rerun_script.page_script_hash = ""
    ws.write_message(msg.SerializeToString(), binary=True)
    elements = 0
    while True:
        raw = await asyncio.wait_for(ws.read_message(), TIMEOUT_S)
        if raw is None:
            return False, time.perf_counter() - started, elements, "closed"
        forward = ForwardMsg()
        forward.ParseFromString(raw)
        kind = forward.WhichOneof("type")
        if kind == "delta":
            elements += 1
        elif kind == "script_finished":
            ok = forward.script_finished == ForwardMsg.FINISHED_SUCCESSFULLY
            return ok, time.perf_counter() - started, elements, None if ok else "script error"


async def visit(base_url: str, query_string: str, interactions: int) -> dict:
    """One visitor: open a session (first load), then `interactions` reruns in the same session."""
    started = time.perf_counter()
    try:
        ws = await asyncio.wait_for(websocket_connect(f"{base_url}/_stcore/stream"), TIMEOUT_S)
        ok, _, elements, error = await _run_once(ws, query_string)
        first_load = time.perf_counter() - started
        reruns = []
        for _ in range(interactions if ok else 0):
            rerun_ok, seconds, _, error = await _run_once(ws, query_string)
            ok = ok and rerun_ok
            reruns.append(seconds)
        ws.close()
        return {"ok": ok, "seconds": first_load, "reruns": reruns, "elements": elements, "error": error}
    except Exception as exc:  # timeouts, refused connections
        return {"ok": False, "seconds": time.perf_counter() - started, "reruns": [], "error": type(exc).__name__}


def percentile(values, pct):
    values = sorted(values)
    if not values:
        return float("nan")
    index = min(len(values) - 1, round(pct / 100 * (len(values) - 1)))
    return values[index]


async def run_level(base_url: str, users: int, rounds: int, interactions: int) -> dict:
    scenario_names = list(SCENARIOS)
    results = []
    level_start = time.perf_counter()
    for _ in range(rounds):
        tasks = [visit(base_url, SCENARIOS[scenario_names[i % len(scenario_names)]], interactions)
                 for i in range(users)]
        results.extend(await asyncio.gather(*tasks))
    wall = time.perf_counter() - level_start
    ok = [r["seconds"] for r in results if r["ok"]]
    reruns = [s for r in results if r["ok"] for s in r["reruns"]]
    errors = [r["error"] for r in results if not r["ok"]]
    return {
        "users": users, "requests": len(results), "success_rate": round(len(ok) / len(results), 3),
        "median_s": round(statistics.median(ok), 2) if ok else None,
        "p95_s": round(percentile(ok, 95), 2) if ok else None,
        "max_s": round(max(ok), 2) if ok else None,
        "interaction_median_s": round(statistics.median(reruns), 2) if reruns else None,
        "interaction_p95_s": round(percentile(reruns, 95), 2) if reruns else None,
        "throughput_per_s": round(len(ok) / wall, 2),
        "errors": sorted(set(errors)),
    }


async def main_async(args) -> list:
    report = []
    for users in args.users:
        result = await run_level(args.url, users, args.rounds, args.interactions)
        print(json.dumps(result, ensure_ascii=False))
        report.append(result)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="WebSocket load test for the Streamlit app")
    parser.add_argument("--url", default="ws://localhost:8511")
    parser.add_argument("--users", type=int, nargs="+", default=[1, 10, 20, 50])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--interactions", type=int, default=3, help="reruns per session after the first load")
    parser.add_argument("--out", help="write the JSON report here")
    args = parser.parse_args()
    report = asyncio.run(main_async(args))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
