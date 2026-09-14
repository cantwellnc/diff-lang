"""
distancetool  —  semantic distance between program versions.

Usage
-----
  distancetool diff old.py new.py --func <name> [--timeout MS] [--json]
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .frontend.python_parser import parse_function, ParseError
from .engine.differencer import compute_diff, DEFAULT_TIMEOUT_MS
from .report.formatter import format_report, format_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="distancetool",
        description="Compute semantic distance between two versions of a Python function.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── diff ──────────────────────────────────────────────────────────────────
    dp = sub.add_parser("diff", help="Compare two versions of a function.")
    dp.add_argument("old", help="Path to the old version of the Python file.")
    dp.add_argument("new", help="Path to the new version of the Python file.")
    dp.add_argument(
        "--func", "-f", required=True,
        help="Name of the function to analyse.",
    )
    dp.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_MS,
        metavar="MS",
        help=f"SMT solver timeout in milliseconds (default: {DEFAULT_TIMEOUT_MS}).",
    )
    dp.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of the human-readable report.",
    )

    args = parser.parse_args(argv)

    if args.command == "diff":
        return _cmd_diff(args)

    parser.print_help()
    return 1


def _cmd_diff(args: argparse.Namespace) -> int:
    old_path = Path(args.old)
    new_path = Path(getattr(args, "new"))

    for p in (old_path, new_path):
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 1

    old_src = old_path.read_text(encoding="utf-8")
    new_src = new_path.read_text(encoding="utf-8")

    try:
        func_old = parse_function(old_src, args.func)
    except ParseError as e:
        print(f"error parsing {old_path}: {e}", file=sys.stderr)
        return 1

    try:
        func_new = parse_function(new_src, args.func)
    except ParseError as e:
        print(f"error parsing {new_path}: {e}", file=sys.stderr)
        return 1

    result = compute_diff(func_old, func_new, timeout_ms=args.timeout)

    if args.json:
        print(format_json(result))
    else:
        print(format_report(result))

    # Exit code: 0 = equivalent, 1 = differs or error
    return 0 if result.equivalent else 1


if __name__ == "__main__":
    sys.exit(main())
