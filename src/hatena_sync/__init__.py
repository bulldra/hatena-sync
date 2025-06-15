from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from functools import partial
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


def fetch_remote_entries(conf: dict[str, Any]):
    user = conf["username"]
    blog = conf["blog_id"]
    api_key = conf["api_key"]
    url: str = HATENA_ATOM_URL.format(user=user, blog=blog)
    headers = wsse_header(user, api_key)
    seen_ids = set()

    with tqdm(total=None, desc="fetch entries", unit="entry") as fetch_bar:
        while url:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            for entry in feed.entries:
                entry_id = getattr(entry, "id", None)
                if entry_id and entry_id in seen_ids:
                    continue
                if entry_id:
                    seen_ids.add(entry_id)
                fetch_bar.update(1)
                yield entry
            next_url = None
            for link in feed.feed.get("links", []):
                if link.get("rel") == "next":
                    next_url = link.get("href")
                    break
            if not feed.entries or next_url is None:
                break
            url = next_url


def is_entry_draft(entry: Any) -> bool:
    if hasattr(entry, "app_draft") and entry.app_draft == "yes":
        return True
    if (
        hasattr(entry, "app_control")
        and hasattr(entry.app_control, "draft")
        and entry.app_control.draft == "yes"
    ):
        return True
    return False


def make_entry_title(entry: Any) -> str:
    return entry.title.strip().replace("/", "_")


def url_to_obsidian_link(
    match: re.Match,
    entry_url_to_filename: dict[str, str],
    entry_url_to_title: dict[str, str],
) -> str:
    url = match.group("url")
    custom_title = match.group("custom_title")
    link_path = entry_url_to_filename.get(url)
    link_title = entry_url_to_title.get(url)
    if link_path:
        link_name = os.path.basename(link_path)
        if custom_title:
            return f"[{link_name}|{custom_title}]"
        if link_title:
            return f"[{link_name}|{link_title}]"
        return f"[{link_name}]"
    return match.group(0)


def make_entry_filename(entry: Any, out_dir: Path) -> Path:
    permalink = getattr(entry, "link", None)
    if permalink:
        parts = permalink.rstrip("/").split("/entry/")
        if len(parts) == 2:
            slug = parts[1].replace("/", "-")
            return out_dir / f"{slug}.md"
    title = make_entry_title(entry)
    return out_dir / f"{title}.md"


def pull(conf: dict[str, Any]) -> None:
    local_dir = Path(conf.get("local_dir", "posts"))
    published_dir = local_dir / "published"
    draft_dir = local_dir / "draft"
    published_dir.mkdir(parents=True, exist_ok=True)
    draft_dir.mkdir(parents=True, exist_ok=True)
    remote_ids_published: set[Path] = set()
    remote_ids_draft: set[Path] = set()
    custom_domains = conf.get("custom_domains", [])
    blog_domains = [
        d.replace("https://", "").replace("http://", "").rstrip("/")
        for d in custom_domains
    ]

    entry_url_to_filename: dict[str, str] = {}
    entry_url_to_title: dict[str, str] = {}
    entries = list(fetch_remote_entries(conf))
    total_entries = len(entries)

    with tqdm(total=total_entries, desc="index entries", unit="entry") as index_bar:
        for entry in entries:
            is_draft = is_entry_draft(entry)
            if is_draft:
                out_dir = draft_dir
            elif hasattr(entry, "hatena_unlisted") and entry.hatena_unlisted == "yes":
                out_dir = published_dir
            else:
                out_dir = published_dir
            filename = make_entry_filename(entry, out_dir)
            permalink = getattr(entry, "link", None)
            title = make_entry_title(entry)
            if permalink:
                entry_url_to_filename[permalink] = os.path.basename(str(filename))
                entry_url_to_title[permalink] = title
            entry_id = getattr(entry, "id", None)
            if entry_id and entry_id.startswith("http"):
                entry_url_to_filename[entry_id] = os.path.basename(str(filename))
                entry_url_to_title[entry_id] = title
            index_bar.update(1)

    with tqdm(total=total_entries, desc="pull entries", unit="entry") as progress_bar:
        for entry in entries:
            updated_dt = datetime(*entry.updated_parsed[:6])
            updated_iso = updated_dt.isoformat()
            is_draft = is_entry_draft(entry)
            if is_draft:
                status_str = "draft"
                out_dir = draft_dir
                remote_ids = remote_ids_draft
            elif hasattr(entry, "hatena_unlisted") and entry.hatena_unlisted == "yes":
                status_str = "unlisted"
                out_dir = published_dir
                remote_ids = remote_ids_published
            else:
                status_str = "published"
                out_dir = published_dir
                remote_ids = remote_ids_published
            filename = make_entry_filename(entry, out_dir)
            content = entry.content[0].value

            domain_pattern = "|".join(re.escape(d) for d in blog_domains)
            url_pattern = re.compile(
                rf"(?P<url>https?://(?:{domain_pattern})/entry/[\w\-/]+)"
                rf"(?P<embed>:embed)?"
                rf"(?P<title>:title)?"
                rf"(?:=?(?P<custom_title>[^\]]+))?"
            )
            content = url_pattern.sub(
                partial(
                    url_to_obsidian_link,
                    entry_url_to_filename=entry_url_to_filename,
                    entry_url_to_title=entry_url_to_title,
                ),
                content,
            )
            if hasattr(entry, "published_parsed"):
                date_str = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
            else:
                date_str = updated_dt.strftime("%Y-%m-%d")
            tags = [t["term"] for t in getattr(entry, "tags", []) if "term" in t]
            category = getattr(entry, "category", None)
            permalink = getattr(entry, "link", None)
            id_ = getattr(entry, "id", None)
            title = make_entry_title(entry)
            yaml_front_matter = (
                f"---\n"
                f'title: "{title}"\n'
                f"date: {date_str}\n"
                f"updated: {updated_iso}\n"
                f"tags: {tags}\n"
                f"status: {status_str}\n"
                f"category: {category if category else ''}\n"
                f"permalink: {permalink if permalink else ''}\n"
                f"id: {id_ if id_ else ''}\n"
                f"---\n\n"
            )
            content_with_yaml = f"{yaml_front_matter}{content}"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content_with_yaml)
            remote_ids.add(filename)
            progress_bar.update(1)
    for file in published_dir.glob("*.md"):
        if file not in remote_ids_published:
            file.unlink()
    for file in draft_dir.glob("*.md"):
        if file not in remote_ids_draft:
            file.unlink()


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
def sync(config_path: str) -> None:
    """Synchronize entries between local files and Hatena Blog."""
    conf = load_config(config_path)
    pull(conf)


if __name__ == "__main__":
    cli()
