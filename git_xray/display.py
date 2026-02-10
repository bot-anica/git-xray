"""Terminal output formatting with ANSI colors."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from .models import (
    BusFactorEntry,
    CouplingEntry,
    DecayEntry,
    Hotspot,
    TrendPeriod,
)


# ── ANSI color codes ──────────────────────────────────────────────────────────

def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def dim(t: str) -> str:
    return _c("2", t)


def bold(t: str) -> str:
    return _c("1", t)


def red(t: str) -> str:
    return _c("91", t)


def yellow(t: str) -> str:
    return _c("93", t)


def green(t: str) -> str:
    return _c("92", t)


def cyan(t: str) -> str:
    return _c("96", t)


def white(t: str) -> str:
    return _c("97", t)


def magenta(t: str) -> str:
    return _c("95", t)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _bar(value: float, width: int = 10) -> str:
    filled = round(value * width)
    return "\u2593" * filled + "\u2591" * (width - filled)


def _risk_colored(risk: str) -> str:
    if risk == "CRITICAL":
        return red(bold("CRITICAL"))
    if risk == "WARNING":
        return yellow("WARNING ")
    if risk == "STALE":
        return red(bold("STALE  "))
    if risk == "AGING":
        return yellow("AGING  ")
    return green("OK      ")


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return "..." + s[-(max_len - 3):]


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'s' if n != 1 else ''}"


def _line(width: int = 70) -> str:
    return dim("\u2500" * width)


def _format_date(dt: datetime) -> str:
    return dt.strftime("%b %d, %Y")


def _pct_bar(entries: list[tuple[str, float]], width: int = 40) -> str:
    """Render a stacked percentage bar for contributors."""
    colors = [white, cyan, yellow, magenta, dim]
    bar = ""
    for i, (name, pct) in enumerate(entries):
        seg_len = max(1, round(pct / 100 * width))
        color_fn = colors[i % len(colors)]
        bar += color_fn("\u2588" * seg_len)
    remaining = width - sum(max(1, round(p / 100 * width)) for _, p in entries)
    if remaining > 0:
        bar += dim("\u2591" * remaining)
    return bar


# ── Section renderers ─────────────────────────────────────────────────────────

def print_header(
    repo_name: str,
    branch: str,
    total_commits: int,
    total_authors: int,
    total_files: int,
    first_date: datetime,
    last_date: datetime,
) -> None:
    days = (last_date - first_date).days
    w = 70

    print()
    print(_line(w))
    print(bold(white("  GIT X-RAY")) + dim("  v0.1.0"))
    print(f"  {bold(repo_name)}  {dim('·')}  {dim(branch)}")
    print(
        f"  {_plural(total_commits, 'commit')}  {dim('·')}  "
        f"{_plural(total_authors, 'author')}  {dim('·')}  "
        f"{_plural(total_files, 'file')}"
    )
    print(f"  {_format_date(first_date)} {dim('—')} {_format_date(last_date)} {dim(f'({days:,} days)')}")
    print(_line(w))
    print()


def print_hotspots(hotspots: list[Hotspot]) -> None:
    if not hotspots:
        return

    print(bold(cyan("  HOTSPOTS")) + dim("  files with highest change frequency"))
    print(_line(70))
    print(dim(f"  {'RISK':<6} {'FILE':<42} {'COMMITS':>7}  {'CHURN':>12}"))
    print()

    for h in hotspots:
        bar = _bar(h.risk_score)
        path = _truncate(h.path, 40)
        churn = f"+{h.total_additions:,}/-{h.total_deletions:,}"

        if h.risk_score > 0.7:
            path_str = red(f"{path:<42}")
        elif h.risk_score > 0.4:
            path_str = yellow(f"{path:<42}")
        else:
            path_str = f"{path:<42}"

        print(f"  {bar} {path_str} {h.commit_count:>5}  {dim(churn):>20}")

    print()


def print_bus_factor(entries: list[BusFactorEntry]) -> None:
    if not entries:
        return

    print(bold(cyan("  BUS FACTOR")) + dim("  knowledge concentration risk"))
    print(_line(70))
    print()

    for entry in entries:
        risk_str = _risk_colored(entry.risk)
        dir_str = bold(f"{entry.directory:<35}")
        bf_str = dim(f"bus factor: {entry.bus_factor}")

        print(f"  {risk_str}  {dir_str}  {bf_str}")

        # Contributor bar
        contrib_parts = [(name, pct) for name, _, pct in entry.top_contributors]
        bar = _pct_bar(contrib_parts)
        print(f"             {bar}")

        # Legend
        legend_parts = []
        for name, commits, pct in entry.top_contributors[:4]:
            # Use email handle as display name (shorter)
            short_name = name.split("@")[0] if "@" in name else name
            if len(short_name) > 12:
                short_name = short_name[:11] + "."
            legend_parts.append(f"{short_name} {dim(f'{pct:.0f}%')}")
        print(f"             {dim(' · ').join(legend_parts)}")
        print()

    print()


def print_coupling(entries: list[CouplingEntry]) -> None:
    if not entries:
        return

    print(bold(cyan("  HIDDEN COUPLING")) + dim("  files that always change together"))
    print(_line(70))
    print()

    for c in entries:
        pct = f"{c.score * 100:.0f}%"
        if c.cross_directory:
            pct_str = red(bold(f"{pct:>4}"))
            tag = red(" (cross-directory!)")
        else:
            pct_str = yellow(f"{pct:>4}")
            tag = ""

        path_a = _truncate(c.file_a, 32)
        path_b = _truncate(c.file_b, 32)

        print(f"  {pct_str}  {path_a}")
        print(f"        {dim('<--->')}  {path_b}")
        print(f"        {dim(f'{c.co_commits} shared commits  (file A: {c.total_a}, file B: {c.total_b})')}{tag}")
        print()

    print()


def print_knowledge_decay(entries: list[DecayEntry]) -> None:
    if not entries:
        return

    print(bold(cyan("  KNOWLEDGE DECAY")) + dim("  code without active maintainers"))
    print(_line(70))
    print()

    for d in entries:
        risk_str = _risk_colored(d.risk)
        path_str = _truncate(d.path, 38)
        active_str = dim("still active") if d.author_active else red("no longer active")
        date_str = _format_date(d.last_date)

        print(f"  {risk_str}  {path_str:<40}")
        print(f"             last: {d.last_author}, {date_str} ({d.days_stale}d ago) — {active_str}")
        print()

    print()


def print_complexity_trend(periods: list[TrendPeriod]) -> None:
    if not periods:
        return

    print(bold(cyan("  COMPLEXITY TREND")) + dim("  is the codebase getting harder to change?"))
    print(_line(70))
    print()

    max_avg = max(p.avg_churn for p in periods) or 1

    for p in periods:
        bar_val = p.avg_churn / max_avg
        bar = _bar(bar_val, 15)

        if p.direction == "UP":
            arrow = red(" ^")
        elif p.direction == "DOWN":
            arrow = green(" v")
        else:
            arrow = dim("  ")

        avg_str = f"avg {p.avg_churn:,.0f} lines/commit"
        count_str = dim(f"({_plural(p.commit_count, 'commit')})")

        print(f"  {dim(p.label)}  {bar}  {avg_str} {count_str}{arrow}")

    # Overall trend
    if len(periods) >= 3:
        first_third = sum(p.avg_churn for p in periods[:len(periods)//3]) / (len(periods)//3)
        last_third = sum(p.avg_churn for p in periods[-len(periods)//3:]) / (len(periods)//3)
        if last_third > first_third * 1.3:
            print()
            print(f"  {red(bold('>> Complexity is trending UP.'))} Changes touch more code over time.")
        elif last_third < first_third * 0.7:
            print()
            print(f"  {green(bold('>> Complexity is trending DOWN.'))} Codebase is getting cleaner.")
        else:
            print()
            print(f"  {dim('>> Complexity is stable.')}")

    print()


def print_footer() -> None:
    print(_line(70))
    print(dim("  git x-ray  ·  https://github.com/bot-anica/git-xray"))
    print()
