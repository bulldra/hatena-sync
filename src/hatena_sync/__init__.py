from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Generator
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple
from xml.etree import ElementTree as ET

import click
import feedparser
import requests
from tqdm import tqdm

from hatena_sync.converters import (
    asin_to_kindle_link,
    build_asin_to_kindle_map,
    hatena_to_markdown,
    obsidian_to_hatena_link,
)

HATENA_ATOM_URL = "https://blog.hatena.ne.jp/{user}/{blog}/atom/entry"


class EntryInfo(NamedTuple):
    """エントリの状態と出力先を保持する"""

    status: str
    out_dir: Path
    remote_ids: set[Path]


def load_config(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise click.ClickException(
            f"設定ファイル '{path}' が見つかりません。"
            "config.sample.json をコピーして作成してください。"
        )
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
        nonce + created.encode("utf-8") + api_key.encode("utf-8"),
        usedforsecurity=False,
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


def fetch_remote_entries(conf: dict[str, Any]) -> Generator[Any, None, None]:
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


def is_markdown_entry(entry: Any) -> bool:
    syntax = getattr(entry, "hatena_syntax", "").lower()
    if syntax:
        return syntax == "markdown"
    if hasattr(entry, "content") and entry.content:
        ctype = entry.content[0].get("type", "").lower()
        return "markdown" in ctype
    return False


def get_entry_info(
    entry: Any,
    published_dir: Path,
    draft_dir: Path,
    remote_ids_published: set[Path],
    remote_ids_draft: set[Path],
) -> EntryInfo:
    """エントリの状態と出力先を判定する"""
    if is_entry_draft(entry):
        return EntryInfo("draft", draft_dir, remote_ids_draft)
    if hasattr(entry, "hatena_unlisted") and entry.hatena_unlisted == "yes":
        return EntryInfo("unlisted", published_dir, remote_ids_published)
    return EntryInfo("published", published_dir, remote_ids_published)


def build_url_pattern(blog_domains: list[str]) -> re.Pattern[str]:
    """ブログURLマッチング用の正規表現を構築する"""
    domain_pattern = "|".join(re.escape(d) for d in blog_domains)
    return re.compile(
        rf"(?P<url>https?://(?:{domain_pattern})/entry/[\w\-/]+)"
        rf"(?P<embed>:embed)?"
        rf"(?P<title>:title)?"
        rf"(?:=?(?P<custom_title>[^\]]+))?"
    )


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

    # Kindle highlight ASIN マッピングを構築
    kindle_highlight_dir = Path(
        conf.get("kindle_highlight_dir", local_dir.parent / "kindle_highlight")
    )
    asin_to_filename = build_asin_to_kindle_map(kindle_highlight_dir)
    blog_domains = [
        d.replace("https://", "").replace("http://", "").rstrip("/")
        for d in custom_domains
    ]

    entry_url_to_filename: dict[str, str] = {}
    entry_url_to_title: dict[str, str] = {}
    entries = list(fetch_remote_entries(conf))
    total_entries = len(entries)

    # はてな記法をMarkdownに変換
    with tqdm(
        total=total_entries, desc="hatena-syntax-to-md entries", unit="entry"
    ) as count_bar:
        for entry in entries:
            if not is_markdown_entry(entry):
                entry.content[0].value = hatena_to_markdown(entry.content[0].value)
            count_bar.update(1)

    # URLマッピング用インデックスを構築
    with tqdm(total=total_entries, desc="index entries", unit="entry") as index_bar:
        for entry in entries:
            info = get_entry_info(
                entry, published_dir, draft_dir, remote_ids_published, remote_ids_draft
            )
            filename = make_entry_filename(entry, info.out_dir)
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

    # 正規表現を事前コンパイル
    url_pattern = build_url_pattern(blog_domains) if blog_domains else None

    # エントリをファイルに書き出し
    with tqdm(total=total_entries, desc="pull entries", unit="entry") as progress_bar:
        for entry in entries:
            updated_dt = datetime(*entry.updated_parsed[:6])
            updated_iso = updated_dt.isoformat()
            info = get_entry_info(
                entry, published_dir, draft_dir, remote_ids_published, remote_ids_draft
            )
            filename = make_entry_filename(entry, info.out_dir)
            content = entry.content[0].value

            if url_pattern:
                content = url_pattern.sub(
                    partial(
                        url_to_obsidian_link,
                        entry_url_to_filename=entry_url_to_filename,
                        entry_url_to_title=entry_url_to_title,
                    ),
                    content,
                )

            # ASIN リンクを Kindle ハイライトへの Obsidian リンクに変換
            if asin_to_filename:
                content = asin_to_kindle_link(content, asin_to_filename)

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
                f"status: {info.status}\n"
                f"category: {category if category else ''}\n"
                f"permalink: {permalink if permalink else ''}\n"
                f"id: {id_ if id_ else ''}\n"
                f"---\n\n"
            )
            content_with_yaml = f"{yaml_front_matter}{content}"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content_with_yaml)
            info.remote_ids.add(filename)
            progress_bar.update(1)

    # リモートにないファイルを削除
    for file in published_dir.glob("*.md"):
        if file not in remote_ids_published:
            file.unlink()
    for file in draft_dir.glob("*.md"):
        if file not in remote_ids_draft:
            file.unlink()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Hatena BlogとローカルMarkdownの同期CLIツール"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sync)


@cli.command()
@click.option(
    "--config",
    "-c",
    default="config.json",
    help="設定ファイルのパス",
    type=click.Path(exists=False),
)
def sync(config: str) -> None:
    """エントリをHatena Blogからローカルに同期する"""
    conf = load_config(config)
    pull(conf)


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """YAMLフロントマターをパースして、メタデータと本文を返す"""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    yaml_part = parts[1].strip()
    body = parts[2].strip()
    metadata: dict[str, Any] = {}
    for line in yaml_part.split("\n"):
        if ":" in line:
            key, raw_value = line.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            parsed_value: str | list[str]
            if raw_value.startswith('"') and raw_value.endswith('"'):
                parsed_value = raw_value[1:-1]
            elif raw_value.startswith("[") and raw_value.endswith("]"):
                items = raw_value[1:-1].split(",")
                parsed_value = [v.strip().strip("'\"") for v in items if v.strip()]
            else:
                parsed_value = raw_value
            metadata[key] = parsed_value
    return metadata, body


def build_yaml_frontmatter(metadata: dict[str, Any]) -> str:
    """メタデータからYAMLフロントマターを生成する"""
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}: {value}")
        elif value is None or value == "":
            lines.append(f"{key}: ")
        else:
            if key == "title":
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def build_atom_entry(
    title: str,
    content: str,
    categories: list[str],
    is_draft: bool = True,
) -> str:
    """AtomPub用のXMLエントリを生成する"""
    entry = ET.Element("entry")
    entry.set("xmlns", "http://www.w3.org/2005/Atom")
    entry.set("xmlns:app", "http://www.w3.org/2007/app")

    title_elem = ET.SubElement(entry, "title")
    title_elem.text = title

    content_elem = ET.SubElement(entry, "content")
    content_elem.set("type", "text/x-markdown")
    content_elem.text = content

    for cat in categories:
        if cat:
            cat_elem = ET.SubElement(entry, "category")
            cat_elem.set("term", cat)

    control = ET.SubElement(entry, "app:control")
    draft = ET.SubElement(control, "app:draft")
    draft.text = "yes" if is_draft else "no"

    return ET.tostring(entry, encoding="unicode")


def extract_entry_id_from_response(response_text: str) -> tuple[str | None, str | None]:
    """APIレスポンスからentry_idとpermalinkを抽出する"""
    try:
        root = ET.fromstring(response_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        id_elem = root.find("atom:id", ns)
        if id_elem is None:
            id_elem = root.find("id")
        entry_id = id_elem.text if id_elem is not None else None

        permalink = None
        for link in root.findall("atom:link", ns) or root.findall("link"):
            if link.get("rel") == "alternate":
                permalink = link.get("href")
                break
        return entry_id, permalink
    except ET.ParseError:
        return None, None


def build_filename_to_url_map(conf: dict[str, Any]) -> dict[str, str]:
    """ローカルファイルのファイル名からURLへのマッピングを構築する"""
    local_dir = Path(conf.get("local_dir", "posts"))
    filename_to_url: dict[str, str] = {}

    for subdir in ["published", "draft"]:
        dir_path = local_dir / subdir
        if not dir_path.exists():
            continue
        for file in dir_path.glob("*.md"):
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()
            metadata, _ = parse_yaml_frontmatter(content)
            permalink = metadata.get("permalink", "")
            if permalink:
                filename_to_url[file.name] = permalink
    return filename_to_url


@cli.command()
@click.argument("filename")
@click.option(
    "--config",
    "-c",
    default="config.json",
    help="設定ファイルのパス",
    type=click.Path(exists=False),
)
def new(filename: str, config: str) -> None:
    """新規記事のテンプレートを作成する"""
    conf = load_config(config)
    local_dir = Path(conf.get("local_dir", "posts"))
    feature_dir = local_dir / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    filepath = feature_dir / filename

    if filepath.exists():
        raise click.ClickException(f"ファイルが既に存在します: {filepath}")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    updated_iso = now.isoformat()

    metadata = {
        "title": "",
        "date": date_str,
        "updated": updated_iso,
        "tags": [],
        "status": "draft",
        "category": "",
        "permalink": "",
        "id": "",
    }
    yaml_content = build_yaml_frontmatter(metadata)
    content = f"{yaml_content}\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    click.echo(f"新規記事を作成しました: {filepath}")


@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option(
    "--config",
    "-c",
    default="config.json",
    help="設定ファイルのパス",
    type=click.Path(exists=False),
)
def push(filepath: str, config: str) -> None:
    """ローカルファイルをHatena Blogに投稿する"""
    conf = load_config(config)
    user = conf["username"]
    blog = conf["blog_id"]
    api_key = conf["api_key"]
    local_dir = Path(conf.get("local_dir", "posts"))

    file_path = Path(filepath)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, body = parse_yaml_frontmatter(content)
    if not metadata:
        raise click.ClickException("YAMLフロントマターが見つかりません")

    title = metadata.get("title", "")
    if not title:
        raise click.ClickException("タイトルが設定されていません")

    entry_id = metadata.get("id", "")
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    category = metadata.get("category", "")
    categories = [category] if category else []

    # Obsidian内部リンクをHatena URLに変換
    filename_to_url = build_filename_to_url_map(conf)
    body = obsidian_to_hatena_link(body, filename_to_url)

    # Atom XMLを生成
    atom_xml = build_atom_entry(title, body, categories, is_draft=True)

    headers = wsse_header(user, api_key)
    headers["Content-Type"] = "application/xml"

    data = atom_xml.encode("utf-8")
    if entry_id:
        # 更新 (PUT)
        entry_id_part = entry_id.split("/")[-1]
        url = f"{HATENA_ATOM_URL.format(user=user, blog=blog)}/{entry_id_part}"
        click.echo(f"記事を更新中: {title}")
        resp = requests.put(url, data=data, headers=headers, timeout=30)
    else:
        # 新規投稿 (POST)
        url = HATENA_ATOM_URL.format(user=user, blog=blog)
        click.echo(f"新規記事を投稿中: {title}")
        resp = requests.post(url, data=data, headers=headers, timeout=30)

    if resp.status_code not in (200, 201):
        raise click.ClickException(
            f"投稿に失敗しました: {resp.status_code} {resp.text}"
        )

    # レスポンスからid, permalinkを取得
    new_entry_id, permalink = extract_entry_id_from_response(resp.text)

    # メタデータを更新
    if new_entry_id:
        metadata["id"] = new_entry_id
    if permalink:
        metadata["permalink"] = permalink
    metadata["updated"] = datetime.now().isoformat()

    # ファイルを更新
    new_yaml = build_yaml_frontmatter(metadata)
    new_content = f"{new_yaml}\n\n{body}"

    # feature/からdraft/に移動
    draft_dir = local_dir / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    new_path = draft_dir / file_path.name

    with open(new_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    if file_path.parent.name == "feature" and file_path != new_path:
        file_path.unlink()
        click.echo(f"ファイルを移動しました: {file_path} -> {new_path}")

    click.echo(f"投稿が完了しました: {permalink or new_entry_id}")


if __name__ == "__main__":
    cli()
