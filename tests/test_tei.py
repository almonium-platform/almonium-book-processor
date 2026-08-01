from __future__ import annotations

import pytest
from defusedxml.common import DefusedXmlException

from almonium_book_processor.ingest.source import ingest_source
from almonium_book_processor.ingest.tei import ingest_tei
from almonium_book_processor.models import BlockType

TEI_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="ENG-TEST" xml:lang="en">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>A TEI Novel</title>
        <author>Ada Author</author>
      </titleStmt>
      <publicationStmt><p>Test edition</p></publicationStmt>
      <sourceDesc><p>Test source</p></sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <front>
      <div type="titlepage"><p>Title page</p></div>
    </front>
    <body>
      <div type="group">
        <head>Volume I</head>
        <div type="chapter" xml:id="chapter-one">
          <head>Chapter One</head>
          <p>First <hi>important</hi> paragraph.<pb/> Still the same paragraph.</p>
          <quote><l>A quoted line</l><l>And another</l><p>The Poet.</p></quote>
          <note xml:id="note-one">A note.</note>
        </div>
      </div>
    </body>
  </text>
</TEI>
"""


def test_tei_extracts_metadata_structure_and_semantic_blocks(tmp_path) -> None:
    source = tmp_path / "novel.xml"
    source.write_text(TEI_FIXTURE)

    artifact = ingest_tei(
        source,
        edition_slug="tei-novel-en-orig",
        work_slug="tei-novel",
    )

    assert artifact.edition.title == "A TEI Novel"
    assert artifact.edition.author == "Ada Author"
    assert artifact.edition.language == "en"
    assert artifact.edition.source.format == "tei"
    assert artifact.edition.source.identifier == "ENG-TEST"
    assert [block.chapter for block in artifact.blocks] == [0, 1, 2, 2, 2, 2, 2]
    assert [block.type for block in artifact.blocks] == [
        BlockType.PARAGRAPH,
        BlockType.HEADING,
        BlockType.HEADING,
        BlockType.PARAGRAPH,
        BlockType.VERSE_STANZA,
        BlockType.EPIGRAPH,
        BlockType.FOOTNOTE,
    ]
    assert artifact.blocks[3].text == "First important paragraph. Still the same paragraph."
    assert artifact.blocks[4].text == "A quoted line\nAnd another"
    assert artifact.blocks[5].text == "The Poet."
    assert artifact.blocks[5].attributes["role"] == "attribution"
    assert artifact.blocks[6].source_ref == "novel.xml#note-one"


def test_xml_dispatches_to_tei_adapter(tmp_path) -> None:
    source = tmp_path / "novel.xml"
    source.write_text(TEI_FIXTURE)

    artifact = ingest_source(
        source,
        edition_slug="tei-novel-en-orig",
        work_slug="tei-novel",
    )

    assert artifact.edition.source.format == "tei"


def test_tei_rejects_entity_expansion(tmp_path) -> None:
    source = tmp_path / "unsafe.xml"
    source.write_text(
        """<?xml version="1.0"?>
        <!DOCTYPE data [<!ENTITY payload "unsafe">]>
        <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>&payload;</p></body></text></TEI>
        """
    )

    with pytest.raises(DefusedXmlException):
        ingest_tei(source, edition_slug="unsafe-en-orig", work_slug="unsafe")
