# ask-your-repo

MCP server for reading docs from your private GitHub repos.

## Tools

- `list_repos` — private repos you can access
- `list_repo_contents` — markdown docs in a repo, with IDs
- `read_repo_file` — read a doc by ID

## Setup

`.env`:

```
GITHUB_TOKEN=...          # required
MCP_TOKEN_SHA256=...      # required, sha256 of the client token
DEFAULT_BRANCH=...        # optional, defaults to repo's default branch
DOCS_FOLDER_PATH=...      # optional, defaults to whole repo
MAX_FILE_TOKENS=100000    # optional
```

Generate a client token and append its hash to `.env` (keep the printed token; it is not stored):

```
uv run python -c "import hashlib,secrets; t=secrets.token_urlsafe(32); open('.env','a').write(f'\nMCP_TOKEN_SHA256={hashlib.sha256(t.encode()).hexdigest()}\n'); print(t)"
```

## Run

```
uv run python main.py
```

## Connect

```
http://127.0.0.1:8000/mcp?token=<client token>
```

## Test

```
uv run python -m unittest
```
