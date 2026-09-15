import base64
import os

from repo_auth import GitHubAuth

# File ID = "owner/repo@branch:path/to/file". Stateless: no ID registry to store or sync.
# Safe to split: repo names can't contain "@" or ":", and branch names can't contain ":".

FIELDS = ("type", "description", "tags")


def _frontmatter(text: str) -> dict:
    # ponytail: reads flat "key: value" lines and [a, b] tag lists (what openwiki writes); use PyYAML if docs get block lists.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key in FIELDS:
            meta[key] = value.strip().strip("\"'")
    if "tags" in meta:
        meta["tags"] = [t.strip().strip("\"'") for t in meta["tags"].strip("[]").split(",") if t.strip()]
    return meta


def _get_private_repo(repo: str):
    # Fine-grained tokens can read every public repo; only private ones are scoped by the token.
    r = GitHubAuth().client.get_repo(repo)
    if not r.private:
        raise ValueError(f"{repo} is not an allowed repo")
    return r


def list_repos() -> list[str]:
    """List the GitHub repos you can access, as "owner/repo"."""
    return [r.full_name for r in GitHubAuth().client.get_user().get_repos(visibility="private")]


def _is_doc(path: str) -> bool:
    docs = os.getenv("DOCS_FOLDER_PATH", "").strip("/")
    prefix = f"{docs}/" if docs else ""
    return path.startswith(prefix) and path.endswith(".md") and ".." not in path.split("/")


def _branch(r, branch: str | None) -> str:
    return branch or os.getenv("DEFAULT_BRANCH") or r.default_branch


def list_repo_contents(repo: str, branch: str | None = None) -> list[dict]:
    """List a repo's docs with their file ID, type, description, and tags. Pass an ID to read_repo_file."""
    r = _get_private_repo(repo)
    branch = _branch(r, branch)
    # ponytail: GitHub truncates trees over ~100k entries; walk subtrees if that ever matters.
    tree = r.get_git_tree(branch, recursive=True).tree
    # Mode 120000 = symlink; it could point outside the docs folder.
    md_files = [t for t in tree if t.type == "blob" and t.mode != "120000" and _is_doc(t.path)]
    # ponytail: one API call per doc; batch with a GraphQL query if the doc count makes this slow.
    return [
        {"id": f"{repo}@{branch}:{t.path}", **_frontmatter(base64.b64decode(r.get_git_blob(t.sha).content).decode("utf-8", errors="replace"))}
        for t in md_files
    ]


def read_repo_file(file_id: str) -> str:
    """Read a doc's full content by the file ID from list_repo_contents."""
    repo_branch, _, path = file_id.partition(":")
    repo, _, branch = repo_branch.partition("@")
    # Same filter as list_repo_contents, so an ID can't reach files outside the docs.
    if not _is_doc(path):
        raise ValueError(f"{file_id} is not a doc")
    r = _get_private_repo(repo)
    f = r.get_contents(path, ref=_branch(r, branch))
    if isinstance(f, list):
        raise ValueError(f"{file_id} is a directory")
    # GitHub follows symlinks and returns the target file, whose path differs from the one asked for.
    if f.type != "file" or f.path != path:
        raise ValueError(f"{file_id} is not a regular file")
    # Files over 1MB come back without content; the blob API still serves them.
    raw = f.decoded_content if f.encoding == "base64" else base64.b64decode(r.get_git_blob(f.sha).content)
    text = raw.decode("utf-8", errors="replace")
    # ponytail: ~4 chars per token; swap in a real tokenizer if the cap needs to be exact.
    limit = int(os.getenv("MAX_FILE_TOKENS", "100000")) * 4
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"
