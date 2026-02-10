"""Parse git log output into structured commit data."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import Commit, FileChange

_SEPARATOR = "__GIT_XRAY_SEP__"


def parse_repo(
    repo_path: str,
    since: str | None = None,
    max_commits: int = 0,
) -> list[Commit]:
    """Run git log and parse into Commit objects.

    Single git command extracts all needed data — hash, author, timestamp,
    subject, and per-file additions/deletions (numstat).
    """
    path = Path(repo_path).resolve()
    if not (path / ".git").exists() and not _is_bare_repo(path):
        raise RuntimeError(f"Not a git repository: {path}")

    fmt = f"{_SEPARATOR}%n%H%n%an%n%ae%n%at%n%s"
    cmd = [
        "git", "-C", str(path), "log",
        "--all", "--no-merges",
        f"--format={fmt}",
        "--numstat",
    ]
    if since:
        cmd.append(f"--since={since}")
    if max_commits > 0:
        cmd.append(f"-n{max_commits}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")

    return _parse_output(result.stdout)


def get_repo_name(repo_path: str) -> str:
    path = Path(repo_path).resolve()
    name = path.name
    if name.endswith(".git"):
        name = name[:-4] or path.parent.name
    return name


def get_default_branch(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _is_bare_repo(path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _parse_output(output: str) -> list[Commit]:
    commits: list[Commit] = []
    blocks = output.split(_SEPARATOR)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 5:
            continue

        hash_val = lines[0].strip()
        author_name = lines[1].strip()
        author_email = lines[2].strip()

        try:
            timestamp = int(lines[3].strip())
        except ValueError:
            continue

        subject = lines[4].strip()

        files: list[FileChange] = []
        for line in lines[5:]:
            line = line.strip()
            if not line:
                continue
            fc = _parse_numstat_line(line)
            if fc:
                files.append(fc)

        commits.append(Commit(hash_val, author_name, author_email, timestamp, subject, files))

    return commits


_RENAME_BRACE = re.compile(r"\{(.+?) => (.+?)\}")


def _parse_numstat_line(line: str) -> FileChange | None:
    parts = line.split("\t")
    if len(parts) < 3:
        return None

    raw_adds, raw_dels, raw_path = parts[0], parts[1], "\t".join(parts[2:])

    # Binary files show "-" for additions/deletions
    adds = -1 if raw_adds == "-" else int(raw_adds)
    dels = -1 if raw_dels == "-" else int(raw_dels)

    # Resolve rename paths like: path/{old => new}/rest or {old => new}
    path = _resolve_rename(raw_path)

    return FileChange(path, adds, dels)


def _resolve_rename(path: str) -> str:
    match = _RENAME_BRACE.search(path)
    if match:
        # Use the new name
        before = path[:match.start()]
        after = path[match.end():]
        new_part = match.group(2)
        path = before + new_part + after
        # Clean up double slashes
        path = path.replace("//", "/")
    return path
