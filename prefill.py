#!/usr/bin/env python3
"""Long-prompt prefill: ~8K tokens, max_tokens 1, unique prefix per run (no cache).

    python3 prefill.py --base http://127.0.0.1:8093 --key bench-key --runs 3
"""
from __future__ import annotations

import argparse
import json
import secrets
import statistics
import urllib.request

FILLER = (
    "The station logs each inspection in a paper ledger, then copies the entry into the digital system at the end of "
    "the shift. Inspectors rotate between the north, south, east and west units on a four-week cycle. The ledger room "
    "is kept at eighteen degrees and the humidity is checked every morning. Spare gaskets are stored in the grey "
    "cabinet beside the service lift, and the calibration weights live in a foam case in the workshop. "
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8091")
    ap.add_argument("--key", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=75, help="filler repeats; ~100 tokens each")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()

    text = FILLER * a.repeat
    rows = []
    for i in range(a.runs):
        p = f"[long {i} {secrets.token_hex(8)}]\n{text}\n\nReply with the single word: ready."
        body = json.dumps({"model": "strata", "temperature": 0, "stream": False, "max_tokens": 1,
                           "messages": [{"role": "user", "content": p}]}).encode()
        h = {"Content-Type": "application/json"}
        if a.key:
            h["Authorization"] = f"Bearer {a.key}"
        req = urllib.request.Request(a.base + "/v1/chat/completions", data=body, headers=h)
        d = json.loads(urllib.request.urlopen(req, timeout=a.timeout).read())
        t = d.get("timings") or {}
        rows.append((d["usage"]["prompt_tokens"], t.get("prompt_per_second"), t.get("prompt_ms"),
                     t.get("cache_n")))
    for n, tps, ms, c in rows:
        print(f"  {n} prompt tokens: {tps:.1f} tok/s ({ms} ms, cache_n {c})")
    vals = [r[1] for r in rows]
    print(f"median: {statistics.median(vals):.1f} tok/s over {sum(r[0] for r in rows)//len(rows)} prompt tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
