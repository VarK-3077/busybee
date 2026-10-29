# BusyBee design language: renderer contract

`design/` holds the whole visual layer of the report. `busybee/render/` copies these four
files into `out/assets/` and emits HTML in exactly the shapes below. There is no build step
and nothing is fetched at runtime, so every page works from `file://` and prints as A4.
The desk is dark (`#282828`, like a PDF reader). The report is shown as separate white A4
sheets, paginated in the browser by `components.js` (section 2, "Pagination").

| File | Purpose |
|---|---|
| `tokens.css` | CSS custom properties: colours, status and grade colours, type, spacing, radii, shadows, print overrides |
| `document.css` | The paper-memo look: dark desk, A4 sheets, header, numbered sections, bulleted fact lists, score lines, tables, `@page` |
| `components.css` | Chips, popover, back button, notice bar, badges, score cards, Lean blocks, inference and concern blocks, explanation list, source pages |
| `components.js` | Report paginator, Export PDF toolbar, popovers, navigation, back stack. Exposes `window.BusyBee` |
| `styleguide.html` | Every component with fake data, plus a working round trip into `example-source.html` |

Open `styleguide.html` in a browser to see everything. To try the round trip, click the chip
on F004, pick page 48, follow "Note 34", then press back twice.

## 1. Page skeleton

Every page (report, source, Lean, policy) has the same head and body:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>…</title>
  <link rel="stylesheet" href="assets/tokens.css">
  <link rel="stylesheet" href="assets/document.css">
  <link rel="stylesheet" href="assets/components.css">
  <script src="assets/components.js" defer></script>
</head>
<body class="bb-desk">
  <!-- optional .bb-notice -->
  <main class="bb-page">…</main>
  <!-- JSON blobs (section 6) -->
</body>
</html>
```

Pages under `sources/` and `lean/` use `../assets/…`. Don't emit the back button or the
popover yourself. `components.js` creates `#bb-back` and `#bb-popover` on load.

## 2. Report (`index.html`)

### Header and footer

```html
<header class="bb-doc-header">
  <p class="bb-doc-kicker"><span>Credit review · Confidential</span><span>{bank name}</span></p>
  <h1 class="bb-doc-title">{company}</h1>
  <p class="bb-doc-subtitle">{facility / purpose}</p>
  <dl class="bb-meta">
    <div><dt>Borrower</dt><dd>…</dd></div>
    <div><dt>Bank policy</dt><dd><a href="policy.html">{policy_version}</a></dd></div>
    <div><dt>Generated</dt><dd>{audit.generated_at}</dd></div>
  </dl>
</header>
<div class="bb-report"> … sections … </div>
<footer class="bb-doc-footer"><span>…audit summary…</span><span>…</span></footer>
```

The Bank policy value always links to `policy.html`, whether or not the policy is approved.
There is no Run field; the run id appears only in the audit footer.

The report's page is `<main class="bb-page bb-flow" data-paginate>` and holds the header,
`.bb-report` and the footer as one long flow. Emit it exactly like that; the sheets are made
in the browser.

### Pagination

On load, `components.js` finds `[data-paginate]` and:

1. sets `data-num` on every `.bb-section > .bb-h2` ("1") and `.bb-group > .bb-h3` ("3.1");
   sheets display it instead of the CSS counters, which cannot continue across split containers;
2. moves a top-level `.bb-notice` into the flow, so it prints on sheet 1;
3. flattens the flow into atoms: header, notice, footer, and every leaf inside a splittable
   container (`.bb-section`, `.bb-group`, `.bb-recommendation`, `.bb-rec-group`, `ul`, `ol`),
   for example a list item, score row, block, paragraph or heading;
4. moves atoms in order into `section.bb-page.bb-sheet > .bb-sheet-body` (210 x 297 mm, content
   box 257 mm high), opening a new sheet when an atom's bottom would pass the content box.
   Headings (`h2`, `h3`, `.bb-rec-heading`, a `.bb-caps` label in the recommendation) move with
   the atom that follows them;
5. shallow-clones the splittable containers onto each sheet. The first clone keeps the `id`,
   later ones lose it, so every `id` stays unique. The first item on a sheet gets `.bb-sheet-top`
   (no top margin);
6. adds a "n / N" number to each sheet, removes the flow and re-scrolls to the URL hash.

Statement ids, chips and the back stack work as before because atoms are moved, never copied.
Without JS the flow stays one long sheet. Sheet geometry does not depend on the viewport
width or the media type, so the layout measured on screen is what prints.

### Toolbar

`components.js` adds `#bb-toolbar.bb-toolbar` to every page: fixed, top right, outside the
sheets, with an "Export PDF" button that calls `window.print()`. Don't emit it yourself.
`busybee export-pdf --bundle DIR --out FILE` does the same with headless Chromium
(`--print-to-pdf`, no header or footer) and exits with an error if no Chromium is installed.

### Sections

Section and group numbers are set by the paginator (CSS counters without JS). Don't write
numbers into headings. They hang in the left margin. Statement ids do not.

```html
<section class="bb-section" id="recommendation"><h2 class="bb-h2">Recommendation</h2>…</section>   <!-- 1 -->
<section class="bb-section" id="scores">
  <h2 class="bb-h2">Policy scores</h2>                                                          <!-- 2 -->
  <ul class="bb-scores"> …score lines… </ul>
</section>
<!-- section 3 lists at most BUSYBEE_REPORT_MAX_PER_CATEGORY (default 6) facts per category:
     referenced facts first (always shown), then importance, consolidated before standalone,
     citation count; all other facts render in the appendix with the same markup. -->
<section class="bb-section" id="facts">
  <h2 class="bb-h2">Relevant important facts</h2>                                               <!-- 3 -->
  <div class="bb-group" id="group-{category}">
    <h3 class="bb-h3">{Category label}</h3>
    <ul class="bb-facts"> …facts… </ul>
  </div>
</section>
<section class="bb-section" id="inferences"><h2 class="bb-h2">Inferences</h2>…</section>       <!-- 4 -->
<section class="bb-section" id="concerns"><h2 class="bb-h2">Open concerns</h2>…</section>      <!-- 5 -->
<section class="bb-section" id="appendix">
  <h2 class="bb-h2">Appendix: other verified facts</h2>                                         <!-- 6 -->
  <div class="bb-group" id="appendix-group-{category}"> …same group markup as section 3… </div>
</section>
```

### Statements: the unit the back button returns to

Every citable unit is an element with class `bb-stmt`, a **stable `id`** and a short
`data-ref`. The back button reads "Back to {data-ref}". Chips go inside it.

| Model | Element | id | data-ref |
|---|---|---|---|
| `VerifiedFact` | `li.bb-fact.bb-stmt` | `fact-F012` | `F012` |
| `ScoreResult` | `li.bb-score.bb-stmt` | `score-{score_id}` | `{score_id}` |
| `Inference` | `article.bb-block.bb-inference.bb-stmt` | `inf-{inference_id}` | `{inference_id}` |
| `Concern` | `article.bb-block.bb-concern.bb-stmt` | `concern-{concern_id}` | `{concern_id}` |
| `KeyReason` | `li.bb-stmt` | `rec-r{n}` | `Reason {n}` |

These ids are also what `bb-ref` links and `fact_href` point at. Keep them as listed.

### Citation chip

```html
<button class="bb-cite" type="button"
        data-cites="D1:p12:c3,D1:p47:c1"
        data-status="supported" data-method="exact_match">D1<span class="bb-cite-sep">·</span>p.12<span class="bb-cite-more">+1</span></button>
```

* `data-cites`: comma-separated chunk ids, in citation order. Each one must be a key of
  `#bb-chunks`.
* `data-status`: `Verification.status`, either `supported` or `resupported`. Re-cited chips
  get a dashed outline. `data-method` is `Verification.method`. The popover header shows
  both.
* Label: the first citation's `{doc_id}·p.{page_no}`. Add `<span class="bb-cite-more">+N</span>`
  when there are N more citations.
* The chip goes directly after the statement text, with no space before it.

### Lean chip (scores and quantitative inferences)

```html
<button class="bb-cite bb-cite--lean" type="button" data-lean="S1" data-status="proved">Lean</button>
```

`data-lean` is a key of `#bb-lean` (a `score_id`, an `inference_id`, or `rule:<rule_id>` for a
policy rule). `data-status` is one
of `proved`, `failed` or `unchecked`, mapped like this:

* `ScoreResult.status = computed` with a successful compile → `proved`
* `lean_failed` → `failed`
* `not_computable` → `unchecked`
* An inference with `quantitative = false` gets no Lean chip.
* A policy rule: its Lean file compiled and the rule was evaluated → `proved` (whatever the
  rule's own result, a failing rule is proved violated); compile error → `failed`;
  `not_evaluable` (no artifact) → `unchecked`.

### Fact

```html
<li class="bb-fact bb-stmt" id="fact-F012" data-ref="F012">{statement} <a class="bb-sid" href="#fact-F012">F012</a><button class="bb-cite" …>…</button></li>
```

Facts are plain bullets (a dot marker) in normal text. The id closes the sentence in small
muted monospace (`.bb-sid`), then the quiet chip (light border, small). Nothing hangs in the
margin. Inferences and concerns end their `.bb-opinion` text the same way, with
`<a class="bb-sid" href="#inf-I1">I1</a>` / `href="#concern-C1"` before any Lean chip.

### Score line

```html
<li class="bb-score bb-stmt" id="score-S1" data-ref="S1">   <!-- no id in the margin or the row; the name is the label -->
  <span class="bb-score-name">{name}</span>
  <span class="bb-score-leader" aria-hidden="true"></span>
  <span class="bb-score-value">{value_display}</span>        <!-- add bb-score-value--none when not computable -->
  <span class="bb-badge bb-grade" data-tone="good">{grade}</span>
  <button class="bb-cite bb-cite--lean" type="button" data-lean="S1" data-status="proved">Lean</button>
</li>
```

Grade tone: grades in `ScoreSpec.grades` run from best to worst. Map them in order to
`good`, `fair`, `weak`, `poor`; for two grades use `good` and `poor`, for three use `good`,
`weak` and `poor`. Use `none` when the score has no grade.

### Recommendation

```html
<div class="bb-recommendation">
  <div class="bb-decision-line">
    <span class="bb-badge bb-decision" data-decision="approve_with_conditions">Approve with conditions</span>
    <span class="bb-small bb-muted">Proposed limit <strong class="bb-score-value">₹60.0 crore</strong></span>
  </div>
  <p class="bb-headline">{headline}</p>
  <ul class="bb-reasons">
    <li class="bb-stmt" id="rec-r1" data-ref="Reason 1">{text} <a class="bb-ref bb-jump" href="#fact-F003">F003</a> <a class="bb-ref bb-jump" href="#score-S1">S1</a> …chips…</li>
  </ul>
  <span class="bb-caps">Conditions</span>
  <ol class="bb-conditions"><li>…</li></ol>
  <p class="bb-small bb-muted">{confidence_note}</p>
</div>
```

`data-decision` takes `approve`, `approve_with_conditions`, `decline` or `refer`.

### Inference and concern

```html
<article class="bb-block bb-inference bb-stmt" id="inf-I1" data-ref="I1">
  <p class="bb-opinion">{opinion} <a class="bb-sid" href="#inf-I1">I1</a><button class="bb-cite bb-cite--lean" …>Lean</button></p>
  <p class="bb-block-facts"><span class="bb-caps">Facts</span><a class="bb-ref bb-jump" href="#fact-F003">F003</a><a class="bb-ref bb-jump" href="#fact-F004">F004</a></p>
  <p class="bb-reasoning">{reasoning}</p>
  <div class="bb-block-meta">
    <span class="bb-badge bb-confidence" data-level="high">High confidence</span>
    <span class="bb-badge" data-status="proved">Proved in Lean</span>   <!-- failed: "Lean failed"; non-quantitative: unchecked "Judgement" -->
  </div>
</article>

<article class="bb-block bb-concern bb-stmt" id="concern-C1" data-ref="C1">
  <p class="bb-opinion">{opinion} <a class="bb-sid" href="#concern-C1">C1</a></p>
  <p class="bb-block-facts"><span class="bb-caps">Facts</span>…bb-ref links…</p>
  <p class="bb-reasoning">{reasoning}</p>
  <p class="bb-query"><span class="bb-caps">Searched</span><q>{query_used}</q></p>
  <div class="bb-block-meta"><span class="bb-badge" data-status="unsupported">Not found in documents</span></div>
</article>
```

`data-level` is `high`, `medium` or `low`.

### Notice bar (policy not approved)

Emit this before the first `.bb-page`, only when `Report.policy_approved` is false:

```html
<div class="bb-notice" role="note"><span><strong>Policy formalisation not yet approved.</strong>
  The Lean encoding of {policy} was generated by <span class="bb-mono">{generated_by}</span> on {date}
  and has not been reviewed by a person. <a href="policy.html">Read the policy explanation →</a></span></div>
```

### Other building blocks

* Key-value rows: `<dl class="bb-kv"><div><dt>…</dt><dd>…</dd></div></dl>`
* Tables: `<div class="bb-table-wrap"><table class="bb-table"><caption>…</caption>…</table></div>`,
  with `class="bb-num"` on numeric cells.
* Score cards (a grid alternative to score lines): `div.bb-scorecards > article.bb-scorecard.bb-stmt`
  containing `.bb-scorecard-name`, `.bb-scorecard-value`, `.bb-scorecard-row` (badges and
  chip) and `.bb-scorecard-rule`.
* Text helpers: `.bb-lede`, `.bb-small`, `.bb-muted`, `.bb-caps`, `.bb-mono`,
  `.bb-visually-hidden`.

## 3. Badges

```html
<span class="bb-badge" data-status="supported|resupported|unsupported|proved|unchecked|failed|conflict">Label</span>
<span class="bb-badge bb-grade" data-tone="good|fair|weak|poor|none">{grade}</span>
<span class="bb-badge bb-confidence" data-level="high|medium|low">High confidence</span>
<span class="bb-badge bb-decision" data-decision="approve|approve_with_conditions|decline|refer">…</span>
```

The CSS adds a glyph to each status badge (✓ ↻ ✕ ⊢ ○ ✕ ⇄), so status still reads in greyscale.
Don't put glyphs in the label text.

### Conflict badge

A fact that won a cross-document conflict (`VerifiedFact.conflicts` non-empty) carries a small
badge right after its id and citation chip. The popover is pure CSS (hover or keyboard focus,
hidden in print) and lists every `ConflictNote` as `fact_id` plus note:

```html
<span class="bb-badge bb-conflict" data-status="conflict" tabindex="0">conflict
  <span class="bb-conflict-pop" role="tooltip"><ul>
    <li><span class="bb-mono">F087</span> {note}</li>
  </ul></span></span>
```

Colours come from `--bb-conflict` and `--bb-conflict-tint` in `tokens.css` (amber, like
`--bb-grade-weak`). The losing fact (`verification.status = conflicted`) is never
rendered in section 3 and is not counted as referenced or bound to a score. It is rendered only in
the appendix under its category as a normal `li.bb-fact.bb-stmt#fact-<id>[data-ref]` (so
`#fact-F087` resolves) with its citation chip, a `bb-badge[data-status="conflicted"]` (muted, text
struck through) and the note "overruled by F001 (source priority)", where the winner id comes from
the winner's `conflicts` or the loser's `verification.notes`. Its conflict also appears as a concern block whose id starts with `CF`
(`id="concern-CF001"`) in Open concerns, with the badge `data-status="conflict"` reading
"Sources conflict" and both fact ids in the Facts row (the excluded id has no anchor).

## 4. Source page (`sources/<doc_id>.html`)

```html
<main class="bb-page bb-source">
  <header class="bb-doc-header">
    <p class="bb-doc-kicker"><span>Source document · D1</span><span>BusyBee evidence bundle</span></p>
    <h1 class="bb-doc-title">{Document.title}</h1>
    <dl class="bb-meta">…kind, num_pages, file, sha256…</dl>
    <p class="bb-source-actions"><a href="{relative path to original}">Open original PDF ↗</a></p>
  </header>

  <section class="bb-src-page" id="D1:p12" aria-label="Page 12">
    <h2 class="bb-src-page-head"><span>Page 12</span><a href="{original}#page=12">Open in PDF ↗</a></h2>
    <section class="bb-chunk" id="D1:p12:c3">
      <a class="bb-chunk-id" href="#D1:p12:c3">c3</a>
      <p>…chunk text…</p>
    </section>
  </section>
</main>
```

* The chunk's `id` **is the chunk id**, unescaped (`D1:p12:c3`). Colons are valid in HTML ids.
  The JS looks ids up with `getElementById`, so nothing needs escaping.
* Chunks overlap by about 80 tokens. To keep the page reading as one continuous text, render
  each chunk's text from `max(char_start, previous chunk's char_end)` to `char_end`, so every
  character appears once and each chunk's section starts at its own new text. Use the full
  chunk text when a chunk has no previous chunk on its page.
* Arriving through a chip, the JS gives the chunk named in the URL fragment the
  `bb-chunk--target` class (`:target` is styled the same way). It wraps the verbatim quote in
  `<mark class="bb-quote">`, matching case-insensitively with whitespace collapsed, and inserts
  a `.bb-arrival` bar ("↩ You came from F012 — "…" Back") just before the chunk.
* To link from inside a source text to another chunk and keep the back stack, use
  `<a class="bb-jump" href="#D1:p61:c1" data-ref="D1 p.48">Note 34</a>`.

## 5. Lean page and policy page

Lean artifact (`lean/<artifact_id>.html`). Give each section the id that `href` in
`#bb-lean` points at:

```html
<section class="bb-lean" id="lean-S1">
  <div class="bb-lean-head">
    <span class="bb-lean-title">{title}</span>
    <span class="bb-lean-file">{file_path}</span>
    <span class="bb-lean-hash">sha256 {short}</span>
    <span class="bb-badge" data-status="proved|failed">…</span>
  </div>
  <pre class="bb-code bb-code--lines"><code><span class="bb-line">…line 1…</span><span class="bb-line bb-line--error">…</span></code></pre>
  <div class="bb-compile" data-ok="true|false">
    <div class="bb-compile-head">Compiled without errors · 0.42 s · {toolchain}</div>
    <pre>{stdout + stderr, or "(no messages)"}</pre>
  </div>
</section>
```

* Line numbers come from CSS. Emit one `.bb-line` per source line, with no newlines between
  the spans. Add `bb-line--error` on lines listed in `CompileResult.errors`.
* For a plain listing without numbers, drop `bb-code--lines` and the line spans.
* Optional highlighting: wrap comments in `.bb-tok-comment` and keywords in `.bb-tok-keyword`.

Explanation list (`LeanExplanation`, used on `policy.html` and Lean pages):

```html
<div class="bb-explain">
  <section class="bb-explain-section">
    <h3 class="bb-h3">{ExplainSection.title}</h3>
    <div class="bb-explain-cols bb-caps"><span>Lean</span><span>In English</span></div>
    <div class="bb-explain-item" id="explain-{name}">
      <div class="bb-explain-name">{name} <span class="bb-explain-kind">{kind}</span></div>
      <pre class="bb-explain-lean">{lean}</pre>
      <div class="bb-explain-english"><p class="bb-explain-doc">{doc}</p><p class="bb-explain-mech">{english}</p></div>
    </div>
  </section>
</div>
```

`policy.html` starts with the same `.bb-notice` (or a plain approval line when the policy is
approved, built from `Approval`), then `.bb-kv` rows for the approval record, then the
explanation list.

### Policy rule results table

Placed in section 2 (Policy scores), directly under the `.bb-scores` list. One row per
`RuleResult` (`report.rule_results`); omit the whole block when the bank defines no rules.

```html
<div class="bb-table-wrap" id="rules"><table class="bb-table bb-rules">
  <caption>Policy rule results</caption>
  <thead><tr><th scope="col">Rule</th><th scope="col">Inputs</th><th scope="col">Result</th><th scope="col">Lean</th></tr></thead>
  <tbody>
    <tr class="bb-rule bb-stmt" id="rule-dscr_min" data-ref="dscr_min" data-status="fail">
      <th scope="row">{name}<br><span class="bb-small bb-muted bb-rule-message">{message} <a class="bb-ref" href="policy.html#P5">Policy §4</a></span></th>
      <td><span class="bb-rule-input"><span class="bb-mono">{slot}</span> {value} {unit} <a class="bb-ref bb-jump" href="#fact-F007">F007</a></span><br>…</td>
      <td><span class="bb-badge bb-grade" data-tone="poor">Fail</span></td>
      <td><button class="bb-cite bb-cite--lean" type="button" data-lean="rule:dscr_min" data-status="proved">Lean</button></td>
    </tr>
  </tbody>
</table></div>
```

* Result badge: `pass` → "Pass" `data-tone="good"`, `caution` → "Caution" `weak`, `fail` →
  "Fail" `poor`, `not_evaluable` → "Not evaluable" `none`. A not-evaluable row lists the
  missing slots (and why) in the Inputs cell instead of values.
* An input read from a score (for example `internal_risk_grade`) has no fact; its link goes to
  `#score-{score_id}` and the label is "score".
* Recommendation reasons that carry `rule_ids` end with `.bb-ref.bb-jump` links to `#rule-{rule_id}`.
* The `#bb-lean` record of a rule has `kind: "rule"`, `title` = rule name, `grade` = the result
  label with its `grade_tone`, `claim` = the rule expression, `warnings` = the unbound slots,
  `theorems` = the rule's theorem names, plus `bindings`, `compile` and `href` as for scores
  (score inputs carry a `note` and no `fact_id`).

## 6. Data blobs

Put these at the end of `<body>` on any page that has chips. JS reads them once and never
fetches anything.

```html
<script type="application/json" id="bb-chunks">
{ "D1:p12:c3": { "doc_id": "D1", "doc_title": "Acme Textiles Ltd — Annual Report FY2025",
                 "page_no": 12, "quote": "{Citation.quote}", "href": "sources/D1.html#D1:p12:c3" } }
</script>

<script type="application/json" id="bb-lean">
{ "S1": {
    "kind": "score",                       // "score" | "inference" | "rule"
    "title": "Net debt to EBITDA",
    "status": "proved",                    // proved | failed | unchecked
    "value_display": "2.41×",              // scores only
    "grade": "Comfortable", "grade_tone": "good",
    "claim": "10 * net_debt ≤ 30 * ebitda",  // optional, the theorem statement
    "bindings": [                          // BoundInput + its citation
      { "slot": "net_debt", "fact_id": "F003", "value": "412.6", "unit": "₹ crore",
        "value_scaled": 41260, "chunk_id": "D1:p47:c1",
        "fact_href": "#fact-F003",          // optional, default "#fact-{fact_id}"
        "metric": "Total borrowings",       // optional, the fact's record.metric, shown beside the fact id
        "note": "proposal" }                // optional, shown when fact_id is null (default "unbound")
    ],
    "compile": { "ok": true, "duration_s": 0.42, "toolchain": "leanprover/lean4:v4.12.0",
                 "output": "{stdout + stderr}" },   // or null when not compiled
    "href": "lean/scores.html#lean-S1"      // or null: no footer link
} }
</script>
```

(The `//` notes above are documentation only. Real JSON can't contain comments.)

* `href` values are relative to the page that holds the blob, so `index.html` uses
  `sources/D1.html#…`.
* `quote` is `Citation.quote`, the verbatim span found during verification. The source page
  highlights that exact text.
* Every `chunk_id` used by a binding must also be a key of `#bb-chunks`, so the binding's
  source link resolves.
* Escape `</` as `<\/` inside the JSON. Jinja's `tojson` filter already does this.

## 7. JavaScript API

`components.js` starts itself on `DOMContentLoaded`. Everything is plain functions on
`window.BusyBee`:

| Call | What it does |
|---|---|
| `BusyBee.popover.open(chipEl)` | Opens the popover for a `.bb-cite` (sources, or Lean if `data-lean`) and focuses the first box |
| `BusyBee.popover.close(returnFocus)` | Closes it and returns focus to the chip if `returnFocus` is true |
| `BusyBee.popover.toggle(chipEl)` / `.isOpen()` | Toggle, or check whether it is open |
| `BusyBee.nav.go(href, fromId, {quote})` | Pushes the current place onto the back stack and opens `href`. `fromId` is the statement's id |
| `BusyBee.nav.back()` | Pops the stack, returns to that page, restores scroll and flashes the statement. Returns false if the stack is empty |
| `BusyBee.nav.stack()` / `.clear()` | Read a copy of the stack, or empty it |
| `BusyBee.data.chunk(id)` / `.lean(id)` | Read records from the blobs |
| `BusyBee.init()` | Idempotent. Only needed if the script is injected after load |

Declarative hooks, handled by one delegated click listener:

* `.bb-cite` toggles the popover.
* `[data-bb-go]` and `a.bb-jump` links go through `nav.go`, so they join the back stack.
  Add `data-chunk="{chunk_id}"` and the destination also highlights that chunk's quote.
  Ctrl-, Cmd-, Shift- and middle-clicks keep the browser's default (new tab), because no
  return is needed there.
* `#bb-back` (created by the JS) calls `nav.back()`.

How the popover closes and handles focus:

* **Esc** closes it and returns focus to the chip.
* A click outside, or focus moving outside, closes it.
* Scrolling the chip out of the viewport closes it. Scrolling inside the popover doesn't.
* Up and Down arrows move between boxes.
* The chip carries `aria-haspopup="dialog"`, `aria-expanded` and `aria-controls`. The popover
  is `role="dialog"` with an `aria-label`.

Back stack:

* **Ctrl-O** (as in vim) also goes back.
* The button shows "Back to {data-ref}" and, once the stack is two or more deep, the depth.

## 8. Back stack persistence

* State is `{t, stack: [{url, fromId, scrollY, ref, label}], pending}`, stored as JSON in
  `sessionStorage["busybee.nav"]`. It is per tab, survives page loads and is cleared when the
  tab closes.
* The same JSON is mirrored into `window.name` with the prefix `busybee.nav:`. Some browsers
  (Firefox) give each `file://` page its own storage origin, and `window.name` survives those
  navigations. On read, the copy with the newer `t` wins.
* `nav.go` stores a `pending: {kind: "arrive", url, targetId, quote, ref, label, at}`.
  `nav.back` to another page stores `pending: {kind: "return", url, fromId, scrollY, at}`.
* The destination page consumes the pending entry on load, but only if its `url` matches and
  it is less than two minutes old. Then it highlights the chunk, or restores `scrollY` and
  flashes the statement (`.bb-returned`).
* The stack is capped at 64 entries.
* A jump within the same page (fact refs, Note 34 links) uses the same stack without a reload.

## 9. Print

Printing (the "Export PDF" button, Ctrl-P, or `busybee export-pdf`) uses `@page { size: A4;
margin: 0 }` and prints one `.bb-sheet` per page:

* The dark desk, shadows, toolbar, popover, back button and arrival bars disappear; the
  background is white.
* Sheet geometry and type sizes are the same as on screen, so the page breaks are the ones the
  paginator chose. Don't change metrics in `@media print`.
* Chips become small grey references with no border; badges become outlined.
* Code wraps.
* Pages that are not paginated (source, Lean, policy) print with their own 18/20/20/26 mm
  padding, each `.bb-page` after the first starting on a new sheet.
