#!/usr/bin/env python3
"""CLI tool for syncing Hatena Blog entries with local Markdown files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click
import requests
import feedparser


HATENA_ATOM_URL = "https://blog.hatena.ne.jp/{user}/{blog}/atom/entry"


def load_config(path: str) -> dict:
    """Load configuration from a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        conf = json.load(fh)
    required = {"username", "blog_id", "api_key"}
    missing = required - conf.keys()
    if missing:
        raise click.ClickException(f"Missing keys in config: {', '.join(sorted(missing))}")
    return conf


def fetch_remote_entries(conf: dict):
    """Fetch **all** entries from Hatena Blog AtomPub API."""
    user = conf["username"]
    blog = conf["blog_id"]
    api_key = conf["api_key"]

    url = HATENA_ATOM_URL.format(user=user, blog=blog)
    headers = {"Authorization": f"Bearer {api_key}"}
    entries = []

    while url:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        entries.extend(feed.entries)

        next_url = None
        for link in feed.feed.get("links", []):
            if link.get("rel") == "next":
                next_url = link.get("href")
                break
        url = next_url

    return entries


def save_entry_to_file(entry, directory: Path):
    """Save a single entry to a Markdown file using its updated date as filename."""
    updated = datetime(*entry.updated_parsed[:6]).strftime('%Y%m%d%H%M%S')
    title = entry.title.strip().replace('/', '_')
    filename = directory / f"{updated}-{title}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(entry.content[0].value)


def pull(conf: dict):
    """Pull entries from Hatena Blog to the local directory."""
    local_dir = Path(conf.get("local_dir", "posts"))
    local_dir.mkdir(parents=True, exist_ok=True)

    entries = fetch_remote_entries(conf)
    for entry in entries:
        save_entry_to_file(entry, local_dir)


def push(conf: dict):
    """Placeholder for pushing local changes back to Hatena Blog."""
    click.echo('push is not implemented yet')


@click.group()
def cli():
    """Entry point for CLI."""
    pass


@cli.command()
@click.option('--config', 'config_path', default='config.json', show_default=True,
              help='Path to configuration file')
@click.option('--direction', type=click.Choice(['pull', 'push', 'both']), default='both',
              show_default=True, help='Sync direction')
def sync(config_path, direction):
    """Synchronize entries between local files and Hatena Blog."""
    conf = load_config(config_path)
    if direction in ('pull', 'both'):
        pull(conf)
    if direction in ('push', 'both'):
        push(conf)


if __name__ == '__main__':
    cli()
