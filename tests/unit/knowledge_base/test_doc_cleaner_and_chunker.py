from __future__ import annotations

from archoptimize.knowledge_base.doc_chunker import CHUNK_CHARS, chunk_pages
from archoptimize.knowledge_base.doc_cleaner import PageText, clean_pages
from archoptimize.knowledge_base.knowledge_sources import KnowledgeSource, load_sources
from archoptimize.schemas import Pillar

HEADER = "Reliability Pillar AWS Well-Architected Framework"
BODY = "Deploy the workload to multiple Availability Zones so that a failure is contained. " * 5


def raw_page(body: str, number: int) -> str:
    return f"{HEADER}\n{body}\n{number}"


def test_removes_repeated_headers_page_numbers_and_toc_lines():
    # each page has its own body text; only the header repeats
    raw = [raw_page(f"Topic {n}. {BODY}", n) for n in range(1, 8)]
    raw[0] = f"{HEADER}\nIntroduction ........................ 3\nTopic 1. {BODY}\n1"
    pages = clean_pages(raw)
    assert len(pages) == 7
    assert all(HEADER not in p.text for p in pages)
    assert "......" not in pages[0].text
    assert not pages[0].text.rstrip().endswith("1")


def test_text_repeated_on_most_pages_is_treated_as_boilerplate():
    # documents what the header remover does with identical lines on every page
    assert clean_pages([raw_page(BODY, n) for n in range(1, 8)]) == []


def test_fixes_ligatures_and_line_break_hyphens():
    body = "Cost eﬃcient designs avoid diﬀerent over-\nprovisioning. " * 6
    text = clean_pages([body])[0].text
    assert "efficient" in text and "different" in text
    assert "overprovisioning" in text


def test_skips_nearly_empty_pages_but_keeps_page_numbers():
    pages = clean_pages(["Cover", BODY, "", BODY])
    assert [p.page for p in pages] == [2, 4]


def test_chunks_have_ids_metadata_and_bounded_size():
    source = KnowledgeSource(
        id_prefix="rel", pillar=Pillar.RELIABILITY, title="Rel", url="https://x/rel.pdf"
    )
    pages = [PageText(page=5, text=BODY * 10), PageText(page=6, text=BODY)]
    chunks = chunk_pages(source, pages)
    assert chunks[0].chunk_id == "rel-0000"
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(len(c.text) <= CHUNK_CHARS for c in chunks)
    assert chunks[-1].page == 6 and chunks[-1].url == "https://x/rel.pdf#page=6"
    assert all(c.pillar is Pillar.RELIABILITY for c in chunks)


def test_source_list_is_valid():
    sources = load_sources()
    assert {s.pillar for s in sources} >= {
        Pillar.SECURITY,
        Pillar.RELIABILITY,
        Pillar.COST_OPTIMIZATION,
        Pillar.PERFORMANCE_EFFICIENCY,
        Pillar.COMPLIANCE,
    }
