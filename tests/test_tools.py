import asyncio
import base64
import hashlib
import os
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.utilities.tests import asgi_server

import main
import tools
from repo_auth import BaseAuth

TOKEN = "t0ken"

DOC = """---
type: subsystem
title: Agent
description: "How the agent works"
tags: [agent, tools]
verified:
  - by: openwiki/0.5.1
---

# Agent
type: not-frontmatter
"""
DOC_META = {"type": "subsystem", "description": "How the agent works", "tags": ["agent", "tools"]}


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class ToolTest(unittest.TestCase):
    """Fakes GitHub: files is the repo tree ({path: text}, "/"-ending paths are directories)."""

    env: ClassVar[dict] = {"DEFAULT_BRANCH": "Copied", "DOCS_FOLDER_PATH": "/openwiki/"}
    files: ClassVar[dict] = {}

    def setUp(self):
        patch.dict(os.environ, self.env, clear=True).start()
        self.client = patch("tools.GitHubAuth").start().return_value.client
        self.addCleanup(patch.stopall)

        self.repo = self.client.get_repo.return_value
        self.repo.private = True
        self.repo.default_branch = "main"
        self.repo.get_git_tree.return_value.tree = [
            SimpleNamespace(type="tree" if p.endswith("/") else "blob", mode="100644", path=p.rstrip("/"), sha=p)
            for p in self.files
        ]
        self.repo.get_git_blob.side_effect = lambda sha: SimpleNamespace(content=b64(self.files[sha]))


class FrontmatterTest(unittest.TestCase):
    def test_reads_only_known_fields(self):
        self.assertEqual(tools._frontmatter(DOC), DOC_META)

    def test_no_frontmatter(self):
        self.assertEqual(tools._frontmatter("# No frontmatter"), {})
        self.assertEqual(tools._frontmatter(""), {})


class BaseAuthTest(unittest.TestCase):
    def test_failed_login_is_retried_then_cached(self):
        logins = []

        class Flaky(BaseAuth):
            def login(self):
                logins.append(1)
                if len(logins) == 1:
                    raise RuntimeError("GitHub down")
                return "client"

        with self.assertRaises(RuntimeError):
            Flaky()
        self.assertIs(Flaky(), Flaky())
        self.assertEqual(Flaky().client, "client")
        self.assertEqual(len(logins), 2)


class ListReposTest(ToolTest):
    def test_lists_private_repo_names(self):
        get_repos = self.client.get_user.return_value.get_repos
        get_repos.return_value = [SimpleNamespace(full_name="o/a"), SimpleNamespace(full_name="o/b")]

        self.assertEqual(tools.list_repos(), ["o/a", "o/b"])
        get_repos.assert_called_once_with(visibility="private")


class ListRepoContentsTest(ToolTest):
    files: ClassVar[dict] = {
        "openwiki/agent.md": DOC,
        "openwiki/api/index.md": "# Files",
        "openwiki/notes.txt": "not markdown",
        "openwiki/dir.md/": "",
        "openwikiold/stale.md": "outside docs folder",
        "README.md": "# Readme",
    }

    def test_uses_env_branch_and_docs_folder(self):
        self.assertEqual(
            tools.list_repo_contents("o/r"),
            [{"id": "o/r@Copied:openwiki/agent.md", **DOC_META}, {"id": "o/r@Copied:openwiki/api/index.md"}],
        )
        self.repo.get_git_tree.assert_called_once_with("Copied", recursive=True)

    def test_skips_symlinks(self):
        link = SimpleNamespace(type="blob", mode="120000", path="openwiki/setup.md", sha="openwiki/agent.md")
        self.repo.get_git_tree.return_value.tree.append(link)
        ids = [d["id"] for d in tools.list_repo_contents("o/r")]
        self.assertNotIn("o/r@Copied:openwiki/setup.md", ids)

    def test_without_env_uses_default_branch_and_whole_repo(self):
        os.environ.clear()
        ids = [d["id"] for d in tools.list_repo_contents("o/r")]
        self.assertEqual(
            ids,
            ["o/r@main:openwiki/agent.md", "o/r@main:openwiki/api/index.md", "o/r@main:openwikiold/stale.md", "o/r@main:README.md"],
        )

    def test_rejects_public_repo(self):
        self.repo.private = False
        with self.assertRaises(ValueError):
            tools.list_repo_contents("o/r")


class ReadRepoFileTest(ToolTest):
    files: ClassVar[dict] = {"big.md": "# Big"}

    def setUp(self):
        super().setUp()
        self.repo.get_contents.return_value = SimpleNamespace(
            type="file", path="openwiki/a.md", encoding="base64", decoded_content=b"# Doc", sha="big.md"
        )

    def test_reads_path_on_branch_from_id(self):
        self.assertEqual(tools.read_repo_file("o/r@Copied:openwiki/a.md"), "# Doc")
        self.client.get_repo.assert_called_once_with("o/r")
        self.repo.get_contents.assert_called_once_with("openwiki/a.md", ref="Copied")

    def test_id_without_branch_uses_env_then_repo_default_branch(self):
        tools.read_repo_file("o/r:openwiki/a.md")
        self.repo.get_contents.assert_called_once_with("openwiki/a.md", ref="Copied")
        del os.environ["DEFAULT_BRANCH"]
        tools.read_repo_file("o/r:openwiki/a.md")
        self.repo.get_contents.assert_called_with("openwiki/a.md", ref="main")

    def test_rejects_paths_outside_docs(self):
        for path in ("openwiki/secrets.yml", "config/a.md", "openwikiold/a.md", "openwiki/../a.md"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tools.read_repo_file(f"o/r@Copied:{path}")
        self.repo.get_contents.assert_not_called()

    def test_rejects_symlink(self):
        # GitHub followed openwiki/a.md to its target, so the returned path differs.
        self.repo.get_contents.return_value.path = "deploy/.env.production"
        with self.assertRaises(ValueError):
            tools.read_repo_file("o/r@Copied:openwiki/a.md")

    def test_file_over_1mb_is_read_from_blob(self):
        self.repo.get_contents.return_value = SimpleNamespace(
            type="file", path="openwiki/big.md", encoding="none", decoded_content=None, sha="big.md"
        )
        self.assertEqual(tools.read_repo_file("o/r@Copied:openwiki/big.md"), "# Big")

    def test_directory_raises(self):
        self.repo.get_contents.return_value = [SimpleNamespace()]
        with self.assertRaises(ValueError):
            tools.read_repo_file("o/r@Copied:openwiki/dir.md")

    def test_truncates_over_token_limit(self):
        os.environ["MAX_FILE_TOKENS"] = "1"  # 4 chars
        self.repo.get_contents.return_value.decoded_content = b"abcd"
        self.assertEqual(tools.read_repo_file("o/r@Copied:openwiki/a.md"), "abcd")
        self.repo.get_contents.return_value.decoded_content = b"abcde"
        self.assertEqual(tools.read_repo_file("o/r@Copied:openwiki/a.md"), "abcd\n[truncated]")

    def test_rejects_public_repo(self):
        self.repo.private = False
        with self.assertRaises(ValueError):
            tools.read_repo_file("o/r@Copied:openwiki/a.md")


@asynccontextmanager
async def http_client(token: str):
    # asgi_server runs the real HTTP app (what main.py serves) without binding a port.
    async with (
        asgi_server(main.mcp) as s,
        Client(StreamableHttpTransport(f"{s.url}?token={token}", httpx_client_factory=s.http_client)) as c,
    ):
        yield c


class ServerTest(ToolTest):
    env: ClassVar[dict] = {**ToolTest.env, "MCP_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest()}
    files: ClassVar[dict] = {"openwiki/agent.md": DOC}

    def test_tools_are_listed_but_in_memory_calls_are_denied(self):
        async def run():
            async with Client(main.mcp) as c:
                with self.assertRaises(ToolError):
                    await c.call_tool("list_repos", {})
                return sorted(t.name for t in await c.list_tools())

        self.assertEqual(asyncio.run(run()), ["list_repo_contents", "list_repos", "read_repo_file"])
        self.client.get_user.assert_not_called()

    def test_rejects_missing_or_wrong_token(self):
        async def run(token):
            async with http_client(token) as c:
                await c.call_tool("list_repos", {})

        for token in ("", "wrong"):
            with self.subTest(token=token), self.assertRaises(ToolError):
                asyncio.run(run(token))
        self.client.get_user.assert_not_called()

    def test_full_flow_over_http(self):
        self.client.get_user.return_value.get_repos.return_value = [SimpleNamespace(full_name="o/r")]
        self.repo.get_contents.return_value = SimpleNamespace(
            type="file", path="openwiki/agent.md", encoding="base64", decoded_content=DOC.encode(), sha="x"
        )

        async def run():
            async with http_client(TOKEN) as c:
                repos = (await c.call_tool("list_repos", {})).data
                docs = (await c.call_tool("list_repo_contents", {"repo": repos[0]})).data
                text = (await c.call_tool("read_repo_file", {"file_id": docs[0]["id"]})).data
                return repos, docs, text

        repos, docs, text = asyncio.run(run())
        self.assertEqual(repos, ["o/r"])
        self.assertEqual(docs, [{"id": "o/r@Copied:openwiki/agent.md", **DOC_META}])
        self.assertEqual(text, DOC)
        self.repo.get_contents.assert_called_once_with("openwiki/agent.md", ref="Copied")


if __name__ == "__main__":
    unittest.main()
