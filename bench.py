#!/usr/bin/env python3
"""Benchmark Strata-HotRod with the same cases as ~/dev/strata/build-revision.md.

PREFILL short (~260 prompt tokens, max_tokens 1)
DECODE 128   (max_tokens 128)
PREFILL long  (~666 prompt tokens, max_tokens 1)
DECODE 256   (max_tokens 256)

temperature 0, non-streaming, one warmup then N measured runs per case; reports
each run and the median of runs 2..N (the first decode after a load is 20-40%
slower in every version). Speeds are the engine's own timings.
"""
from __future__ import annotations

import argparse
import json
import secrets
import statistics
import urllib.request

PARA = (
    "A cache keeps the values a program reads most often close to the processor, so the slow memory behind it is "
    "touched less. Every level of the hierarchy trades size for latency: registers are tiny and immediate, DRAM is "
    "large and distant. A good replacement policy guesses which lines will stay useful and evicts the rest, and a "
    "good prefetcher guesses which lines will be needed next and fetches them early. Both guesses can be wrong, and "
    "when they are, the cost is a stall that no amount of arithmetic can hide. Engines that stream weights therefore "
    "measure their hit rate, their read time per megabyte and the queue depth of their reads, and they change the "
    "policy only when the measurement says it pays. "
)
INSTR = "Read the notes below and reply with the single word: ready.\n\n"


def prompt(words: int) -> str:
    text = (PARA * 40)
    ws = text.split()
    return INSTR + " ".join(ws[:words])


def ask(base: str, content: str, max_tokens: int, timeout: float, key: str = "") -> dict:
    body = json.dumps({
        "model": "strata", "temperature": 0, "stream": False,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def one(base: str, content: str, max_tokens: int, timeout: float, key: str = "") -> dict:
    d = ask(base, content, max_tokens, timeout, key)
    t = d.get("timings") or {}
    u = d.get("usage") or {}
    return {
        "prompt_tokens": u.get("prompt_tokens"),
        "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "completion": u.get("completion_tokens"),
        "prompt_n": t.get("prompt_n"),
        "cache_n": t.get("cache_n"),
        "prompt_tps": t.get("prompt_per_second"),
        "decode_tps": t.get("predicted_per_second"),
        "prompt_ms": t.get("prompt_ms"),
        "decode_ms": t.get("predicted_ms"),
        "draft_n": t.get("draft_n"),
        "draft_ok": t.get("draft_n_accepted"),
        "text": d["choices"][0]["message"]["content"],
    }


def fmt(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows[1:] if r[key] is not None]
    return f"{statistics.median(vals):.1f}" if vals else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8091")
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--warm", type=int, default=2,
                    help="warmup requests per case, not measured (the swap cache learns over requests)")
    ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--key", default="", help="API key (Bearer), when the server requires one")
    ap.add_argument("--out", help="write the raw results as JSON here")
    a = ap.parse_args()

    short = prompt(190)
    long = prompt(500)
    cases = [
        # fresh=True: a unique prefix per run, so the prompt is really read (no prefix cache)
        ("PREFILL short", short, 1, "prompt_tps", True),
        ("DECODE 128", short, 128, "decode_tps", False),
        ("PREFILL long", long, 1, "prompt_tps", True),
        ("DECODE 256", long, 256, "decode_tps", False),
    ]

    # warmup: load the model and the caches before any measurement
    w = one(a.base, short, 8, a.timeout, a.key)
    print(f"warmup: {w['prompt_tokens']} prompt tokens, {w['decode_tps']} tok/s, "
          f"draft {w['draft_ok']}/{w['draft_n']}")

    out = {"warmup": w, "cases": {}}
    for name, content, mt, key, fresh in cases:
        for i in range(a.warm):
            c = (f"[warm {i} {secrets.token_hex(6)}]\n" + content) if fresh else content
            one(a.base, c, mt, a.timeout, a.key)
        rows = []
        for i in range(a.runs):
            c = (f"[bench {i} {secrets.token_hex(6)}]\n" + content) if fresh else content
            rows.append(one(a.base, c, mt, a.timeout, a.key))
        out["cases"][name] = rows
        pts = rows[0]["prompt_tokens"]
        print(f"\n{name}: {pts} prompt tokens, max_tokens {mt}")
        for i, r in enumerate(rows, 1):
            extra = f" cache_n {r['cache_n']}" if r["cache_n"] else ""
            print(f"  run {i}: {r[key]:6.1f} tok/s  "
                  f"({r['prompt_ms'] if key == 'prompt_tps' else r['decode_ms']} ms){extra}"
                  + (f" draft {r['draft_ok']}/{r['draft_n']}" if key == "decode_tps" else ""))
        print(f"  median (runs 2+): {fmt(rows, key)} tok/s")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(f"\nraw results: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
