# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/bcmp/.venv/bin:$PATH"

WORKDIR /bcmp

# uv for dependency management
RUN pip install --no-cache-dir uv

# Install dependencies first (cached layer) from the lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# App source
COPY . .

RUN chmod +x /bcmp/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/bcmp/entrypoint.sh"]
