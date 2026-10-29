"""Section headings of table rows: path lookup on a real Indoco balance sheet page, statements."""

import json
from decimal import Decimal
from pathlib import Path

from busybee.extract.notebook import add_entries
from busybee.extract.prompts import RecordDraft
from busybee.extract.sections import record_section, section_phrase
from busybee.extract.templates import statement_from_record
from busybee.schema.documents import Chunk
from busybee.schema.facts import FactRecord, FactScope

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_balance_sheet_chunks.json"
CHUNKS = {item["chunk_id"]: Chunk(**item) for item in json.loads(FIXTURE.read_text())}


def test_same_label_gets_the_heading_it_sits_under() -> None:
    non_current = record_section("Investments", Decimal("15974.92"), ["D1:p187:c0"], CHUNKS)
    assert non_current == "Non Current Assets > Financial Assets"
    receivables = record_section("Trade Receivables", Decimal("54120.19"), ["D1:p187:c1"], CHUNKS)
    assert receivables == "Current Assets > Financial Assets"


def test_closing_a_lettered_group_drops_the_second_level() -> None:
    assert (
        record_section("Other Non Current Assets", Decimal("9654.48"), ["D1:p187:c0"], CHUNKS)
        == "Non Current Assets"
    )
    assert (
        record_section("Inventories", Decimal("32183.42"), ["D1:p187:c0"], CHUNKS)
        == "Current Assets"
    )


def test_unknown_row_or_chunk_has_no_section() -> None:
    assert record_section("Goodwill", Decimal(1), ["D1:p187:c0"], CHUNKS) is None
    assert record_section("Investments", Decimal(1), ["nope"], CHUNKS) is None


def test_statement_names_current_or_non_current() -> None:
    record = FactRecord(
        metric="Investments",
        value=Decimal("15974.92"),
        unit="lakh",
        period="March 31, 2026",
        scope=FactScope.standalone,
        section="Non Current Assets > Financial Assets",
    )
    assert statement_from_record(record).startswith("Standalone non-current investments was INR")
    assert section_phrase("Current Assets > Financial Assets") == "current"
    assert section_phrase("Revenue") == ""
    plain = record.model_copy(update={"section": None, "scope": None})
    assert statement_from_record(plain).startswith("Investments was")


def test_add_entries_records_the_section_and_writes_it_in_the_statement() -> None:
    draft = RecordDraft(
        m="Investments",
        v="15,974.92",
        u="lakh",
        p="March 31, 2026",
        sc="standalone",
        c=["D1:p187:c0"],
    )
    kept, dropped = add_entries([draft], doc_id="D1", window_no=1, chunks_by_id=CHUNKS)
    assert not dropped
    assert kept[0].record is not None
    assert kept[0].record.section == "Non Current Assets > Financial Assets"
    assert kept[0].statement.startswith("Standalone non-current investments was")
