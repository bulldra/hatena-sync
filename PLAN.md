# hatena-sync 新規記事作成・push機能 実装計画

## 概要

ローカルMarkdownファイルからHatena Blogへの投稿機能を実装する。

## 決定事項

| 項目 | 選択 | 備考 |
|------|------|------|
| 実装機能 | 新規記事作成 + push | ローカルからHatenaへの書き込み機能 |
| 作成フロー | CLIでテンプレート生成 + 下書き反映 | newとpushを分離 |
| 初期状態 | 常に下書き | 誤公開を防止 |
| コマンドUI | ファイル名引数のみ | `hatena-sync new "2026-01-09-slug"` |
| 投稿タイミング | 別コマンド | newでローカル、pushでHatena |
| push対象 | 特定ファイル指定 | `hatena-sync push ファイル名.md` |
| 新規/更新判定 | YAMLのidで判定 | id空=新規、あり=更新 |
| ファイル名 | URLベース（ユーザー指定） | `2026-01-09-slug.md` |
| 保存先 | local_dir/feature/ | 同期対象外で管理 |
| YAMLテンプレート | フル形式 | 既存pullと同様 |
| Markdown変換 | 不要 | Markdownのまま投稿 |
| push後のファイル更新 | idとpermalinkを書き戻す | YAMLを自動更新 |
| エラー処理 | エラー表示して終了 | リトライなし |
| 内部リンク変換 | 必要 | Obsidian連携（pullの逆操作） |
| push後のファイル移動 | draftに移動 | feature/ → draft/ |

## 実装タスク

### 1. `hatena-sync new` コマンド

```python
@cli.command()
@click.argument("filename")
@click.option("--config", "-c", default="config.json")
def new(filename: str, config: str) -> None:
    """新規記事のテンプレートを作成する"""
```

- feature/ディレクトリを作成（存在しない場合）
- YAMLフロントマター付きMarkdownファイルを生成
- ファイル名: `{filename}.md`

**テンプレート形式:**
```markdown
---
title: ""
date: 2026-01-09
updated: 2026-01-09T00:00:00
tags: []
status: draft
category:
permalink:
id:
---

```

### 2. `hatena-sync push` コマンド

```python
@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--config", "-c", default="config.json")
def push(filepath: str, config: str) -> None:
    """ローカルファイルをHatena Blogに投稿する"""
```

**処理フロー:**
1. ファイルを読み込み、YAMLフロントマターをパース
2. idの有無で新規/更新を判定
3. Obsidian内部リンクをHatena URLに変換
4. AtomPub APIで投稿
   - 新規: POST /atom/entry
   - 更新: PUT /atom/entry/{entry_id}
5. レスポンスからid, permalinkを取得
6. YAMLに書き戻し
7. ファイルをfeature/からdraft/に移動

### 3. Obsidian→Hatena リンク変換

`converters.py` に追加:

```python
def obsidian_to_hatena_link(
    content: str,
    filename_to_url: dict[str, str],
) -> str:
    """[[filename|title]] → https://domain/entry/... に変換"""
```

### 4. pullの修正

- feature/ディレクトリを削除対象から除外

## ファイル構成

```
src/hatena_sync/
├── __init__.py  # cli, new, push コマンド追加
└── converters.py  # obsidian_to_hatena_link 追加
```

## AtomPub API仕様

### 新規投稿 (POST)

```
POST https://blog.hatena.ne.jp/{user}/{blog}/atom/entry
Content-Type: application/xml
X-WSSE: ...

<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>記事タイトル</title>
  <content type="text/x-markdown">本文</content>
  <category term="カテゴリ" />
  <app:control>
    <app:draft>yes</app:draft>
  </app:control>
</entry>
```

### 更新 (PUT)

```
PUT https://blog.hatena.ne.jp/{user}/{blog}/atom/entry/{entry_id}
```

## テスト計画

- `tests/test_new.py`: newコマンドのテスト
- `tests/test_push.py`: pushコマンドのテスト（モック使用）
- `tests/test_obsidian_link.py`: リンク変換のテスト
