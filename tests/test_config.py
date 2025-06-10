import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from hatena_sync import load_config


def test_load_config(tmp_path):
    data = {
        "username": "u",
        "blog_id": "b",
        "api_key": "k",
        "local_dir": "posts",
    }
    conf_path = tmp_path / "conf.json"
    conf_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_config(str(conf_path))
    assert loaded == data
