"""Bounded parsers with real source locators and explicit OCR failure."""

import csv
import io
import itertools
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import pymupdf as fitz
from docx import Document
from openpyxl import load_workbook  # type: ignore[import-untyped]


class ParseRejected(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    text: str
    locator: str
    heading: str | None = None
    kind: Literal["paragraph", "heading", "table"] = "paragraph"


@dataclass(frozen=True)
class ParsedDocument:
    segments: tuple[Segment, ...]
    metadata: dict[str, str]


@dataclass(frozen=True)
class ParsedDataset:
    columns: tuple[str, ...]
    rows: tuple[dict[str, str | int | float | None], ...]
    locator_prefix: str


def _safe_text(value: object) -> str:
    return str(value).strip().replace("\x00", "")[:20000]


def parse_pdf(data: bytes, *, ocr: bool = False, max_pages: int = 500) -> ParsedDocument:
    try:
        doc = fitz.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
        if doc.is_encrypted or doc.page_count > max_pages:
            raise ParseRejected("Encrypted or oversized PDF")
        segments: list[Segment] = []
        for page_index in range(doc.page_count):
            page = doc[page_index]
            blocks = page.get_text("blocks", sort=True)  # type: ignore[no-untyped-call]
            text_blocks = [
                str(block[4]).strip()
                for block in blocks
                if len(block) > 4 and str(block[4]).strip()
            ]
            if not text_blocks and ocr:
                try:
                    textpage = page.get_textpage_ocr(  # type: ignore[no-untyped-call]
                        language="eng", dpi=150, full=True
                    )
                    text_blocks = [
                        page.get_text("text", textpage=textpage).strip()  # type: ignore[no-untyped-call]
                    ]
                except Exception:
                    raise ParseRejected("OCR unavailable or failed") from None
            if not text_blocks:
                raise ParseRejected(f"No text on PDF page {page_index + 1}; OCR required")
            for block_index, block in enumerate(text_blocks, 1):
                if block:
                    segments.append(Segment(block, f"page:{page_index + 1}:block:{block_index}"))
        return ParsedDocument(tuple(segments), {"page_count": str(doc.page_count)})
    except ParseRejected:
        raise
    except Exception:
        raise ParseRejected("Invalid PDF") from None


def parse_docx(data: bytes) -> ParsedDocument:
    try:
        doc = Document(io.BytesIO(data))
        segments: list[Segment] = []
        for index, block in enumerate(doc.element.body):
            if block.tag.endswith("}p"):
                from docx.text.paragraph import Paragraph

                paragraph = Paragraph(block, doc)
                value = paragraph.text.strip()
                if value:
                    heading = (
                        value
                        if paragraph.style and paragraph.style.name.startswith("Heading")
                        else None
                    )
                    segments.append(
                        Segment(
                            value,
                            f"body:{index + 1}",
                            heading,
                            "heading" if heading else "paragraph",
                        )
                    )
            elif block.tag.endswith("}tbl"):
                from docx.table import Table

                table = Table(block, doc)
                value = "\n".join("\t".join(cell.text for cell in row.cells) for row in table.rows)
                if value:
                    segments.append(Segment(value, f"table:{index + 1}", kind="table"))
        return ParsedDocument(tuple(segments), {"paragraph_or_table_count": str(len(segments))})
    except Exception:
        raise ParseRejected("Invalid DOCX") from None


def parse_txt(data: bytes) -> ParsedDocument:
    try:
        value = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseRejected("TXT must be UTF-8") from None
    segments = [
        Segment(line.strip(), f"line:{index}")
        for index, line in enumerate(value.splitlines(), 1)
        if line.strip()
    ]
    return ParsedDocument(tuple(segments), {"line_count": str(len(value.splitlines()))})


def _scalar(value: object) -> str | int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return _safe_text(value)


def _dataset(rows: list[list[object]], prefix: str, *, max_rows: int) -> ParsedDataset:
    if not rows or not rows[0]:
        raise ParseRejected("Dataset has no header")
    columns = tuple(_safe_text(cell) for cell in rows[0])
    if (
        len(columns) > 100
        or any(not column for column in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ParseRejected("Invalid or duplicate dataset columns")
    if len(rows) - 1 > max_rows:
        raise ParseRejected("Dataset row limit exceeded")
    values: list[dict[str, str | int | float | None]] = []
    for row in rows[1:]:
        if len(row) != len(columns):
            raise ParseRejected("Ragged dataset row")
        values.append(dict(zip(columns, (_scalar(value) for value in row), strict=True)))
    return ParsedDataset(columns, tuple(values), prefix)


def parse_csv(data: bytes, *, max_rows: int = 100000) -> ParsedDataset:
    try:
        content = data.decode("utf-8-sig")
        rows: list[list[object]] = [
            list(row)
            for row in itertools.islice(csv.reader(io.StringIO(content, newline="")), max_rows + 2)
        ]
        return _dataset(rows, "csv:row", max_rows=max_rows)
    except ParseRejected:
        raise
    except (UnicodeDecodeError, csv.Error):
        raise ParseRejected("Invalid UTF-8 CSV") from None


def parse_xlsx(data: bytes, *, max_rows: int = 100000) -> ParsedDataset:
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        if len(workbook.worksheets) != 1:
            raise ParseRejected("XLSX must contain exactly one data sheet")
        sheet = workbook.worksheets[0]
        rows = [
            list(row) for row in itertools.islice(sheet.iter_rows(values_only=True), max_rows + 2)
        ]
        return _dataset(rows, f"sheet:{sheet.title}:row", max_rows=max_rows)
    except ParseRejected:
        raise
    except Exception:
        raise ParseRejected("Invalid XLSX") from None


def parse(data: bytes, suffix: str, *, ocr: bool = False) -> ParsedDocument | ParsedDataset:
    if suffix == ".pdf":
        return parse_pdf(data, ocr=ocr)
    if suffix == ".docx":
        return parse_docx(data)
    if suffix == ".txt":
        return parse_txt(data)
    if suffix == ".csv":
        return parse_csv(data)
    if suffix == ".xlsx":
        return parse_xlsx(data)
    raise ParseRejected("Unsupported parser type")
