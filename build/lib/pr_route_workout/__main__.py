"""Run the router against a GitHub pull request or a named fixture."""

from __future__ import annotations

import argparse
import os
import sys

from pr_route_workout.canvas_view import write_canvas
from pr_route_workout.dashboard import render_dashboard, serve
from pr_route_workout.fixtures import FIXTURES
from pr_route_workout.github import GitHubError, fetch_pull_request, parse_ref
from pr_route_workout.jev import JevError
from pr_route_workout.report import render_json, render_text
from pr_route_workout.run import evaluate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pr-route-workout",
        description="Route one pull request for workout-app.",
    )
    parser.add_argument(
        "pull_request",
        nargs="?",
        help="https://github.com/owner/repo/pull/N, owner/repo#N, or owner/repo",
    )
    parser.add_argument(
        "number",
        nargs="?",
        type=int,
        help="pull request number, when the first argument is owner/repo",
    )
    parser.add_argument(
        "--fixture",
        choices=sorted(FIXTURES),
        help="route an in-memory pull request instead of GitHub",
    )
    parser.add_argument(
        "--jira-projects",
        help="comma-separated Jira project allowlist (not used for workout-app, kept for compat)",
    )
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--no-color", action="store_true", help="do not color the disposition")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the routing page on a free local port",
    )
    args = parser.parse_args(argv)

    allow = None
    if args.jira_projects:
        allow = frozenset(
            part.strip().upper() for part in args.jira_projects.split(",") if part.strip()
        )

    try:
        if args.fixture:
            pr = FIXTURES[args.fixture]
        else:
            if not args.pull_request:
                parser.error("pass a pull request: a url, owner/repo#N, or owner/repo and a number")
            repo, number = parse_ref(args.pull_request, args.number)
            pr = fetch_pull_request(repo, number)
        result = evaluate(pr, allow_projects=allow)
    except (GitHubError, JevError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    color = sys.stdout.isatty() and not args.no_color and not os.environ.get("NO_COLOR")
    print(render_json(result) if args.json else render_text(result, color=color))
    try:
        write_canvas(result)
    except OSError:
        pass
    if args.serve:
        server = serve(render_dashboard(result))
        host, port = server.server_address
        print(f"http://{host}:{port}", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())