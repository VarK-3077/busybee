/*
  BusyBee report behaviour: pagination into A4 sheets, the Export PDF toolbar, citation
  popovers, source navigation and the back stack.

  Loaded (deferred, no build step, works from file://) by every page the renderer emits:
  the report, source pages, Lean pages and the policy page. It reads two optional JSON
  blobs from the page and never fetches anything:

    <script type="application/json" id="bb-chunks">  chunk_id -> {doc_id, doc_title,
        page_no, quote, href}
    <script type="application/json" id="bb-lean">    score / inference id -> Lean binding
        record (see README.md)

  Pagination: the report arrives as one <main class="bb-page bb-flow" data-paginate>. A
  small block-level paginator numbers the headings (data-num), flattens the page into
  atoms (header, notice, paragraphs, list items, score rows, blocks, footer), and moves
  them one by one into successive .bb-sheet pages, opening a new sheet as soon as an atom
  would cross the sheet's content box. Splittable containers (sections, groups, lists,
  reason groups) are shallow-cloned onto each sheet; the first clone keeps the original
  id, so every statement id, chip and anchor survives. A heading is never stranded at the
  bottom of a sheet. The same sheets print: document.css sizes them to one A4 page each.
  A fixed .bb-toolbar with an "Export PDF" button (window.print()) is added to every page.

  Interaction model (README.md has the exact markup):
  * .bb-cite[data-cites] opens a popover with one box per cited chunk, showing the citing fact's own
    quote from the parallel data-quotes JSON list; .bb-cite[data-lean]
    opens the fact-to-Lean binding with the compiler output. Esc, a click outside, moving
    focus away or scrolling the chip out of view closes it; focus returns to the chip.
  * Following a box (or any [data-bb-go] / a.bb-jump link) calls nav.go(href, fromId):
    it pushes {url, fromId, scrollY, ref, label} onto a back stack and records a pending
    "arrive" so the destination page highlights the chunk (and the verbatim quote inside
    it) and shows a "you came from" bar.
  * nav.back() (floating button, Ctrl-O, or the bar's Back) pops the stack, returns to the
    exact page, restores the scroll position and flashes the statement it came from.
  * State lives in sessionStorage under "busybee.nav" and is mirrored into window.name,
    because some browsers give every file:// page its own storage origin; the newer copy
    wins on read.

  Public API: window.BusyBee = {init, paginate, popover: {open, close, toggle, isOpen},
  nav: {go, back, stack, clear}, data: {chunk, lean}}.
*/

(function (global) {
  "use strict";

  const STORAGE_KEY = "busybee.nav";
  const WINDOW_NAME_PREFIX = "busybee.nav:";
  const MAX_STACK_DEPTH = 64;
  const PENDING_MAX_AGE_MS = 120000;
  const FLASH_MS = 1600;
  const LABEL_MAX_CHARS = 110;
  const POPOVER_ID = "bb-popover";
  const BACK_BUTTON_ID = "bb-back";
  const POPOVER_GAP_PX = 6;
  const VIEWPORT_MARGIN_PX = 8;

  const jsonBlobs = {};
  let openPopoverState = null;
  let isInitialised = false;
  let generatedIdCount = 0;

  function readJsonBlob(blobId) {
    if (!(blobId in jsonBlobs)) {
      const script = document.getElementById(blobId);
      jsonBlobs[blobId] = parseJsonOr(script ? script.textContent : "", {});
    }
    return jsonBlobs[blobId];
  }

  function parseJsonOr(text, fallback) {
    try {
      return text ? JSON.parse(text) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function chunkById(chunkId) {
    return readJsonBlob("bb-chunks")[chunkId] || null;
  }

  function leanRecordById(recordId) {
    return readJsonBlob("bb-lean")[recordId] || null;
  }

  function createElement(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(function ([key, value]) {
      if (value === null || value === undefined || value === false) {
        return;
      }
      if (key === "text") {
        node.textContent = String(value);
      } else if (typeof value === "function") {
        node.addEventListener(key.replace(/^on/, ""), value);
      } else if (key === "class") {
        node.className = value;
      } else {
        node.setAttribute(key, value === true ? "" : String(value));
      }
    });
    (children || []).forEach(function (child) {
      if (child !== null && child !== undefined && child !== false) {
        node.append(child);
      }
    });
    return node;
  }

  function ensureId(node, prefix) {
    if (!node.id) {
      generatedIdCount += 1;
      node.id = prefix + "-" + generatedIdCount;
    }
    return node.id;
  }

  function collapseWhitespace(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function truncate(text, maxChars) {
    return text.length > maxChars ? text.slice(0, maxChars - 1).trimEnd() + "…" : text;
  }

  function emptyNavState() {
    return { t: 0, stack: [], pending: null };
  }

  function parseNavState(text) {
    const state = parseJsonOr(text, null);
    if (!state || !Array.isArray(state.stack)) {
      return emptyNavState();
    }
    return { t: Number(state.t) || 0, stack: state.stack, pending: state.pending || null };
  }

  function readSessionNavState() {
    try {
      return parseNavState(global.sessionStorage.getItem(STORAGE_KEY));
    } catch (error) {
      return emptyNavState();
    }
  }

  function readWindowNameNavState() {
    const name = String(global.name || "");
    return name.startsWith(WINDOW_NAME_PREFIX)
      ? parseNavState(name.slice(WINDOW_NAME_PREFIX.length))
      : emptyNavState();
  }

  function loadNavState() {
    const fromSession = readSessionNavState();
    const fromWindowName = readWindowNameNavState();
    return fromWindowName.t > fromSession.t ? fromWindowName : fromSession;
  }

  function saveNavState(state) {
    state.t = Date.now();
    const text = JSON.stringify(state);
    try {
      global.sessionStorage.setItem(STORAGE_KEY, text);
    } catch (error) {
      global.console.debug("BusyBee: sessionStorage unavailable, using window.name only");
    }
    global.name = WINDOW_NAME_PREFIX + text;
  }

  function absoluteUrl(href) {
    return new URL(href, global.location.href);
  }

  function pageUrlOf(href) {
    const url = absoluteUrl(href);
    url.hash = "";
    return url.href;
  }

  function currentPageUrl() {
    return pageUrlOf(global.location.href);
  }

  function fragmentIdOf(href) {
    const hash = absoluteUrl(href).hash.slice(1);
    try {
      return decodeURIComponent(hash);
    } catch (error) {
      return hash;
    }
  }

  function statementOf(node) {
    return node.closest(".bb-stmt[id]") || node.closest(".bb-stmt") || node;
  }

  function statementRef(statement) {
    return statement ? statement.getAttribute("data-ref") || "" : "";
  }

  function statementLabel(statement) {
    if (!statement) {
      return collapseWhitespace(document.title);
    }
    const source = statement.querySelector(".bb-opinion") || statement;
    const copy = source.cloneNode(true);
    copy
      .querySelectorAll(".bb-cite, .bb-fact-id, .bb-block-id, .bb-badge, .bb-block-meta, [data-bb-skip-label]")
      .forEach(function (node) {
        node.remove();
      });
    return truncate(collapseWhitespace(copy.textContent), LABEL_MAX_CHARS);
  }

  function flash(node) {
    node.classList.add("bb-returned");
    global.setTimeout(function () {
      node.classList.remove("bb-returned");
    }, FLASH_MS);
  }

  function focusWithoutScroll(node) {
    if (!node.matches("a, button, input, select, textarea, [tabindex]")) {
      node.setAttribute("tabindex", "-1");
    }
    try {
      node.focus({ preventScroll: true });
    } catch (error) {
      node.focus();
    }
  }

  function isInViewport(node) {
    const rect = node.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < global.innerHeight;
  }

  function runNowAndAfterLoad(task) {
    task();
    if (document.readyState !== "complete") {
      global.addEventListener("load", task, { once: true });
    }
  }

  function go(href, fromId, options) {
    const from = fromId ? document.getElementById(fromId) : null;
    const target = absoluteUrl(href);
    const state = loadNavState();
    const ref = statementRef(from);
    const label = statementLabel(from);
    state.stack.push({
      url: global.location.href,
      fromId: fromId || null,
      scrollY: Math.round(global.scrollY),
      ref: ref,
      label: label,
    });
    state.stack = state.stack.slice(-MAX_STACK_DEPTH);
    state.pending = {
      kind: "arrive",
      url: pageUrlOf(target.href),
      at: Date.now(),
      targetId: fragmentIdOf(target.href),
      quote: (options && options.quote) || null,
      ref: ref,
      label: label,
    };
    saveNavState(state);
    closePopover(false);
    if (pageUrlOf(target.href) === currentPageUrl()) {
      arriveOnSamePage(target);
    } else {
      global.location.href = target.href;
    }
  }

  function arriveOnSamePage(target) {
    if (target.hash && target.hash !== global.location.hash) {
      global.location.hash = target.hash;
    }
    highlightChunkFromHash();
    consumePendingNavigation();
    renderBackButton();
  }

  function back() {
    const state = loadNavState();
    const entry = state.stack.pop();
    if (!entry) {
      return false;
    }
    closePopover(false);
    if (pageUrlOf(entry.url) === currentPageUrl()) {
      state.pending = null;
      saveNavState(state);
      removeArrivalBars();
      if (absoluteUrl(entry.url).hash !== global.location.hash) {
        global.history.replaceState(null, "", entry.url);
        highlightChunkFromHash();
      }
      restoreReturn(entry);
      renderBackButton();
    } else {
      state.pending = {
        kind: "return",
        url: pageUrlOf(entry.url),
        at: Date.now(),
        fromId: entry.fromId,
        scrollY: entry.scrollY,
      };
      saveNavState(state);
      global.location.href = entry.url;
    }
    return true;
  }

  function stack() {
    return loadNavState().stack.slice();
  }

  function clearStack() {
    saveNavState(emptyNavState());
    renderBackButton();
  }

  function restoreReturn(entry) {
    const statement = entry.fromId ? document.getElementById(entry.fromId) : null;
    runNowAndAfterLoad(function () {
      global.scrollTo(0, entry.scrollY || 0);
      if (statement && !isInViewport(statement)) {
        statement.scrollIntoView({ block: "center" });
      }
    });
    if (statement) {
      flash(statement);
      focusWithoutScroll(statement.querySelector(".bb-cite") || statement);
    }
  }

  function consumePendingNavigation() {
    const state = loadNavState();
    const pending = state.pending;
    if (!pending || pending.url !== currentPageUrl()) {
      return;
    }
    state.pending = null;
    saveNavState(state);
    if (Date.now() - (pending.at || 0) > PENDING_MAX_AGE_MS) {
      return;
    }
    if (pending.kind === "arrive") {
      showArrival(pending);
    } else if (pending.kind === "return") {
      restoreReturn(pending);
    }
  }

  function showArrival(pending) {
    const target = pending.targetId ? document.getElementById(pending.targetId) : null;
    if (!target) {
      return;
    }
    removeArrivalBars();
    let anchor = target;
    if (target.classList.contains("bb-chunk")) {
      markChunkAsTarget(target);
      if (pending.quote) {
        markQuoteIn(target, pending.quote);
      }
      anchor = arrivalBar(pending);
      target.before(anchor);
    } else {
      flash(target);
    }
    runNowAndAfterLoad(function () {
      anchor.scrollIntoView({ block: "start" });
    });
    focusWithoutScroll(target);
  }

  function removeArrivalBars() {
    document.querySelectorAll(".bb-arrival").forEach(function (bar) {
      bar.remove();
    });
  }

  function arrivalBar(pending) {
    const backButton = createElement("button", { type: "button", text: "Back" });
    backButton.addEventListener("click", back);
    const ref = pending.ref ? createElement("strong", { text: pending.ref }) : "the previous page";
    return createElement("div", { class: "bb-arrival", role: "note" }, [
      createElement("span", { class: "bb-arrival-text" }, [
        "↩ You came from ",
        ref,
        pending.label ? " — " : "",
        pending.label ? createElement("q", { text: pending.label }) : "",
      ]),
      backButton,
    ]);
  }

  function markChunkAsTarget(chunk) {
    document.querySelectorAll(".bb-chunk--target").forEach(function (node) {
      node.classList.remove("bb-chunk--target");
    });
    chunk.classList.add("bb-chunk--target");
  }

  function highlightChunkFromHash() {
    const id = fragmentIdOf(global.location.href);
    const target = id ? document.getElementById(id) : null;
    if (target && target.classList.contains("bb-chunk")) {
      markChunkAsTarget(target);
    }
  }

  function textNodesWithOffsets(container) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let offset = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!node.parentElement.closest(".bb-chunk-id")) {
        nodes.push({ node: node, start: offset, end: offset + node.data.length });
        offset += node.data.length;
      }
    }
    return nodes;
  }

  function normalisedWithIndexMap(text) {
    let normalised = "";
    const rawIndexOf = [];
    let previousWasSpace = true;
    for (let index = 0; index < text.length; index += 1) {
      const isSpace = /\s/.test(text[index]);
      if (isSpace && previousWasSpace) {
        continue;
      }
      normalised += isSpace ? " " : text[index].toLowerCase();
      rawIndexOf.push(index);
      previousWasSpace = isSpace;
    }
    return { normalised: normalised, rawIndexOf: rawIndexOf };
  }

  function markQuoteIn(container, quote) {
    const nodes = textNodesWithOffsets(container);
    const fullText = nodes.map(function (entry) {
      return entry.node.data;
    }).join("");
    const haystack = normalisedWithIndexMap(fullText);
    const needle = collapseWhitespace(quote).toLowerCase();
    const found = needle ? haystack.normalised.indexOf(needle) : -1;
    if (found < 0) {
      return false;
    }
    const rawStart = haystack.rawIndexOf[found];
    const rawEnd = haystack.rawIndexOf[found + needle.length - 1] + 1;
    nodes.forEach(function (entry) {
      wrapTextRange(entry, Math.max(rawStart, entry.start), Math.min(rawEnd, entry.end));
    });
    return true;
  }

  function wrapTextRange(entry, rawStart, rawEnd) {
    if (rawEnd <= rawStart) {
      return;
    }
    const middle = entry.node.splitText(rawStart - entry.start);
    middle.splitText(rawEnd - rawStart);
    const mark = createElement("mark", { class: "bb-quote" });
    middle.replaceWith(mark);
    mark.append(middle);
  }

  function popoverElement() {
    let popover = document.getElementById(POPOVER_ID);
    if (!popover) {
      popover = createElement("div", {
        id: POPOVER_ID,
        class: "bb-popover",
        role: "dialog",
        tabindex: "-1",
        hidden: true,
      });
      document.body.append(popover);
    }
    return popover;
  }

  function isPopoverOpen() {
    return openPopoverState !== null;
  }

  function openPopover(chip) {
    closePopover(false);
    const popover = popoverElement();
    const content = chip.hasAttribute("data-lean") ? leanPopoverContent(chip) : citationPopoverContent(chip);
    popover.replaceChildren(content.head, content.body);
    if (content.footer) {
      popover.append(content.footer);
    }
    popover.setAttribute("aria-label", content.label);
    popover.hidden = false;
    popover.classList.remove("bb-popover--open");
    chip.setAttribute("aria-expanded", "true");
    chip.setAttribute("aria-controls", POPOVER_ID);
    openPopoverState = { chip: chip, fromId: ensureId(statementOf(chip), "bb-stmt") };
    positionPopover(popover, chip);
    global.requestAnimationFrame(function () {
      popover.classList.add("bb-popover--open");
    });
    focusWithoutScroll(firstFocusableIn(popover) || popover);
  }

  function closePopover(returnFocus) {
    if (!openPopoverState) {
      return;
    }
    const chip = openPopoverState.chip;
    const popover = popoverElement();
    openPopoverState = null;
    popover.hidden = true;
    popover.classList.remove("bb-popover--open");
    popover.replaceChildren();
    chip.setAttribute("aria-expanded", "false");
    if (returnFocus) {
      focusWithoutScroll(chip);
    }
  }

  function togglePopover(chip) {
    if (openPopoverState && openPopoverState.chip === chip) {
      closePopover(true);
    } else {
      openPopover(chip);
    }
  }

  function firstFocusableIn(container) {
    return [".bb-pop-item", ".bb-pop-body a", ".bb-pop-link", ".bb-pop-close"]
      .map(function (selector) {
        return container.querySelector(selector);
      })
      .find(Boolean);
  }

  function focusablesIn(container) {
    return Array.from(container.querySelectorAll("a[href], button"));
  }

  function positionPopover(popover, chip) {
    popover.style.left = "0px";
    popover.style.top = "0px";
    const chipRect = chip.getBoundingClientRect();
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = global.innerHeight;
    const spaceBelow = viewportHeight - chipRect.bottom;
    const spaceAbove = chipRect.top;
    const placeAbove = spaceBelow < height + POPOVER_GAP_PX + VIEWPORT_MARGIN_PX && spaceAbove > spaceBelow;
    const maxLeft = viewportWidth - width - VIEWPORT_MARGIN_PX;
    const left = Math.max(VIEWPORT_MARGIN_PX, Math.min(chipRect.left - 12, maxLeft));
    const top = placeAbove ? chipRect.top - height - POPOVER_GAP_PX : chipRect.bottom + POPOVER_GAP_PX;
    popover.style.left = Math.round(left + global.scrollX) + "px";
    popover.style.top = Math.round(Math.max(VIEWPORT_MARGIN_PX, top) + global.scrollY) + "px";
    popover.setAttribute("data-placement", placeAbove ? "above" : "below");
  }

  function popoverHead(titleChildren) {
    const closeButton = createElement("button", {
      type: "button",
      class: "bb-pop-close",
      "aria-label": "Close",
      text: "×",
    });
    closeButton.addEventListener("click", function () {
      closePopover(true);
    });
    return createElement("div", { class: "bb-pop-head" }, [
      createElement("span", { class: "bb-pop-title" }, titleChildren),
      closeButton,
    ]);
  }

  function statusBadge(status, text) {
    return status ? createElement("span", { class: "bb-badge", "data-status": status, text: text || status }) : null;
  }

  function citedChunkIds(chip) {
    return String(chip.getAttribute("data-cites") || "")
      .split(",")
      .map(function (id) {
        return id.trim();
      })
      .filter(Boolean);
  }

  function citedQuotes(chip) {
    try {
      const quotes = JSON.parse(chip.getAttribute("data-quotes") || "[]");
      return Array.isArray(quotes) ? quotes : [];
    } catch (error) {
      return [];
    }
  }

  function citationPopoverContent(chip) {
    const chunkIds = citedChunkIds(chip);
    const quotes = citedQuotes(chip);
    const countText = chunkIds.length === 1 ? "1 source" : chunkIds.length + " sources";
    const status = chip.getAttribute("data-status");
    const method = chip.getAttribute("data-method");
    const statusText = status ? status + (method ? " · " + method.replace(/_/g, " ") : "") : "";
    const items = chunkIds.map(function (chunkId, index) {
      return chunkBox(chunkId, quotes[index]);
    });
    return {
      label: "Sources for this statement",
      head: popoverHead([countText, statusBadge(status, statusText)]),
      body: createElement("div", { class: "bb-pop-body" }, items.length ? items : [missingNote("No sources listed.")]),
    };
  }

  function chunkBox(chunkId, ownQuote) {
    const chunk = chunkById(chunkId);
    if (!chunk) {
      return missingNote("Source " + chunkId + " is not in this bundle.");
    }
    const linked = Boolean(chunk.href);
    const quote = ownQuote || chunk.quote;
    const base = { class: "bb-pop-item", "data-chunk": chunkId, "data-quote": quote };
    const attributes = linked ? Object.assign({ href: chunk.href, "data-bb-go": true }, base) : base;
    const item = createElement(linked ? "a" : "div", attributes, [
      createElement("span", { class: "bb-pop-item-head" }, [
        createElement("span", { class: "bb-pop-doc", text: chunk.doc_title || chunk.doc_id, title: chunk.doc_title }),
        chunk.page_no ? createElement("span", { class: "bb-pop-page", text: "p. " + chunk.page_no }) : null,
      ]),
      createElement("blockquote", { class: "bb-pop-quote", text: quote }),
      createElement("span", { class: "bb-pop-item-foot" }, [
        createElement("span", { class: "bb-pop-chunk", text: chunkId }),
        linked ? createElement("span", { class: "bb-pop-go", text: "Open page →" }) : null,
      ]),
    ]);
    if (!chunk.pdf_href) {
      return item;
    }
    const pdfLink = createElement("a", {
      class: "bb-pop-textlink",
      href: chunk.pdf_href,
      target: "_blank",
      rel: "noopener",
      text: "PDF p." + chunk.page_no,
    });
    return createElement("div", { class: "bb-pop-entry" }, [item, pdfLink]);
  }

  function missingNote(text) {
    return createElement("p", { class: "bb-pop-missing", text: text });
  }

  function leanPopoverContent(chip) {
    const recordId = chip.getAttribute("data-lean");
    const record = leanRecordById(recordId);
    if (!record) {
      return {
        label: "Lean record",
        head: popoverHead(["Lean"]),
        body: createElement("div", { class: "bb-pop-body" }, [missingNote("Lean record " + recordId + " is not in this bundle.")]),
      };
    }
    const kindText = record.kind === "inference" ? "Lean · inference" : record.kind === "rule" ? "Lean · policy rule" : "Lean · score";
    return {
      label: kindText + " " + (record.title || recordId),
      head: popoverHead([kindText, statusBadge(record.status)]),
      body: createElement("div", { class: "bb-pop-body" }, [
        leanSummary(record),
        warningSection(record.warnings || []),
        bindingSection(record.bindings || []),
        compileSection(record.compile),
      ]),
      footer: record.href
        ? createElement("a", { class: "bb-pop-link", href: record.href, "data-bb-go": true, text: "Open the full Lean artifact →" })
        : null,
    };
  }

  function leanSummary(record) {
    return createElement("div", { class: "bb-pop-score" }, [
      createElement("span", { class: "bb-pop-score-name", text: record.title || "" }),
      record.value_display ? createElement("span", { class: "bb-pop-score-value", text: record.value_display }) : null,
      record.grade
        ? createElement("span", { class: "bb-badge bb-grade", "data-tone": record.grade_tone || "none", text: record.grade })
        : null,
      (record.warnings || []).length
        ? createElement("span", { class: "bb-badge", "data-status": "unchecked", title: record.warnings.join("; "), text: "Warning" })
        : null,
      record.claim ? createElement("code", { class: "bb-mono bb-muted", text: record.claim }) : null,
    ]);
  }

  function warningSection(warnings) {
    if (!warnings.length) {
      return null;
    }
    return createElement("div", { class: "bb-pop-section" }, [
      createElement("span", { class: "bb-caps" }, [
        createElement("span", { class: "bb-badge", "data-status": "unchecked", text: "Warning" }),
      ]),
      createElement("ul", { class: "bb-pop-warnings" }, warnings.map(function (text) {
        return createElement("li", { text: text });
      })),
    ]);
  }

  function bindingSection(bindings) {
    if (!bindings.length) {
      return null;
    }
    const head = createElement("thead", {}, [
      createElement("tr", {}, ["Slot", "", "Fact", "Value", "Scaled", "Source"].map(function (text) {
        return createElement("th", { scope: "col", text: text });
      })),
    ]);
    const body = createElement("tbody", {}, bindings.map(bindingRow));
    return createElement("div", { class: "bb-pop-section" }, [
      createElement("span", { class: "bb-caps", text: "Inputs bound from facts" }),
      createElement("table", { class: "bb-bind" }, [head, body]),
    ]);
  }

  function bindingRow(binding) {
    const chunk = binding.chunk_id ? chunkById(binding.chunk_id) : null;
    const factLink = binding.fact_id
      ? createElement("a", {
          class: "bb-ref",
          href: binding.fact_href || "#fact-" + binding.fact_id,
          "data-bb-go": true,
          text: binding.fact_id,
        })
      : createElement("span", { class: "bb-muted", text: binding.note || "unbound" });
    const sourceLink = chunk && !chunk.href
      ? createElement("span", { title: chunk.doc_title, text: "bank input" })
      : chunk
      ? createElement("a", { href: chunk.href, "data-bb-go": true, "data-chunk": binding.chunk_id, title: chunk.doc_title, text: chunk.doc_id + " p." + chunk.page_no })
      : binding.chunk_id || "—";
    return createElement("tr", {}, [
      createElement("td", { class: "bb-bind-slot", text: binding.slot }),
      createElement("td", { class: "bb-bind-arrow", "aria-label": "bound to", text: "←" }),
      createElement("td", {}, [
        factLink,
        binding.fact_id && binding.metric
          ? createElement("span", { class: "bb-bind-note", text: binding.metric })
          : null,
        binding.fact_id && binding.note
          ? createElement("span", { class: "bb-bind-note", text: binding.note })
          : null,
      ]),
      createElement("td", { class: "bb-num", text: binding.display || [binding.value, binding.unit].filter(Boolean).join(" ") }),
      createElement("td", { class: "bb-num bb-bind-scaled", text: binding.value_scaled === undefined ? "" : binding.value_scaled }),
      createElement("td", {}, [sourceLink]),
    ]);
  }

  function compileSection(compile) {
    if (!compile) {
      return null;
    }
    const facts = [
      compile.ok ? "Compiled without errors" : "Compilation failed",
      compile.duration_s !== undefined ? Number(compile.duration_s).toFixed(2) + " s" : "",
      compile.toolchain || "",
    ].filter(Boolean);
    return createElement("div", { class: "bb-pop-section" }, [
      createElement("span", { class: "bb-caps", text: "Compiler output" }),
      createElement("div", { class: "bb-compile", "data-ok": compile.ok ? "true" : "false" }, [
        createElement("div", { class: "bb-compile-head", text: facts.join(" · ") }),
        createElement("pre", { text: collapseTrailing(compile.output) || "(no output)" }),
      ]),
    ]);
  }

  function collapseTrailing(text) {
    return String(text || "").replace(/\s+$/, "");
  }

  function backButtonElement() {
    let button = document.getElementById(BACK_BUTTON_ID);
    if (!button) {
      button = createElement("button", {
        id: BACK_BUTTON_ID,
        type: "button",
        class: "bb-back",
        hidden: true,
        "aria-keyshortcuts": "Control+O",
      }, [
        createElement("span", { class: "bb-back-glyph", "aria-hidden": "true", text: "↩" }),
        createElement("span", { class: "bb-back-label" }),
        createElement("span", { class: "bb-back-depth", "aria-hidden": "true" }),
        createElement("kbd", { "aria-hidden": "true", text: "Ctrl O" }),
      ]);
      document.body.append(button);
    }
    return button;
  }

  function renderBackButton() {
    const button = backButtonElement();
    const entries = loadNavState().stack;
    const top = entries[entries.length - 1];
    button.hidden = !top;
    if (!top) {
      return;
    }
    const label = button.querySelector(".bb-back-label");
    const depth = button.querySelector(".bb-back-depth");
    label.replaceChildren("Back", top.ref ? " to " : "", top.ref ? createElement("strong", { text: top.ref }) : "");
    depth.textContent = entries.length > 1 ? String(entries.length) : "";
    depth.hidden = entries.length < 2;
    button.title = top.label || "";
    button.setAttribute(
      "aria-label",
      "Back to " + (top.ref || "previous place") + (top.label ? ": " + top.label : "") + ". " + entries.length + " in history."
    );
  }

  function isPlainClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  function onDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const backButton = target.closest("#" + BACK_BUTTON_ID);
    if (backButton) {
      back();
      return;
    }
    const goLink = target.closest("[data-bb-go], a.bb-jump");
    if (goLink && isPlainClick(event)) {
      event.preventDefault();
      followLink(goLink);
      return;
    }
    const chip = target.closest(".bb-cite");
    if (chip) {
      event.preventDefault();
      togglePopover(chip);
      return;
    }
    if (openPopoverState && !popoverElement().contains(target)) {
      closePopover(false);
    }
  }

  function followLink(link) {
    const inPopover = openPopoverState && popoverElement().contains(link);
    const fromId = inPopover ? openPopoverState.fromId : ensureId(statementOf(link), "bb-stmt");
    const chunkId = link.getAttribute("data-chunk");
    const chunk = chunkId ? chunkById(chunkId) : null;
    go(link.getAttribute("href"), fromId, { quote: link.getAttribute("data-quote") || (chunk ? chunk.quote : null) });
  }

  function onKeyDown(event) {
    if (event.key === "Escape" && openPopoverState) {
      event.preventDefault();
      closePopover(true);
    } else if ((event.key === "o" || event.key === "O") && event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
      if (stack().length) {
        event.preventDefault();
        back();
      }
    } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && openPopoverState) {
      moveFocusInPopover(event);
    }
  }

  function moveFocusInPopover(event) {
    const popover = popoverElement();
    if (!popover.contains(document.activeElement)) {
      return;
    }
    const focusables = focusablesIn(popover);
    const index = focusables.indexOf(document.activeElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    const next = focusables[(index + step + focusables.length) % focusables.length];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  function onFocusIn(event) {
    if (!openPopoverState) {
      return;
    }
    const target = event.target;
    if (target === openPopoverState.chip || popoverElement().contains(target)) {
      return;
    }
    closePopover(false);
  }

  function onScroll(event) {
    if (!openPopoverState) {
      return;
    }
    if (event.target instanceof Node && popoverElement().contains(event.target)) {
      return;
    }
    if (!isInViewport(openPopoverState.chip)) {
      closePopover(false);
    }
  }

  function onResize() {
    if (openPopoverState) {
      positionPopover(popoverElement(), openPopoverState.chip);
    }
  }

  function prepareChips() {
    document.querySelectorAll(".bb-cite").forEach(function (chip) {
      if (chip.tagName === "BUTTON" && !chip.hasAttribute("type")) {
        chip.setAttribute("type", "button");
      }
      chip.setAttribute("aria-haspopup", "dialog");
      chip.setAttribute("aria-expanded", "false");
    });
  }

  const SPLITTABLE = ".bb-section, .bb-group, .bb-recommendation, .bb-rec-group, ul, ol, " +
    ".bb-table-wrap, table, tbody";
  const KEEP_WITH_NEXT = "h2, h3, .bb-rec-heading, caption, thead";
  const repeatedHeads = new Map();

  function rememberHead(table) {
    const head = table.querySelector(":scope > thead");
    if (head && !repeatedHeads.has(table)) {
      const copy = head.cloneNode(true);
      copy.removeAttribute("id");
      copy.querySelectorAll("[id]").forEach(function (node) {
        node.removeAttribute("id");
      });
      copy.setAttribute("data-bb-repeat", "");
      repeatedHeads.set(table, copy);
    }
  }

  function holderIsEmpty(holder) {
    return Array.from(holder.children).every(function (child) {
      return child.hasAttribute("data-bb-repeat");
    });
  }

  function numberHeadings(flow) {
    flow.querySelectorAll(".bb-report > .bb-section").forEach(function (section, sectionIndex) {
      const heading = section.querySelector(":scope > .bb-h2");
      if (heading) {
        heading.setAttribute("data-num", String(sectionIndex + 1));
      }
      section.querySelectorAll(":scope > .bb-group > .bb-h3").forEach(function (title, groupIndex) {
        title.setAttribute("data-num", sectionIndex + 1 + "." + (groupIndex + 1));
      });
    });
  }

  function flattenIntoAtoms(node, path, atoms) {
    Array.from(node.children).forEach(function (child) {
      if (child.matches(".bb-report")) {
        flattenIntoAtoms(child, path, atoms);
      } else if (child.matches(SPLITTABLE) && child.children.length) {
        if (child.matches("table")) {
          rememberHead(child);
        }
        flattenIntoAtoms(child, path.concat([child]), atoms);
      } else {
        const keep = child.matches(KEEP_WITH_NEXT) ||
          (child.matches(".bb-caps") && child.parentElement.matches(".bb-recommendation"));
        atoms.push({ el: child, path: path, keep: keep, chain: null });
      }
    });
  }

  function paginate(flow) {
    numberHeadings(flow);
    const notice = document.querySelector("body > .bb-notice");
    if (notice) {
      flow.prepend(notice);
    }
    const atoms = [];
    flattenIntoAtoms(flow, [], atoms);

    const sheets = createElement("div", { class: "bb-sheets" });
    const firstClone = new Map();
    let body = null;
    let chain = [];
    let placed = [];

    function openSheet() {
      body = createElement("div", { class: "bb-sheet-body" });
      sheets.append(createElement("section", { class: "bb-page bb-sheet" }, [body]));
      chain = [];
      placed = [];
    }

    function mount(atom) {
      let depth = 0;
      while (depth < chain.length && depth < atom.path.length && chain[depth].orig === atom.path[depth]) {
        depth += 1;
      }
      chain = chain.slice(0, depth);
      let parent = depth ? chain[depth - 1].clone : body;
      const atSheetTop = placed.length === 0;
      for (let level = depth; level < atom.path.length; level += 1) {
        const orig = atom.path[level];
        const clone = orig.cloneNode(false);
        if (firstClone.has(orig)) {
          clone.removeAttribute("id");
          if (repeatedHeads.has(orig)) {
            clone.append(repeatedHeads.get(orig).cloneNode(true));
          }
        } else {
          firstClone.set(orig, clone);
        }
        if (atSheetTop) {
          clone.classList.add("bb-sheet-top");
        }
        parent.append(clone);
        chain.push({ orig: orig, clone: clone });
        parent = clone;
      }
      atom.el.classList.toggle("bb-sheet-top", atSheetTop);
      parent.append(atom.el);
      atom.chain = chain.slice();
      placed.push(atom);
    }

    function unplaceLast() {
      const atom = placed.pop();
      let holder = atom.el.parentElement;
      atom.el.remove();
      while (holder && holder !== body && holderIsEmpty(holder)) {
        const parent = holder.parentElement;
        firstClone.forEach(function (clone, orig) {
          if (clone === holder) {
            firstClone.delete(orig);
          }
        });
        holder.remove();
        holder = parent;
      }
      chain = placed.length ? placed[placed.length - 1].chain.slice() : [];
      return atom;
    }

    function overflows(atom) {
      return atom.el.getBoundingClientRect().bottom > body.getBoundingClientRect().bottom + 0.5;
    }

    flow.before(sheets);
    openSheet();
    let index = 0;
    while (index < atoms.length) {
      mount(atoms[index]);
      if (placed.length > 1 && overflows(atoms[index])) {
        unplaceLast();
        let moved = 0;
        while (placed.length > 1 && placed[placed.length - 1].keep) {
          unplaceLast();
          moved += 1;
        }
        index -= moved;
        openSheet();
        continue;
      }
      index += 1;
    }
    flow.remove();

    const sheetList = sheets.querySelectorAll(".bb-sheet");
    sheetList.forEach(function (sheet, position) {
      sheet.append(createElement("span", {
        class: "bb-sheet-number",
        "aria-hidden": "true",
        text: position + 1 + " / " + sheetList.length,
      }));
    });
    if (global.location.hash.length > 1) {
      const target = document.getElementById(decodeURIComponent(global.location.hash.slice(1)));
      if (target) {
        target.scrollIntoView();
      }
    }
  }

  function paginateReport() {
    const flow = document.querySelector("[data-paginate]");
    if (flow) {
      paginate(flow);
    }
  }

  function renderToolbar() {
    if (document.getElementById("bb-toolbar")) {
      return;
    }
    document.body.append(createElement("div", { id: "bb-toolbar", class: "bb-toolbar" }, [
      createElement("button", {
        type: "button",
        title: "Save this report as a PDF (print dialog)",
        text: "Export PDF",
        onclick: function () {
          global.print();
        },
      }),
    ]));
  }

  function init() {
    if (isInitialised) {
      return;
    }
    isInitialised = true;
    paginateReport();
    renderToolbar();
    prepareChips();
    renderBackButton();
    highlightChunkFromHash();
    consumePendingNavigation();
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("scroll", onScroll, { capture: true, passive: true });
    global.addEventListener("resize", onResize);
    global.addEventListener("hashchange", highlightChunkFromHash);
    global.addEventListener("pageshow", renderBackButton);
  }

  global.BusyBee = {
    init: init,
    paginate: paginateReport,
    popover: { open: openPopover, close: closePopover, toggle: togglePopover, isOpen: isPopoverOpen },
    nav: { go: go, back: back, stack: stack, clear: clearStack },
    data: { chunk: chunkById, lean: leanRecordById },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
