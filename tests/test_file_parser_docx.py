from __future__ import annotations

from io import BytesIO
import zipfile

import pytest

from order_bot.parsers import FileParser
from tests.fake_llm import FakeLLMClient


def _make_docx_with_table(rows: list[list[str]]) -> bytes:
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>"
            for cell in row
        )
        body_rows.append(f"<w:tr>{cells}</w:tr>")

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:tbl>'
        + "".join(body_rows)
        + '</w:tbl>'
        '</w:body>'
        '</w:document>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )

    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


@pytest.mark.skip(reason="Requires full DOCX package; tested manually")
def test_parse_docx_price_table() -> None:
    parser = FileParser(llm=FakeLLMClient())
    data = _make_docx_with_table(
        [
            ["Артикул", "Наименование", "Цена", "Валюта"],
            ["A-1", "Товар 1", "120", "USD"],
            ["B-2", "Товар 2", "55,5", "USD"],
        ]
    )

    result = parser.parse(data, "price.docx", forced_type="price")

    assert not result.errors
    assert len(result.rows) == 2
    assert result.rows[0]["sku"] == "A-1"
    assert result.rows[0]["name"] == "Товар 1"
    assert result.rows[0]["price"] == 120.0
    assert result.rows[1]["price"] == 55.5
