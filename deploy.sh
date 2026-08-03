#!/usr/bin/env bash
#
# Deploy the bcmp Django project to a VPS that already has:
#   - nginx (running on the host)
#   - Docker Engine + the "docker compose" plugin
#
# It syncs the code, (re)builds the container, runs migrations/collectstatic
# via the image entrypoint, and configures host nginx as a reverse proxy.
#
# Usage:
#   ./deploy.sh --host user@1.2.3.4 --domain example.com
#
# Options:
#   --host     SSH target, e.g. root@1.2.3.4          (required)
#   --domain   Public hostname served by nginx         (required)
#   --dir      Remote deploy directory                 (default: /opt/bcmp)
#   --key      Path to SSH private key                 (default: ssh default)
#   --ssl      Obtain/renew a Let's Encrypt cert via certbot after deploy
#   --email    Email for certbot registration          (required with --ssl)
#   --no-nginx Skip host nginx configuration
#   -h|--help  Show this help
#
# Config can also be supplied via a local `deploy.env` file (KEY=value lines).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & config
# ---------------------------------------------------------------------------
REMOTE_DIR="/opt/bcmp"
SSH_KEY=""
DOMAIN=""
HOST=""
USE_SSL=0
CERTBOT_EMAIL=""
CONFIGURE_NGINX=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load deploy.env if present (does not override explicit CLI flags)
if [[ -f "${SCRIPT_DIR}/deploy.env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.env"
  HOST="${HOST:-${VPS_HOST:-}}"
  DOMAIN="${DOMAIN:-${VPS_DOMAIN:-}}"
  REMOTE_DIR="${REMOTE_DIR:-${VPS_DIR:-/opt/bcmp}}"
fi

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_OFF=$'\033[0m'
else
  C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""; C_OFF=""
fi
log()  { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s ok%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%s warn%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%serror%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }

usage() { sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)     HOST="$2"; shift 2 ;;
    --domain)   DOMAIN="$2"; shift 2 ;;
    --dir)      REMOTE_DIR="$2"; shift 2 ;;
    --key)      SSH_KEY="$2"; shift 2 ;;
    --ssl)      USE_SSL=1; shift ;;
    --email)    CERTBOT_EMAIL="$2"; shift 2 ;;
    --no-nginx) CONFIGURE_NGINX=0; shift ;;
    -h|--help)  usage 0 ;;
    *)          die "Unknown option: $1 (use --help)" ;;
  esac
done

[[ -n "$HOST" ]]   || die "Missing --host (SSH target, e.g. root@1.2.3.4)"
[[ -n "$DOMAIN" ]] || die "Missing --domain (public hostname)"
if [[ "$USE_SSL" -eq 1 && -z "$CERTBOT_EMAIL" ]]; then
  die "--ssl requires --email <address> for certbot registration"
fi

# ---------------------------------------------------------------------------
# SSH / rsync helpers
# ---------------------------------------------------------------------------
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
[[ -n "$SSH_KEY" ]] && SSH_OPTS+=(-i "$SSH_KEY")

ssh_run()  { ssh "${SSH_OPTS[@]}" "$HOST" "$@"; }
ssh_sudo() { ssh "${SSH_OPTS[@]}" "$HOST" "sudo $*"; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
log "Checking local prerequisites"
command -v rsync >/dev/null || die "rsync not installed locally"
command -v ssh   >/dev/null || die "ssh not installed locally"
[[ -f "${SCRIPT_DIR}/docker-compose.yml" ]] || die "docker-compose.yml not found next to this script"

log "Checking connectivity to ${HOST}"
ssh_run true || die "Cannot SSH to ${HOST}"

log "Verifying remote has docker + compose plugin"
ssh_run 'command -v docker >/dev/null' || die "docker not found on remote"
ssh_run 'docker compose version >/dev/null 2>&1' \
  || die "docker compose plugin not found on remote"
ok "Remote tooling present"

# ---------------------------------------------------------------------------
# Sync code
# ---------------------------------------------------------------------------
log "Ensuring remote directories exist"
ssh_sudo "mkdir -p '${REMOTE_DIR}/data' '${REMOTE_DIR}/staticfiles' && chown -R \$(id -u):\$(id -g) '${REMOTE_DIR}'"

log "Syncing project to ${HOST}:${REMOTE_DIR}"
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
rsync -az --delete \
  -e "$RSYNC_SSH" \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'deploy.env' \
  --exclude 'data/' \
  --exclude 'staticfiles/' \
  --exclude 'db.sqlite3' \
  "${SCRIPT_DIR}/" "${HOST}:${REMOTE_DIR}/"
ok "Code synced"

# ---------------------------------------------------------------------------
# Environment file
# ---------------------------------------------------------------------------
if ssh_run "test -f '${REMOTE_DIR}/.env'"; then
  ok ".env already present on server (left untouched)"
else
  warn "No .env on server — seeding from .env.example"
  ssh_run "cp '${REMOTE_DIR}/.env.example' '${REMOTE_DIR}/.env'"
  # Auto-fill a secret key and the domain so the first boot works.
  SECRET_KEY="$(LC_ALL=C tr -dc 'a-z0-9!@#%^&*(-_=+)' </dev/urandom | head -c 50 || true)"
  ssh_run "cd '${REMOTE_DIR}' && \
    sed -i \
      -e 's|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${SECRET_KEY}|' \
      -e 's|^DJANGO_DEBUG=.*|DJANGO_DEBUG=0|' \
      -e 's|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${DOMAIN},www.${DOMAIN}|' \
      -e 's|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://www.${DOMAIN}|' \
      .env"
  warn "Review ${REMOTE_DIR}/.env on the server before relying on it in production"
fi

# Seed the SQLite DB on first deploy if one exists locally and none on server.
if [[ -f "${SCRIPT_DIR}/db.sqlite3" ]] && ! ssh_run "test -f '${REMOTE_DIR}/data/db.sqlite3'"; then
  log "Seeding initial database from local db.sqlite3"
  rsync -az -e "$RSYNC_SSH" "${SCRIPT_DIR}/db.sqlite3" "${HOST}:${REMOTE_DIR}/data/db.sqlite3"
  ok "Database seeded"
fi

# ---------------------------------------------------------------------------
# Build & run
# ---------------------------------------------------------------------------
log "Building and starting the container (migrate + collectstatic run on boot)"
ssh_run "cd '${REMOTE_DIR}' && docker compose up -d --build"
ok "Container up"

log "Waiting for the app to answer on 127.0.0.1:8000"
if ssh_run "for i in \$(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:8000/ && exit 0; sleep 2; done; exit 1"; then
  ok "App is responding"
else
  warn "App did not respond in time — check: ssh ${HOST} 'cd ${REMOTE_DIR} && docker compose logs --tail=100'"
fi

# ---------------------------------------------------------------------------
# Host nginx reverse proxy
# ---------------------------------------------------------------------------
if [[ "$CONFIGURE_NGINX" -eq 1 ]]; then
  log "Configuring host nginx for ${DOMAIN}"
  NGINX_CONF="$(cat <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    client_max_body_size 25m;

    location /static/ {
        alias ${REMOTE_DIR}/staticfiles/;
        access_log off;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
EOF
)"
  echo "$NGINX_CONF" | ssh_run "cat > /tmp/bcmp.nginx.conf"
  ssh_sudo "mv /tmp/bcmp.nginx.conf /etc/nginx/sites-available/bcmp.conf"
  ssh_sudo "ln -sf /etc/nginx/sites-available/bcmp.conf /etc/nginx/sites-enabled/bcmp.conf"
  ssh_sudo "nginx -t" || die "nginx config test failed — not reloading"
  ssh_sudo "systemctl reload nginx"
  ok "nginx reverse proxy live for ${DOMAIN}"

  if [[ "$USE_SSL" -eq 1 ]]; then
    log "Requesting/renewing TLS certificate via certbot"
    ssh_run "command -v certbot >/dev/null" \
      || die "certbot not installed on remote (install it, or drop --ssl)"
    ssh_sudo "certbot --nginx --non-interactive --agree-tos \
      -m '${CERTBOT_EMAIL}' -d '${DOMAIN}' -d 'www.${DOMAIN}' --redirect"
    ok "HTTPS enabled for ${DOMAIN}"
  fi
else
  warn "Skipped nginx configuration (--no-nginx). App listens on 127.0.0.1:8000."
fi

echo
ok "Deployment complete."
echo "   URL:      http${USE_SSL:+s}://${DOMAIN}"
echo "   Logs:     ssh ${HOST} 'cd ${REMOTE_DIR} && docker compose logs -f'"
echo "   Restart:  ssh ${HOST} 'cd ${REMOTE_DIR} && docker compose restart'"
