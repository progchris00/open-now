"""Pick the environment and image tag for a push, inside GitHub Actions.

- A push to develop deploys to staging. Images are tagged sha-<12 chars>.
- A release tag like v1.2.3 deploys to production, but only when the tag
  points at a commit on main (develop merged into main, then main tagged).

Usage: release_target.py GITHUB_REF GITHUB_SHA
Writes environment= and image_tag= to $GITHUB_OUTPUT when it is set.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
STAGING_BRANCH = "refs/heads/develop"
TAG_PREFIX = "refs/tags/"


@dataclass(frozen=True)
class Release:
    environment: str
    image_tag: str


def resolve(ref: str, sha: str, on_main: bool) -> Release:
    if not COMMIT_SHA.fullmatch(sha):
        raise ValueError(f"{sha!r} is not a full commit SHA.")

    if ref == STAGING_BRANCH:
        return Release("staging", f"sha-{sha[:12]}")

    if ref.startswith(TAG_PREFIX):
        tag = ref.removeprefix(TAG_PREFIX)
        if not RELEASE_TAG.fullmatch(tag):
            raise ValueError(f"{tag} is not a release tag like v1.2.3.")
        if not on_main:
            raise ValueError(
                f"{tag} does not point at a commit on main. "
                "Merge develop into main first, then tag main."
            )
        return Release("production", tag)

    raise ValueError(
        f"{ref} does not deploy. Only develop and v1.2.3 tags on main deploy."
    )


def is_on_main(
    sha: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    result = run(
        ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
        check=False,
    )
    if result.returncode not in (0, 1):
        raise ValueError("Unable to compare the commit with origin/main.")
    return result.returncode == 0


def main(arguments: Sequence[str]) -> int:
    if len(arguments) != 2:
        print("Usage: release_target.py GITHUB_REF GITHUB_SHA")
        return 2

    ref, sha = arguments
    try:
        on_main = ref.startswith(TAG_PREFIX) and is_on_main(sha)
        release = resolve(ref, sha, on_main)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    lines = f"environment={release.environment}\nimage_tag={release.image_tag}\n"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(lines)
    print(lines, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
