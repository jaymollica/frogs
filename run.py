#!/usr/bin/env python3
"""FROGS harness: send the fixed prompt to every model on the roster.

Python port of the original PHP harness (generate.php) that runs
https://frogs.vaguespac.es — same prompt, same SVG extraction and
sanitization rules. Unlike the PHP original it retains the full raw
OpenRouter response for every run under results/{month}/raw/.

Usage:
    OPENROUTER_API_KEY=... python run.py                    # 3 runs of every active model
    python run.py --release 2026-09-29 --models grok --runs 1

Outputs, per run:
    results/{release}/raw/{run_id}.json   request params, timing, full response
    results/{release}/svg/{stem}.svg      sanitized SVG (successful runs only)

Only models with status `current` or `control` in models.yaml run by default;
pass --all-statuses to include retired ones.

Then `python build_dataset.py` turns raw/ + svg/ into runs.jsonl.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import secrets
import sys
import time

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parent
TIMEOUT_S = 600
VARIANTS = ("habsburg", "clinical", "plain")


def load_prompt(variant: str) -> str:
    # prompt.txt is the canonical 'habsburg' arm; control arms live in prompts/
    path = ROOT / "prompt.txt" if variant == "habsburg" else ROOT / "prompts" / f"{variant}.txt"
    return path.read_text(encoding="utf-8")

SVG_RE = re.compile(r"<svg\b.*?</svg>", re.I | re.S)
FENCE_RE = re.compile(r"^```[a-z]*\s*$", re.I | re.M)

# mirror of frogs_sanitize_svg() in the PHP harness
_SANITIZERS = [
    (re.compile(r"<script\b.*?</script\s*>", re.I | re.S), ""),
    (re.compile(r"<script\b[^>]*/?>", re.I), ""),
    (re.compile(r"<foreignObject\b.*?</foreignObject\s*>", re.I | re.S), ""),
    (re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I), ""),
    (re.compile(r"\s(xlink:href|href|src)\s*=\s*(\"(?:javascript|https?):[^\"]*\"|'(?:javascript|https?):[^']*')", re.I), ""),
]


def sanitize_svg(svg: str) -> str:
    for rx, repl in _SANITIZERS:
        svg = rx.sub(repl, svg)
    return svg


def extract_svg(text: str):
    text = FENCE_RE.sub("", text)
    m = SVG_RE.search(text)
    return m.group(0).strip() if m else None


def slugify(model: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", model.replace("/", "--"), flags=re.I)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the FROGS benchmark")
    ap.add_argument("--release", "--month", dest="release",
                    default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
                    help="release label, e.g. 2026-09-29 (default: today, UTC)")
    ap.add_argument("--all-statuses", action="store_true",
                    help="also run retired models (default: current + control only)")
    ap.add_argument("--models", default=None,
                    help="only models whose slug contains this substring")
    ap.add_argument("--runs", type=int, default=3, help="runs per model (default 3)")
    ap.add_argument("--variant", choices=VARIANTS, default="habsburg",
                    help="prompt arm (halo experiment); default: the canonical 'habsburg' arm")
    args = ap.parse_args()
    prompt = load_prompt(args.variant)

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    roster = yaml.safe_load((ROOT / "models.yaml").read_text())["models"]
    if not args.all_statuses:
        roster = [m for m in roster if m.get("status", "current") in ("current", "control")]
    if args.models:
        roster = [m for m in roster if args.models.lower() in m["slug"].lower()]
    if not roster:
        print(f"no models match --models {args.models}", file=sys.stderr)
        return 1

    month_dir = ROOT / "results" / args.release
    raw_dir, svg_dir = month_dir / "raw", month_dir / "svg"
    raw_dir.mkdir(parents=True, exist_ok=True)
    svg_dir.mkdir(parents=True, exist_ok=True)

    total = len(roster) * args.runs
    n = ok = 0
    for m in roster:
        for _ in range(args.runs):
            n += 1
            now = dt.datetime.now(dt.UTC)
            run_id = now.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)[:5]
            print(f"[{n}/{total}] {m['slug']} ... ", end="", flush=True)

            payload = {
                "model": m["slug"],
                "messages": [{"role": "user", "content": prompt}],
                **(m.get("params") or {}),
            }
            record = {
                "run_id": run_id,
                "model": m["slug"],
                "provider": m["provider"],
                "variant": args.variant,
                "release": args.release,
                "prompt": prompt,
                "ts": now.isoformat().replace("+00:00", "Z"),
                "request_params": m.get("params") or {},
                "timeout_s": TIMEOUT_S,
            }

            t0 = time.monotonic()
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}",
                             "HTTP-Referer": "https://frogs.vaguespac.es",
                             "X-Title": "FROGS benchmark"},
                    timeout=TIMEOUT_S,
                )
                record["duration_s"] = round(time.monotonic() - t0, 3)
                record["http_status"] = resp.status_code
                body = resp.json()
                record["response"] = body
                if resp.status_code >= 400 or "error" in body:
                    raise RuntimeError(body.get("error", {}).get("message", f"HTTP {resp.status_code}"))
                content = body["choices"][0]["message"]["content"] or ""
                if isinstance(content, list):
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                svg = extract_svg(content)
                if svg is None:
                    record["error"] = "no <svg> block in reply"
                    print("FAIL  no svg")
                else:
                    svg = sanitize_svg(svg)
                    stem = f"{slugify(m['slug'])}--{run_id}"
                    (svg_dir / f"{stem}.svg").write_text(svg, encoding="utf-8")
                    record["svg_file"] = f"svg/{stem}.svg"
                    ok += 1
                    print(f"ok  {record['duration_s']:.1f}s  {len(svg.encode())} bytes")
            except Exception as e:  # noqa: BLE001 — every failure is a data point
                record.setdefault("duration_s", round(time.monotonic() - t0, 3))
                record["error"] = str(e)[:500]
                print(f"FAIL  {record['error'][:120]}")

            (raw_dir / f"{run_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\ndone — {ok}/{total} runs produced an SVG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
