#!/usr/bin/env python3
"""Generate a combined GitHub + GitLab contribution heatmap SVG.

Sources (both public, no private code is touched):
  - GitHub: GraphQL contributionsCollection for user HaziqShake
    (needs a token; in GitHub Actions the automatic GITHUB_TOKEN works)
  - GitLab: https://gitlab.com/users/HaziqShake/calendar.json (public)

Usage:
  python3 generate_combined_graph.py [--out combined-contributions.svg]
  python3 generate_combined_graph.py --github-json github.json --gitlab-json gitlab.json

Only contribution counts per date are used. No repository code is read.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import date

GITHUB_USER = "HaziqShake"
GITLAB_USER = "HaziqShake"

CELL = 10
GAP = 3
PITCH = CELL + GAP
LEFT_PAD = 28
TOP_PAD = 24
BOTTOM_PAD = 30

# GitHub light-theme green scale.
COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


def color_for(count):
    if count == 0:
        return COLORS[0]
    if count <= 2:
        return COLORS[1]
    if count <= 5:
        return COLORS[2]
    if count <= 9:
        return COLORS[3]
    return COLORS[4]


def fetch_github_counts(token):
    query = """
    query {
      user(login: "%s") {
        contributionsCollection {
          totalContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """ % GITHUB_USER
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    coll = data["data"]["user"]["contributionsCollection"]
    counts = {}
    for week in coll["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            counts[day["date"]] = day["contributionCount"]
    return counts, coll["totalContributions"]


def fetch_gitlab_counts():
    url = "https://gitlab.com/users/%s/calendar.json" % GITLAB_USER
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    return {d: int(c) for d, c in data.items()}


def load_github_counts(path):
    with open(path) as f:
        coll = json.load(f)
    calendar = coll["contributionCalendar"]
    counts = {}
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            counts[day["date"]] = day["contributionCount"]
    return counts, calendar["totalContributions"]


def load_gitlab_counts(path):
    with open(path) as f:
        data = json.load(f)
    return {d: int(c) for d, c in data.items()}


def build_weeks(counts):
    """Group sorted dates into Sunday-start weeks, like GitHub's calendar."""
    dates = sorted(counts)
    if not dates:
        return []
    first = date.fromisoformat(dates[0])
    # Back up to the Sunday starting that week.
    start = first.fromordinal(first.toordinal() - (first.weekday() + 1) % 7)
    last = date.fromisoformat(dates[-1])
    weeks = []
    current = []
    d = start
    while d <= last:
        current.append(d)
        if len(current) == 7:
            weeks.append(current)
            current = []
        d = d.fromordinal(d.toordinal() + 1)
    if current:
        weeks.append(current)
    return weeks


def render_svg(weeks, counts, gh_total, gl_total, out_path):
    width = LEFT_PAD + len(weeks) * PITCH + 4
    height = TOP_PAD + 7 * PITCH + BOTTOM_PAD
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="sans-serif">' % (width, height, width, height)
    )
    # Month labels.
    seen_month = set()
    for i, week in enumerate(weeks):
        first_day = week[0]
        key = (first_day.year, first_day.month)
        if key not in seen_month and first_day.day <= 7:
            seen_month.add(key)
            x = LEFT_PAD + i * PITCH
            parts.append(
                '<text x="%d" y="12" font-size="10" fill="#656d76">%s</text>'
                % (x, months[first_day.month - 1])
            )
    # Day labels (Mon / Wed / Fri).
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = TOP_PAD + row * PITCH + 9
        parts.append(
            '<text x="2" y="%d" font-size="10" fill="#656d76">%s</text>'
            % (y, label)
        )
    # Cells.
    for i, week in enumerate(weeks):
        for row, d in enumerate(week):
            key = d.isoformat()
            count = counts.get(key, 0)
            x = LEFT_PAD + i * PITCH
            y = TOP_PAD + row * PITCH
            parts.append(
                '<rect x="%d" y="%d" width="%d" height="%d" rx="2" '
                'fill="%s"><title>%s: %d contribution%s</title></rect>'
                % (x, y, CELL, CELL, color_for(count), key, count,
                   "" if count == 1 else "s")
            )
    # Totals + legend.
    total = gh_total + gl_total
    y = TOP_PAD + 7 * PITCH + 20
    parts.append(
        '<text x="2" y="%d" font-size="12" fill="#1f2328">%d contributions in the '
        'last year: %d on GitHub and %d on GitLab</text>'
        % (y, total, gh_total, gl_total)
    )
    legend_x = width - 140
    parts.append(
        '<text x="%d" y="%d" font-size="10" fill="#656d76">Less</text>'
        % (legend_x, y)
    )
    for j, c in enumerate(COLORS):
        parts.append(
            '<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s" />'
            % (legend_x + 32 + j * 13, y - 10, c)
        )
    parts.append(
        '<text x="%d" y="%d" font-size="10" fill="#656d76">More</text>'
        % (legend_x + 32 + 5 * 13 + 4, y)
    )
    parts.append("</svg>")
    with open(out_path, "w") as f:
        f.write("\n".join(parts) + "\n")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github-json", default=None)
    ap.add_argument("--gitlab-json", default=None)
    ap.add_argument("--out", default="combined-contributions.svg")
    args = ap.parse_args()

    if args.github_json:
        gh_counts, gh_total = load_github_counts(args.github_json)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print("error: set GITHUB_TOKEN or pass --github-json", file=sys.stderr)
            return 1
        gh_counts, gh_total = fetch_github_counts(token)

    if args.gitlab_json:
        gl_counts = load_gitlab_counts(args.gitlab_json)
    else:
        gl_counts = fetch_gitlab_counts()

    combined = dict(gh_counts)
    for d, c in gl_counts.items():
        combined[d] = combined.get(d, 0) + c
    gl_total = sum(gl_counts.values())

    weeks = build_weeks(combined)
    total = render_svg(weeks, combined, gh_total, gl_total, args.out)
    print("wrote %s: %d weeks, %d combined contributions "
          "(GitHub %d, GitLab %d)" % (args.out, len(weeks), total, gh_total, gl_total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
