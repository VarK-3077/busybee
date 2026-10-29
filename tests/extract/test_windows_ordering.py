"""Tests for token-bounded windows, chunk rendering, and document ordering."""

from busybee.extract.ordering import order_documents
from busybee.extract.windows import make_windows, window_text
from busybee.llm import count_tokens
from busybee.schema.documents import Chunk, Document, DocumentKind


def chunk(chunk_id: str, text: str, page_no: int = 1, index: int = 0) -> Chunk:
    doc_id = chunk_id.split(":")[0]
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        page_no=page_no,
        index_in_page=index,
        text=text,
    )


def words(prefix: str, count: int = 12) -> str:
    return " ".join(f"{prefix}{number}" for number in range(count))


def test_windows_respect_the_token_budget_and_never_split_a_chunk() -> None:
    chunks = [
        chunk("D1:p1:c0", words("alpha")),
        chunk("D1:p1:c1", words("beta")),
        chunk("D1:p2:c0", words("gamma")),
    ]
    sizes = [count_tokens(item.text) for item in chunks]
    windows = make_windows(chunks, sizes[0] + sizes[1])

    assert windows == [[chunks[0], chunks[1]], [chunks[2]]]
    assert [item.chunk_id for window in windows for item in window] == [
        "D1:p1:c0",
        "D1:p1:c1",
        "D1:p2:c0",
    ]


def test_an_oversized_chunk_becomes_its_own_window() -> None:
    chunks = [chunk("D1:p1:c0", words("big", 30)), chunk("D1:p1:c1", words("small", 2))]
    windows = make_windows(chunks, count_tokens(chunks[1].text))

    assert windows == [[chunks[0]], [chunks[1]]]


def test_empty_chunks_make_no_windows() -> None:
    assert make_windows([], 100) == []


def test_window_text_prefixes_every_chunk_with_its_id() -> None:
    chunks = [chunk("D1:p12:c3", "Revenue was 100 crore."), chunk("D1:p12:c4", "Cash was 20.")]

    text = window_text(chunks)

    assert text == "[D1:p12:c3]\nRevenue was 100 crore.\n\n[D1:p12:c4]\nCash was 20."


def test_documents_are_ordered_by_kind_priority_then_name() -> None:
    documents = [
        Document(doc_id="D1", title="Story", kind=DocumentKind.news, source_path="/x/news.md"),
        Document(
            doc_id="D2",
            title="Accounts",
            kind=DocumentKind.financial_statements,
            source_path="/x/accounts.md",
        ),
        Document(
            doc_id="D3",
            title="Report",
            kind=DocumentKind.annual_report,
            source_path="/x/annual.md",
        ),
        Document(
            doc_id="D4",
            title="Another news",
            kind=DocumentKind.news,
            source_path="/x/another_news.md",
        ),
    ]

    ordered = order_documents(documents)

    assert [document.doc_id for document in ordered] == ["D2", "D3", "D4", "D1"]


def test_window_text_shows_the_table_prefix() -> None:
    split = chunk("D1:p1:c1", "Revenue | 100")
    split.prefix = "[TABLE: item | crore]"
    assert "[TABLE: item | crore]\nRevenue | 100" in window_text([split])
