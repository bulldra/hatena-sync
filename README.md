# hatena-sync

A command-line tool for synchronizing Hatena Blog entries with local Markdown files.

## Features

-   Works with Obsidian or any Markdown editor.
-   Supports two-way sync between local files and Hatena Blog using the AtomPub API.
-   Sync direction can be specified (`push`, `pull`, or `both`).
-   Uses timestamps to determine the latest version of an entry.

## Usage

1. Prepare a `config.json` with your Hatena credentials (see `config.sample.json`).
2. Install dependencies using `uv` or `pip`:
    ```bash
    uv pip install -e .
    # または
    pip install -e .
    ```
3. Run the sync command:
    ```bash
    hatena-sync
    ```

## Configuration

The config file stores your blog ID and authentication token. Do **not** commit real credentials to the repository.

```json
{
	"blog_id": "example.hatenablog.com",
	"username": "your-name",
	"api_key": "your-api-key",
	"local_dir": "posts"
}
```

## License

MIT
