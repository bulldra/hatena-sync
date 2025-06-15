from hatena_sync.converters import hatena_to_markdown


def test_hatena_to_markdown_headings():
    src = "* Heading\n** Sub\n*** SubSub"
    expected = "# Heading\n## Sub\n### SubSub"
    assert hatena_to_markdown(src) == expected


def test_hatena_to_markdown_formatting_and_links():
    src = "This is ''italic'' and '''bold''' [https://example.com:title=Example]"
    expected = "This is *italic* and **bold** [Example](https://example.com)"
    assert hatena_to_markdown(src) == expected
