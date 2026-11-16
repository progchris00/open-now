from __future__ import annotations

import re

from conftest import read_file


def test_merges_to_develop_deploy_staging_after_ci() -> None:
    workflow = read_file(".github/workflows/deploy.yml")

    assert re.search(r"push:\s+branches:\s+\[develop\]", workflow)
    assert "uses: ./.github/workflows/ci.yml" in workflow
    assert re.search(r"needs: \[ci, release\]", workflow)


def test_release_tags_deploy_production() -> None:
    workflow = read_file(".github/workflows/deploy.yml")

    assert 'tags: ["v*.*.*"]' in workflow
    assert "python3 infra/release_target.py" in workflow
    assert "name: ${{ needs.release.outputs.environment }}" in workflow


def test_deploy_runs_the_server_script_and_the_smoke_test() -> None:
    workflow = read_file(".github/workflows/deploy.yml")

    assert "deploy.py deploy" in workflow
    assert "pnpm --dir e2e test" in workflow
    assert "PLAYWRIGHT_BASE_URL: https://${{ vars.APP_DOMAIN }}" in workflow


def test_failed_smoke_test_rolls_back() -> None:
    workflow = read_file(".github/workflows/deploy.yml")

    assert "steps.smoke.outcome == 'failure'" in workflow
    assert "deploy.py rollback" in workflow


def test_images_are_built_for_the_oracle_arm_server() -> None:
    workflow = read_file(".github/workflows/deploy.yml")

    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "platforms: linux/arm64" in workflow
    for service in ("api", "web", "db"):
        assert f"service: {service}" in workflow


def test_rollback_is_one_manual_job() -> None:
    workflow = read_file(".github/workflows/rollback.yml")

    assert "workflow_dispatch:" in workflow
    assert "options: [production, staging]" in workflow
    assert "deploy.py rollback" in workflow
    assert "pnpm --dir e2e test" in workflow


def test_deploy_and_rollback_never_run_at_the_same_time() -> None:
    deploy = read_file(".github/workflows/deploy.yml")
    rollback = read_file(".github/workflows/rollback.yml")

    assert "cancel-in-progress: false" in deploy
    assert "group: deploy-${{ inputs.environment }}" in rollback


def test_ci_can_be_called_and_skips_test_first_on_release_pull_requests() -> None:
    workflow = read_file(".github/workflows/ci.yml")

    assert "workflow_call:" in workflow
    assert "github.base_ref != 'main'" in workflow
    assert "pytest infra/tests" in workflow


def test_server_compose_has_no_development_fallbacks() -> None:
    compose = read_file("docker/compose.server.yaml")

    for name in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "APP_DOMAIN", "APP_PORT"):
        assert f"${{{name}:?" in compose
    assert "development-only-secret-key" not in compose
    assert 'DJANGO_DEBUG: "false"' in compose


def test_server_compose_only_exposes_caddy_on_localhost() -> None:
    compose = read_file("docker/compose.server.yaml")

    assert '"127.0.0.1:${APP_PORT:?' in compose
    assert "5432:5432" not in compose
    assert len(re.findall(r"^\s+ports:", compose, flags=re.MULTILINE)) == 1


def test_server_compose_runs_the_release_images() -> None:
    compose = read_file("docker/compose.server.yaml")

    assert "${IMAGE_PREFIX:?" in compose
    for service in ("api", "web", "db"):
        assert f"/{service}:${{IMAGE_TAG:?" in compose


def test_edge_caddy_serves_both_domains_with_the_cloudflare_certificate() -> None:
    caddyfile = read_file("docker/edge/Caddyfile")

    assert "{$PRODUCTION_DOMAIN}" in caddyfile
    assert "{$STAGING_DOMAIN}" in caddyfile
    assert caddyfile.count("tls /etc/caddy/certs/origin.pem") == 2
