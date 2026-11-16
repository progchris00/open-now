from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from conftest import load_script

PREFIX = "ghcr.io/progchris00/open-now"


@pytest.fixture(scope="module")
def deploy():
    return load_script("opennow_deploy", "infra/deploy.py")


class FakeShell:
    """Records commands instead of running them."""

    def __init__(
        self,
        *,
        unhealthy_tags: Sequence[str] = (),
        failing_pulls: Sequence[str] = (),
        images: Sequence[str] = (),
        images_in_use: Sequence[str] = (),
    ) -> None:
        self.unhealthy_tags = set(unhealthy_tags)
        self.failing_pulls = set(failing_pulls)
        self.images = list(images)
        self.images_in_use = set(images_in_use)
        self.commands: list[tuple[list[str], dict[str, str]]] = []

    def run(
        self,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
    ) -> None:
        command = list(command)
        env = dict(env or {})
        self.commands.append((command, env))
        tag = env.get("IMAGE_TAG")

        if "up" in command and tag in self.unhealthy_tags:
            raise subprocess.CalledProcessError(1, command)
        if "pull" in command and tag in self.failing_pulls:
            raise subprocess.CalledProcessError(1, command)
        is_removal = command[:3] == ["docker", "image", "rm"]
        if is_removal and command[3] in self.images_in_use:
            raise subprocess.CalledProcessError(1, command)

    def output(self, command: Sequence[str]) -> str:
        self.commands.append((list(command), {}))
        return "\n".join(self.images) + "\n"

    def started_tags(self) -> list[str]:
        return [env["IMAGE_TAG"] for command, env in self.commands if "up" in command]

    def removed_images(self) -> list[str]:
        return [
            command[3]
            for command, _ in self.commands
            if command[:3] == ["docker", "image", "rm"]
        ]


def make_target(deploy, root: Path, environment: str = "staging"):
    (root / environment).mkdir(parents=True, exist_ok=True)
    return deploy.Target(environment=environment, root=root, image_prefix=PREFIX)


def write_state(root: Path, environment: str, current, previous) -> None:
    directory = root / environment
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "release.json").write_text(
        json.dumps({"current": current, "previous": previous})
    )


def read_state(root: Path, environment: str) -> dict:
    return json.loads((root / environment / "release.json").read_text())


def test_first_staging_deploy_records_the_release(deploy, tmp_path: Path) -> None:
    shell = FakeShell()
    target = make_target(deploy, tmp_path)

    state = deploy.deploy(target, "sha-1a2b3c4d5e6f", shell)

    assert state.current == "sha-1a2b3c4d5e6f"
    assert state.previous is None
    assert read_state(tmp_path, "staging") == {
        "current": "sha-1a2b3c4d5e6f",
        "previous": None,
    }
    assert shell.started_tags() == ["sha-1a2b3c4d5e6f"]


def test_deploy_pulls_then_starts_with_the_release_images(
    deploy, tmp_path: Path
) -> None:
    shell = FakeShell()
    target = make_target(deploy, tmp_path)

    deploy.deploy(target, "sha-1a2b3c4d5e6f", shell)

    pull, up = shell.commands[0], shell.commands[1]
    assert "pull" in pull[0]
    assert up[0][-3:] == ["--detach", "--wait", "--remove-orphans"]
    assert up[1] == {"IMAGE_PREFIX": PREFIX, "IMAGE_TAG": "sha-1a2b3c4d5e6f"}


def test_production_release_keeps_the_previous_release(
    deploy, tmp_path: Path
) -> None:
    write_state(tmp_path, "production", "v1.0.0", None)
    shell = FakeShell()
    target = make_target(deploy, tmp_path, "production")

    state = deploy.deploy(target, "v1.0.1", shell)

    assert (state.current, state.previous) == ("v1.0.1", "v1.0.0")
    assert read_state(tmp_path, "production") == {
        "current": "v1.0.1",
        "previous": "v1.0.0",
    }


def test_production_only_accepts_release_tags(deploy, tmp_path: Path) -> None:
    shell = FakeShell()
    target = make_target(deploy, tmp_path, "production")

    with pytest.raises(deploy.DeployError, match="v1.2.3"):
        deploy.deploy(target, "sha-1a2b3c4d5e6f", shell)

    assert shell.commands == []


def test_staging_only_accepts_develop_build_tags(deploy, tmp_path: Path) -> None:
    shell = FakeShell()
    target = make_target(deploy, tmp_path)

    with pytest.raises(deploy.DeployError, match="sha-"):
        deploy.deploy(target, "v1.0.0", shell)


def test_unknown_environment_is_rejected(deploy) -> None:
    with pytest.raises(deploy.DeployError, match="staging or production"):
        deploy.validate_tag("qa", "v1.0.0")


def test_unhealthy_release_restores_the_running_release(
    deploy, tmp_path: Path
) -> None:
    write_state(tmp_path, "production", "v1.0.0", "v0.9.0")
    shell = FakeShell(unhealthy_tags=["v1.1.0"])
    target = make_target(deploy, tmp_path, "production")

    with pytest.raises(deploy.DeployError, match="Restored v1.0.0"):
        deploy.deploy(target, "v1.1.0", shell)

    assert shell.started_tags() == ["v1.1.0", "v1.0.0"]
    assert read_state(tmp_path, "production") == {
        "current": "v1.0.0",
        "previous": "v0.9.0",
    }


def test_unhealthy_first_release_says_there_is_nothing_to_restore(
    deploy, tmp_path: Path
) -> None:
    shell = FakeShell(unhealthy_tags=["sha-1a2b3c4d5e6f"])
    target = make_target(deploy, tmp_path)

    with pytest.raises(deploy.DeployError, match="no earlier release"):
        deploy.deploy(target, "sha-1a2b3c4d5e6f", shell)

    assert not (tmp_path / "staging" / "release.json").exists()


def test_failed_restore_is_reported(deploy, tmp_path: Path) -> None:
    write_state(tmp_path, "production", "v1.0.0", None)
    shell = FakeShell(unhealthy_tags=["v1.1.0", "v1.0.0"])
    target = make_target(deploy, tmp_path, "production")

    with pytest.raises(deploy.DeployError, match="restoring v1.0.0 also failed"):
        deploy.deploy(target, "v1.1.0", shell)


def test_redeploying_the_same_release_keeps_the_previous_one(
    deploy, tmp_path: Path
) -> None:
    write_state(tmp_path, "production", "v1.0.1", "v1.0.0")
    target = make_target(deploy, tmp_path, "production")

    state = deploy.deploy(target, "v1.0.1", FakeShell())

    assert (state.current, state.previous) == ("v1.0.1", "v1.0.0")


def test_rollback_returns_to_the_previous_release(deploy, tmp_path: Path) -> None:
    write_state(tmp_path, "production", "v1.0.1", "v1.0.0")
    shell = FakeShell()
    target = make_target(deploy, tmp_path, "production")

    state = deploy.rollback(target, shell)

    assert (state.current, state.previous) == ("v1.0.0", "v1.0.1")
    assert shell.started_tags() == ["v1.0.0"]
    assert not any("pull" in command for command, _ in shell.commands)
    assert read_state(tmp_path, "production") == {
        "current": "v1.0.0",
        "previous": "v1.0.1",
    }


def test_rollback_without_a_previous_release_fails(deploy, tmp_path: Path) -> None:
    write_state(tmp_path, "production", "v1.0.0", None)
    shell = FakeShell()
    target = make_target(deploy, tmp_path, "production")

    with pytest.raises(deploy.DeployError, match="no previous release"):
        deploy.rollback(target, shell)

    assert shell.commands == []


def test_pruning_keeps_current_and_previous_images_of_both_environments(
    deploy, tmp_path: Path
) -> None:
    write_state(tmp_path, "staging", "sha-bbbbbbbbbbbb", "sha-aaaaaaaaaaaa")
    write_state(tmp_path, "production", "v1.0.0", None)
    shell = FakeShell(
        images=[
            f"{PREFIX}/api:sha-cccccccccccc",
            f"{PREFIX}/api:v0.9.0",
            f"{PREFIX}/web:v1.0.0",
            f"{PREFIX}/db:<none>",
            "caddy:2-alpine",
            "ghcr.io/someone-else/api:v0.1.0",
            f"{PREFIX}/other:v0.9.0",
        ]
    )
    target = make_target(deploy, tmp_path, "staging")

    deploy.deploy(target, "sha-cccccccccccc", shell)

    assert shell.removed_images() == [
        f"{PREFIX}/api:v0.9.0",
    ]
    assert read_state(tmp_path, "staging")["previous"] == "sha-bbbbbbbbbbbb"


def test_pruning_skips_images_that_are_still_in_use(
    deploy, tmp_path: Path, capsys
) -> None:
    shell = FakeShell(
        images=[f"{PREFIX}/api:v0.8.0", f"{PREFIX}/web:v0.8.0"],
        images_in_use=[f"{PREFIX}/api:v0.8.0"],
    )
    target = make_target(deploy, tmp_path, "production")

    deploy.deploy(target, "v1.0.0", shell)

    assert shell.removed_images() == [
        f"{PREFIX}/api:v0.8.0",
        f"{PREFIX}/web:v0.8.0",
    ]
    assert "Kept" in capsys.readouterr().err


def test_compose_command_uses_the_environment_project_and_files(
    deploy, tmp_path: Path
) -> None:
    target = make_target(deploy, tmp_path, "production")

    assert target.compose("ps") == [
        "docker",
        "compose",
        "--project-name",
        "opennow-production",
        "--file",
        str(tmp_path / "production" / "compose.yaml"),
        "--env-file",
        str(tmp_path / "production" / ".env"),
        "ps",
    ]


def test_main_deploys_and_reports_the_release(
    deploy, tmp_path: Path, capsys
) -> None:
    (tmp_path / "staging").mkdir()
    code = deploy.main(
        [
            "deploy",
            "--env",
            "staging",
            "--tag",
            "sha-1a2b3c4d5e6f",
            "--image-prefix",
            PREFIX,
            "--root",
            str(tmp_path),
        ],
        shell=FakeShell(),
    )

    assert code == 0
    assert "staging is now on sha-1a2b3c4d5e6f" in capsys.readouterr().out


def test_main_rolls_back(deploy, tmp_path: Path, capsys) -> None:
    write_state(tmp_path, "production", "v1.0.1", "v1.0.0")

    code = deploy.main(
        [
            "rollback",
            "--env",
            "production",
            "--image-prefix",
            PREFIX,
            "--root",
            str(tmp_path),
        ],
        shell=FakeShell(),
    )

    assert code == 0
    assert "production is now on v1.0.0" in capsys.readouterr().out


def test_main_prints_status(deploy, tmp_path: Path, capsys) -> None:
    write_state(tmp_path, "production", "v1.0.1", "v1.0.0")

    code = deploy.main(
        ["status", "--env", "production", "--root", str(tmp_path)],
        shell=FakeShell(),
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "current": "v1.0.1",
        "previous": "v1.0.0",
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["deploy", "--env", "staging", "--image-prefix", PREFIX], "--tag"),
        (["deploy", "--env", "staging", "--tag", "sha-1a2b3c4"], "--image-prefix"),
        (["rollback", "--env", "staging"], "--image-prefix"),
    ],
)
def test_main_explains_missing_arguments(
    deploy, tmp_path: Path, capsys, arguments: list[str], message: str
) -> None:
    code = deploy.main([*arguments, "--root", str(tmp_path)], shell=FakeShell())

    assert code == 1
    assert message in capsys.readouterr().err


def test_main_reports_a_failed_pull(deploy, tmp_path: Path, capsys) -> None:
    (tmp_path / "production").mkdir()

    code = deploy.main(
        [
            "deploy",
            "--env",
            "production",
            "--tag",
            "v1.0.0",
            "--image-prefix",
            PREFIX,
            "--root",
            str(tmp_path),
        ],
        shell=FakeShell(failing_pulls=["v1.0.0"]),
    )

    assert code == 1
    assert "Error" in capsys.readouterr().err
    assert not (tmp_path / "production" / "release.json").exists()


def test_subprocess_shell_runs_commands(deploy) -> None:
    shell = deploy.SubprocessShell()

    shell.run(["true"], env={"IMAGE_TAG": "v1.0.0"})
    assert shell.output(["printf", "%s", "ready"]) == "ready"

    with pytest.raises(subprocess.CalledProcessError):
        shell.run(["false"])
