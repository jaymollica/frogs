#!/usr/bin/env python3
"""Rebuild results/{release}/runs.jsonl from source, for every release.

A release is one batch of runs published together. The first two releases
were calendar months ("2026-08", "2026-09"); from 2026-09-27 releases are
dated ("2026-09-29") and happen whenever notable new models land.

Sources, in order of preference per release:
  1. results/{release}/raw/*.json  — full records written by run.py
  2. results/{release}/legacy-meta.json + svg/ — snapshot of the live PHP
     harness's meta.json (the production site runs the PHP harness)

Also (when run on the production server) ingests the live PHP layout into the
repo first: pass --import-legacy /var/www/frogs/results (or let the default
autodetect it). Ingestion copies SVGs and snapshots meta.json; it never
modifies the live site.

Every run emits the full 20-column schema (see README); unknown = null,
never fabricated. svg_bytes and comment_count are always recomputed from the
SVG text; discrepancies against stored values are logged and the computed
value wins. Fully idempotent: rebuilds from source every time.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
PROMPT = (ROOT / "prompt.txt").read_text(encoding="utf-8")
PROMPTS = {"habsburg": PROMPT} | {
    p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "prompts").glob("*.txt")}
RESULTS = ROOT / "results"

LEGACY_DEFAULT = pathlib.Path("/var/www/frogs/results")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

COLUMNS = [
    "run_id", "model", "provider", "release", "month", "variant", "run_index", "timestamp",
    "prompt", "system_prompt", "temperature", "top_p", "max_tokens", "seed",
    "produced_svg", "svg", "svg_bytes", "duration_s",
    "prompt_tokens", "completion_tokens", "comment_count", "raw_response",
]


def base_row() -> dict:
    return {k: None for k in COLUMNS} | {
        "prompt": PROMPT, "variant": "habsburg", "system_prompt": None}


def finish_svg_fields(row: dict, svg: str | None, stored_bytes=None, run_id=""):
    if svg is None:
        row["produced_svg"] = False
        return
    row["produced_svg"] = True
    row["svg"] = svg
    row["svg_bytes"] = len(svg.encode("utf-8"))
    row["comment_count"] = len(COMMENT_RE.findall(svg))
    if stored_bytes is not None and stored_bytes != row["svg_bytes"]:
        print(f"  note: {run_id}: stored bytes {stored_bytes} != computed "
              f"{row['svg_bytes']} — using computed", file=sys.stderr)


def release_of(r: dict) -> str:
    """A run's release id: its `release` field, else its UTC month (legacy)."""
    return r.get("release") or dt.datetime.fromtimestamp(r["ts"], dt.UTC).strftime("%Y-%m")


def ingest_legacy(src: pathlib.Path) -> None:
    """Copy the live PHP harness's releases into the repo. Read-only on src."""
    meta_file = src / "meta.json"
    if not meta_file.is_file():
        return
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    for release in sorted({release_of(r) for r in meta}):
        mdir = RESULTS / release
        (mdir / "svg").mkdir(parents=True, exist_ok=True)
        entries = [r for r in meta if release_of(r) == release]
        (mdir / "legacy-meta.json").write_text(
            json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        for r in entries:
            f = r.get("file")
            if f and (src / f).is_file():
                shutil.copy2(src / f, mdir / "svg" / pathlib.Path(f).name)
        print(f"ingested release {release}: {len(entries)} runs")
    rel_file = src / "releases.json"
    if rel_file.is_file():
        shutil.copy2(rel_file, RESULTS / "releases.json")


def rows_from_legacy(release: str, mdir: pathlib.Path) -> list[dict]:
    entries = json.loads((mdir / "legacy-meta.json").read_text(encoding="utf-8"))
    # run_index: chronological within (model, variant, release)
    order: dict[tuple, list] = {}
    for r in sorted(entries, key=lambda r: r["ts"]):
        order.setdefault((r["model"], r.get("variant", "habsburg")), []).append(r["id"])

    rows = []
    for r in entries:
        row = base_row()
        stem = pathlib.Path(r["file"]).stem if r.get("file") else r["id"]
        variant = r.get("variant", "habsburg")
        row.update(
            run_id=stem,
            model=r["model"],
            provider=r.get("lab"),
            release=release,
            month=dt.datetime.fromtimestamp(r["ts"], dt.UTC).strftime("%Y-%m"),
            variant=variant,
            prompt=PROMPTS.get(variant, PROMPT),
            run_index=order[(r["model"], variant)].index(r["id"]) + 1,
            timestamp=dt.datetime.fromtimestamp(r["ts"], dt.UTC)
                        .isoformat().replace("+00:00", "Z"),
            duration_s=(r["duration_ms"] / 1000) if r.get("duration_ms") is not None else None,
            completion_tokens=r.get("tokens_out"),
        )
        row["produced_svg"] = bool(r.get("ok"))
        # gemini-2.5-pro is the one model called with an explicit max_tokens
        if r["model"] == "google/gemini-2.5-pro":
            row["max_tokens"] = 20000
        svg = None
        if r.get("ok") and r.get("file"):
            p = mdir / "svg" / pathlib.Path(r["file"]).name
            svg = p.read_text(encoding="utf-8") if p.is_file() else None
        finish_svg_fields(row, svg, r.get("bytes"), stem)
        rows.append(row)
    return rows


def rows_from_raw(release: str, mdir: pathlib.Path) -> list[dict]:
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted((mdir / "raw").glob("*.json"))]
    # run_index is chronological within (model, variant, release)
    order: dict[tuple, list] = {}
    for r in sorted(records, key=lambda r: r["ts"]):
        order.setdefault((r["model"], r.get("variant", "habsburg")), []).append(r["run_id"])

    rows = []
    for r in records:
        row = base_row()
        params = r.get("request_params") or {}
        resp = r.get("response") or {}
        usage = resp.get("usage") or {}
        content = ""
        try:
            content = resp["choices"][0]["message"]["content"] or ""
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        except (KeyError, IndexError, TypeError):
            pass
        stem = pathlib.Path(r["svg_file"]).stem if r.get("svg_file") else r["run_id"]
        row.update(
            run_id=stem,
            model=r["model"],
            provider=r.get("provider"),
            release=release,
            month=r["ts"][:7],
            variant=r.get("variant", "habsburg"),
            prompt=r.get("prompt", PROMPT),
            run_index=order[(r["model"], r.get("variant", "habsburg"))].index(r["run_id"]) + 1,
            timestamp=r["ts"],
            temperature=params.get("temperature"),
            top_p=params.get("top_p"),
            max_tokens=params.get("max_tokens"),
            seed=params.get("seed"),
            duration_s=r.get("duration_s"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw_response=content or None,
        )
        svg = None
        if r.get("svg_file"):
            p = mdir / r["svg_file"]
            svg = p.read_text(encoding="utf-8") if p.is_file() else None
        finish_svg_fields(row, svg, None, stem)
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-legacy", default=None, metavar="DIR",
                    help="live PHP results dir to ingest (default: autodetect "
                         f"{LEGACY_DEFAULT} if present)")
    args = ap.parse_args()

    legacy = pathlib.Path(args.import_legacy) if args.import_legacy else LEGACY_DEFAULT
    if legacy.is_dir() and legacy.resolve() != RESULTS.resolve():
        ingest_legacy(legacy)

    total = 0
    for mdir in sorted(RESULTS.iterdir()) if RESULTS.is_dir() else []:
        if not mdir.is_dir():
            continue
        release = mdir.name
        if (mdir / "raw").is_dir():
            rows = rows_from_raw(release, mdir)
        elif (mdir / "legacy-meta.json").is_file():
            rows = rows_from_legacy(release, mdir)
        else:
            continue
        rows.sort(key=lambda r: (r["model"], r["variant"], r["run_index"]))
        with (mdir / "runs.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                assert list(row) == COLUMNS, f"column drift in {row['run_id']}"
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        total += len(rows)
        print(f"{release}: {len(rows)} rows -> {mdir / 'runs.jsonl'}")

    if total == 0:
        print("no source data found under results/", file=sys.stderr)
        return 1
    print(f"total: {total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
