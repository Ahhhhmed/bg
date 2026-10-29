#!/usr/bin/env python3
"""
List backlog items and pick the next one to work on.

Usage (from the repo root):
  python3 scripts/backlog.py list            # open items, in pick order
  python3 scripts/backlog.py next            # top suggestion (the owner decides)
  python3 scripts/backlog.py next --json     # same, machine-readable
  python3 scripts/backlog.py check           # validate every item's frontmatter

Suggestion order: status `ready`, every `depends_on` item done, no open
`claude/backlog-<id>-*` branch on origin (someone is already on it), then by
priority (P1 first), then by id. See .claude/skills/backlog/SKILL.md.

Standard library only, so it runs before any setup.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "backlog"
DONE = BACKLOG / "done"

STATUSES = {"draft", "ready", "in-progress", "review", "blocked", "done"}
PRIORITIES = {"P1", "P2", "P3"}
SIZES = {"S", "M", "L"}
REQUIRED = ["id", "title", "status", "priority", "size", "area", "depends_on", "hosts", "blocked_on", "pr", "updated"]


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError(f"{path.name}: no frontmatter")
    fm = {}
    for line in m.group(1).splitlines():
        line = re.sub(r"\s+#.*$", "", line)  # trailing comments (template)
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith(("[", '"')):
            value = json.loads(value)
        fm[key.strip()] = value
    fm["file"] = str(path.relative_to(ROOT))
    return fm


def load_items():
    items = []
    for d in (BACKLOG, DONE):
        for p in sorted(d.glob("[0-9][0-9][0-9]-*.md")):
            items.append(parse_frontmatter(p))
    return items


def active_branches():
    """claude/backlog-* branch names on origin."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", "claude/backlog-*"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return []
    return re.findall(r"refs/heads/(claude/backlog-\S+)", out)


def active_branch_ids():
    """Item ids that already have a claude/backlog-<id>-* branch on origin."""
    return {m.group(1) for b in active_branches() if (m := re.match(r"claude/backlog-(\d{3})-", b))}


def pick_order(items):
    done = {i["id"] for i in items if i["status"] == "done"}
    busy = active_branch_ids()
    candidates = [
        i for i in items
        if i["status"] == "ready" and set(i["depends_on"]) <= done and i["id"] not in busy
    ]
    return sorted(candidates, key=lambda i: (i["priority"], i["id"]))


def check(items):
    problems = []
    ids = set()
    for i in items:
        name = i["file"]
        for k in REQUIRED:
            if k not in i:
                problems.append(f"{name}: missing `{k}`")
        if i.get("status") not in STATUSES:
            problems.append(f"{name}: bad status {i.get('status')!r}")
        if i.get("priority") not in PRIORITIES:
            problems.append(f"{name}: bad priority {i.get('priority')!r}")
        if i.get("size") not in SIZES:
            problems.append(f"{name}: bad size {i.get('size')!r}")
        if not Path(name).name.startswith(f"{i.get('id')}-"):
            problems.append(f"{name}: id {i.get('id')!r} doesn't match filename")
        if i.get("id") in ids:
            problems.append(f"{name}: duplicate id {i.get('id')}")
        ids.add(i.get("id"))
        if i.get("status") == "blocked" and not i.get("blocked_on"):
            problems.append(f"{name}: blocked but `blocked_on` is empty")
        if i.get("status") == "done" and not name.startswith("backlog/done/"):
            problems.append(f"{name}: done items belong in backlog/done/")
    for i in items:
        for dep in i.get("depends_on", []):
            if dep not in ids:
                problems.append(f"{i['file']}: depends on unknown id {dep}")
    return problems


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    items = load_items()
    if cmd == "check":
        problems = check(items)
        print("\n".join(problems) if problems else f"ok: {len(items)} items")
        sys.exit(1 if problems else 0)
    if cmd == "next":
        order = pick_order(items)
        nxt = order[0] if order else None
        if "--json" in sys.argv:
            print(json.dumps(nxt))
        else:
            print(f"{nxt['id']}  {nxt['title']}  ({nxt['file']})" if nxt else "nothing ready")
        return
    if cmd == "list":
        order = pick_order(items)
        ranked = {i["id"]: n + 1 for n, i in enumerate(order)}
        for i in sorted(items, key=lambda i: (i["status"] == "done", i["priority"], i["id"])):
            if i["status"] == "done":
                continue
            rank = f"#{ranked[i['id']]}" if i["id"] in ranked else "  "
            extra = f"  blocked_on: {i['blocked_on']}" if i["status"] in ("blocked", "draft") and i["blocked_on"] else ""
            deps = f"  after {','.join(i['depends_on'])}" if i["depends_on"] else ""
            print(f"{rank:>3} {i['id']} {i['priority']} {i['size']} {i['status']:<11} {i['title']}{deps}{extra}")
        return
    sys.exit(f"unknown command {cmd!r}; use list | next | check")


if __name__ == "__main__":
    main()
