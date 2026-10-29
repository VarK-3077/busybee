# BusyBee — Architecture

BusyBee is a pipeline around an LLM that reads a borrower's document pack and produces a
compact, fully auditable credit-review report (static HTML that looks like a simple PDF
document). Three goals, in priority order:

1. **No errors.** Every statement in the report is either verified against its cited chunk,
   or (for calculations) proved in Lean, or clearly marked as a judgement with its evidence.
2. **Nothing important missing.** Everything a credit officer needs to decide on a credit line.
3. **Fast to audit.** Every sentence opens a popup listing the exact source chunks; one click
   lands on the page; a back button returns to the sentence. Lean proofs link to the
   human-auditable premises.

Problem statement: AEGIS 2026 PS 05 (explainable, responsible credit review generation).

---

## 1. Repository layout

```
aegis26/
  pyproject.toml  uv.lock  Makefile  README.md
  busybee/                 Python package (3.12, uv). One directory per component,
                           one file per sub-component, functions for everything.
    schema/                pydantic v2 models — THE CONTRACT every stage reads/writes
    llm/                   provider abstraction (openai-compatible, anthropic, mock) + audit log
    ingest/                documents -> pages -> chunks (page-exact, stable ids)
    index/                 embeddings + vector store + search
    extract/               rolling-window reader that writes the "notebook" of candidate facts
    verify/                relevance + citation verification + re-citation via vDB
    policy/                bank filesystem, score input binding, Lean score generation,
                           auto-formalisation (writer/checker loop)
    lean/                  Lean toolchain wrapper (compile, hash, errors) + manual explainer
    infer/                 Section 3 inferences (+ Lean for quantitative ones)
    adversary/             fresh-context critique -> vDB gap search -> concerns
    compose/               recommendation + report assembly
    render/                Jinja2 -> static HTML bundle (report, sources, lean pages, popups)
    orchestrate/           stage DAG, workspace, resume, concurrency
    eval/                  internal + official metrics, gold sets, planted errors
    cli.py                 `busybee run / eval / rescue / formalize / export-pdf`
  design/                  design language: tokens.css, components.css, components.js,
                           styleguide.html (built once, reused by render/)
  lean/                    Lake project: lean-toolchain, lakefile, BusyBee/ library
  banks/<bank_id>/         bank filesystem: policy.md, scores.yaml, policy.lean, approval.json
  data/synthetic/<co>/     tiny hand-written corpus for fast tests
  data/companies/<co>/     public docs (DRHP, annual reports, rating rationales, news)
  data/gold/<co>.json      analyst-style gold list of material facts
  tests/                   pytest, mirrors busybee/ layout
  docs/                    this file, CODE_STYLE.md, tasks/
  workspace/<run_id>/      (gitignored) all per-run intermediate + final outputs
```

---

## 2. Pipeline

```
ingest ──┬── index  ─────────────────────────┐
         └── extract (rolling notebook) ──► verify ──┬── scores (policy + Lean) ──┐
                                                     └── infer (+ Lean) ─────────┤
                                                                                 ▼
                                      render ◄── compose(recommendation) ◄── adversary
```

Branches drawn in parallel are independent and run concurrently. Every stage:

* reads only files in `workspace/<run_id>/` written by earlier stages (plus `banks/`),
* writes its own output files atomically (write to `*.tmp`, then rename),
* records status in `workspace/<run_id>/stages.json`, so a run can be resumed and a
  finished stage is skipped,
* makes LLM calls only through `busybee.llm`, which logs every call to `llm_log.jsonl`.

Stability beats speed: no shared mutable state between stages, parallelism inside a stage is
`asyncio.gather` over independent items behind one global semaphore.

### 2.1 ingest  (`busybee/ingest/`)
Input: a directory of files (pdf, html, md, txt). Output: `corpus/documents.json`,
`corpus/pages/<doc_id>.jsonl`, `corpus/chunks.jsonl`.

* Documents get ids `D1, D2, …` in a deterministic order (sorted by kind priority then name).
* Pages are 1-based; page text is extracted with PyMuPDF (text + simple table flattening).
  Non-PDF files are a single page unless they contain explicit page breaks.
* Chunks never cross a page boundary (this is what makes citations page-exact). Target
  ~700 tokens, overlap ~80 tokens, split on paragraph boundaries. Chunk id `D{doc}:p{page}:c{n}`.
  Each chunk stores `char_start/char_end` offsets into the page text, so the source viewer can
  highlight it.
* Document kind is inferred from filename/first page keywords, overridable by a
  `manifest.json` in the input directory.

### 2.2 index  (`busybee/index/`)
Embeds every chunk and stores vectors in a local, serverless store (`index/vectors.npy` +
`index/meta.jsonl`, cosine search in numpy). Embedder is pluggable: `local` (fastembed,
bge-small-en-v1.5, CPU) or `openai_compatible` (any `/v1/embeddings` endpoint).
`search(query, k, doc_kinds=None) -> list[ScoredChunk]`. Also exposes `get_chunk(chunk_id)`.

### 2.3 extract — the rolling notebook  (`busybee/extract/`)
The "temporary document". Documents are read in order of kind priority
(financial_statements, annual_report, drhp, rating_rationale, covenant, bank_statement, news,
other). Chunks are grouped into windows of `window_tokens` (default 12000). For each window the
LLM receives: the condensed notebook so far (one line per entry) + the new chunks (each
prefixed with its chunk id) and returns new `NotebookEntry` objects, each with the chunk ids it
came from, a category, a kind (fact | number | concern) and an importance 1–4 from the model (4 only for policy-named topics, 3 useful context, 2 minor detail, 1 boilerplate); code raises policy-feeding facts to 5. It may also
mark an entry as superseding an earlier one (e.g. a restated figure).

* Default mode `segmented`: each document's windows are grouped into K contiguous, balanced
  segments, K = max(1, min(`concurrency`, n_windows // `segment_min_windows`)) with
  `segment_min_windows` default 2 (env `BUSYBEE_SEGMENT_MIN_WINDOWS`). Every segment keeps its
  own sequential rolling notebook (condensing and supersedes as below) and is told which pages
  it is reading ("pages 120–180 of 300"); segments and documents run concurrently via
  `asyncio.gather` behind the global limiter. Segment notebooks are concatenated in document
  order and ids renumbered per document; supersede links are only resolved inside a segment,
  and cross-segment duplicates are left to verify's dedupe. `notebook.jsonl` is appended in
  merged order once extraction finishes, so its order is deterministic.
* Mode `per_document`: one sequential rolling notebook per document, documents in parallel,
  then merged. Mode `global` processes the whole corpus sequentially. Both append to
  `notebook.jsonl` per window.
* If the condensed notebook exceeds `notebook_budget_tokens`, `condense.py` asks the LLM to
  merge duplicates (union of citations kept). This is rare and logged.
* Importance from the policy (`policy_focus.py`): after a document's entries are merged, 5 is
  set by code for a fact whose metric matches a score input, rule input or judged slot of the
  bank (`scores.yaml`: slot names, description heads, `derive_from` components, judge keywords,
  rating grades); every other entry keeps the model's rating capped at 4, where the prompt
  allows 4 only for policy-named topics (ratings and outlook, litigation, auditor remarks,
  promoter holding and pledge, regulatory actions, defaults, caution-list sectors). There is
  no `extract_calibrate` call. The extraction system prompt also carries a short policy
  checklist built from the bank and tells the model to write only facts relevant to the credit
  decision.
* Rating rationales first (`rating_first.py`): documents of kind `rating_rationale` are
  extracted before the rest, and a digest of their key points (importance order, at most 800
  tokens, no LLM call) is added to every other document's prompt as "what the rating agency
  flagged".
* Boilerplate pages (`boilerplate.py`): pages of annual reports and DRHPs under an AGM notice,
  director profiles, CSR report, BRSR, corporate governance report, secretarial audit MR-3,
  route map, proxy form or attendance slip titles are skipped before windowing (never pages
  with financial statements, notes, the auditor's report or the MD&A); listed in
  `extract_skipped_pages.json`. `BUSYBEE_SKIP_BOILERPLATE=0` disables, `BUSYBEE_BOILERPLATE_TITLES`
  adds title regexes.
* Table-row records keep their statement heading (`FactRecord.section`, `sections.py`), e.g.
  "Non Current Assets > Financial Assets"; the statement then says "non-current investments".
* Structured fact records (`FactRecord`: metric, value, unit, period, scope, qualifier,
  previous_value, previous_period; `NotebookEntry.record`, carried to `VerifiedFact.record`).
  When a window contains a `[TABLE:` block the prompt also asks for `records` (response model
  `WindowOutput.records: list[RecordDraft]`): one per material table row, metric exactly as the
  row label, unit as printed, period from the column header, scope from the caption, chunk ids
  and importance; sentence `entries` remain for prose. Code builds the entry: `statement =
  statement_from_record(record)` (`templates.py`, deterministic, Indian digit grouping, e.g.
  "Consolidated revenue from operations was INR 1,845.32 crore in FY2025-26 (FY2024-25: INR
  1,664.92 crore)."), `kind="number"`, category from the metric by a keyword map
  (`record_category.py`, else `other`), importance from the rating. A record without chunk ids
  goes through the same citation rescue (its templated numbers must appear in one or two window
  chunks); a row without a metric or value is skipped.
* Output: `notebook.jsonl` (append-only) and `notebook.json` (final merged list).

### 2.4 verify  (`busybee/verify/`)
For every notebook entry (concurrently):

1. **Relevance** — in batches of ~40 entries, with the condensed notebook as context: keep or
   drop for the purpose of deciding a credit line. Dropped entries go to `dropped.json` with
   the reason (auditable, never silently lost).
2. **Citation check** — load the cited chunks.
   0. *Record path* (`record_match.py`): an entry with a `record` is first checked
      deterministically against each cited chunk (table header prefix included). It passes, with
      method `record_match` and no LLM call, when the value (and `previous_value`) occurs as a
      number on a line holding at least 60% of the metric label's content tokens, the unit word
      (crore, lakh, million, billion, %, x) occurs within 120 characters of that value (or is the
      only unit word of the chunk when a table states it once), and the period (and
      `previous_period`) is a fiscal token of the chunk (FY2024-25 = FY25) or appears verbatim.
      The citation quote is the matching row. Any failure falls through to a and b below with the
      templated statement; it never rejects by itself.
   a. `number_match.py`: deterministic. Every number in the statement (normalised: commas,
      %, crore/lakh/million/billion, negative parentheses) must occur in the cited text.
   b. `entailment.py`: LLM judges supported / partially / unsupported and extracts the
      verbatim quote. Verification method is recorded (`exact_match`, `llm_entailment`).
      Verification is LLM only by default (`BUSYBEE_JUDGE=llm`; no sidecar needed). The entries
      that pass the deterministic checks are judged **per cited passage** (`passage_batch.py`,
      `BUSYBEE_VERIFY_BATCH=passage`, default; `entry` restores one call per entry): one call per
      chunk lists every entry citing it (local ids, groups capped at 25 entries / ~8k prompt
      tokens) and returns a top-level JSON list of `{"id","v","q"}`. An entry citing several chunks
      sits in each chunk's group and is supported if any chunk supports it. Missing or malformed
      ids are retried once in a smaller batch, then judged by the single-entry call. Adjacent-chunk
      evidence and re-citation stay per entry. `tools/verify_agreement.py` replays
      `data/judge/entailment.jsonl` in this mode against the provider in the environment and
      reports agreement with the logged verdicts, call count and wall-clock.
      The classifier/tiered judges remain, used only when `BUSYBEE_JUDGE=classifier|tiered` is set
      (`judge.py`, sidecar in `tools/judge_sidecar/`, HHEM on a 1,500-char window; classifier
      verdicts get `quote_span.py` quotes and method `classifier_entailment`/`tiered_entailment`).
3. **Re-cite** — if unsupported, search the vDB with the statement, run entailment on the top-k
   results; if found, replace the citation (`resupported`), else mark `unsupported` and
   exclude from the report (kept in `dropped.json`).
4. Assign `fact_id` = `F001…` in notebook order. Output `verified_facts.json`. Each fact carries
   the entry's extraction `importance` (1–5, default 3; the max when duplicates merge).

   Dedupe compares money by canonical size in crore (lakh, million, billion converted; 0.05%
   tolerance) and reads periods from FY tokens and "year ended <date>"; a consolidated and a
   standalone statement are never merged (`VerifiedFact.scope`: consolidated | standalone | null).
   When both facts carry a `record`, dedupe is field-wise (`record_compare.py`): equal metric
   tokens, canonical period (FY25 = FY2024-25 = FY2025), scope, qualifier and canonical crore
   value; no Jaccard.

5. **Conflicts** (`conflicts.py`, also run by the adversary on facts it adds) — same-category
   facts with the same metric and period but numbers differing by more than 1% become
   candidates (two facts with records compare metric tokens, period, scope and canonical crore
   values directly, and any difference above 1% is a candidate); an LLM judge (`verify_conflict`, <=10 pairs per call) confirms. The fact from the
   higher-authority document kind (the §2.3 order) is kept with `conflicts: [ConflictNote]`; the
   other gets `verification.status = conflicted`, is kept in `verified_facts.json` but left out of
   the report, scores and inferences. Each conflict is a `Concern` (`CF001…`) in `conflicts.json`,
   which compose appends to the adversary's concerns.

### 2.5 policy & scores  (`busybee/policy/`)
The bank filesystem `banks/<bank_id>/` holds:

* `policy.md` — natural-language policy (eligibility, ratios, limits, red flags).
* `scores.yaml` — machine-readable `ScoreSpec` list: inputs (named slots with unit and integer
  scale), the Lean function name, and grade thresholds in words.
* `policy.lean` — formalisation (may be absent).
* `scores.yaml` may also hold `invariants:` (`{name, expression, message}`, e.g.
  `net_debt <= total_debt`), checked by `invariants.py` after binding and before Lean with a
  tiny safe parser. A violation gives the binder one retry on the involved slots; if it still
  fails, the message and fact ids are stored in `ScoreResult.warnings` and shown as a warning
  badge and popover list in the report. Scores still compute; Lean output is unchanged.
* `scores.yaml` also holds `rules:` — the bank's hard policy rules, `{rule_id, name, expression,
  outcome: decline|refer|caution|pass_required, policy_section, message, caution_expression?}`.
  `expression` must hold and is over slot names and score ids: integer, cross-multiplied
  comparisons (`100 * cfads >= 125 * debt_service`) joined by `and` / `or`, parsed by the
  `invariants.py` parser (`rules.py`); `caution_expression` is true inside the caution zone of
  a rule that holds. A rule that does not hold forces its `outcome` (`decline`, `refer`);
  `caution` rules only condition an approval and `pass_required` rules cap a plain approve
  (exposure above the cap). `policy_section` is the section number in `policy.md`
  (resolved to its `P<n>` id). Unknown slots or bad expressions raise `RuleError` at load.
* `approval.json` — `{approved, by, date, notes, generated_by}`.

Stage `scores`:
1. If `policy.lean` is missing → `formalize/` loop: a writer LLM drafts `policy.lean` from
   `policy.md` + `scores.yaml` following the Lean conventions (§4); it is compiled; a checker
   LLM with fresh context compares it against the policy text and lists discrepancies; repeat
   until it compiles and the checker is satisfied (max N rounds). Save with
   `approval.json.approved = false, generated_by = <model>`.
1b. Bank inputs: `busybee run --proposed-exposure <crore> [--projected-turnover <crore>]` (env
   `BUSYBEE_PROPOSED_EXPOSURE` / `BUSYBEE_PROJECTED_TURNOVER`, stored in `RunConfig` and
   `run.json`). `bank_inputs.py` writes each into `verified_facts.json` as a synthetic fact (next
   F id, category other, `added_by = bank_input`, statement "Bank input: proposed exposure INR X
   crore (from the credit request)", citation to document `REQ` "Credit request" with
   `source = bank_input`). Re-running replaces them in place; render shows a "bank input" chip.
2. `bind_inputs.py`: LLM maps every input slot of every score to a verified fact (fact_id,
   value, unit → scaled Int). Unbound slots make the score `not_computable` (reported as such).
   Slot kinds, all declared in `scores.yaml` (`InputSlot`):
   * plain: the model picks a fact among per-slot candidates; bank-input facts are ordinary candidates.
     Candidate pre-selection scores a record fact on its `record.metric` words against the slot
     (not the whole templated sentence), and the deterministic derivation reads record values
     (metric, `value`, `period` year) before parsing any statement.
   * derived: `definition` (shown in the prompt) and `derive_from` hints (their candidate facts
     are added); the model answers with signed `terms` (a worked example is in the prompt) and
     code sums the exactly scaled terms (cfads, debt_service, net_debt, tangible_net_worth). An
     optional `note` records proxies, shown in the Lean binding popover.
   * categorical: `mapping` (rating grade → index, copied from the policy). `bind_rating.py`
     finds the latest long-term grade in fact statements by regex (short-term grades and prose
     never match) and cites that fact; only if none states a grade is the model asked.
   * judged: `judge` (rubric policy headings, keywords, flag or count), for `default_flag` and
     `major_red_flag_count`. One `policy.judge_slot` call per slot with the rubric and keyword
     candidates; the answer must cite shown facts; the justification goes to `BoundInput.note`.
     No candidate facts means unbound (absence from the pack is not evidence).
   * fallback: `fallback_slot` + `fallback_note` (projected turnover uses the latest revenue,
     "projection not provided; latest revenue used"); `run_parameter` adds the CLI hint to the
     unbound reason.
   `BoundInput.note` is appended to the Lean provenance comment (`-- F012 D1:p2:c0 | note: …`).
2b. `slot_search.py` (after binding and the deterministic derivation fallback): every plain,
   non-run-parameter slot still unbound, and each unresolved `derive_from` component of an
   unbound derived slot, is fetched on demand. 1-3 queries (component phrase, description,
   definition, plus the fiscal year of the latest money facts) go to vector search (k=8,
   `financial_statements` and `annual_report` first); for at most 4 hits per component one
   `policy.slot_extract` call reads the chunk (with its table prefix) and returns
   `{found: false}` or `{statement, value, unit, period, quote}`, accepted only with a quote that
   is verbatim in the chunk; the first accepted hit ends the component. Results become
   `NotebookEntry(added_by="slot_search")` and pass `verify_entries(check_relevance=False)`
   (number match, entailment, citations); survivors not duplicating an existing fact are appended
   to `verified_facts.json` with the next F ids. At most 24 extract calls per run
   (`BUSYBEE_SLOT_SEARCH_BUDGET`, 0 disables); queries, hits tried with outcomes, verification
   results and call counts are written to `slot_search.json` and summarised in the LLM audit
   log. The affected slots are then bound again (retry path plus deterministic derivation, other
   slots untouched). The new facts are cited by bindings, so compose places them in the report.
3. `generate.py` writes `lean/Runs/<run_id>/Scores.lean`: one `def` per slot with a comment
   `-- F012 D1:p214:c2`, one theorem per score grade/threshold, proofs by `decide`/`omega`.
4. `busybee.lean.compile` runs it. The generated file also contains `#eval` lines for each
   score's value and grade; their output on stdout is parsed into `value_display` / `grade`,
   so Lean is the only place a score is ever computed. Output `scores.json` with
   `ScoreResult`s including the Lean source, compile output and hash.
5. Policy rules, in the same `Scores.lean` (`-- SECTION: Policy rules`): for each rule whose slots
   are all bound (a bound fact, or a computable score's `_value`) generate `rule_<id>_holds`
   (`decide` of the Lean proposition), an optional `rule_<id>_in_zone`, `rule_<id>_status`
   (`pass` / `caution` / `fail`) and `#eval IO.println s!"rule_<id>=…"`. Pass two adds `decide`
   theorems: `rule_<id>_status_is`, then `rule_<id>_met` (and `_in_caution_zone`) or
   `rule_<id>_violated` (the negation). A rule with an unbound input is `not_evaluable` and lists
   the unbound slots with reasons. `policy_eval.json` is a `PolicyEvaluation{rules:
   [RuleResult{rule_id, name, status: pass|caution|fail|not_evaluable, outcome, message,
   expression, inputs: [BoundInput], score_ids, unbound, policy_section, policy_section_id,
   lean}]}`; compose copies it into `Report.rule_results`. Demo bank rules: net debt/EBITDA
   <= 4.5 (caution zone above 3.5), interest cover >= 2.5 (caution below 4.0), DSCR >= 1.25 (caution
   below 1.50), current ratio >= 1.10 (caution below 1.33), debt/equity <= 3.0 (caution above 2.0),
   revenue trend >= -10% (caution below 0), all `refer` when missed; TNW positive, rating index
   <= 10 (BBB-), default flag 0, IRG <= 7: `decline`; fewer than two major red flags, IRG <= 5:
   `refer`; no major red flag, IRG <= 3: `caution`; proposed exposure <= maximum exposure:
   `pass_required`.

If the policy is not approved, the report shows a notice at the top linking to the
explanation page (§2.7).

### 2.6 infer  (`busybee/infer/`)
Input: compact list of verified facts (+ scores). LLM produces at most ~8 `Inference`s:
`opinion` (one sentence), `fact_ids`, `reasoning` (2–4 sentences), `confidence`, and a flag
`quantitative`. Code checks every fact_id exists. For quantitative inferences `quantify.py`
emits a Lean file (facts as defs, claim as theorem) and compiles it; failure keeps the
inference but marks it `lean: failed` (rendered as unchecked). A fresh-context LLM check
confirms the reasoning only relies on the listed facts. Output `inferences.json`.

Quantification rules (`quantify.py`): a fact reference is `F012` (first number) or
`F012#1.25` (the number with that value). All numbers of one claim share ONE integer scale,
10^(most decimals among them, capped at 4), stated once as `-- scale: x100` and in the doc
comments; money is normalised to crore, percent and basis points to percent. A claim is
rejected with a clear message when its variables mix incompatible units (crore with percent,
a ratio with a percentage), when two variables resolve to the same number of a fact (the
model forgot the `#` selector), or when it chains comparisons (`a < b < c`).

### 2.7 lean  (`busybee/lean/`, `lean/`)
* `toolchain.py` locates `lean`/`lake` (elan), `project.py` manages the Lake project,
  `compile.py` compiles a single file with `lake env lean <file>` (no per-run `lake build`),
  returning `CompileResult{ok, stdout, stderr, duration_s, toolchain}`; `hash.py` sha256 of
  source; `errors.py` parses Lean error messages into `(line, col, message)`.
* `explain/` is **manual code, not AI**: parses a Lean file into sections (`-- SECTION: title`
  markers and `/-- doc comments -/`), each `def`/`theorem` with name, signature, body, and a
  best-effort English rendering (operator table: `≤` → "at most", `*` → "times", …; doc
  comment wins when present). Output `LeanExplanation` for the explanation page.

### 2.8 adversary  (`busybee/adversary/`)
Fresh context. Input: a markdown draft of sections 2–3 (facts, scores, inferences). The LLM
lists what a credit officer would still want to know and what looks weak. For each question
(concurrently): vDB search → entailment on top chunks → if answered, a new notebook entry
that runs through `verify` and is appended to the facts (tagged `added_by: adversary`); if
not, a `Concern{opinion, fact_ids, reasoning, query_used, found=false}`. Output
`concerns.json` and `verified_facts.json` (updated).

### 2.9 compose  (`busybee/compose/`)
Recommendation JSON: decision (approve | approve_with_conditions | decline | refer), an
actionable headline with the amount when the sizing rule allows one, conditions, and key
reasons in three groups rendered in this order: **hard rules from bank policy** (the
company's number, the policy clause it trips, citing the policy section `P<n>` and the
facts/scores), **hard facts** (verdict with numbers, citing facts), **inferences** (citing
inference ids). Every id is code-checked; `policy.md` is split into sections `P1…` that are
citable like chunks and rendered with anchors on `policy.html`.
Hard policy thresholds never rest on the model's narrative. `policy_floor.py` turns the Lean
rule results (`policy_eval.json`) into a **decision floor**: a failing `decline` rule forces
decline, a failing `refer` rule or a rule inside its caution zone (policy §4: "refer to credit
committee") at least refer, a failing `caution`-outcome rule (one red flag, IRG 4 to 5) or a
failing `pass_required` rule (exposure above the cap; §11: "exposure reduced to the maximum
exposure") at least approve with conditions (order approve < approve with conditions
< refer < decline). The compose prompt carries a "Policy rule results" table and the floor, and
a `policy_rule` reason cites its rules in `KeyReason.rule_ids` (unknown ids are dropped by
`check_ids.py`). After the verdict checks, code enforces the floor: a more lenient decision is
replaced, the headline comes from the template "<Decision>: <rule message>", a proposed limit is
dropped for refer / decline, the confidence note records the override, and the outcome is
written to `decision_override.json` and `AuditBlock.decision_override` (`DecisionOverride{
overridden, model_decision, final_decision, floor, rule_ids, model_headline, headline}`). Every
failing or caution rule that no reason cites gets a deterministic `policy_rule` reason built
from the rule message, its inputs' fact ids, score ids and policy section. Rules that were not
evaluable are named in the confidence note and add no floor.
Assembles `report.json` (`Report` model) with `rule_results`, the audit block (models, stage
timings, call counts, policy version, Lean toolchain, decision override).

### 2.10 render  (`busybee/render/`)
Static bundle `out/`: `index.html` (the report), `sources/<doc_id>.html` (page by page,
chunk anchors, highlight, link to the original PDF `#page=N`), `lean/<artifact>.html`
(source, compile output, explanation), `policy.html` (approval notice + explanation),
`assets/` (copied from `design/`), `data/report.json`.

The report is shown on a dark reader background as separate A4 sheets (paginated in the
browser by `design/components.js`), with an Export PDF button (browser print; also
`busybee export-pdf` via headless Chromium). Sections, in order:
0. notice bar if policy Lean is unapproved (header's bank-policy link always opens `policy.html`);
1. **Recommendation** — headline + hard rules from policy / hard facts / inferences;
2. **Policy scores** — name, value, grade, Lean chip; below them the **Policy rule results**
   table (rule name and message, bound inputs with fact links, Pass / Caution / Fail / Not
   evaluable badge, Lean chip whose popover shows the rule's inputs and compile output);
3. **Relevant important facts** — dot bullets grouped by category, fact id and citation chip
   at the end of the sentence. Per category at most `BUSYBEE_REPORT_MAX_PER_CATEGORY` facts
   (default 10; `RunConfig.report_max_facts_per_category`; 0 = no cap), chosen from facts with
   extraction `importance` ≥ `BUSYBEE_REPORT_MIN_IMPORTANCE` (default 4) and ranked by:
   referenced by the recommendation, a score binding, an inference or a concern; then
   cited from a rating-agency rationale (these qualify at importance ≥ threshold − 1); then
   importance desc; then consolidated before unscoped before standalone
   (`VerifiedFact.scope`, derived from the statement's words); then number of citations desc.
   Every referenced fact is shown even if that exceeds the cap; everything else goes to
   section 6;
4. **Inferences** — `opinion` · (facts) · reasoning;
5. **Open concerns** (temporary section) — same shape as 4, from the adversary stage;
6. **Appendix: other verified facts** — the facts left out of section 3, same bullet style
   grouped by category (omitted when empty), so every verified fact stays auditable.

Popup behaviour (shared JS from `design/`): every statement with citations has a chip;
click → scrollable popover with one box per cited chunk (doc title, page, quote); click a box
→ source page with the chunk highlighted; a persistent **back** button returns to the exact
statement (history stack, like Ctrl-O in vim). Score / Lean statements → popover shows the
fact-to-Lean binding and the compile output, with a link to the Lean page.

### 2.11 orchestrate + cli
`dag.py` declares stages and dependencies; `run.py` executes with asyncio, honouring the
dependency graph and `stages.json` for resume. `cli.py` (typer):
`busybee run --docs DIR --bank ID --out DIR [--run-id …] [--resume]`,
`busybee eval --workspace-dir DIR [--company NAME]`, `busybee rescue --workspace DIR --bank ID`,
`busybee formalize --bank ID`, `busybee export-pdf --bundle DIR --out FILE`.

### 2.12 eval  (`busybee/eval/`)
Internal metrics (what we actually optimise):
* **Important-statement recall** — gold facts found in the report (LLM-judged match).
* **Important-statement precision** — report facts judged important and correct.
* **Citation precision** — cited chunk supports the statement (LLM-judged; sample for human).
* **Planted-error catch rate** — perturbed entries injected into the notebook; share dropped
  by `verify`.
* **Proof pass rate**, **page-exact rate** (deterministic), **run time and call count**.
Official proposal metrics are reported where computable. Gold sets live in `data/gold/`.

---

## 3. Data contract (`busybee/schema/`)

All models are pydantic v2, one file per group, serialised as JSON in the workspace.

**documents.py** — `DocumentKind` (annual_report, drhp, financial_statements,
rating_rationale, covenant, bank_statement, news, other); `Document{doc_id, title, kind,
source_path, sha256, num_pages, metadata}`; `Page{doc_id, page_no, text}`; `Chunk{chunk_id,
doc_id, page_no, index_in_page, text, char_start, char_end}`; `ScoredChunk{chunk, score}`.

**facts.py** — `FactCategory` (revenue, profitability, debt_leverage, liquidity, cash_flow,
credit_history, ratings, stock, ownership_governance, litigation_regulatory,
industry_market, news, other); `Citation{chunk_id, doc_id, page_no, quote}`;
`NumericValue{label, value: Decimal, unit, period}`; `NotebookEntry{entry_id, statement,
citations, category, kind, importance, window_no, doc_id, supersedes, added_by}`;
`Verification{status: supported|resupported|unsupported, method, notes}`;
`VerifiedFact{fact_id, statement, category, citations, numbers, verification,
source_entry_id, added_by}`; `DroppedEntry{entry, reason, stage}`.

**policy.py** — `InputSlot{slot, description, unit, scale}`; `GradeRule{label,
condition_text}`; `ScoreSpec{score_id, name, description, inputs, lean_function, grades}`;
`Approval{approved, by, date, notes, generated_by}`; `BankPolicy{bank_id, name, version,
policy_md, scores, lean_path, approval}`; `BoundInput{slot, fact_id, value, unit,
value_scaled}`; `ScoreResult{score_id, status: computed|not_computable|lean_failed, inputs,
value_display, grade, lean}`.

**lean.py** — `CompileResult{ok, stdout, stderr, duration_s, toolchain, errors:
list[LeanError{line, col, message}]}`; `LeanArtifact{artifact_id, kind: policy|scores|inference,
file_path, source, sha256, theorems, compile}`; `LeanExplanation{sections:
list[ExplainSection{title, items: list[ExplainItem{name, kind, lean, english, doc}]}]}`.

**report.py** — `PolicyCitation{section_id, heading, quote}`; `KeyReason{kind:
policy_rule|hard_fact|inference, text, fact_ids, score_ids, inference_ids, rule_ids,
policy_citations}`;
`Recommendation{decision, headline, proposed_limit, conditions, key_reasons,
confidence_note}`; `FactGroup{category, fact_ids}`; `Inference{inference_id, opinion,
fact_ids, reasoning, confidence, quantitative, lean}`; `Concern{concern_id, opinion,
fact_ids, reasoning, query_used, found}`; `AuditBlock{models, stage_timings, llm_calls,
policy_version, lean_toolchain, generated_at}`; `Report{run_id, company, bank_id,
policy_approved, recommendation, facts: dict[fact_id, VerifiedFact], fact_groups, scores,
rule_results,
inferences, concerns, documents, audit}`.

**run.py** — `RunConfig{run_id, docs_dir, bank_id, out_dir, workspace_dir, window_tokens,
notebook_budget_tokens, concurrency, extract_mode, models: dict[stage, model_name]}`;
`StageStatus{name, state: pending|running|done|failed, started_at, finished_at, error}`.

---

## 4. Lean conventions (every agent writing Lean follows these)

* **Lean 4 core only, no Mathlib** (keeps the toolchain small and builds reliable). Toolchain
  pinned in `lean/lean-toolchain`.
* All quantities are `Int` in a declared integer scale (e.g. INR crore × 100 for two
  decimals, percentages in basis points). The scale is in `scores.yaml` and in a comment.
* Ratios never appear as division. A threshold `net_debt / ebitda ≤ 3.5` is written as
  `2 * net_debt ≤ 7 * ebitda` under the hypothesis `0 < ebitda`.
* Proof tactics allowed: `decide`, `omega`, `simp`, `rfl`. `native_decide` only as a last
  resort and flagged in the artifact.
* Every fact `def` carries its provenance comment on the same line: `-- F012 D1:p214:c2`.
* Policy files are organised with `-- SECTION: <title>` markers and `/-- doc comments -/`
  on every `def`/`theorem`, because the manual explainer renders those for humans.

---

## 5. LLM access (`busybee/llm/`)

`Provider` protocol: `async complete(messages, *, json_schema=None, temperature=0.0,
max_tokens=…, task="") -> Completion{text, usage, model, latency_s}`.
Implementations: `openai_compatible.py` (works for NVIDIA NIM, vLLM, LM Studio, OpenAI),
`anthropic.py`, `mock.py` (fixtures keyed by `task`, or a callable), `recording.py`
(wraps a real provider and saves fixtures). `structured.py` turns a pydantic model into a
JSON schema, validates the reply, and re-prompts with the validation error (max 2 retries).
`limiter.py` is the global semaphore. `audit_log.py` appends every call to
`workspace/<run>/llm_log.jsonl`. `registry.py` builds providers from env:

```
BUSYBEE_LLM_PROVIDER=openai_compatible|anthropic|mock
BUSYBEE_LLM_BASE_URL, BUSYBEE_LLM_API_KEY, BUSYBEE_LLM_MODEL
BUSYBEE_LLM_MODEL_<STAGE>  (optional per-stage override, e.g. a cheap model for verify)
BUSYBEE_EMBED_PROVIDER=hashing|local|openai_compatible (default hashing), BUSYBEE_EMBED_MODEL
```
Until the hackathon LLM endpoint arrives, everything runs end to end on `mock` with the
synthetic corpus; tests must never need network.

---

## 6. Test strategy

* Unit tests per component with the mock provider.
* `tests/e2e/test_synthetic_run.py`: full pipeline on `data/synthetic/acme_textiles/` with
  recorded mock responses, asserting the bundle renders and every citation resolves.
* Deterministic checks are tested exhaustively (number matching, chunk offsets, Lean
  explainer parsing, id resolution).
