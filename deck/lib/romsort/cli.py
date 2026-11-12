"""Command line: sort ROMs from a folder (usually Downloads) into ES-DE's ROM folders, and undo the last sort.

  python3 -m romsort --rom-root ~/ROMs --from ~/Downloads [--deep] [--dry-run] [--journal FILE]
  python3 -m romsort --rom-root ~/ROMs --undo --journal FILE

Only files whose type the evidence supports (header or extension) are moved; the rest are listed and left alone.
Nothing is ever overwritten or deleted. Every move is written to the journal so the last sort can be undone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .shim import Config
from .sorter import Confidence, Journal, apply_plan, build_plan, default_selection


def _plan(folder: Path, config: Config, deep: bool, min_age: float):
    plan = build_plan(folder, config, min_age=min_age)
    if not deep:
        return plan
    queue = [p for p in sorted(folder.iterdir()) if p.is_dir() and not p.name.startswith(".")] if folder.is_dir() else []
    taken = {i.source for i in plan.items}
    depth = {p: 1 for p in queue}
    seen = 0
    while queue and seen < 2000:
        here = queue.pop(0)
        seen += 1
        if here in taken or any(t == here or here in t.parents for t in taken):
            continue
        sub = build_plan(here, config, min_age=min_age)
        plan.items += sub.items
        plan.waiting += sub.waiting
        plan.ignored += sub.ignored
        taken |= {i.source for i in sub.items}
        if depth[here] < 6:
            for child in sorted(here.iterdir()):
                if child.is_dir() and not child.name.startswith(".") and not child.is_symlink() and child not in taken:
                    depth[child] = depth[here] + 1
                    queue.append(child)
    return plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="romsort", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom-root", type=Path, required=True)
    ap.add_argument("--from", dest="source", type=Path, help="the folder to sort")
    ap.add_argument("--journal", type=Path, required=True, help="where moves are recorded for undo")
    ap.add_argument("--deep", action="store_true", help="also search the folders inside it")
    ap.add_argument("--dry-run", action="store_true", help="only say what would move")
    ap.add_argument("--undo", action="store_true", help="move the last sort's files back")
    ap.add_argument("--min-age", type=float, default=5.0, help="leave files changed in the last N seconds (still downloading)")
    args = ap.parse_args(argv)
    config = Config(args.rom_root)
    journal = Journal(args.journal)

    if args.undo:
        n = journal.last_count()
        if not n:
            print("Nothing to undo.")
            return 0
        restored, problems = journal.undo_last()
        print(f"Moved {restored} file(s) back.")
        for p in problems:
            print(f"  • {p}")
        return 0

    if args.source is None or not args.source.is_dir():
        print(f"There is no folder to sort: {args.source}", file=sys.stderr)
        return 1
    plan = _plan(args.source, config, args.deep, args.min_age)
    chosen = default_selection(plan.items)
    held = [i for i in plan.items if i not in chosen]
    if args.dry_run:
        for item in chosen:
            print(f"would move  {item.label}  ->  {item.dest_label()}   ({item.reason})")
    else:
        result = apply_plan(chosen, journal, keep_both=False)
        for item in result.moved:
            print(f"moved  {item.label if hasattr(item, 'label') else item}")
        for item, why in result.skipped:
            print(f"skipped  {item.label}: {why}")
        print(f"Moved {len(result.moved)} ROM(s) into {args.rom_root}.")
    for item in held:
        why = "something with that name is already there" if item.exists and item.confidence is not Confidence.UNSURE else item.reason
        print(f"left alone  {item.label}: {why}")
    if plan.waiting:
        print(f"{len(plan.waiting)} file(s) still downloading; run it again later.")
    if not plan.items:
        print("No ROMs found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
