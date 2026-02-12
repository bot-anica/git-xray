# git-xray

Reveal hidden risks in any git repository. Zero dependencies, pure Python.

Point it at a repo and get an instant report on bus factor, change hotspots, hidden coupling between files, knowledge decay, and complexity trends — all from git history alone.

```
pip install git-xray-cli
git-xray /path/to/repo
```

## What it finds

| Analysis | What it reveals |
|---|---|
| **Hotspots** | Files that change most often with highest churn — statistically where bugs concentrate |
| **Bus Factor** | Directories where 1-2 people own all knowledge — team risk if they leave |
| **Hidden Coupling** | Files in different directories that always change together — hidden architectural dependencies |
| **Knowledge Decay** | Code last modified by people no longer active on the project |
| **Complexity Trend** | Whether average churn per commit is rising — a sign the codebase is getting harder to maintain |

## Example output

```
──────────────────────────────────────────────────────────────────────
  GIT X-RAY  v0.1.2
  my-project  ·  main
  4,300 commits  ·  60 authors  ·  4,404 files
  Jun 14, 2025 — Feb 10, 2026 (241 days)
──────────────────────────────────────────────────────────────────────

  HOTSPOTS  files with highest change frequency
──────────────────────────────────────────────────────────────────────
  RISK   FILE                                       COMMITS         CHURN

  ▓▓▓▓▓▓▓▓▓░ shared/types.ts                              448     +4,516/-3,245
  ▓▓▓▓▓▓▓▓░░ package.json                                 397       +554/-497
  ▓▓▓▓▓▓▓░░░ crates/server/src/routes/task_attempts.rs    265     +9,690/-6,866

  BUS FACTOR  knowledge concentration risk
──────────────────────────────────────────────────────────────────────

  CRITICAL  frontend/src/                        bus factor: 1
             ██████████████████████████████████░░░░░░
             louis 61% · alex 12% · gabriel 6%

  CRITICAL  backend/src/                         bus factor: 1
             █████████████████████████████████████░░░
             louis 61% · anastasiya 11% · gabriel 5%

  HIDDEN COUPLING  files that always change together
──────────────────────────────────────────────────────────────────────

  100%  KanbanContainer.tsx
        <--->  AssigneeDropdown.tsx
        6 shared commits  (cross-directory!)

  COMPLEXITY TREND  is the codebase getting harder to change?
──────────────────────────────────────────────────────────────────────

  2025 Q3  ▓▓▓▓▓▓▓▓▓▓▓░░░░  avg 286 lines/commit (1,440 commits)
  2025 Q4  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  avg 381 lines/commit (1,285 commits)  ^
  2026 Q1  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  avg 367 lines/commit (1,233 commits)

  >> Complexity is trending UP.
```

## Usage

```bash
# Full report on current directory
git-xray

# Analyze a specific repo
git-xray /path/to/repo

# Only show specific sections
git-xray . --section hotspots
git-xray . --section bus-factor --section coupling

# Limit to recent history
git-xray . --since "6 months ago"
git-xray . --since "2024-01-01"

# More results per section
git-xray . --top 20

# Machine-readable output
git-xray . --json

# Adjust bus-factor directory depth
git-xray . --depth 3

# Change "active author" threshold (default: 90 days)
git-xray . --active-days 180
```

## Installation

Requires Python 3.9+ and git. No other dependencies.

```bash
# From PyPI
pip install git-xray-cli

# From source
git clone https://github.com/bot-anica/git-xray
cd git-xray
pip install .

# Or just run directly
python3 -m git_xray /path/to/repo
```

## How it works

Git X-Ray runs a single `git log --numstat` command and parses the output in one pass. All analysis is done in-memory. No network calls, no external services, no data leaves your machine.

**Performance:** Parses ~4,000 commits in under 2 seconds.

### Analysis details

**Hotspots** rank files by a weighted score: 60% change frequency + 40% normalized churn magnitude. Lock files and generated assets are automatically excluded.

**Bus Factor** calculates the minimum number of authors needed to cover >50% of commits per directory. CRITICAL = bus factor of 1 (single point of failure).

**Hidden Coupling** uses confidence-based co-change analysis: `coupling(A, B) = co_commits / min(commits_A, commits_B)`. Commits touching >30 files are excluded as noise (bulk reformats, merges). Cross-directory coupling is prioritized.

**Knowledge Decay** identifies files where the last modifier hasn't committed in N days (default: 90). STALE = author inactive + file untouched for 6+ months.

**Complexity Trend** tracks average churn (additions + deletions) per commit by quarter. Rising averages suggest the codebase is becoming harder to work with.

## JSON output

Use `--json` for machine-readable output suitable for CI dashboards:

```bash
git-xray . --json | jq '.bus_factor[] | select(.risk == "CRITICAL")'
```

## License

MIT
