#!/usr/bin/env bash
# One-time setup of the Oracle Cloud Always Free server
# (Ubuntu 24.04 on an Ampere A1 arm64 VM). Safe to run again.
#
#   sudo bash bootstrap.sh "<deploy public key>" <production domain> <staging domain>
#   sudo bash bootstrap.sh "$(cat opennow_deploy.pub)" openow.online staging.openow.online
#
# It installs Docker, creates the deploy user, opens ports 80 and 443,
# and writes the .env files with new random secrets (existing files are kept).
set -euo pipefail

DEPLOY_PUBLIC_KEY="${1:?Pass the deploy public key as the first argument}"
PRODUCTION_DOMAIN="${2:?Pass the production domain as the second argument}"
STAGING_DOMAIN="${3:?Pass the staging domain as the third argument}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
PRODUCTION_PORT="${PRODUCTION_PORT:-8082}"
STAGING_PORT="${STAGING_PORT:-8081}"
ROOT=/srv/opennow

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

echo "Installing Docker, Compose and Python"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 python3 netfilter-persistent iptables-persistent
systemctl enable --now docker

echo "Creating the $DEPLOY_USER user"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
printf '%s\n' "$DEPLOY_PUBLIC_KEY" > "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"

echo "Opening ports 80 and 443"
# Oracle's Ubuntu image rejects everything except SSH. Insert the rules
# before that REJECT rule and save them so they survive a reboot.
for port in 80 443; do
  if ! iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    reject_line="$(iptables -L INPUT --line-numbers | awk '/REJECT/ {print $1; exit}')"
    if [[ -n "$reject_line" ]]; then
      iptables -I INPUT "$reject_line" -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    else
      iptables -A INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    fi
  fi
done
netfilter-persistent save

echo "Creating $ROOT"
for directory in "$ROOT" "$ROOT/staging" "$ROOT/production" "$ROOT/edge"; do
  install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$directory"
done
install -d -m 700 /etc/opennow/certs

new_secret() {
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
}

write_env() {
  local file="$1" domain="$2" port="$3"
  if [[ -f "$file" ]]; then
    echo "Keeping existing $file"
    return
  fi
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /dev/null "$file"
  cat > "$file" <<EOF
APP_DOMAIN=$domain
APP_PORT=$port
DJANGO_SECRET_KEY=$(new_secret)
POSTGRES_DB=opennow
POSTGRES_USER=opennow
POSTGRES_PASSWORD=$(new_secret)
EOF
  echo "Wrote $file"
}

write_env "$ROOT/staging/.env" "$STAGING_DOMAIN" "$STAGING_PORT"
write_env "$ROOT/production/.env" "$PRODUCTION_DOMAIN" "$PRODUCTION_PORT"

if [[ ! -f "$ROOT/edge/.env" ]]; then
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /dev/null "$ROOT/edge/.env"
  cat > "$ROOT/edge/.env" <<EOF
PRODUCTION_DOMAIN=$PRODUCTION_DOMAIN
PRODUCTION_PORT=$PRODUCTION_PORT
STAGING_DOMAIN=$STAGING_DOMAIN
STAGING_PORT=$STAGING_PORT
EOF
  echo "Wrote $ROOT/edge/.env"
fi

echo
echo "Done. Next: save the Cloudflare origin certificate to"
echo "/etc/opennow/certs/origin.pem and origin.key, then start the edge proxy"
echo "(infra/README.md, step 5)."
