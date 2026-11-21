#!/usr/bin/env python3
"""Quality checks for the Strata-HotRod test service.

Four checks, temperature 0, answers saved as JSON:
  math    a multi-step word problem with one numeric answer
  code    a Python function, extracted and executed against test cases
  json    a strict JSON reply, parsed and validated
  needle  a fact buried in ~4K tokens of text, asked back at the end

These are smoke checks, not a benchmark: they catch broken output (the failure
mode stand-ins can cause), not small quality deltas.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.request

BASE = "http://127.0.0.1:8091"

MATH = (
    "A workshop has 7 shelves. Each shelf holds 12 boxes, and each box holds 9 gears. "
    "On Monday 4 boxes are taken away and 2 shelves are emptied completely. "
    "On Tuesday 31 new gears are added to the remaining stock. "
    "How many gears are in the workshop now? Show the steps and end with the line: ANSWER: <number>"
)

CODE = (
    "Write a Python function `merge_ints(*lists)` that takes any number of lists of integers, merges them, "
    "removes duplicates, and returns the result sorted ascending. It must accept zero arguments (returns []) "
    "and must not modify the input lists. Reply with one fenced ```python block containing only the function."
)

JSON_Q = (
    'Reply with one JSON object and nothing else, with exactly these keys: "name" (string), '
    '"ports" (array of 3 integers, ascending), "enabled" (boolean), "note" (string or null). '
    'Use the name "edge-7", ports 8080, 8443, 9090, enabled true, note null.'
)

NEEDLE = (
    "The maintenance code for the west turbine is TANGO-4417-ZULU. "
    "It must be quoted exactly, with the dashes, when the audit asks for it."
)

FILLER = (
    "The station logs each inspection in a paper ledger, then copies the entry into the digital system at the end of "
    "the shift. Inspectors rotate between the north, south, east and west units on a four-week cycle. The ledger room "
    "is kept at eighteen degrees and the humidity is checked every morning. Spare gaskets are stored in the grey "
    "cabinet beside the service lift, and the calibration weights live in a foam case in the workshop. "
)


KEY = ""


def ask(base: str, prompt: str, max_tokens: int, timeout: float, key: str = "") -> dict:
    body = json.dumps({
        "model": "strata", "temperature": 0, "stream": False, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    headers = {"Content-Type": "application/json"}
    k = key or KEY
    if k:
        headers["Authorization"] = f"Bearer {k}"
    req = urllib.request.Request(base + "/v1/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    t = d.get("timings") or {}
    msg = d["choices"][0]["message"] or {}
    return {
        "text": msg.get("content") or "",
        "reasoning": msg.get("reasoning_content") or msg.get("reasoning") or "",
        "finish": d["choices"][0].get("finish_reason"),
        "usage": d.get("usage"),
        "timings": {k: t.get(k) for k in ("prompt_n", "cache_n", "prompt_per_second",
                                          "predicted_per_second", "draft_n", "draft_n_accepted")},
    }


def check_math(text: str) -> dict:
    m = re.findall(r"ANSWER:\s*(-?\d+)", text)
    # 7*12*9 = 756; remove 4 boxes (36 gears) and 2 shelves (2*108=216): 756-36-216=504; +31 = 535
    return {"answer": int(m[-1]) if m else None, "expected": 535,
            "ok": bool(m) and int(m[-1]) == 535}


def check_code(text: str) -> dict:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if not m:
        return {"ok": False, "why": "no fenced python block"}
    code = m.group(1)
    tests = (
        "assert merge_ints([1,3],[2,3],[]) == [1,2,3]\n"
        "assert merge_ints() == []\n"
        "a=[3,1]; merge_ints(a); assert a==[3,1]\n"
        "assert merge_ints([5],[5,5]) == [5]\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = f"{d}/t.py"
        open(p, "w").write(code + "\n" + tests)
        r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=30)
    return {"ok": r.returncode == 0, "stderr": r.stderr[-800:], "code": code}


def check_json(text: str) -> dict:
    try:
        d = json.loads(text.strip())
    except Exception as e:
        return {"ok": False, "why": f"parse: {e}"}
    ok = (d.get("name") == "edge-7" and d.get("ports") == [8080, 8443, 9090]
          and d.get("enabled") is True and d.get("note") is None and set(d) == {"name", "ports", "enabled", "note"})
    return {"ok": ok, "parsed": d}


def check_needle(text: str, needle: str) -> dict:
    return {"ok": needle in text, "needle": needle}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--key", default="", help="API key (Bearer), when the server requires one")
    ap.add_argument("--out", default="quality.json")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    global KEY
    KEY = a.key

    filler = (FILLER * 40)  # ~4K tokens
    needle_prompt = (
        f"Here is the station log.\n\n{NEEDLE}\n\n{filler}\n\nEnd of log.\n\n"
        "According to the log, what is the maintenance code for the west turbine? Quote it exactly."
    )

    out = {}
    cases = [("math", MATH, 1500), ("code", CODE, 900), ("json", JSON_Q, 400),
             ("needle", needle_prompt, 600)]
    for name, prompt, mt in cases:
        r = ask(a.base, prompt, mt, a.timeout)
        if name == "math":
            r["check"] = check_math(r["text"])
        elif name == "code":
            r["check"] = check_code(r["text"])
        elif name == "json":
            r["check"] = check_json(r["text"])
        else:
            r["check"] = check_needle(r["text"] + "\n" + r["reasoning"], "TANGO-4417-ZULU")
        out[name] = r
        print(f"\n=== {name}: {'OK' if r['check']['ok'] else 'FAIL'} "
              f"(prompt {r['usage']['prompt_tokens']}, {r['timings']['predicted_per_second']} tok/s, "
              f"finish {r['finish']}) ===")
        print(r["text"][:1200] or f"(empty; reasoning:) {r['reasoning'][:1200]}")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    ok = sum(1 for r in out.values() if r["check"]["ok"])
    print(f"\n{ok}/{len(out)} checks passed; raw answers in {a.out}")
    return 0 if ok == len(out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
