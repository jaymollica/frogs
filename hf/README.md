---
license: cc-by-4.0
language:
  - en
tags:
  - benchmark
  - evaluation
  - llm-behavior
  - svg
  - code-generation
pretty_name: FROGS — the Habsburg-jaw SVG benchmark
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files: "data/*/runs.jsonl"
---

# FROGS — the Habsburg-jaw SVG benchmark

## What this is

One prompt, every model, three runs per release, drawn sight-unseen. Each
release, the models involved are asked — via a single identical user message,
with no system prompt and no feedback loop — to produce an SVG of a frog with
a Habsburg jaw. Every attempt is published unedited at
<https://frogs.vaguespac.es>, and archived here as data.

The value is longitudinal and behavioral: the same obscure prompt, forever.
What changes from release to release is the models.

**Cadence.** The first two releases were calendar months (`2026-08`,
`2026-09`: the whole roster, on the 1st). From 2026-09-27 releases are
event-driven: a daily scout watches OpenRouter's catalogue, and when a cluster
of notable new models has appeared it proposes a release, which a human
approves. A release runs the new models plus a frozen **control set** of five
models that draw again every time, so drift in a fixed slug stays visible
between releases.

## The exact prompt

```
Generate an SVG of a frog with a Habsburg jaw. Reply with only the SVG markup — no explanation, no markdown fences.
```

(Single line, no trailing newline; the dash is an em dash, U+2014. The
canonical bytes are in [`prompt.txt`](prompt.txt).)

## Protocol

- **Models:** the OpenRouter slugs in [`models.yaml`](models.yaml), each with
  a status and dated roster changes. A model's absence in a release means it
  wasn't on the roster (or wasn't new) then, not that it failed.
- **Roster policy (from 2026-09-27): rolling membership, add-only history.**
  A model joins when it clears the scout's gate — an Artificial Analysis
  intelligence index at or above the current roster's median, or a top-30
  place on OpenRouter's daily token rankings while still unscored, or being
  the newest member of a model family already on the roster — and the
  release is approved. When a newer member of its family joins, the older
  one is **retired**: it stops running, but every run it ever made stays in
  the dataset. Five **control** models never retire and run in every
  release; they are the drift-control group. Before 2026-09-27 the policy
  was add-only membership by hand.
- **Runs:** 3 per model per prompt arm per release, sequential.
- **Prompt arms (halo experiment, from 2026-09):** the same anatomy is
  requested under three names, in fully independent calls —
  `habsburg` ("a Habsburg jaw", the canonical arm shown on the site),
  `clinical` ("mandibular prognathism"), and `plain` ("a heavily protruding
  lower jaw"). Only the anatomy term differs; the wrapper sentence is
  identical (canonical bytes in [`prompt.txt`](prompt.txt) and
  [`prompts/`](prompts/)). The design isolates how much royal imagery the
  word "Habsburg" itself summons: crowns that appear under one name but not
  another are contributed by the name. Release 2026-08 predates the
  experiment and contains only the `habsburg` arm.
- **Routing:** OpenRouter `/chat/completions`, provider chosen by OpenRouter's
  default routing. No retries; a failure is recorded as a failure.
- **Sampling:** `temperature`, `top_p`, and `seed` are **never set** — provider
  defaults, unset. `max_tokens` is unset except for `google/gemini-2.5-pro`,
  which is called with `max_tokens: 20000` and a reasoning-token cap
  (`reasoning: {max_tokens: 4096}`) because it otherwise tends to spend its
  entire output budget on reasoning tokens and return empty content.
- **Timeout:** 600 seconds per request. (The first 15 runs of 2026-08 used a
  180 s timeout; one DeepSeek run failed against it and was re-run after the
  timeout was raised.)
- **Post-processing:** the first `<svg>…</svg>` block is extracted; markdown
  fences are stripped if present; the SVG is sanitized for serving
  (`<script>`, `foreignObject`, `on*` handlers, and `javascript:`/external
  `href`/`src` references removed). Sanitization is part of the published
  artifact — the stored SVG is the sanitized one; the unmodified model output
  is retained in `raw_response` for rows produced with `run.py`.

## What it measures

Cross-model variation on a fixed, unrehearsed task:

- **Unprompted elaboration** — "Habsburg jaw" names an anatomical feature
  (mandibular prognathism), yet in August 2026, 7 of 14 models dressed the
  frog in crowns, ruffs, or regalia the prompt never mentioned.
- **Semantic association** — what a model reaches for when a prompt joins two
  distant concepts (amphibian anatomy × Habsburg iconography).
- **Output determinism** — e.g. `mistralai/mistral-large-2512` produced two
  byte-identical SVGs in separate August runs.
- **Verbosity** — output sizes in the same release ranged from 536 bytes to
  14,329 bytes for the same prompt.
- **Latency** — wall-clock generation time ranged from ~5 s to ~257 s.
- **Code commentary** — what models say in SVG comments while drawing
  (`comment_count`, and the comments themselves inside `svg`).

## Limitations

State-of-the-art honesty section; read this before citing anything.

- **No image-quality judgement is performed.** Nothing scores whether a frog
  is good, frog-like, or has a convincing jaw. A ranking stage (pairwise
  vision-model judging) was prototyped and deliberately removed; this dataset
  is observational only.
- **The release digest on the website is generated from SVG comments and run
  metadata, not from rendered images.** No component of the pipeline ever
  looks at the drawings.
- **n = 3 runs/model/release is far too small** to separate model differences
  from sampling noise. Byte-identical repeats are informative; almost nothing
  else about within-model variance is.
- **Sampling parameters are provider defaults and unrecorded** (except where
  noted). Cross-model comparisons conflate model behavior with provider
  serving configuration. OpenRouter routing may also change providers between
  releases for the same slug.
- **2026-08 contains only successful runs.** Three failed runs from the first
  benchmark day (2 × gemini-2.5-pro empty responses, 1 × deepseek-v4-pro
  timeout at the original 180 s limit) were re-run and their failure records
  discarded before this dataset existed. From 2026-09 onward, failures are
  retained as `produced_svg: false` rows.
- **`prompt_tokens` and `raw_response` are null for rows produced by the live
  PHP harness** (all releases so far) — it does not retain raw API responses.
  Rows produced with `run.py` carry both.
- **Roster selection is partly automatic** from 2026-09-27 (see Protocol).
  The gate leans on a third-party benchmark index and on OpenRouter usage,
  so which models appear reflects those signals' coverage and biases.
- **One prompt.** This measures behavior at a single point in prompt space;
  it says nothing about breadth.

## Data schema

`results/{release}/runs.jsonl`, one JSON object per line, one line per run.
Release ids are `YYYY-MM` for the two monthly releases and `YYYY-MM-DD` after
that. `results/releases.json` records what each dated release added, retired
and re-ran as control. Every key present on every row; `null` = not recorded,
never estimated.

| field | type | notes |
|---|---|---|
| `run_id` | string | Stable unique ID (SVG filename stem) |
| `model` | string | Exact OpenRouter slug, e.g. `anthropic/claude-opus-5` |
| `provider` | string | e.g. `Anthropic` |
| `release` | string | release id: `2026-08`, `2026-09`, then `YYYY-MM-DD` |
| `month` | string | `YYYY-MM` of the run timestamp |
| `variant` | string | prompt arm: `habsburg` (canonical), `clinical`, `plain` |
| `run_index` | int | 1..3, chronological within (model, variant, release) |
| `timestamp` | string | ISO 8601 UTC (`Z`) |
| `prompt` | string | Full prompt text as sent for this row's arm |
| `system_prompt` | string \| null | `null` — none is ever sent |
| `temperature` | float \| null | `null` = provider default, unset |
| `top_p` | float \| null | ditto |
| `max_tokens` | int \| null | set only for gemini-2.5-pro (20000) |
| `seed` | int \| null | never set |
| `produced_svg` | bool | response contained a parseable `<svg>` block |
| `svg` | string \| null | sanitized SVG source; `null` if none |
| `svg_bytes` | int \| null | UTF-8 byte length, recomputed at build time |
| `duration_s` | float \| null | wall-clock request latency |
| `prompt_tokens` | int \| null | null for 2026-08 (not retained) |
| `completion_tokens` | int \| null | from OpenRouter usage |
| `comment_count` | int \| null | `<!-- -->` nodes in the SVG, recomputed |
| `raw_response` | string \| null | full pre-extraction output; null for 2026-08 |

The SVG files themselves are also checked in under `results/{release}/svg/`,
and, for rows produced with `run.py`, full raw API records under
`results/{release}/raw/`.

## Reproducing

```bash
git clone <REPO_URL> && cd frogs
pip install -r requirements.txt

# rebuild runs.jsonl from the checked-in source data
python build_dataset.py

# run a fresh release yourself (spends OpenRouter credit)
export OPENROUTER_API_KEY=sk-or-...
python run.py --release 2026-10-05         # canonical arm, active models × 3 runs
python run.py --release 2026-10-05 --variant clinical
python run.py --release 2026-10-05 --variant plain
python run.py --models grok --runs 1       # or a smaller slice
python build_dataset.py

# load the published dataset
python -c "from datasets import load_dataset; print(load_dataset('<HF_USER>/frogs', split='train'))"
```

## Licensing

- **Code** (`run.py`, `build_dataset.py`, `push_to_hf.py`): MIT — see
  [`LICENSE-CODE`](LICENSE-CODE).
- **Data** (`results/`, including SVGs and raw responses): CC BY 4.0 — see
  [`LICENSE-DATA`](LICENSE-DATA). Rows are outputs of third-party models;
  provider terms may independently apply to reuse.

## Citation

```bibtex
@misc{frogs2026,
  author       = {Mollica, Jay},
  title        = {FROGS: the Habsburg-jaw SVG benchmark},
  year         = {2026},
  howpublished = {\url{https://frogs.vaguespac.es}},
  note         = {Longitudinal dataset of LLM-generated SVGs, released as new models appear}
}
```
