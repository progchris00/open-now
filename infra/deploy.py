"""Deploy, roll back or inspect an OpenNow release on the Oracle server.

This script runs on the server with the system Python 3 and the standard
library only. Each environment lives in its own folder under the root:

    /srv/opennow/staging/      compose.yaml, Caddyfile, .env, release.json
    /srv/opennow/production/   compose.yaml, Caddyfile, .env, release.json

release.json records the running release and the one before it, so a
rollback is one step and the previous images are never pruned.

    python3 deploy.py deploy --env staging --tag sha-1a2b3c4d5e6f \
        --image-prefix ghcr.io/progchris00/open-now
    python3 deploy.py rollback --env production \
        --image-prefix ghcr.io/progchris00/open-now
    python3 deploy.py status --env production
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

ENVIRONMENTS = ("staging", "production")
SERVICES = ("api", "web", "db")
DEFAULT_ROOT = Path("/srv/opennow")
STATE_FILE = "release.json"
COMPOSE_FILE = "compose.yaml"
ENV_FILE = ".env"

RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")
BUILD_TAG = re.compile(r"sha-[0-9a-f]{7,40}")


class DeployError(Exception):
    """A deploy or rollback could not finish."""


class Shell(Protocol):
    def run(
        self,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
    ) -> None: ...

    def output(self, command: Sequence[str]) -> str: ...


class SubprocessShell:
    """Runs commands on this machine and raises when one fails."""

    def run(
        self,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
    ) -> None:
        subprocess.run(list(command), check=True, env={**os.environ, **(env or {})})

    def output(self, command: Sequence[str]) -> str:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


@dataclass(frozen=True)
class ReleaseState:
    current: str | None = None
    previous: str | None = None

    def kept_tags(self) -> set[str]:
        return {tag for tag in (self.current, self.previous) if tag}


@dataclass(frozen=True)
class Target:
    environment: str
    root: Path
    image_prefix: str

    @property
    def directory(self) -> Path:
        return self.root / self.environment

    @property
    def state_path(self) -> Path:
        return self.directory / STATE_FILE

    def compose(self, *arguments: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            f"opennow-{self.environment}",
            "--file",
            str(self.directory / COMPOSE_FILE),
            "--env-file",
            str(self.directory / ENV_FILE),
            *arguments,
        ]

    def release_env(self, tag: str) -> dict[str, str]:
        return {"IMAGE_PREFIX": self.image_prefix, "IMAGE_TAG": tag}


def validate_tag(environment: str, tag: str) -> None:
    if environment not in ENVIRONMENTS:
        raise DeployError(
            f"Unknown environment {environment!r}. Use staging or production."
        )

    if environment == "production" and not RELEASE_TAG.fullmatch(tag):
        raise DeployError(
            f"Production only runs release tags like v1.2.3, not {tag!r}."
        )

    if environment == "staging" and not BUILD_TAG.fullmatch(tag):
        raise DeployError(
            f"Staging only runs develop builds tagged like sha-1a2b3c4, not {tag!r}."
        )


def load_state(path: Path) -> ReleaseState:
    if not path.exists():
        return ReleaseState()

    data = json.loads(path.read_text())
    return ReleaseState(current=data.get("current"), previous=data.get("previous"))


def save_state(path: Path, state: ReleaseState) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(asdict(state), indent=2) + "\n")
    temporary.replace(path)


def start(target: Target, shell: Shell, tag: str) -> None:
    shell.run(
        target.compose("up", "--detach", "--wait", "--remove-orphans"),
        env=target.release_env(tag),
    )


def deploy(target: Target, tag: str, shell: Shell) -> ReleaseState:
    """Start a release, or put the running one back if it fails its checks."""
    validate_tag(target.environment, tag)
    state = load_state(target.state_path)

    shell.run(target.compose("pull"), env=target.release_env(tag))

    try:
        start(target, shell, tag)
    except subprocess.CalledProcessError as error:
        if state.current is None:
            raise DeployError(
                f"Release {tag} failed its health checks and there is "
                "no earlier release to restore."
            ) from error

        try:
            start(target, shell, state.current)
        except subprocess.CalledProcessError as restore_error:
            raise DeployError(
                f"Release {tag} failed its health checks, and restoring "
                f"{state.current} also failed. Check the server now."
            ) from restore_error

        raise DeployError(
            f"Release {tag} failed its health checks. Restored {state.current}."
        ) from error

    if tag == state.current:
        new_state = state
    else:
        new_state = ReleaseState(current=tag, previous=state.current)

    save_state(target.state_path, new_state)
    prune_images(target, shell)
    return new_state


def rollback(target: Target, shell: Shell) -> ReleaseState:
    """Swap the running release for the previous one."""
    state = load_state(target.state_path)

    if state.previous is None:
        raise DeployError(
            f"{target.environment} has no previous release to roll back to."
        )

    start(target, shell, state.previous)
    new_state = ReleaseState(current=state.previous, previous=state.current)
    save_state(target.state_path, new_state)
    return new_state


def kept_tags(root: Path) -> set[str]:
    """Tags still needed by either environment, now or for a rollback."""
    tags: set[str] = set()
    for environment in ENVIRONMENTS:
        tags |= load_state(root / environment / STATE_FILE).kept_tags()
    return tags


def images_to_remove(listing: str, image_prefix: str, keep: set[str]) -> list[str]:
    removable = []
    repositories = {f"{image_prefix}/{service}" for service in SERVICES}

    for line in listing.splitlines():
        reference = line.strip()
        repository, _, tag = reference.rpartition(":")

        if repository not in repositories or tag in ("", "<none>"):
            continue
        if tag not in keep:
            removable.append(reference)

    return removable


def prune_images(target: Target, shell: Shell) -> None:
    listing = shell.output(
        ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]
    )

    for reference in images_to_remove(
        listing, target.image_prefix, kept_tags(target.root)
    ):
        try:
            shell.run(["docker", "image", "rm", reference])
        except subprocess.CalledProcessError:
            print(f"Kept {reference} because it is still in use.", file=sys.stderr)


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("deploy", "rollback", "status"))
    parser.add_argument("--env", required=True, choices=ENVIRONMENTS)
    parser.add_argument("--tag", help="Image tag to deploy.")
    parser.add_argument(
        "--image-prefix",
        help="Registry path of the images, for example ghcr.io/owner/repo.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str], shell: Shell | None = None) -> int:
    arguments = parse_arguments(argv)
    shell = shell or SubprocessShell()
    target = Target(arguments.env, arguments.root, arguments.image_prefix or "")

    try:
        if arguments.command == "status":
            print(json.dumps(asdict(load_state(target.state_path))))
            return 0

        if not arguments.image_prefix:
            raise DeployError("--image-prefix is required for deploy and rollback.")

        if arguments.command == "deploy":
            if not arguments.tag:
                raise DeployError("--tag is required for deploy.")
            state = deploy(target, arguments.tag, shell)
        else:
            state = rollback(target, shell)
    except (DeployError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(
        f"{target.environment} is now on {state.current} "
        f"(previous: {state.previous or 'none'})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
