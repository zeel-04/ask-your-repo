# ask-your-repo

MCP server for reading docs from your private GitHub repos.

## Tools

- `list_repos` — private repos you can access
- `list_repo_contents` — markdown docs in a repo, with IDs
- `read_repo_file` — read a doc by ID

## Setup

Copy [`.env.example`](.env.example) to `.env` and fill it in.

Generate a client token and append its hash to `.env` (keep the printed token; it is not stored):

```
uv run python -c "import hashlib,secrets; t=secrets.token_urlsafe(32); open('.env','a').write(f'\nMCP_TOKEN_SHA256={hashlib.sha256(t.encode()).hexdigest()}\n'); print(t)"
```

## Run

```
uv run python main.py
```

Or with Docker:

```
docker build -t ask-your-repo .
docker run --env-file .env -p 8000:8000 ask-your-repo
```

## Connect

```
http://127.0.0.1:8000/mcp?token=<client token>
```

## Test

```
uv run python -m unittest
```
