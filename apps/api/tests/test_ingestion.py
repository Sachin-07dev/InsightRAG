"""Synthetic Phase 4 extraction, chunking, validation and vector contract tests."""

import io
from decimal import Decimal

import httpx
import pymupdf as fitz
import pytest
from docx import Document
from insightrag.ingestion.chunking import chunk_segments
from insightrag.ingestion.embeddings import (
    EmbeddingUnavailable,
    OpenAICompatibleEmbedder,
    validate_vectors,
)
from insightrag.ingestion.parsers import (
    ParsedDataset,
    ParsedDocument,
    ParseRejected,
    parse,
)
from insightrag.security.uploads import UploadRejected, validate_upload
from openpyxl import Workbook


def test_pdf_page_locator_and_extractable_text():
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Revenue fell in Delhi")
    parsed = parse(pdf.tobytes(), ".pdf")
    assert isinstance(parsed, ParsedDocument)
    assert parsed.metadata["page_count"] == "1"
    assert parsed.segments[0].locator.startswith("page:1:block:")
    assert "Revenue fell" in parsed.segments[0].text


def test_scanned_pdf_requires_explicit_ocr():
    pdf = fitz.open()
    pdf.new_page()
    with pytest.raises(ParseRejected, match="OCR required"):
        parse(pdf.tobytes(), ".pdf", ocr=False)


def test_docx_heading_and_table_locators():
    doc = Document()
    doc.add_heading("Quarterly review", 1)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "region"
    table.cell(0, 1).text = "sales"
    table.cell(1, 0).text = "Delhi"
    table.cell(1, 1).text = "100.10"
    buffer = io.BytesIO()
    doc.save(buffer)
    parsed = parse(buffer.getvalue(), ".docx")
    assert isinstance(parsed, ParsedDocument)
    assert parsed.segments[0].heading == "Quarterly review"
    assert parsed.segments[1].kind == "table"
    assert "Delhi" in parsed.segments[1].text
    assert parsed.segments[1].locator.startswith("table:")


def test_chunk_budget_heading_and_complete_text():
    from insightrag.ingestion.parsers import Segment

    segments = (
        Segment("Financials", "line:1", "Financials", "heading"),
        Segment("Delhi revenue " * 300, "line:2"),
    )
    chunks = chunk_segments(segments, max_tokens=64, overlap=8)
    assert len(chunks) > 2
    assert all(chunk.token_count <= 64 and chunk.locator.startswith("line:") for chunk in chunks)
    assert all(chunk.heading == "Financials" for chunk in chunks)
    assert "Delhi revenue" in " ".join(chunk.text for chunk in chunks)


def test_csv_xlsx_are_structured_and_numeric_values_remain_traceable():
    csv_data = parse(b"region,net_sales\nDelhi,100.10\nMumbai,200.20\n", ".csv")
    assert isinstance(csv_data, ParsedDataset)
    assert sum(Decimal(str(row["net_sales"])) for row in csv_data.rows) == Decimal("300.30")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["region", "net_sales"])
    sheet.append(["Delhi", 100.1])
    buffer = io.BytesIO()
    workbook.save(buffer)
    xlsx_data = parse(buffer.getvalue(), ".xlsx")
    assert isinstance(xlsx_data, ParsedDataset)
    assert xlsx_data.rows[0]["region"] == "Delhi"
    assert xlsx_data.locator_prefix.startswith("sheet:")


def test_dataset_duplicate_header_and_empty_text_fail():
    with pytest.raises(ParseRejected, match="duplicate"):
        parse(b"region,region\nDelhi,Delhi\n", ".csv")
    assert isinstance(parse(b"\n  \n", ".txt"), ParsedDocument)


def test_embedding_dimension_and_nan_rejected():
    validate_vectors([[1.0] + [0.0] * 1535], 1, 1536)
    with pytest.raises(EmbeddingUnavailable):
        validate_vectors([[1.0, 0.0]], 1, 1536)
    with pytest.raises(EmbeddingUnavailable):
        validate_vectors([[0.0] * 1536], 1, 1536)


class CleanScanner:
    async def scan(self, data: bytes) -> str:
        return "clean"


async def stream(data: bytes):
    yield data


@pytest.mark.anyio
async def test_upload_validation_keeps_exact_scanned_bytes_and_hash():
    result = await validate_upload(
        stream(b"region,net_sales\nDelhi,100.10\n"),
        filename="sales.csv",
        content_type="text/csv",
        scanner=CleanScanner(),
    )
    assert result.data == b"region,net_sales\nDelhi,100.10\n"
    assert len(result.sha256) == 64
    with pytest.raises(UploadRejected):
        await validate_upload(
            stream(b"bad"),
            filename="archive.exe",
            content_type="application/octet-stream",
            scanner=CleanScanner(),
        )


@pytest.mark.anyio
async def test_embedding_provider_rejects_duplicate_indices(monkeypatch):
    client_type = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        def respond(request):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 0, "embedding": [1.0] + [0.0] * 1535},
                        {"index": 0, "embedding": [1.0] + [0.0] * 1535},
                    ]
                },
            )

        return client_type(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    provider = OpenAICompatibleEmbedder(
        endpoint="https://embeddings.synthetic.invalid",
        api_key="synthetic",
        model_id="synthetic-1536",
    )
    with pytest.raises(EmbeddingUnavailable):
        await provider.embed(["one", "two"])
