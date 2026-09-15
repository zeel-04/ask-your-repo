FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY *.py ./

# fastmcp binds 127.0.0.1 by default, unreachable from outside the container.
ENV FASTMCP_HOST=0.0.0.0
EXPOSE 8000
USER nobody
CMD [".venv/bin/python", "main.py"]
