from types import SimpleNamespace

from hatena_sync import is_markdown_entry


def make_entry(syntax=None, content_type="text/x-hatena-syntax"):
    content = [{"type": content_type, "value": "body"}]
    entry = SimpleNamespace(content=content)
    if syntax is not None:
        setattr(entry, "hatena_syntax", syntax)
    return entry


def test_is_markdown_entry_via_syntax():
    entry = make_entry(syntax="markdown")
    assert is_markdown_entry(entry)


def test_is_markdown_entry_via_content_type():
    entry = make_entry(content_type="text/x-markdown")
    assert is_markdown_entry(entry)


def test_is_markdown_entry_false():
    entry = make_entry(syntax="hatena")
    assert not is_markdown_entry(entry)
