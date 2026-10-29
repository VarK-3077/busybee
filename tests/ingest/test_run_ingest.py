"""End-to-end tests for run_ingest and the corpus store round trip."""

import json
from pathlib import Path

from busybee.ingest.corpus_store import load_corpus
from busybee.ingest.run_ingest import run_ingest
from busybee.schema.documents import DocumentKind
from busybee.schema.ids import make_chunk_id


async def test_manifest_overrides_kind_and_title(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "news_story.md").write_text("# Story\n\nCompany reported results.\n", encoding="utf-8")
    (docs / "annual_report.md").write_text(
        "# Annual Report\n\nChairman message.\n", encoding="utf-8"
    )
    (docs / "manifest.json").write_text(
        json.dumps({"news_story.md": {"title": "Custom Title", "kind": "covenant"}}),
        encoding="utf-8",
    )

    documents = await run_ingest(docs, tmp_path / "workspace")
    by_name = {Path(document.source_path).name: document for document in documents}
    assert by_name["news_story.md"].title == "Custom Title"
    assert by_name["news_story.md"].kind is DocumentKind.covenant
    assert by_name["annual_report.md"].kind is DocumentKind.annual_report
    assert by_name["annual_report.md"].title == "annual_report"
    assert by_name["annual_report.md"].doc_id == "D1"
    assert by_name["news_story.md"].doc_id == "D2"


async def test_document_ids_are_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for name in ["news_b.md", "news_a.md"]:
        (first / name).write_text("# News\n\nCompany reported results.\n", encoding="utf-8")
    for name in ["news_a.md", "news_b.md"]:
        (second / name).write_text("# News\n\nCompany reported results.\n", encoding="utf-8")

    first_documents = await run_ingest(first, tmp_path / "workspace-first")
    second_documents = await run_ingest(second, tmp_path / "workspace-second")
    first_ids = [(Path(d.source_path).name, d.doc_id) for d in first_documents]
    second_ids = [(Path(d.source_path).name, d.doc_id) for d in second_documents]
    assert first_ids == second_ids == [("news_a.md", "D1"), ("news_b.md", "D2")]


async def test_chunks_stay_on_their_page_with_exact_offsets(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    first_page = "Alpha sentinel. " + " ".join(
        f"First page sentence {number} has some words." for number in range(50)
    )
    second_page = "Beta sentinel. " + " ".join(
        f"Second page sentence {number} has some words." for number in range(50)
    )
    (docs / "long_report.md").write_text(
        f"{first_page}\n\n<!-- page -->\n\n{second_page}", encoding="utf-8"
    )

    documents = await run_ingest(docs, tmp_path / "workspace")
    assert len(documents) == 1
    document = documents[0]
    assert document.num_pages == 2

    corpus = load_corpus(tmp_path / "workspace")
    assert corpus.documents == documents
    assert corpus.chunks
    for chunk in corpus.chunks:
        page = corpus.page(chunk.doc_id, chunk.page_no)
        assert page is not None
        assert page.text[chunk.char_start : chunk.char_end] == chunk.text
        assert chunk.chunk_id == make_chunk_id(chunk.doc_id, chunk.page_no, chunk.index_in_page)
        if chunk.page_no == 1:
            assert "Beta sentinel" not in chunk.text
        else:
            assert "Alpha sentinel" not in chunk.text


async def test_corpus_store_round_trip(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "annual_report.md").write_text(
        "# Annual Report\n\nChairman message.\n\n<!-- page -->\n\nRevenue was 100 crore.",
        encoding="utf-8",
    )

    documents = await run_ingest(docs, tmp_path / "workspace")
    corpus_dir = tmp_path / "workspace" / "corpus"
    assert (corpus_dir / "documents.json").exists()
    assert (corpus_dir / "pages" / "D1.jsonl").exists()
    assert (corpus_dir / "chunks.jsonl").exists()

    corpus = load_corpus(tmp_path / "workspace")
    assert corpus.documents == documents
    assert [page.page_no for page in corpus.pages("D1")] == [1, 2]
    assert corpus.page("D1", 2).text == "Revenue was 100 crore."
    assert corpus.page("D1", 99) is None
    for chunk in corpus.chunks:
        assert corpus.chunks_by_id[chunk.chunk_id] == chunk
