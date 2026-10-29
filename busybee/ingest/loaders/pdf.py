"""Extract per-page text from PDFs with column-aware ordering and header-carrying tables.

Raw `get_text("text")` follows the PDF content stream, which detaches labels from values on
multi-column pages and flattens tables into cell-per-line soup. This loader rebuilds the page
text from the line geometry instead (everything is a plain function):

1. Lines come from `page.get_text("dict")`. Lines whose centre falls inside a table found by
   `page.find_tables()` are dropped; the table is rendered separately.
2. Card grids (a row of short names with a row of short labels right below, as in a
   "corporate information" board list) are paired by horizontal overlap and emitted as
   "NAME | label" so a designation stays next to its name.
3. Reading order: the page is cut into vertical segments at full-width lines or tables; inside
   a segment the widest empty vertical gutter (with at least three items on each side) splits
   it into columns, recursively, and the columns are emitted left to right. Segments without a
   gutter keep the content-stream order.
4. Tables: `page.find_tables()` only supplies the table region (its own cell text scrambles
   digits on some PDFs). Words in the region are clustered into rows by y and into cells by
   x gaps. When at least two rows hold numeric cells that line up in right-aligned columns,
   header cells above the first numeric row are attached to the nearest column and each row is
   rendered "<row label> | <header1>: <cell1> | <header2>: <cell2> ..." inside sentinel lines
   `[TABLE: <headers joined by ' | '>]` ... `[/TABLE]`; label-only rows that mention a year
   (e.g. "Year ended March 31, 2026") are prefixed to the following row labels. Numeric cells
   stay verbatim (1,23,456.78 and (1,234) are never reformatted). Any other table keeps its
   rows as plain pipe-joined lines, so e.g. a rating-history row keeps each date next to its
   rating. Because every row repeats its headers, a table split across chunks keeps them; the
   chunker also exposes the `[TABLE: ...]` line as `Chunk.prefix`.
5. Pages whose text is rotated by a quarter turn (landscape tables printed sideways) are
   rotated back in coordinate space and rendered with the same row/column logic over the whole
   page, split into blocks at big vertical gaps and prose rows; find_tables is not used there.
"""

import re
from pathlib import Path
from typing import NamedTuple

import pymupdf

_NUMERIC_CELL = re.compile(r"^[\(\-–—]?\s*(?:₹|Rs\.?|\$)?\s*\d[\d,]*(?:\.\d+)?\s*%?\s*\)?$")
_PLACEHOLDER_CELL = re.compile(r"^[\-–—\s]*$")
_YEAR_CELL = re.compile(r"^(?:FY\s?)?(?:19|20)\d\d(?:\s?[-–/]\s?\d{2,4})?$", re.IGNORECASE)
_FULL_WIDTH_SHARE = 0.6
_MIN_GUTTER = 10.0
_MIN_ITEMS_PER_COLUMN = 3
_BAND_TOLERANCE = 3.0
_CARD_MAX_CHARS = 45
_CARD_MAX_GAP = 8.0
_MAX_COLUMN_DEPTH = 3
_CELL_GAP = 5.0
_COLUMN_TOLERANCE = 6.0
_HEADER_REACH = 40.0
_BLOCK_GAP = 18.0
_PROSE_WORDS = 10
_MIN_NUMERIC_SHARE = 0.6
_YEAR_IN_TEXT = re.compile(r"\b(?:19|20)\d\d\b")


class _Item(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    order: int


class _Cell(NamedTuple):
    x0: float
    x1: float
    text: str


class _Row(NamedTuple):
    y0: float
    y1: float
    cells: list[_Cell]


def _is_year(cell: str) -> bool:
    return bool(_YEAR_CELL.match(cell))


def _is_numeric(cell: str) -> bool:
    return not _is_year(cell) and (
        bool(_NUMERIC_CELL.match(cell)) or bool(_PLACEHOLDER_CELL.match(cell))
    )


def _word_rows(words: list[tuple[float, float, float, float, str]]) -> list[_Row]:
    """Cluster upright words into rows by y and into cells by horizontal gaps."""
    rows: list[list[tuple[float, float, float, float, str]]] = []
    anchor = 0.0
    for word in sorted(words, key=lambda entry: ((entry[1] + entry[3]) / 2, entry[0])):
        centre = (word[1] + word[3]) / 2
        if rows and abs(centre - anchor) <= _BAND_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])
            anchor = centre
    result: list[_Row] = []
    for row in rows:
        row.sort(key=lambda entry: entry[0])
        cells: list[_Cell] = []
        for x0, y0, x1, y1, text in row:
            if cells and x0 - cells[-1].x1 <= max(_CELL_GAP, 0.6 * (y1 - y0)):
                last = cells[-1]
                cells[-1] = _Cell(last.x0, max(last.x1, x1), f"{last.text} {text}")
            else:
                cells.append(_Cell(x0, x1, text))
        result.append(_Row(min(w[1] for w in row), max(w[3] for w in row), cells))
    return result


def _plain_row(row: _Row) -> str:
    return " | ".join(cell.text for cell in row.cells)


def _numeric_columns(rows: list[_Row]) -> list[tuple[float, float, float]]:
    """Return (centre, x0, x1) of right-aligned numeric columns, left to right."""
    numeric_rows = [row for row in rows if any(_is_numeric(cell.text) for cell in row.cells)]
    edges = sorted(
        (cell.x1, cell.x0) for row in numeric_rows for cell in row.cells if _is_numeric(cell.text)
    )
    clusters: list[list[tuple[float, float]]] = []
    for edge in edges:
        if clusters and edge[0] - clusters[-1][-1][0] <= _COLUMN_TOLERANCE:
            clusters[-1].append(edge)
        else:
            clusters.append([edge])
    needed = max(2, int(0.3 * len(numeric_rows)))
    columns = [
        (
            (min(x0 for _, x0 in group) + max(x1 for x1, _ in group)) / 2,
            min(x0 for _, x0 in group),
            max(x1 for x1, _ in group),
        )
        for group in clusters
        if len(group) >= needed
    ]
    return columns if len(numeric_rows) >= 2 and len(columns) >= 2 else []


def _nearest_column(columns: list[tuple[float, float, float]], centre: float) -> int | None:
    distances = [abs(centre - column[0]) for column in columns]
    best = min(range(len(columns)), key=lambda index: distances[index])
    others = [
        abs(columns[best][0] - column[0]) for index, column in enumerate(columns) if index != best
    ]
    reach = min(min(others) / 2 if others else _HEADER_REACH, _HEADER_REACH)
    return best if distances[best] <= reach else None


def _numeric_share(rows: list[_Row], columns: list[tuple[float, float, float]]) -> float:
    cells = [
        cell
        for row in rows
        for cell in row.cells
        if columns and cell.x0 >= columns[0][1] - _COLUMN_TOLERANCE
    ]
    return sum(_is_numeric(cell.text) for cell in cells) / len(cells) if cells else 0.0


def _render_rows(rows: list[_Row]) -> str | None:
    """Render a block of rows, attaching headers to numeric cells when columns line up."""
    columns = _numeric_columns(rows)
    first_numeric = next(
        (i for i, row in enumerate(rows) if any(_is_numeric(c.text) for c in row.cells)), 0
    )
    headers: list[list[str]] = [[] for _ in columns]
    leftovers: list[str] = []
    for row in rows[:first_numeric] if columns else []:
        loose = []
        for cell in row.cells:
            index = _nearest_column(columns, (cell.x0 + cell.x1) / 2)
            if index is None:
                loose.append(cell.text)
            else:
                headers[index].append(cell.text)
        if loose:
            leftovers.append(" ".join(loose))
    names = [" ".join(parts) for parts in headers]
    if not any(names) or _numeric_share(rows, columns) < _MIN_NUMERIC_SHARE:
        return None
    lines = list(leftovers)
    lines.append(f"[TABLE: {' | '.join(name for name in names if name)}]")
    label_edge = columns[0][1] - _COLUMN_TOLERANCE
    last_numeric = max(
        i for i, row in enumerate(rows) if any(_is_numeric(c.text) for c in row.cells)
    )
    trailing = [_plain_row(row) for row in rows[last_numeric + 1 :]]
    rows = rows[: last_numeric + 1]
    context = next((line for line in reversed(leftovers) if _YEAR_IN_TEXT.search(line)), "")
    for row in rows[first_numeric:]:
        label = " ".join(c.text for c in row.cells if c.x1 <= label_edge)
        values = []
        for cell in row.cells:
            if cell.x1 <= label_edge:
                continue
            index = _nearest_column(columns, (cell.x0 + cell.x1) / 2)
            name = names[index] if index is not None else ""
            values.append(f"{name}: {cell.text}" if name else cell.text)
        if not values:
            context = label if _YEAR_IN_TEXT.search(label) else context
            lines.append(label)
            continue
        if context and label and not _YEAR_IN_TEXT.search(label):
            label = f"{context} / {label}"
        lines.append(" | ".join(([label] if label else []) + values))
    lines.append("[/TABLE]")
    return "\n".join(lines + trailing)


def _blocks(rows: list[_Row]) -> list[list[_Row]]:
    blocks: list[list[_Row]] = [[]]
    for row in rows:
        prose = any(len(cell.text.split()) >= _PROSE_WORDS for cell in row.cells)
        far = blocks[-1] and row.y0 - blocks[-1][-1].y1 > _BLOCK_GAP
        if prose or far:
            blocks.append([])
        blocks[-1].append(row)
        if prose:
            blocks.append([])
    return [block for block in blocks if block]


def _cell_text(words: list[tuple], box: tuple[float, float, float, float] | None) -> str:
    """Join the words whose centre lies in the cell, in stream order."""
    if box is None:
        return ""
    inside = [
        word
        for word in words
        if box[0] <= (word[0] + word[2]) / 2 <= box[2]
        and box[1] <= (word[1] + word[3]) / 2 <= box[3]
    ]
    inside.sort(key=lambda word: (word[5], word[6], word[7]))
    return " ".join(word[4] for word in inside)


def _tables(page: pymupdf.Page, words: list[tuple]) -> list[tuple[pymupdf.Rect, str]]:
    try:
        found = page.find_tables()
    except Exception:
        return []
    rendered: list[tuple[pymupdf.Rect, str]] = []
    for table in found.tables:
        if table.row_count < 2 or table.col_count < 2:
            continue
        box = pymupdf.Rect(table.bbox)
        inside = [
            (w[0], w[1], w[2], w[3], w[4])
            for w in words
            if box.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
        ]
        text = _render_rows(_word_rows(inside)) if inside else None
        if text is None:
            cell_rows = [[_cell_text(words, cell) for cell in row.cells] for row in table.rows]
            text = "\n".join(" | ".join(c for c in row if c) for row in cell_rows if any(row))
        if text:
            rendered.append((box, text))
    return rendered


def _quarter_turn(page: pymupdf.Page) -> int:
    """Return 1 when most text runs bottom-to-top, -1 when top-to-bottom, else 0."""
    weight = {1: 0, -1: 0, 0: 0}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            direction = line["dir"]
            size = sum(len(span["text"]) for span in line["spans"])
            if abs(direction[0]) < 0.2 and direction[1] < -0.8:
                weight[1] += size
            elif abs(direction[0]) < 0.2 and direction[1] > 0.8:
                weight[-1] += size
            else:
                weight[0] += size
    turn = max(weight, key=lambda key: weight[key])
    return turn if weight[turn] > 0 else 0


def _rotated_page_text(page: pymupdf.Page, turn: int) -> str:
    width, height = page.rect.width, page.rect.height
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if turn == 1:
            words.append((height - y1, x0, height - y0, x1, text))
        else:
            words.append((y0, width - x1, y1, width - x0, text))
    blocks = _blocks(_word_rows(words))
    rendered = (_render_rows(block) or "\n".join(map(_plain_row, block)) for block in blocks)
    return "\n".join(rendered).strip()


def _page_lines(page: pymupdf.Page, table_boxes: list[pymupdf.Rect]) -> list[_Item]:
    items: list[_Item] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
            if any(box.contains(centre) for box in table_boxes):
                continue
            items.append(_Item(x0, y0, x1, y1, text, len(items)))
    return items


def _bands(items: list[_Item]) -> list[list[_Item]]:
    bands: list[list[_Item]] = []
    for item in sorted(items, key=lambda entry: ((entry.y0 + entry.y1) / 2, entry.x0)):
        centre = (item.y0 + item.y1) / 2
        if bands and abs(centre - (bands[-1][0].y0 + bands[-1][0].y1) / 2) <= _BAND_TOLERANCE:
            bands[-1].append(item)
        else:
            bands.append([item])
    return [sorted(band, key=lambda entry: entry.x0) for band in bands]


def _overlaps(first: _Item, second: _Item) -> bool:
    shared = min(first.x1, second.x1) - max(first.x0, second.x0)
    return shared > 0.3 * min(first.x1 - first.x0, second.x1 - second.x0)


def _is_card_band(band: list[_Item]) -> bool:
    if len(band) < 2 or any(len(item.text) > _CARD_MAX_CHARS for item in band):
        return False
    return all(right.x0 - left.x1 >= 1 for left, right in zip(band, band[1:], strict=False))


def _pair_cards(items: list[_Item]) -> list[_Item]:
    """Join each label row to the name row above it, cell by cell, by horizontal overlap."""
    bands = _bands(items)
    merged: list[_Item] = []
    index = 0
    while index < len(bands):
        upper = bands[index]
        lower = bands[index + 1] if index + 1 < len(bands) else None
        if lower is not None and _is_card_band(upper) and _is_card_band(lower):
            gap = min(item.y0 for item in lower) - max(item.y1 for item in upper)
            matches = [[name for name in upper if _overlaps(name, label)] for label in lower]
            targets = [match[0] for match in matches if len(match) == 1]
            if (
                gap <= _CARD_MAX_GAP
                and len(targets) == len(lower)
                and len({target.order for target in targets}) == len(targets)
            ):
                labels = {target.order: label for target, label in zip(targets, lower, strict=True)}
                for name in upper:
                    label = labels.get(name.order)
                    if label is None:
                        merged.append(name)
                        continue
                    merged.append(
                        _Item(
                            min(name.x0, label.x0),
                            name.y0,
                            max(name.x1, label.x1),
                            label.y1,
                            f"{name.text} | {label.text}",
                            name.order,
                        )
                    )
                index += 2
                continue
        merged.extend(upper)
        index += 1
    return merged


def _gutter(items: list[_Item]) -> float | None:
    spans = sorted((item.x0, item.x1) for item in items)
    best: tuple[float, float] | None = None
    reach = spans[0][1]
    for start, end in spans[1:]:
        if start - reach >= _MIN_GUTTER:
            middle = (start + reach) / 2
            left = sum(1 for item in items if item.x1 <= middle)
            if min(left, len(items) - left) >= _MIN_ITEMS_PER_COLUMN and (
                best is None or start - reach > best[0]
            ):
                best = (start - reach, middle)
        reach = max(reach, end)
    return best[1] if best else None


def _in_columns(items: list[_Item], depth: int = 0) -> list[_Item]:
    middle = _gutter(items) if depth < _MAX_COLUMN_DEPTH and len(items) >= 6 else None
    if middle is None:
        return sorted(_pair_cards(items), key=lambda item: item.order)
    left = [item for item in items if item.x1 <= middle]
    right = [item for item in items if item.x0 >= middle]
    return _in_columns(left, depth + 1) + _in_columns(right, depth + 1)


def _reading_order(items: list[_Item]) -> list[_Item]:
    if not items:
        return []
    text_width = max(item.x1 for item in items) - min(item.x0 for item in items)
    ordered: list[_Item] = []
    segment: list[_Item] = []
    for item in sorted(items, key=lambda entry: (entry.y0, entry.x0)):
        if item.x1 - item.x0 >= _FULL_WIDTH_SHARE * text_width:
            ordered.extend(_in_columns(segment))
            ordered.append(item)
            segment = []
        else:
            segment.append(item)
    ordered.extend(_in_columns(segment))
    return ordered


def _page_text(page: pymupdf.Page) -> str:
    turn = _quarter_turn(page)
    if turn:
        return _rotated_page_text(page, turn)
    tables = _tables(page, page.get_text("words"))
    items = _page_lines(page, [box for box, _ in tables])
    base = len(items)
    for offset, (box, text) in enumerate(tables):
        items.append(_Item(box.x0, box.y0, box.x1, box.y1, text, base + offset))
    return "\n".join(item.text for item in _reading_order(items)).strip()


def load_pdf_pages(path: str | Path) -> list[str]:
    """Return one text string per PDF page: column-ordered text with header-carrying tables."""
    with pymupdf.open(path) as document:
        return [_page_text(page) for page in document]
