# Hosting and releases

OpenNow runs staging and production on one Oracle Cloud Always Free server
(Ampere A1, arm64), behind Cloudflare Free. Images are built by GitHub
Actions and stored in GitHub Container Registry. Everything here uses free
tiers only.

## How a change reaches users

| Step | What you do | What happens |
|---|---|---|
| Staging | Merge a pull request into `develop` | **Deploy** runs CI, builds the images, deploys staging and runs the smoke test |
| Production | Open a pull request from `develop` into `main`, merge it, then tag `main` with `v1.2.3` | **Deploy** checks the tag is on `main`, runs CI, deploys production and runs the smoke test |
| Rollback | Actions → **Roll back** → Run workflow → pick the environment | The environment returns to the release before the current one |

To tag a release after the release pull request is merged:

```bash
git checkout main
git pull
git tag v1.0.0
git push origin v1.0.0
```

If the smoke test fails right after a deploy, the Deploy workflow rolls back
by itself. If a new release fails its health checks during the deploy, the
running release is put back and the workflow fails.

Each environment keeps its current release and the one before it. Older
images are removed from the server; every image stays in the registry.

Rollback swaps images only. Database migrations are not reversed, so keep
migrations backward compatible: add columns and tables first, and remove old
ones in a later release.

Check what an environment runs:

```bash
ssh deploy@<server> python3 /srv/opennow/production/deploy.py status --env production
```

## Server layout

```text
Cloudflare (proxied DNS, SSL Full strict)
  └─ Oracle server, ports 80 and 443
       └─ edge Caddy (docker/edge)          Cloudflare origin certificate
            ├─ openow.online         → 127.0.0.1:8082 → production stack
            └─ staging.openow.online → 127.0.0.1:8081 → staging stack

/srv/opennow/production/  compose.yaml, Caddyfile, deploy.py, .env, release.json
/srv/opennow/staging/     same files, its own database volume
/srv/opennow/edge/        compose.yaml, Caddyfile, .env
/etc/opennow/certs/       origin.pem, origin.key (root only)
```

Each stack is `docker/compose.server.yaml`: web, api, worker, beat, PostGIS,
Redis and its own Caddy. Only that Caddy listens, and only on localhost.

## One-time setup

The deploy jobs stay off until step 7, so `develop` keeps working while this
is done.

### 1. Create the server (Oracle Cloud)

1. Create a compute instance: shape **VM.Standard.A1.Flex** (Always Free),
   image **Ubuntu 24.04**. Stay within the Always Free limits.
2. Reserve its public IP.
3. In the instance's VCN security list, add ingress rules for TCP 80 and 443.

### 2. Make the deploy key

On your own computer:

```bash
ssh-keygen -t ed25519 -f opennow_deploy -C opennow-deploy -N ""
```

`opennow_deploy.pub` goes on the server. `opennow_deploy` becomes a GitHub
secret. Don't commit either file.

### 3. Prepare the server

Copy `infra/server/bootstrap.sh` to the server and run it:

```bash
sudo bash bootstrap.sh "$(cat opennow_deploy.pub)" openow.online staging.openow.online
```

It installs Docker, creates the `deploy` user, opens ports 80 and 443, and
writes `/srv/opennow/<environment>/.env` with new random secrets. Running it
again keeps existing `.env` files.

### 4. Point Cloudflare at the server

1. DNS: add `A` records for `@` and `staging` with the server IP, **Proxied**.
2. SSL/TLS → Overview: set the mode to **Full (strict)**.
3. SSL/TLS → Origin Server → **Create Certificate** for `openow.online` and
   `*.openow.online`. Save the certificate as `/etc/opennow/certs/origin.pem`
   and the private key as `/etc/opennow/certs/origin.key`, owned by root with
   mode 600.

### 5. Start the edge proxy

```bash
scp docker/edge/compose.yaml docker/edge/Caddyfile deploy@<server>:/srv/opennow/edge/
ssh deploy@<server> docker compose --project-name opennow-edge \
  --file /srv/opennow/edge/compose.yaml \
  --env-file /srv/opennow/edge/.env up --detach
```

Run the same two commands again whenever `docker/edge/` changes.

### 6. Add the GitHub settings (repository admin)

Settings → Secrets and variables → Actions → **Secrets**:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | Server public IP |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | Contents of `opennow_deploy` (the private key) |
| `DEPLOY_KNOWN_HOSTS` | Output of `ssh-keyscan -t ed25519 <server IP>`; check the fingerprint against the server |

Settings → **Environments**:

| Environment | Variable `APP_DOMAIN` | Deployment branches and tags |
|---|---|---|
| `staging` | `staging.openow.online` | `develop` |
| `production` | `openow.online` | Tags `v*.*.*`, and the default branch (**Roll back** runs from it) |

Add yourself as a required reviewer on `production` if releases should wait
for approval.

### 7. Turn deploys on

Settings → Secrets and variables → Actions → **Variables**: add
`DEPLOY_ENABLED` = `true`. The next merge into `develop` deploys staging.

After the first deploy, open each package under the repository's
**Packages** (`api`, `web`, `db`) and set its visibility to public, so the
images don't count against the private package storage limit.

## Files

| File | Purpose |
|---|---|
| `.github/workflows/deploy.yml` | Build, deploy and smoke test on pushes to `develop` and `v*.*.*` tags |
| `.github/workflows/rollback.yml` | Manual one-step rollback |
| `docker/compose.server.yaml` | Stack for one environment on the server |
| `docker/edge/` | Edge Caddy for both domains |
| `infra/deploy.py` | Deploy, rollback and status on the server |
| `infra/release_target.py` | Picks staging or production for a push |
| `infra/ci/setup-ssh.sh` | SSH access for the workflow runners |
| `infra/server/bootstrap.sh` | One-time server setup |
