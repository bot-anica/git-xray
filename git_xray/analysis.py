"""Core analysis algorithms for git repository insights."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations

from .models import (
    BusFactorEntry,
    Commit,
    CouplingEntry,
    DecayEntry,
    Hotspot,
    TrendPeriod,
)


# Files that generate noise in hotspot analysis — auto-generated or vendored
_NOISY_PATTERNS = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock",
    "poetry.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock",
    "go.sum", ".min.js", ".min.css", ".map",
)


def _is_noisy(path: str) -> bool:
    return any(path.endswith(p) for p in _NOISY_PATTERNS)


def analyze_hotspots(commits: list[Commit], top_n: int = 15) -> list[Hotspot]:
    """Find files with highest change frequency and churn.

    These are statistically where most bugs live — files that change often
    and change a lot are the riskiest parts of the codebase.
    """
    file_commits: dict[str, int] = defaultdict(int)
    file_adds: dict[str, int] = defaultdict(int)
    file_dels: dict[str, int] = defaultdict(int)

    for commit in commits:
        seen = set()
        for fc in commit.files:
            if _is_noisy(fc.path):
                continue
            if fc.path not in seen:
                file_commits[fc.path] += 1
                seen.add(fc.path)
            if fc.additions >= 0:
                file_adds[fc.path] += fc.additions
            if fc.deletions >= 0:
                file_dels[fc.path] += fc.deletions

    if not file_commits:
        return []

    # Risk score: combines frequency and churn magnitude
    max_commits = max(file_commits.values())
    max_churn = max((file_adds[f] + file_dels[f]) for f in file_commits) or 1

    hotspots = []
    for path, count in file_commits.items():
        adds = file_adds[path]
        dels = file_dels[path]
        churn = adds + dels
        freq_norm = count / max_commits
        churn_norm = math.log1p(churn) / math.log1p(max_churn)
        risk = 0.6 * freq_norm + 0.4 * churn_norm
        hotspots.append(Hotspot(path, count, adds, dels, churn, risk))

    hotspots.sort(key=lambda h: h.risk_score, reverse=True)
    return hotspots[:top_n]


def analyze_bus_factor(
    commits: list[Commit],
    top_n: int = 15,
    dir_depth: int = 2,
) -> list[BusFactorEntry]:
    """Calculate bus factor per directory.

    Bus factor = minimum number of people who need to leave before
    a directory has lost >50% of its institutional knowledge.
    """
    dir_author_commits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in commits:
        seen_dirs: set[str] = set()
        for fc in commit.files:
            parts = fc.path.split("/")
            # Aggregate at specified depth
            if len(parts) > dir_depth:
                d = "/".join(parts[:dir_depth]) + "/"
            elif len(parts) > 1:
                d = "/".join(parts[:-1]) + "/"
            else:
                d = "(root)"
            if d not in seen_dirs:
                dir_author_commits[d][commit.author_email] += 1
                seen_dirs.add(d)

    results = []
    for directory, authors in dir_author_commits.items():
        total = sum(authors.values())
        if total < 5:  # skip dirs with very few commits
            continue

        # Sort authors by contribution descending
        sorted_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)

        # Calculate bus factor: minimum authors to cover >50% of commits
        cumulative = 0
        bus_factor = 0
        for _, count in sorted_authors:
            cumulative += count
            bus_factor += 1
            if cumulative > total * 0.5:
                break

        # Build top contributors list (name, commits, percentage)
        top_contribs = [
            (name, count, count / total * 100)
            for name, count in sorted_authors[:5]
        ]

        if bus_factor == 1:
            risk = "CRITICAL"
        elif bus_factor == 2:
            risk = "WARNING"
        else:
            risk = "OK"

        results.append(BusFactorEntry(directory, bus_factor, total, top_contribs, risk))

    # Sort: CRITICAL first, then WARNING, then by commit count
    risk_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2}
    results.sort(key=lambda r: (risk_order[r.risk], -r.total_commits))
    return results[:top_n]


def analyze_coupling(
    commits: list[Commit],
    top_n: int = 15,
    min_commits: int = 5,
    min_coupling: float = 0.4,
) -> list[CouplingEntry]:
    """Find files that always change together — especially across directories.

    Uses confidence-based coupling: coupling(A,B) = co_commits / min(commits_A, commits_B).
    High coupling between files in different directories often signals hidden
    architectural dependencies that should be made explicit.
    """
    # Count commits per file
    file_commit_count: dict[str, int] = defaultdict(int)
    # Count co-occurrences
    pair_count: dict[tuple[str, str], int] = defaultdict(int)

    for commit in commits:
        files_in_commit = list({fc.path for fc in commit.files})

        for f in files_in_commit:
            file_commit_count[f] += 1

        # Only compute pairs for commits with a reasonable number of files
        # (huge commits like merges or reformats are noise)
        if 2 <= len(files_in_commit) <= 30:
            for a, b in combinations(sorted(files_in_commit), 2):
                pair_count[(a, b)] += 1

    results = []
    for (file_a, file_b), co_count in pair_count.items():
        count_a = file_commit_count[file_a]
        count_b = file_commit_count[file_b]

        if count_a < min_commits or count_b < min_commits:
            continue
        if co_count < 3:
            continue

        score = co_count / min(count_a, count_b)
        if score < min_coupling:
            continue

        dir_a = "/".join(file_a.split("/")[:-1])
        dir_b = "/".join(file_b.split("/")[:-1])
        cross = dir_a != dir_b

        results.append(CouplingEntry(
            file_a, file_b, score, co_count, count_a, count_b, cross,
        ))

    # Prioritize cross-directory coupling (that's the hidden stuff)
    results.sort(key=lambda c: (-int(c.cross_directory), -c.score))
    return results[:top_n]


def analyze_knowledge_decay(
    commits: list[Commit],
    top_n: int = 15,
    active_days: int = 90,
) -> list[DecayEntry]:
    """Find code that's maintained by people who are no longer active.

    A file is at risk when the last person who understood it (last to modify)
    hasn't committed anything recently — they may have left the team.
    """
    now = datetime.now()
    active_cutoff = now - timedelta(days=active_days)

    # Determine active authors (committed within active_days)
    author_last_seen: dict[str, datetime] = {}
    for commit in commits:
        dt = commit.date
        email = commit.author_email
        if email not in author_last_seen or dt > author_last_seen[email]:
            author_last_seen[email] = dt

    active_authors = {
        email for email, last in author_last_seen.items()
        if last >= active_cutoff
    }

    # Find last touch per file
    file_last_touch: dict[str, tuple[str, str, datetime]] = {}
    for commit in commits:
        dt = commit.date
        for fc in commit.files:
            if fc.path not in file_last_touch or dt > file_last_touch[fc.path][2]:
                file_last_touch[fc.path] = (commit.author_name, commit.author_email, dt)

    results = []
    for path, (author_name, author_email, last_date) in file_last_touch.items():
        days_stale = (now - last_date).days
        is_active = author_email in active_authors

        if days_stale < 30:
            risk = "FRESH"
        elif not is_active:
            risk = "STALE"
        elif days_stale > 180:
            risk = "AGING"
        else:
            risk = "FRESH"

        if risk == "FRESH":
            continue  # only report concerning files

        results.append(DecayEntry(path, author_name, last_date, days_stale, is_active, risk))

    risk_order = {"STALE": 0, "AGING": 1, "FRESH": 2}
    results.sort(key=lambda d: (risk_order[d.risk], -d.days_stale))
    return results[:top_n]


def analyze_complexity_trend(
    commits: list[Commit],
) -> list[TrendPeriod]:
    """Track how code churn changes over time.

    Rising average churn per commit suggests growing complexity — each change
    touches more code, a sign the codebase is becoming harder to work with.
    """
    if not commits:
        return []

    # Group commits by quarter
    quarters: dict[str, list[Commit]] = defaultdict(list)

    for commit in commits:
        dt = commit.date
        q = (dt.month - 1) // 3 + 1
        label = f"{dt.year} Q{q}"
        quarters[label] = quarters.get(label, [])
        quarters[label].append(commit)

    # Sort chronologically
    sorted_labels = sorted(quarters.keys())

    results = []
    prev_avg: float | None = None

    for label in sorted_labels:
        period_commits = quarters[label]
        total_adds = 0
        total_dels = 0
        files_touched: set[str] = set()

        for commit in period_commits:
            for fc in commit.files:
                files_touched.add(fc.path)
                if fc.additions >= 0:
                    total_adds += fc.additions
                if fc.deletions >= 0:
                    total_dels += fc.deletions

        churn = total_adds + total_dels
        avg_churn = churn / len(period_commits) if period_commits else 0

        if prev_avg is None:
            direction = "STABLE"
        elif avg_churn > prev_avg * 1.15:
            direction = "UP"
        elif avg_churn < prev_avg * 0.85:
            direction = "DOWN"
        else:
            direction = "STABLE"

        results.append(TrendPeriod(
            label, len(period_commits), total_adds, total_dels,
            avg_churn, len(files_touched), direction,
        ))
        prev_avg = avg_churn

    return results
