#!/usr/bin/env python3
"""Run the 22-prompt reporting-AI statistical stress test against a live INT instance.

Usage:
    python tools/reporting_ai_eval/run_eval.py [base_url] [out_dir]

Defaults: base_url=http://127.0.0.1:8000, out_dir=tools/reporting_ai_eval/results

Logs in via /dev/login/<user>, POSTs each prompt from prompts.json to
/api/reporting/ai/agent (stream: false, empty history), and saves the full
JSON response per case as <NN>.json. Skips cases whose output file already
exists, so an interrupted run resumes where it left off - delete a file (or
the whole out_dir) to force a re-run.

# ponytail: sequential, one session, single 429 retry - a 22-case eval isn't
# worth a retry framework.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "results"
LOGIN_USER = "ben.streich"

PROMPTS = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))

OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
r = s.get(f"{BASE}/dev/login/{LOGIN_USER}", timeout=30)
r.raise_for_status()
r = s.get(f"{BASE}/reporting", timeout=30)
m = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
if not m:
    print("FATAL no csrf token - is /dev/login enabled on this environment?")
    sys.exit(1)
csrf = m.group(1)
print(
    f"logged in as {LOGIN_USER}, csrf ok, chat toggle present: {'rpChatToggle' in r.text}",
    flush=True,
)

for case in PROMPTS:
    n, q = case["n"], case["prompt"]
    out = OUT / f"{n:02d}.json"
    if out.exists():
        print(f"{n:02d} skip (exists)", flush=True)
        continue
    t0 = time.time()
    body = {"question": q, "history": [], "source": None, "stream": False}
    try:
        r = s.post(
            f"{BASE}/api/reporting/ai/agent", json=body, headers={"X-CSRFToken": csrf}, timeout=600
        )
        if r.status_code == 429:
            print(f"{n:02d} 429, waiting 70s", flush=True)
            time.sleep(70)
            r = s.post(
                f"{BASE}/api/reporting/ai/agent",
                json=body,
                headers={"X-CSRFToken": csrf},
                timeout=600,
            )
        elapsed = round(time.time() - t0, 1)
        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text[:2000]}
        rec = {"n": n, "prompt": q, "status": r.status_code, "elapsed_s": elapsed, "response": data}
        out.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        answer = data.get("answer") or ""
        print(
            f"{n:02d} http={r.status_code} {elapsed}s turns={data.get('turns')} "
            f"sql={bool(data.get('sql'))} def={bool(data.get('definition'))} "
            f"stop={data.get('stoppedReason')} ans={len(answer)}ch",
            flush=True,
        )
    except Exception as e:
        out.write_text(
            json.dumps({"n": n, "prompt": q, "error": str(e)}, indent=2), encoding="utf-8"
        )
        print(f"{n:02d} EXC {e}", flush=True)
    time.sleep(7)  # AI routes are rate-limited to 10/min

print("ALL DONE", flush=True)
