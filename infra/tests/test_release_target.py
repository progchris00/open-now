from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import load_script

SHA = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"


@pytest.fixture(scope="module")
def release():
    return load_script("opennow_release_target", "infra/release_target.py")


def test_develop_deploys_to_staging_with_a_commit_tag(release) -> None:
    target = release.resolve("refs/heads/develop", SHA, on_main=False)

    assert target.environment == "staging"
    assert target.image_tag == "sha-1a2b3c4d5e6f"


def test_release_tag_on_main_deploys_to_production(release) -> None:
    target = release.resolve("refs/tags/v1.2.3", SHA, on_main=True)

    assert target.environment == "production"
    assert target.image_tag == "v1.2.3"


def test_release_tag_must_point_at_main(release) -> None:
    with pytest.raises(ValueError, match="Merge develop into main first"):
        release.resolve("refs/tags/v1.2.3", SHA, on_main=False)


@pytest.mark.parametrize("tag", ["v1.2", "1.2.3", "v1.2.3-rc1", "release"])
def test_only_release_tags_deploy_to_production(release, tag: str) -> None:
    with pytest.raises(ValueError, match="v1.2.3"):
        release.resolve(f"refs/tags/{tag}", SHA, on_main=True)


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/feature/x"])
def test_other_branches_do_not_deploy(release, ref: str) -> None:
    with pytest.raises(ValueError, match="does not deploy"):
        release.resolve(ref, SHA, on_main=True)


def test_commit_sha_must_be_a_full_sha(release) -> None:
    with pytest.raises(ValueError, match="commit SHA"):
        release.resolve("refs/heads/develop", "1a2b3c", on_main=False)


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False)])
def test_is_on_main_reads_git_merge_base(
    release, returncode: int, expected: bool
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode)

    assert release.is_on_main(SHA, run=fake_run) is expected
    assert calls == [["git", "merge-base", "--is-ancestor", SHA, "origin/main"]]


def test_is_on_main_fails_when_git_cannot_answer(release) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 128)

    with pytest.raises(ValueError, match="origin/main"):
        release.is_on_main(SHA, run=fake_run)


def test_main_writes_github_outputs(
    release, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    code = release.main(["refs/heads/develop", SHA])

    assert code == 0
    assert output.read_text() == "environment=staging\nimage_tag=sha-1a2b3c4d5e6f\n"


def test_main_checks_main_for_release_tags(
    release, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(release, "is_on_main", lambda sha: True)

    code = release.main(["refs/tags/v1.0.0", SHA])

    assert code == 0
    assert "environment=production" in capsys.readouterr().out


def test_main_explains_why_a_push_does_not_deploy(
    release, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(release, "is_on_main", lambda sha: False)

    code = release.main(["refs/tags/v1.0.0", SHA])

    assert code == 1
    assert "Merge develop into main first" in capsys.readouterr().err


def test_main_shows_usage(release, capsys) -> None:
    assert release.main([]) == 2
    assert "Usage" in capsys.readouterr().out
