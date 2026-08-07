# bcmp

Django project with a one-command deploy to a VPS (nginx + Docker).

## Deployment

### What was created / fixed

| File | Purpose |
|---|---|
| **`deploy.sh`** | The deploy script — run it from your machine |
| `Dockerfile` | Rewrote it (was broken: no `requirements.txt`, wrong Python, no server). Now uv-based on Python 3.13 |
| `entrypoint.sh` | Runs `migrate` + `collectstatic`, then launches gunicorn |
| `docker-compose.yml` | Runs the container on `127.0.0.1:8000`, persists SQLite + static via bind mounts |
| `.env.example` | Template for server env (secret key, hosts, CSRF) |
| `bcmp/settings.py` | Made `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, DB path env-driven; added `STATIC_ROOT` |
| `.dockerignore` | Excludes venv/db/static/secrets from the build |
| `package.json`, `assets/css/app.css` | Tailwind + daisyUI stylesheet, compiled by the Node stage of the image build |

### How to deploy

The VPS must already have nginx and Docker Engine with the `docker compose` plugin.

```bash
./deploy.sh --host root@YOUR_VPS_IP --domain example.com
```

With HTTPS (needs certbot already installed on the VPS):

```bash
./deploy.sh --host root@YOUR_VPS_IP --domain example.com --ssl --email you@adrone.ai
```

The script: checks connectivity + that docker/compose exist → rsyncs code to
`/opt/bcmp` → seeds `.env` (auto-generates a secret key) →
`docker compose up -d --build` → health-checks port 8000 → writes an nginx
reverse-proxy vhost (`/static/` served from disk, everything else proxied) →
`nginx -t` + reload.

### Decisions worth knowing

- **Architecture**: gunicorn in the container bound to loopback; **host nginx**
  reverse-proxies and serves static. That's why static is a bind mount
  (`/opt/bcmp/staticfiles`).
- **SQLite lives in `/opt/bcmp/data/`** — a persisted mount that deploys never
  overwrite. On the *first* deploy only, your local `db.sqlite3` is copied up as
  a seed.
- **`.env` is never overwritten** once it exists on the server, so re-deploys
  are safe. First run auto-fills a secret key + your domain, but review it.
- Re-running the script = a normal redeploy (rebuild + restart).

## Статика

Tailwind + daisyUI, single light theme, plus HTMX and Alpine for the
ИИ-управляющий panel. Neither `static/css/` nor `static/js/` is committed — the
Node stage of the Docker build produces both, so a stale artifact cannot ship
(ADR 0002). The runtime image keeps no Node. HTMX and Alpine are vendored out of
`node_modules` by `npm run build:js` rather than loaded from a CDN, so the app
serves everything it runs.

Working on templates locally:

```bash
npm install
npm run build       # stylesheet + vendored scripts, once
npm run watch:css   # stylesheet on every template change
```

`npm run build:js` only copies files, so it needs re-running only after
`npm install` changes the htmx or Alpine version.

