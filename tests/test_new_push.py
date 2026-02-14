"""new/pushコマンドおよびリンク変換のテスト"""

import tempfile
from pathlib import Path

from click.testing import CliRunner

from hatena_sync import build_yaml_frontmatter, cli, parse_yaml_frontmatter
from hatena_sync.converters import obsidian_to_hatena_link


class TestObsidianToHatenaLink:
    def test_simple_link(self):
        content = "See [[2024-01-01-article.md]]"
        filename_to_url = {"2024-01-01-article.md": "https://example.com/entry/2024/01/01/article"}
        result = obsidian_to_hatena_link(content, filename_to_url)
        assert result == "See [2024-01-01-article.md](https://example.com/entry/2024/01/01/article)"

    def test_link_with_title(self):
        content = "See [[2024-01-01-article.md|My Article]]"
        filename_to_url = {"2024-01-01-article.md": "https://example.com/entry/2024/01/01/article"}
        result = obsidian_to_hatena_link(content, filename_to_url)
        assert result == "See [My Article](https://example.com/entry/2024/01/01/article)"

    def test_link_without_extension(self):
        content = "See [[2024-01-01-article]]"
        filename_to_url = {"2024-01-01-article.md": "https://example.com/entry/2024/01/01/article"}
        result = obsidian_to_hatena_link(content, filename_to_url)
        assert result == "See [2024-01-01-article](https://example.com/entry/2024/01/01/article)"

    def test_unknown_link_unchanged(self):
        content = "See [[unknown-article.md]]"
        filename_to_url = {"2024-01-01-article.md": "https://example.com/entry/2024/01/01/article"}
        result = obsidian_to_hatena_link(content, filename_to_url)
        assert result == "See [[unknown-article.md]]"

    def test_multiple_links(self):
        content = "See [[a.md]] and [[b.md|Title B]]"
        filename_to_url = {
            "a.md": "https://example.com/a",
            "b.md": "https://example.com/b",
        }
        result = obsidian_to_hatena_link(content, filename_to_url)
        assert result == "See [a.md](https://example.com/a) and [Title B](https://example.com/b)"


class TestYamlFrontmatter:
    def test_parse_yaml(self):
        content = '''---
title: "Test Title"
date: 2024-01-01
tags: ['a', 'b']
status: draft
---

Body content here'''
        metadata, body = parse_yaml_frontmatter(content)
        assert metadata["title"] == "Test Title"
        assert metadata["date"] == "2024-01-01"
        assert metadata["status"] == "draft"
        assert body == "Body content here"

    def test_parse_no_yaml(self):
        content = "Just plain content"
        metadata, body = parse_yaml_frontmatter(content)
        assert metadata == {}
        assert body == "Just plain content"

    def test_build_yaml(self):
        metadata = {
            "title": "Test",
            "date": "2024-01-01",
            "tags": ["a", "b"],
            "status": "draft",
        }
        result = build_yaml_frontmatter(metadata)
        assert "---" in result
        assert 'title: "Test"' in result
        assert "date: 2024-01-01" in result
        assert "status: draft" in result


def make_config(tmpdir: str) -> str:
    """テスト用の設定JSONを生成"""
    return (
        '{"username":"test","blog_id":"test.hatenablog.com",'
        f'"api_key":"xxx","local_dir":"{tmpdir}"}}'
    )


class TestNewCommand:
    def test_new_creates_file(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(make_config(tmpdir))

            result = runner.invoke(
                cli, ["new", "2024-01-01-test", "-c", str(config_path)]
            )
            assert result.exit_code == 0

            feature_dir = Path(tmpdir) / "feature"
            assert feature_dir.exists()

            created_file = feature_dir / "2024-01-01-test.md"
            assert created_file.exists()

            content = created_file.read_text()
            assert "---" in content
            assert "title:" in content
            assert "status: draft" in content

    def test_new_file_already_exists(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(make_config(tmpdir))

            feature_dir = Path(tmpdir) / "feature"
            feature_dir.mkdir()
            existing_file = feature_dir / "existing.md"
            existing_file.write_text("content")

            result = runner.invoke(
                cli, ["new", "existing", "-c", str(config_path)]
            )
            assert result.exit_code != 0
            assert "既に存在します" in result.output
