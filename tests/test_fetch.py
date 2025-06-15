from unittest.mock import patch

from hatena_sync import fetch_remote_entries

PAGE1 = """<?xml version='1.0' encoding='utf-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <link rel='next' href='http://example.com/next'/>
  <entry>
    <id>1</id>
    <updated>2020-01-01T00:00:00Z</updated>
    <title>post1</title>
    <content type='text/plain'>body1</content>
  </entry>
</feed>
"""

PAGE2 = """<?xml version='1.0' encoding='utf-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <entry>
    <id>2</id>
    <updated>2020-01-02T00:00:00Z</updated>
    <title>post2</title>
    <content type='text/plain'>body2</content>
  </entry>
</feed>
"""


class Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_remote_entries():
    conf = {"username": "", "blog_id": "b", "api_key": "k"}
    with patch("hatena_sync.requests.get", side_effect=[Resp(PAGE1), Resp(PAGE2)]) as m:
        entries = list(fetch_remote_entries(conf))
    assert len(entries) == 2
    assert m.call_count == 2
