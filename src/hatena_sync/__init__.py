from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import feedparser
import requests
from tqdm import tqdm

HATENA_ATOM_URL = "https://blog.hatena.ne.jp/{user}/{blog}/atom/entry"


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        conf = json.load(fh)
    required = {"username", "blog_id", "api_key"}
    missing = required - conf.keys()
    if missing:
        raise click.ClickException(
            f"Missing keys in config: {', '.join(sorted(missing))}"
        )
    return conf


def wsse_header(username: str, api_key: str) -> dict[str, str]:
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha1(
        nonce + created.encode("utf-8") + api_key.encode("utf-8")
    ).digest()
    password_digest = base64.b64encode(digest).decode("utf-8")
    nonce_b64 = base64.b64encode(nonce).decode("utf-8")
    wsse = (
        f'UsernameToken Username="{username}", '
        f'PasswordDigest="{password_digest}", '
        f'Nonce="{nonce_b64}", '
        f'Created="{created}"'
    )
    return {"X-WSSE": wsse}


def iter_remote_entries(conf: dict[str, Any]):
    user = conf["username"]
    blog = conf["blog_id"]
    api_key = conf["api_key"]
    url: str | None = HATENA_ATOM_URL.format(user=user, blog=blog)
    headers = wsse_header(user, api_key)
    seen_ids = set()
    while url:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            entry_id = getattr(entry, "id", None)
            # 下書き判定: hatena:unlisted, app:control, app:draft など
            is_draft = False
            if hasattr(entry, "hatena_unlisted") and entry.hatena_unlisted == "yes":
                is_draft = True
            if hasattr(entry, "app_draft") and entry.app_draft == "yes":
                is_draft = True
            if (
                hasattr(entry, "app_control")
                and hasattr(entry.app_control, "draft")
                and entry.app_control.draft == "yes"
            ):
                is_draft = True
            if is_draft:
                continue
            if entry_id and entry_id in seen_ids:
                continue
            if entry_id:
                seen_ids.add(entry_id)

            yield entry
        next_url = None
        for link in feed.feed.get("links", []):
            if link.get("rel") == "next":
                next_url = link.get("href")
                break
        if not feed.entries or next_url is None:
            break
        url = next_url  # type: ignore


def pull(conf: dict[str, Any]) -> None:
    local_dir = Path(conf.get("local_dir", "posts"))
    local_dir.mkdir(parents=True, exist_ok=True)
    remote_ids = set()
    with tqdm(total=None, desc="pull entries", unit="entry") as bar:
        for entry in iter_remote_entries(conf):
            updated = datetime(*entry.updated_parsed[:6]).strftime("%Y%m%d%H%M%S")
            title = entry.title.strip().replace("/", "_")
            filename = local_dir / f"{updated}-{title}.md"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(entry.content[0].value)
            remote_ids.add(filename)
            bar.update(1)
    for file in local_dir.glob("*.md"):
        if file not in remote_ids:
            file.unlink()


def push(conf: dict[str, Any]) -> None:
    """Placeholder for pushing local changes back to Hatena Blog."""
    click.echo("push is not implemented yet")


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.json",
    show_default=True,
    help="Path to configuration file",
)
@click.option(
    "--direction",
    type=click.Choice(["pull", "push", "both"]),
    default="both",
    show_default=True,
    help="Sync direction",
)
def sync(config_path: str, direction: str) -> None:
    """Synchronize entries between local files and Hatena Blog."""
    conf = load_config(config_path)
    if direction in ("pull", "both"):
        pull(conf)
    if direction in ("push", "both"):
        push(conf)


if __name__ == "__main__":
    cli()
