"""evidence.cli — run the portfolio over a tree and emit ONE aggregate verdict.

    evidence audit .                     the human report
    evidence audit . --format sarif      GitHub code scanning
    evidence audit . --format junit      any CI's test view
    evidence audit . --format markdown   a job summary
    evidence tools                       what can run, and what deliberately cannot

Exit codes are the portfolio dialect: 0 checked and holds, 1 checked and fails, 2 NOT checked.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .audit import audit, render
from .constituents import NOT_AUTOMATABLE, REGISTRY
from .formats import FORMATS, to_junit, to_markdown, to_sarif


def _cmd_audit(a) -> int:
    only = {s.strip() for s in a.only.split(",") if s.strip()} if a.only else None
    if only:
        known = {c.name for c in REGISTRY}
        unknown = only - known
        if unknown:
            print(f"evidence: unknown constituent(s): {', '.join(sorted(unknown))}\n"
                  f"  known: {', '.join(sorted(known))}", file=sys.stderr)
            return 2

    agg = audit(a.path, only=only, timeout=a.timeout)

    if a.format == "json":
        print(json.dumps(agg.to_dict(), indent=2))
    elif a.format == "sarif":
        print(to_sarif(agg, a.path, __version__))
    elif a.format == "junit":
        print(to_junit(agg, a.path))
    elif a.format == "markdown":
        print(to_markdown(agg, a.path))
    else:
        print(f"evidence audit {a.path}")
        print(render(agg, a.path, show_excluded=a.show_excluded))
    return agg.exit_code


def _cmd_tools(a) -> int:
    print("Constituents this audit can run:\n")
    for c in sorted(REGISTRY, key=lambda c: c.name):
        print(f"  {c.name:<14} {c.scope}")
    print("\nDeliberately NOT auto-run, and why:\n")
    for name, why in sorted(NOT_AUTOMATABLE.items()):
        print(f"  {name:<28} {why}")
    print("\nA tool that is not installed reports MISSING and does not vote. It cannot drag the")
    print("verdict down — and it cannot hold it up either.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="evidence",
        description="run the portfolio over your repository and emit ONE aggregate verdict "
                    "(measure-only)")
    ap.add_argument("--version", action="version", version=f"evidence {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    au = sub.add_parser("audit", help="detect what applies, run it, aggregate to the weakest leg")
    au.add_argument("path", nargs="?", default=".")
    au.add_argument("--format", choices=sorted(FORMATS), default="text")
    au.add_argument("--json", dest="format", action="store_const", const="json",
                    help="shorthand for --format json")
    au.add_argument("--only", default="", metavar="NAME[,NAME...]",
                    help="restrict to these constituents")
    au.add_argument("--timeout", type=int, default=300, help="per-constituent seconds")
    au.add_argument("--show-excluded", action="store_true",
                    help="also list the tools that are deliberately not auto-run")
    au.set_defaults(fn=_cmd_audit)

    t = sub.add_parser("tools", help="what can run here, and what deliberately cannot")
    t.set_defaults(fn=_cmd_tools)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
