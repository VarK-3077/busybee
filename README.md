# BusyBee

**Verified, explainable credit reviews.** AEGIS 2026, problem statement 05 (explainable and
responsible credit review generation). Team Stardust Crusaders.

BusyBee reads a borrower's whole document pack (annual report, rating rationales, news, bank
records: hundreds of pages, more than any model can read at once) and writes a credit review
against a bank's lending policy. A reviewer never has to take the model's word for anything:

1. **Every fact cites its page.** The pack is read in fixed windows; each fact carries the chunk
   (document, page) it came from, and one click opens the original PDF at that page.
2. **Every fact is checked against that page.** A verifier compares each statement with the text
   it cites (numbers matched in code first); wrong pages are re-cited from a vector index, wrong
   facts are dropped.
3. **Every score and rule is proved in Lean.** The bank's policy (scores, thresholds, hard rules)
   is written in Lean 4 once, with guarantees that hold for every borrower. On each run Lean
   computes the scores from cited inputs and proves each rule's outcome.
4. **What is missing or conflicting is listed, not guessed.** A fresh investigator agent reads the
   draft, searches the index for what a credit officer would still want, verifies what it finds,
   and lists the rest as open questions with the search it ran.

```
ingest ──┬── index (vector DB) ───────────────────────────┐
         └── extract (windows) ──► verify ──┬── scores (policy + Lean) ──┐
                                            └── infer (+ Lean) ─────────┤
                                                                        ▼
                             render ◄── compose (recommendation) ◄── adversary (investigate)
```

Results on Indoco Remedies (369 pages, same model for both): BusyBee found 93.3% of the facts a
credit officer must see against 20% for the model given the pack directly, with 99.2% of
citations verified, 100% page-exact, and 100% of proofs passing. The plain agent approved a loan
the policy says to decline; BusyBee declined it and proved why.

## Sample output (included)

Open **`workspace/indoco-v11/out/index.html`** in a browser. Click any fact to see its quote and
open the source PDF page; click a "Lean" chip to see the proof behind a score; section 5 lists the
open questions and conflicts. The evaluation of that run is
`workspace/eval-indoco-v11/indoco-v11/metrics.md`.

## How to run

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and Lean 4 via elan (no Mathlib; version
pinned in `lean/lean-toolchain`).

```
uv sync
cd lean && lake build && cd ..        # builds the bank policy proofs once
make test                             # unit tests, no network
make run-synthetic                    # whole pipeline with a mock LLM; open workspace/synthetic/out/index.html
```

With a real model (any OpenAI-compatible endpoint, e.g. vLLM or NVIDIA NIM), set in `.env`
(gitignored) and load it into the shell:

```
BUSYBEE_LLM_PROVIDER=openai_compatible
BUSYBEE_LLM_BASE_URL=http://127.0.0.1:8000/v1
BUSYBEE_LLM_API_KEY=<key>
BUSYBEE_LLM_MODEL=<served model name>
BUSYBEE_EMBED_PROVIDER=local
```

```
set -a; source .env; set +a
uv run busybee run --docs data/companies/indoco_remedies --bank demo_bank \
    --run-id indoco --out workspace/indoco/out --proposed-exposure 150
uv run busybee eval --workspace-dir workspace/indoco --company indoco_remedies --bank demo_bank
uv run busybee ask --workspace-dir workspace/indoco "What did the USFDA find at Goa?"
```

`--proposed-exposure` is the bank's input (the loan asked for, INR crore). `busybee ask` answers
questions over a finished run's documents, citing and verifying each sentence. Add `--resume` to
continue an interrupted run. All commands and environment variables: `docs/USAGE.md`.

## Where things live

Inputs:
* `data/companies/<slug>/`: a borrower's document pack (PDF, HTML, Markdown) plus `manifest.json`.
* `banks/<bank>/`: the bank's policy (`policy.md`), score and rule definitions (`scores.yaml`),
  its Lean formalisation (`policy.lean`) and approval record.
* `data/gold/`: hand-written lists of important facts per company, used only by `busybee eval`.

Each run writes `workspace/<run_id>/`:
* `corpus/`: parsed pages and chunks. `index/`: the vector database (`vectors.npy` embeddings,
  `chunks.jsonl`, `meta.jsonl`), used for re-citing, the investigator and `busybee ask`.
* `notebook.jsonl`: raw extracted facts; `verified_facts.json` / `dropped.json`: what verification
  kept and rejected, with reasons.
* `scores.json`, `policy_eval.json`, `lean/`: bound inputs, scores, rule outcomes and the Lean files.
* `concerns.json`, `conflicts.json`: the investigator's open questions and cross-document conflicts.
* `llm_log.jsonl`: every LLM call; `stages.json`: progress, for `--resume`.
* `out/`: the HTML report (`index.html`, `sources/`, `lean/`, `policy.html`, `originals/` PDFs).

`busybee eval` writes `eval/<run_id>/metrics.md` (or under `--eval-root`).

## Docs

`docs/ARCHITECTURE.md` (stages, data contract, Lean conventions), `docs/USAGE.md` (CLI and
configuration).
