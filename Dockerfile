# syntax=docker/dockerfile:1

# --- CSS build stage --------------------------------------------------------
# Tailwind + daisyUI need Node, the runtime image does not have it. This stage
# compiles the stylesheet and only its output crosses into the runtime image,
# so nobody can ship a stale stylesheet by forgetting to rebuild it (ADR 0002).
FROM node:22-slim AS css

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY assets ./assets
COPY templates ./templates
RUN npm run build:css


# --- Runtime image ----------------------------------------------------------
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

# Compiled stylesheet from the CSS stage, into a STATICFILES_DIRS location so
# collectstatic picks it up in the entrypoint
COPY --from=css /build/static/css/app.css /bcmp/static/css/app.css

RUN chmod +x /bcmp/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/bcmp/entrypoint.sh"]
