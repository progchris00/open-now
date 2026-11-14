from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
TEST_FIRST_CHECK = (
    REPOSITORY_ROOT
    / ".github"
    / "workflows"
    / "scripts"
    / "check_test_first.py"
)


def read_ci_workflow() -> str:
    assert CI_WORKFLOW.is_file(), "CI workflow has not been added"
    return CI_WORKFLOW.read_text()


def test_settings_load_in_ci() -> None:
    workflow = read_ci_workflow()

    assert "python backend/manage.py check" in workflow

    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    from django.conf import settings

    django.setup()

    assert settings.configured


def test_coverage_gate_is_80() -> None:
    workflow = read_ci_workflow()
    vitest_config = (REPOSITORY_ROOT / "web" / "vitest.config.ts").read_text()

    assert "--cov-fail-under=80" in workflow
    assert all(
        f"{metric}: 80" in vitest_config
        for metric in ("lines", "branches", "functions", "statements")
    )


def test_first_commit_check_flags_code_before_tests() -> None:
    assert TEST_FIRST_CHECK.is_file(), "Test-first check has not been added"

    spec = importlib.util.spec_from_file_location(
        "check_test_first",
        TEST_FIRST_CHECK,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    valid, message = module.validate_first_commit(["backend/core/views.py"])

    assert valid is False
    assert "failing-test commit first" in message
    assert module.validate_first_commit(
        [
            "backend/core/tests/test_ci_smoke.py",
            "e2e/smoke.spec.ts",
        ]
    )[0]
