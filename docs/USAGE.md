# BusyBee usage reference

Run every command from the repo root. Prefix with `uv run` (or activate `.venv`).
Setup and a first run are in `README.md`. This file is the reference.

## 1. Commands

`busybee --help` lists them. All paths are relative to the current directory unless absolute.

### run

Runs the full pipeline on a document pack.

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--docs DIR` | yes | | Directory of source documents (pdf, html, md, txt) and an optional `manifest.json`. |
| `--bank ID` | yes | | Bank folder name under the banks directory. |
| `--out DIR` | yes | | Where the HTML bundle is written. |
| `--run-id ID` | no | docs directory name, slugified | Names `workspace/<run-id>/`. Reuse the same id to resume. |
| `--resume` | no | off | Skip stages already finished (section 6). Without it the old `stages.json` is deleted and every stage runs. |
| `--workspace DIR` | no | `workspace` | Parent directory of run folders. |
| `--banks-dir DIR` | no | `banks` | Parent directory of bank folders. |

On success it prints `report: <out>/index.html`. If a stage fails it prints `pipeline failed: <stage>: <error>` and exits 1.
Independent stages still finish when one fails.

```
uv run busybee run --docs data/synthetic/acme_textiles --bank demo_bank --run-id acme --out workspace/acme/out
# bank inputs from the credit request (INR crore); both optional:
#   ... --proposed-exposure 150 --projected-turnover 1100
```

### eval

Scores a finished run against a gold file and prints a metrics table. It calls the LLM as judge (stage name `eval`).

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--workspace-dir DIR` | yes | | The run folder, e.g. `workspace/acme`. Needs `report.json` and `corpus/`. |
| `--company NAME` | no | company in `report.json` | Name or slug used to find `data/gold/<slug>.json`. |
| `--bank ID` | no | bank in `report.json` | Recorded in the eval report. |
| `--gold PATH` | no | | Explicit gold file. Wins over `--company`. |
| `--eval-root DIR` | no | `eval` | Output goes to `<eval-root>/<run_id>/`. |

The gold directory is fixed at `data/gold` (no CLI option).

```
uv run busybee eval --workspace-dir workspace/acme --gold data/gold/acme_textiles.json
```

### rescue

Re-judges facts that the relevance filter dropped (`dropped.json`, stage `verify.relevance`). New facts get the next free `F` ids.
It then sets `scores`, `infer`, `adversary`, `compose` and `render` back to `pending`, so `run --resume` recomputes them.
It uses the LLM (stage name `verify`).

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--workspace DIR` | yes | | The run folder (needs `run.json`). Note: this is the run folder, not the parent. |
| `--bank ID` | yes | | Bank id. |
| `--banks-dir DIR` | no | `banks` | |

```
uv run busybee rescue --workspace workspace/acme --bank demo_bank
uv run busybee run --docs data/synthetic/acme_textiles --bank demo_bank --run-id acme --out workspace/acme/out --resume
```

### formalize

Writes `banks/<bank>/policy.lean` from `policy.md` and `scores.yaml` using a writer LLM and a checker LLM (stage name `formalize`).
It also writes `approval.json` with `approved: false`. A human must review the Lean file (section 4).

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--bank ID` | yes | | Bank id. |
| `--banks-dir DIR` | no | `banks` | |
| `--workspace DIR` | no | `workspace/formalize` | Scratch folder; rounds go to `<workspace>/<bank>`. |

### export-pdf

Prints a finished bundle to PDF with headless Chromium. It tries `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable` on `PATH`.

| Option | Required | Meaning |
| --- | --- | --- |
| `--bundle DIR` | yes | Bundle directory containing `index.html` (the `--out` of `run`). |
| `--out FILE` | yes | PDF to write. Parent folders are created. |

```
uv run busybee export-pdf --bundle workspace/acme/out --out workspace/acme/report.pdf
```

## 2. Environment variables

Nothing is loaded from `.env` automatically. In bash or zsh run `set -a; source .env; set +a`.
In fish, export each variable. Never commit `.env`.

### LLM (`busybee/llm/registry.py`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUSYBEE_LLM_PROVIDER` | `mock` | `openai_compatible` (aliases `openai`, `vllm`, `nim`), `anthropic` (`claude`), or `mock` (`fixture`, `fixtures`). |
| `BUSYBEE_LLM_BASE_URL` | none | Endpoint, e.g. `http://127.0.0.1:8000/v1`. |
| `BUSYBEE_LLM_API_KEY` | none | Key. Falls back to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, then `not-needed`. |
| `BUSYBEE_LLM_MODEL` | `gpt-4o-mini` (openai_compatible), `claude-3-5-sonnet-latest` (anthropic), `mock` | Model id sent to the endpoint. The Brev box serves `busybee-llm`. |
| `BUSYBEE_LLM_MODEL_<STAGE>` | none | Per-stage model. Stage name upper-cased, e.g. `BUSYBEE_LLM_MODEL_VERIFY`. Stages: `extract`, `verify`, `scores`, `infer`, `adversary`, `compose`, `formalize`, `eval`. |
| `BUSYBEE_LLM_TIMEOUT_S` | `1800` | Per-request timeout (seconds) on the OpenAI and Anthropic clients. Extract calls override it with `120 + max_tokens // 4` seconds. A timed-out attempt is charged to the retry budget only for its elapsed time, and the retry log line shows it. |
| `BUSYBEE_LLM_RETRY_BUDGET_S` | `900` | Total seconds a call keeps retrying connection errors, timeouts, 429 and 5xx (exponential backoff, at most 60 s between attempts). |
| `BUSYBEE_LLM_MOCK_CALLABLE` | none | Mock only. `module:function` that answers calls. `make run-synthetic` uses `fake_llm:fake_llm` with `PYTHONPATH=tests/e2e`. |
| `BUSYBEE_LLM_MOCK_DIR` | none | Mock only. Directory of recorded fixtures. |

### Judge (`busybee/verify/judge.py`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUSYBEE_JUDGE` | `llm` | Entailment judge: `llm` (today's behaviour), `classifier` (sidecar only; method `classifier_entailment`, quote is the deterministic chunk line), `tiered` (classifier accepts at prob >= `BUSYBEE_JUDGE_HIGH`, LLM decides the rest; method `tiered_entailment` when the LLM decided). |
| `BUSYBEE_JUDGE_URL` | `http://127.0.0.1:8100` | Sidecar base URL. |
| `BUSYBEE_JUDGE_LOW` / `BUSYBEE_JUDGE_HIGH` | `0.35` / `0.80` | Accept threshold (`HIGH`); `LOW` only matters when accept-only is off, where a prob strictly between them goes to the LLM. |
| `BUSYBEE_JUDGE_ACCEPT_ONLY` | `1` | `1`: the classifier only auto-accepts (prob >= HIGH); everything else goes to the LLM, never auto-reject (benchmark: low scores are not unsupported). `0`: old symmetric band. |
| `BUSYBEE_JUDGE_TIMEOUT_S` / `BUSYBEE_JUDGE_RETRY_BUDGET_S` | `60` / `120` | Per-request timeout and retry budget for the sidecar client. |
| `BUSYBEE_JUDGE_RELEVANCE` | `llm` | `classifier`: entries whose reranker score against the policy slot lines is below `BUSYBEE_RELEVANCE_MIN` are dropped without an LLM call; the rest go to the LLM relevance batch. |
| `BUSYBEE_RELEVANCE_MIN` | `0.2` | Reranker score floor for the above. |

Every classifier decision is appended to `llm_log.jsonl` with task `judge_entailment_classifier`
and its prob. Start the sidecar on the GPU box with `bash tools/judge_sidecar/serve-judge.sh`
(installs `~/judge-venv`, systemd unit `busybee-judge` on port 8100); lower vLLM to
`--gpu-memory-utilization 0.80` first when they share the L40S. API and details:
`tools/judge_sidecar/README.md`. Example: `BUSYBEE_JUDGE=tiered BUSYBEE_JUDGE_URL=http://<box>:8100`.

### Embeddings (`busybee/index/embedder/registry.py`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUSYBEE_EMBED_PROVIDER` | `hashing` | `hashing` (offline, deterministic, weak), `local` (fastembed, bge-small-en-v1.5, CPU; alias `fastembed`), `openai_compatible` (alias `openai`). Use `local` for real runs. |
| `BUSYBEE_EMBED_MODEL` | provider default | Model name override. |
| `BUSYBEE_EMBED_BASE_URL` | `BUSYBEE_LLM_BASE_URL` | openai_compatible only. |
| `BUSYBEE_EMBED_API_KEY` | `BUSYBEE_LLM_API_KEY`, then `OPENAI_API_KEY` | openai_compatible only. |
| `BUSYBEE_EMBED_DIM` | `1536` | openai_compatible only. Must be positive. |

### Pipeline (`busybee/orchestrate/config.py`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUSYBEE_WINDOW_TOKENS` | `12000` | Chunk tokens per extraction window. Doubled from 6000 (half the extract calls); each call holds twice the prompt in the server's KV cache and takes longer, so with `MAX_LEN` 131072 and 16 sequences keep it at or below about 12000 and lower it if the server reports out-of-memory or request timeouts. |
| `BUSYBEE_NOTEBOOK_BUDGET_TOKENS` | `16000` | When the condensed notebook exceeds this, the LLM merges duplicates. |
| `BUSYBEE_EXTRACT_CONCURRENCY` | `6` | Extract windows in flight at once (a dedicated semaphore in `busybee.extract`; the global limit still applies). Extract replies are long (up to 9000 output tokens) and the server is decode-bound, so fewer, longer requests finish sooner than many parallel ones: at 12 streams each decodes slower and calls hit the request timeout, wasting a whole generation. Verify and other stages keep `BUSYBEE_CONCURRENCY`. |
| `BUSYBEE_CONCURRENCY` | `12` | Global limit on parallel LLM calls (`busybee.llm.limiter`); also caps segments per document. The vLLM server is configured for 16 sequences (`--max-num-seqs 16` in `tools/brev/serve-remote.sh`), so 12 keeps it busy with headroom for retries; never set it above 16. |
| `BUSYBEE_SEGMENT_MIN_WINDOWS` | `3` | Minimum windows per segment in `segmented` mode. |
| `BUSYBEE_SLOT_SEARCH_BUDGET` | `24` | Maximum `policy.slot_extract` LLM calls per run when the scores stage searches the documents for score inputs no fact states (at most 4 per component). `0` disables the search. Log: `slot_search.json`. |
| `BUSYBEE_PROPOSED_EXPOSURE` | none | Proposed aggregate bank exposure in INR crore (`--proposed-exposure`). Becomes a `bank_input` fact the Maximum Exposure test binds to. |
| `BUSYBEE_PROJECTED_TURNOVER` | none | Projected next-year turnover in INR crore (`--projected-turnover`). Without it the test falls back to the latest revenue, noted "projection not provided; latest revenue used". |
| `BUSYBEE_EXTRACT_MODE` | `segmented` | `segmented`, `per_document` or `global` (ARCHITECTURE 2.3). |
| `BUSYBEE_REPORT_MIN_IMPORTANCE` | `4` | Facts below this importance (1-5) go to the report appendix instead of section 3. |
| `BUSYBEE_REPORT_MAX_PER_CATEGORY` | `10` | At most this many facts per category in section 3 (referenced facts always stay; 0 = no cap). The rest go to the appendix. |

The extract, render and policy code read no other `BUSYBEE_*` variables.
Values are read when `run` starts and stored in `workspace/<run>/run.json`.

## 3. Workspace files

`workspace/<run_id>/` (gitignored). Models are in `busybee/schema/`.

| Path | Holds |
| --- | --- |
| `run.json` | `RunConfig`: ids, paths, window and concurrency settings. Rewritten at start and end of each run. |
| `stages.json` | List of `StageStatus` (name, state pending/running/done/failed, times, error). |
| `llm_log.jsonl` | One line per LLM call (task, model, usage, latency). |
| `corpus/documents.json` | `Document` list (ids `D1...`, title, kind, sha256, pages). |
| `corpus/pages/<doc_id>.jsonl` | Page text per document. |
| `corpus/chunks.jsonl` | `Chunk`s, ids `D1:p12:c0`. Never cross a page. |
| `index/` | `vectors.npy`, `meta.jsonl`, `chunks.jsonl`: the vector store. |
| `notebook.jsonl` | Append-only `NotebookEntry`s as extract produces them. |
| `notebook.json` | Final merged `NotebookEntry` list. |
| `verified_facts.json` | `VerifiedFact`s (`F001...`) with citations and verification result. Scores (`slot_search`) and adversary add facts here. |
| `slot_search.json` | Queries, hits tried and outcomes of the on-demand search for unbound score inputs. |
| `dropped.json` | `DroppedEntry`s removed by verify, with reason and stage. Input to `rescue`. |
| `scores.json` | `ScoreResult`s with bound inputs, grade, Lean source and compile output. |
| `inferences.json` | `Inference`s (opinion, fact ids, reasoning, Lean status). |
| `concerns.json`, `concerns_dropped.json` | `Concern`s from the adversary stage, and those it discarded. |
| `report.json` | The final `Report`, including audit block. |
| `lean/` | Lean files for inferences (`Inference_I001.lean`, ...). |
| `out/` | Conventional `--out` target: `index.html`, `policy.html`, `sources/`, `lean/`, `assets/`, `data/report.json`, `originals/`. |

Score Lean files are also generated under `lean/Runs/<run_id>/` in the Lake project.
Other folders in `workspace/` (`brev/`, `scratch/`, `remote-logs/`) are tool state, not runs.

## 4. Adding a bank

Create `banks/<bank_id>/` with these files. `demo_bank` is the template.

* `policy.md`. Natural language. The first `# ` heading is the bank name. A line `Version X.Y` sets the version.
  Use `## 1. Title` style sections; they become citable sections `P1...` and anchors on `policy.html`.
* `scores.yaml`. A `scores:` list. Each item has `score_id`, `name`, `unit`, `description`, `inputs`
  (each: `slot`, `description`, `unit`, `scale`), `lean_function`, and `grades` (label plus condition in words).
  Look at `banks/demo_bank/scores.yaml` for exact fields. Money is stored as an integer: INR crore x 100 has `scale: 100`.
* `policy.lean`. Optional. If missing, the scores stage generates one and saves it unapproved.
  Conventions (ARCHITECTURE section 4):
  * Lean 4 core only, no Mathlib. Toolchain is pinned in `lean/lean-toolchain`.
  * All quantities are `Int` in the scale from `scores.yaml`. Write the scale in a comment.
  * No division. `net_debt / ebitda <= 3.5` becomes `2 * net_debt <= 7 * ebitda` with `0 < ebitda`.
  * Tactics: `decide`, `omega`, `simp`, `rfl`. `native_decide` only as a last resort.
  * Mark sections with `-- SECTION: <title>` and put a `/-- doc comment -/` on every `def` and `theorem`.
    The explainer page is built from these.
  * Each score has a value function named by `lean_function`, taking arguments in the order of the input slots,
    and a `_grade` function returning the label exactly as in `scores.yaml`.
* `approval.json`: `{"approved": false, "by": null, "date": null, "notes": "...", "generated_by": null}`.

What "approved" means: a named human has read `policy.lean` against `policy.md` and agrees it says the same thing.
Only then set `approved` to `true`, and fill `by` and `date`. While it is `false`, the report shows a notice bar at the top
that links to the explanation page. `busybee formalize` always writes `approved: false`. Editing
`policy.lean` by hand does not change `approval.json`.

Steps: write `policy.md` and `scores.yaml`, run `busybee formalize --bank <id>`, read the Lean, fix it, then approve.

## 5. Adding a company pack, and a gold file

Pack: a folder of documents, e.g. `data/companies/<company>/`. Add `manifest.json`:

```
{
  "company": "Acme Textiles Limited",
  "annual_report.pdf": {"title": "Acme Annual Report 2024-25", "kind": "annual_report"}
}
```

* Top-level `company` (string) is the name shown in the report. If absent, the first document title is used.
* Each other key is a file name in the same folder. `title` and `kind` are optional per file.
  `kind` must be one of `annual_report`, `drhp`, `financial_statements`, `rating_rationale`, `covenant`,
  `bank_statement`, `news`, `other`. An invalid kind is ignored and the kind is guessed from the file.
* Extra keys (`url`, `fetched_at`, `pages` in `data/companies/*`) are allowed and ignored.
* Files without an entry still load; they get their file stem as title. Unsupported extensions are skipped.
* PDFs under `data/companies/` are gitignored. Do not commit downloaded documents.

Gold file: `data/gold/<slug>.json`. The slug is the company name lower-cased, non-alphanumerics to `_`,
with a trailing `limited`, `ltd`, `pvt`, `private`, `inc` or `corp` dropped ("Acme Textiles Limited" becomes `acme_textiles`).

```
{
  "company": "Acme Textiles Limited",
  "slug": "acme_textiles",
  "material_facts": [
    {"statement": "Revenue from operations was Rs 931.2 crore in FY25.", "category": "revenue",
     "doc_hint": "annual_report.md", "page_hint": 2, "must_have": true}
  ],
  "planted_errors": [
    {"statement": "A wrong claim that must be rejected.", "why_wrong": "What the source really says."}
  ]
}
```

Write facts the way an analyst would: one checkable statement with its number and period. Mark the decisive ones `must_have`.
`category` uses the fact categories in ARCHITECTURE section 3. `planted_errors` are plausible but false; the eval checks that verify rejects them.
Dev gold (`indoco_remedies`, `craftsman_automation`) may be used to tune prompts. Eval-set companies (`bikaji_foods`, `ashoka_buildcon`, `tata_capital`) are held out.

## 6. Resume

`run --resume` reads `workspace/<run_id>/stages.json`. A stage is skipped only if all hold:

1. Its state is `done`.
2. Its output file still exists (ingest `corpus/documents.json`, index `index/vectors.npy`, extract `notebook.json`,
   verify `verified_facts.json`, scores `scores.json`, infer `inferences.json`, adversary `concerns.json`,
   compose `report.json`, render `<out>/index.html`).
3. Every stage it depends on was also skipped.

So a stage that re-runs forces everything downstream to re-run. A failed or interrupted stage (state `failed` or `running`) re-runs.
To redo one stage on purpose, delete its output file, or set its state to `pending` in `stages.json`, then resume.
Use the same `--run-id` (or the same docs folder name) and the same `--workspace`. Without `--resume`, `stages.json` is deleted and all stages run.

Extract and verify also checkpoint inside the stage: `extract_progress.jsonl` (finished segment notebooks) and
`verify_progress.jsonl` (each entry's outcome) in `workspace/<run_id>/`. A resumed stage that is `running` or `failed`
re-runs but reuses everything already in its progress file, then deletes the file when its outputs are written.
Without `--resume` the progress files are deleted.

Dependencies: index and extract need ingest; verify needs extract and index; scores and infer need verify;
adversary needs scores and infer; compose needs adversary; render needs compose.

## 7. Troubleshooting

* **Endpoint refuses connections.** The ssh tunnel is down or the instance is stopped. Run `tools/brev/status.sh`.
  If the instance is stopped or the tunnel is down, run `tools/brev/start.sh` (cold start takes 6-8 minutes).
  `status.sh` shows `vllm: not answering` while the model loads. `start.sh` reads the key from `.env` (`BUSYBEE_LLM_API_KEY`) or `workspace/scratch/brev/key`.
* **Server restarted mid-run (vLLM crashed or reloaded).** Every LLM call retries connection errors, timeouts, 429 and 5xx
  with exponential backoff (at most 60 s between attempts) for up to `BUSYBEE_LLM_RETRY_BUDGET_S` seconds (default 900, 15 minutes),
  logging one `llm retry ...` line per attempt on the `busybee.llm.retry` logger. A reload of about 8 minutes is covered, so the run just pauses and continues.
  Other 4xx errors and schema errors fail at once. If the outage outlasts the budget the run fails with `APIConnectionError`; raise the budget
  (e.g. `BUSYBEE_LLM_RETRY_BUDGET_S=1800`) for longer outages. Then:
  1. `tools/brev/status.sh`: wait for `vllm: healthy` and `127.0.0.1:8000 answers /v1/models`. The tunnel is a self-healing loop
     (`tools/brev/tunnel.sh`, re-opens ssh 5 s after it dies); if it shows `loop down`, run `tools/brev/tunnel.sh start`.
  2. Re-run the same command with `--resume` (same `--run-id`). The failed stage re-runs but picks up `extract_progress.jsonl` /
     `verify_progress.jsonl`, so finished segments and entries are not sent to the LLM again.
* **Authentication errors.** `BUSYBEE_LLM_API_KEY` must equal `VLLM_API_KEY` on the box (`/etc/busybee-vllm.env`).
* **Variables seem ignored.** `.env` is not auto-loaded. Source it in the same shell.
  `BUSYBEE_LLM_PROVIDER` defaults to `mock`, which uses the mock provider, not a real model.
* **Bill is running.** The instance costs $2.23/hr whenever it runs. Run `tools/brev/stop.sh` when idle.
* **vLLM startup problems on the box** (from ORCHESTRATOR_NOTES, only if you re-provision with `tools/brev/serve-remote.sh`):
  * Context 262144 runs out of GPU memory during CUDA-graph profiling on the 48 GB L40S. The unit uses 131072.
  * systemd ignores `Environment=PATH`. The unit's `ExecStart` exports `PATH` and `CUDA_HOME` itself, because vLLM's JIT needs `ninja` and `nvcc`.
  * Do not install `flashinfer-cubin`; its version does not match flashinfer.
  * The NVMe at `/opt/dlami/nvme` is wiped on stop. Models live on the root disk.
  * `brev exec` is flaky. Use `ssh busybee-llm`.
* **Lean not found / all scores `lean_failed` or proofs fail.** BusyBee looks for `lean` and `lake` on `PATH`, then `~/.elan/bin`.
  Install elan (see README). In `lean/`, `lean --version` should print the version in `lean/lean-toolchain`.
  Lean compiles with `lake env lean <file>`; it does not need `lake build` per run.
* **Scores are `not_computable`.** An input slot has no bound fact. Check `dropped.json` for the missing input, run `busybee rescue`, then `run --resume`.
* **`no run.json in ...` from rescue.** `--workspace` must be the run folder (`workspace/<id>`), not `workspace`.
* **`export-pdf needs Chromium`.** Install a Chromium-family browser and make it available on `PATH`.
* **Runs hang or are slow.** Lower `BUSYBEE_CONCURRENCY` if the endpoint queues. The synthetic pack takes about 14 minutes on the Brev box.
* **Tests.** `make test` never needs network or a real model. `make lint` runs ruff.
* **Free opencode models stall.** Wrap agent tasks with `tools/run_opencode_task.sh <name> <model> <prompt-file> [log-dir]`
  (`HARD_TIMEOUT` default 1800 s, `STALL_TIMEOUT` default 300 s; exits 124 or 125). `tools/agent_status.sh` shows task age.
