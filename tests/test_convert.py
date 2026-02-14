from pathlib import Path
from tempfile import TemporaryDirectory

from hatena_sync.converters import (
    asin_to_kindle_link,
    build_asin_to_kindle_map,
    hatena_to_markdown,
)


def test_hatena_to_markdown_headings():
    src = "* Heading\n** Sub\n*** SubSub"
    expected = "# Heading\n## Sub\n### SubSub"
    assert hatena_to_markdown(src) == expected


def test_hatena_to_markdown_formatting_and_links():
    src = "This is ''italic'' and '''bold''' [https://example.com:title=Example]"
    expected = "This is *italic* and **bold** [Example](https://example.com)"
    assert hatena_to_markdown(src) == expected


def test_build_asin_to_kindle_map():
    with TemporaryDirectory() as tmpdir:
        kindle_dir = Path(tmpdir)
        # テスト用のKindleハイライトファイルを作成
        test_file = kindle_dir / "テスト本.md"
        test_file.write_text(
            "---\n"
            "kindle-sync:\n"
            "  bookId: '12345'\n"
            "  title: テスト本\n"
            "  asin: B0TEST1234\n"
            "---\n"
            "# テスト本\n"
        )
        result = build_asin_to_kindle_map(kindle_dir)
        assert result == {"B0TEST1234": "テスト本.md"}


def test_build_asin_to_kindle_map_empty_dir():
    with TemporaryDirectory() as tmpdir:
        kindle_dir = Path(tmpdir)
        result = build_asin_to_kindle_map(kindle_dir)
        assert result == {}


def test_build_asin_to_kindle_map_nonexistent_dir():
    result = build_asin_to_kindle_map(Path("/nonexistent/dir"))
    assert result == {}


def test_asin_to_kindle_link_with_match():
    asin_map = {"B0G13D2JS4": "AI駆動開発入門.md"}
    content = "この本がおすすめです [asin:B0G13D2JS4:detail]"
    expected = "この本がおすすめです 『[[AI駆動開発入門]]』"
    assert asin_to_kindle_link(content, asin_map) == expected


def test_asin_to_kindle_link_without_match():
    asin_map = {"B0G13D2JS4": "Claude CodeによるAI駆動開発入門.md"}
    content = "この本 [asin:B0UNKNOWN:detail] は見つからない"
    assert asin_to_kindle_link(content, asin_map) == content


def test_asin_to_kindle_link_multiple():
    asin_map = {
        "B0ASIN0001": "本1.md",
        "B0ASIN0002": "本2.md",
    }
    content = "[asin:B0ASIN0001:detail] と [asin:B0ASIN0002:detail]"
    expected = "『[[本1]]』 と 『[[本2]]』"
    assert asin_to_kindle_link(content, asin_map) == expected


def test_asin_to_kindle_link_various_formats():
    asin_map = {"B0TEST1234": "テスト.md"}
    # detail以外のフォーマットもサポート
    assert asin_to_kindle_link("[asin:B0TEST1234:image]", asin_map) == "『[[テスト]]』"
    assert asin_to_kindle_link("[asin:B0TEST1234:title]", asin_map) == "『[[テスト]]』"
