import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from tools import list_repo_contents, list_repos, read_repo_file

load_dotenv()


class TokenAuthMiddleware(Middleware):
    async def on_call_tool(self, context, call_next):
        # .env holds only sha256(token): one-way, so a leaked .env doesn't leak the token.
        try:
            token = get_http_request().query_params.get("token", "")
        except RuntimeError:  # no HTTP request (in-memory/stdio): deny
            token = ""
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(digest, os.environ["MCP_TOKEN_SHA256"]):
            raise ToolError("Access denied")
        return await call_next(context)


mcp = FastMCP("ask-your-repo", instructions=os.getenv("MCP_INSTRUCTIONS") or None)
mcp.add_middleware(TokenAuthMiddleware())
for tool in (list_repos, list_repo_contents, read_repo_file):
    mcp.add_tool(tool)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


if __name__ == "__main__":
    # Access log would print each URL, including ?token=, in plaintext.
    mcp.run(transport="http", uvicorn_config={"access_log": False})
