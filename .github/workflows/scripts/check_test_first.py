from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import PurePosixPath


def is_test_file(path: str) -> bool:
    file_path = PurePosixPath(path)
    parts = file_path.parts
    name = file_path.name

    return (
        "tests" in parts
        or "__tests__" in parts
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )


def validate_first_commit(paths: Sequence[str]) -> tuple[bool, str]:
    changed_paths = [path.strip() for path in paths if path.strip()]
    production_paths = [path for path in changed_paths if not is_test_file(path)]

    if not changed_paths:
        return False, "The first branch commit does not contain any test files."

    if production_paths:
        files = "\n".join(f"  - {path}" for path in production_paths)
        return (
            False,
            (
                "Add the failing-test commit first. The first branch commit "
                f"contains non-test files:\n{files}"
            ),
        )

    return True, "The first branch commit contains test files only."


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def first_branch_commit(base_revision: str, head_revision: str) -> str:
    merge_base = git_output("merge-base", base_revision, head_revision)
    commits = git_output(
        "rev-list",
        "--reverse",
        f"{merge_base}..{head_revision}",
    ).splitlines()

    if not commits:
        raise ValueError("The pull request does not contain any commits.")

    return commits[0]


def changed_files(commit: str) -> list[str]:
    return git_output(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        commit,
    ).splitlines()


def main(arguments: Sequence[str]) -> int:
    if len(arguments) != 2:
        print("Usage: check_test_first.py BASE_REVISION HEAD_REVISION")
        return 2

    try:
        commit = first_branch_commit(arguments[0], arguments[1])
        valid, message = validate_first_commit(changed_files(commit))
    except (subprocess.CalledProcessError, ValueError) as error:
        print(f"Unable to check the first branch commit: {error}")
        return 1

    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
