"""CLI entry point for git-xray."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime

from . import __version__
from .analysis import (
    analyze_bus_factor,
    analyze_complexity_trend,
    analyze_coupling,
    analyze_hotspots,
    analyze_knowledge_decay,
)
from .display import (
    print_bus_factor,
    print_complexity_trend,
    print_coupling,
    print_footer,
    print_header,
    print_hotspots,
    print_knowledge_decay,
)
from .parser import get_default_branch, get_repo_name, parse_repo

ALL_SECTIONS = ["hotspots", "bus-factor", "coupling", "decay", "trend"]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="git-xray",
        description="Reveal hidden risks in any git repository.",
    )
    p.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to git repository (default: current directory)",
    )
    p.add_argument(
        "--top", "-n",
        type=int,
        default=10,
        help="Number of results per section (default: 10)",
    )
    p.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only analyze commits since date (e.g. '2023-01-01', '1 year ago')",
    )
    p.add_argument(
        "--section", "-s",
        type=str,
        action="append",
        choices=ALL_SECTIONS,
        help="Only show specific section(s). Can be repeated.",
    )
    p.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Directory depth for bus-factor analysis (default: 2)",
    )
    p.add_argument(
        "--active-days",
        type=int,
        default=90,
        help="Days since last commit to consider an author active (default: 90)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    p.add_argument(
        "--version", "-v",
        action="version",
        version=f"git-xray {__version__}",
    )
    return p


def _run_analysis(args: argparse.Namespace) -> dict:
    sections = set(args.section) if args.section else set(ALL_SECTIONS)

    t0 = time.time()
    sys.stderr.write("  Parsing git history... ")
    sys.stderr.flush()

    commits = parse_repo(args.repo, since=args.since)

    elapsed = time.time() - t0
    sys.stderr.write(f"done ({len(commits):,} commits in {elapsed:.1f}s)\n")

    if not commits:
        sys.stderr.write("  No commits found.\n")
        sys.exit(1)

    results: dict = {"commits": commits}

    if "hotspots" in sections:
        sys.stderr.write("  Analyzing hotspots...\n")
        results["hotspots"] = analyze_hotspots(commits, top_n=args.top)

    if "bus-factor" in sections:
        sys.stderr.write("  Analyzing bus factor...\n")
        results["bus_factor"] = analyze_bus_factor(commits, top_n=args.top, dir_depth=args.depth)

    if "coupling" in sections:
        sys.stderr.write("  Analyzing coupling...\n")
        results["coupling"] = analyze_coupling(commits, top_n=args.top)

    if "decay" in sections:
        sys.stderr.write("  Analyzing knowledge decay...\n")
        results["decay"] = analyze_knowledge_decay(commits, top_n=args.top, active_days=args.active_days)

    if "trend" in sections:
        sys.stderr.write("  Analyzing complexity trend...\n")
        results["trend"] = analyze_complexity_trend(commits)

    sys.stderr.write("\n")
    return results


def _json_serializer(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        results = _run_analysis(args)
    except RuntimeError as e:
        sys.stderr.write(f"\n  Error: {e}\n\n")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.stderr.write("\n  Interrupted.\n")
        sys.exit(130)

    commits = results["commits"]

    if args.json_output:
        output = {}
        for key in ("hotspots", "bus_factor", "coupling", "decay", "trend"):
            if key in results:
                output[key] = [asdict(r) for r in results[key]]
        json.dump(output, sys.stdout, indent=2, default=_json_serializer)
        sys.stdout.write("\n")
        return

    # Collect stats for header
    all_authors = {c.author_email for c in commits}
    all_files = set()
    for c in commits:
        for f in c.files:
            all_files.add(f.path)

    dates = sorted(c.date for c in commits)
    repo_name = get_repo_name(args.repo)
    branch = get_default_branch(args.repo)

    print_header(repo_name, branch, len(commits), len(all_authors), len(all_files), dates[0], dates[-1])

    if "hotspots" in results:
        print_hotspots(results["hotspots"])
    if "bus_factor" in results:
        print_bus_factor(results["bus_factor"])
    if "coupling" in results:
        print_coupling(results["coupling"])
    if "decay" in results:
        print_knowledge_decay(results["decay"])
    if "trend" in results:
        print_complexity_trend(results["trend"])

    print_footer()


if __name__ == "__main__":
    main()
