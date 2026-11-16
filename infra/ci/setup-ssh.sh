#!/usr/bin/env bash
# Prepare a GitHub Actions runner to reach the Oracle server as
# "opennow-server". Used by the Deploy and Roll back workflows.
set -euo pipefail

missing=()
for name in APP_DOMAIN DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "::error::Missing deploy settings: ${missing[*]}. See infra/README.md."
  exit 1
fi

install -m 700 -d "$HOME/.ssh"
printf '%s\n' "$DEPLOY_SSH_KEY" > "$HOME/.ssh/opennow_deploy"
chmod 600 "$HOME/.ssh/opennow_deploy"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" >> "$HOME/.ssh/known_hosts"

cat >> "$HOME/.ssh/config" <<EOF
Host opennow-server
  HostName $DEPLOY_HOST
  User $DEPLOY_USER
  IdentityFile ~/.ssh/opennow_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking yes
EOF
chmod 600 "$HOME/.ssh/config"
