#!/usr/bin/env python3
"""Print a save file's conversation as narration interleaved with tool calls.

Every bug in PORTING_BACK_TO_PYTHON.md's Part A was found by reading what the
engine actually returned to the model next to what the model then said. This
is the cheapest debugging tool in the project.

    python scripts/inspect_save.py                       # saves/autosave.json
    python scripts/inspect_save.py saves/mysave.json
    python scripts/inspect_save.py --tool ability_check  # only these calls
    python scripts/inspect_save.py --failures            # only failed calls
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DIM, BOLD, RED, GREEN, YELLOW, CYAN, RESET = (
    "\033[2m", "\033[1m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
)


def _short(value, limit: int = 160) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save", nargs="?", default="saves/autosave.json")
    ap.add_argument("--tool", action="append", help="only show these tools (repeatable)")
    ap.add_argument("--failures", action="store_true", help="only show failed tool calls")
    ap.add_argument("--full", action="store_true", help="do not truncate")
    args = ap.parse_args()

    path = Path(args.save)
    if not path.exists():
        print(f"No such save: {path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text())
    history = data.get("conversation_history", [])
    limit = 10_000 if args.full else 160
    wanted = set(args.tool or [])

    print(f"{BOLD}{path}{RESET} — {len(history)} messages, save version "
          f"{data.get('version', '?')}\n")

    pending: dict[str, str] = {}   # tool_use id -> name
    counts: dict[str, list[int]] = {}   # name -> [calls, failures]

    for msg in history:
        role, content = msg.get("role"), msg.get("content")

        if isinstance(content, str):
            if not wanted and not args.failures:
                colour = CYAN if role == "user" else ""
                print(f"{colour}{role:>9}{RESET}  {_short(content, limit)}\n")
            continue

        for block in content or []:
            btype = block.get("type")
            if btype == "text":
                if not wanted and not args.failures:
                    print(f"{'narration':>9}  {_short(block.get('text', ''), limit)}\n")
            elif btype == "tool_use":
                pending[block.get("id", "")] = block.get("name", "?")
                if wanted and block.get("name") not in wanted:
                    continue
                if not args.failures:
                    print(f"{YELLOW}{'→ call':>9}{RESET}  {BOLD}{block.get('name')}{RESET}"
                          f"({_short(block.get('input', {}), limit)})")
            elif btype == "tool_result":
                name = block.get("name") or pending.get(block.get("tool_use_id", ""), "?")
                try:
                    result = json.loads(block.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    result = {"raw": block.get("content")}

                ok = result.get("success", True) if isinstance(result, dict) else True
                stats = counts.setdefault(name, [0, 0])
                stats[0] += 1
                if not ok:
                    stats[1] += 1

                if wanted and name not in wanted:
                    continue
                if args.failures and ok:
                    continue
                if args.failures:
                    print(f"{YELLOW}{'→ call':>9}{RESET}  {BOLD}{name}{RESET}")
                mark = f"{GREEN}ok{RESET}" if ok else f"{RED}FAILED{RESET}"
                print(f"{DIM}{'← result':>9}{RESET}  [{mark}] {_short(result, limit)}\n")

    if counts:
        print(f"\n{BOLD}Tool call summary{RESET}")
        for name, (calls, failures) in sorted(counts.items(), key=lambda kv: -kv[1][0]):
            flag = f"  {RED}{failures} failed{RESET}" if failures else ""
            print(f"  {calls:>4}  {name}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
