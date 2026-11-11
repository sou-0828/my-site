"""社長（オーケストレーター）。

使い方:
  python -m company daily              # 毎朝: リサーチ→企画→執筆→検品→デザイン→営業(下書き)
  python -m company research|plan|write|review|design|sales [--day YYYY-MM-DD]
  python -m company launch --day YYYY-MM-DD --url https://note.com/...   # note公開後、営業ポストを予約確定
  python -m company publish-due [--dry-run]                              # 時刻が来た予約ポストを投稿
  python -m company queue                                                # 予約状況を表示
"""
from __future__ import annotations

import argparse
import sys

from . import designer, planner, publisher, research, reviewer, sales, storage, writer

STEPS = {
    "research": research.run,
    "plan": planner.run,
    "write": writer.run,
    "review": reviewer.run,
    "design": designer.run,
    "sales": sales.run,
}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="company")
    ap.add_argument("command", choices=[*STEPS, "daily", "launch", "publish-due", "queue"])
    ap.add_argument("--day", default=None, help="対象日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--url", default=None, help="launch: 公開したnoteのURL")
    ap.add_argument("--from", dest="start", default=None, choices=list(STEPS), help="daily: 途中の担当から再開")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.command == "daily":
        names = list(STEPS)
        if a.start:
            names = names[names.index(a.start):]
        for name in names:
            print(f"\n===== {name} =====")
            STEPS[name](a.day)
        day = a.day or storage.today()
        print(f"\n✅ 完成: {storage.day_dir(day) / 'article.md'}")
        print(f"   noteに公開したら: python -m company launch --day {day} --url <noteのURL>")
    elif a.command in STEPS:
        STEPS[a.command](a.day)
    elif a.command == "launch":
        if not a.url:
            sys.exit("--url が必要です")
        sales.launch(a.day or storage.today(), a.url)
    elif a.command == "publish-due":
        publisher.publish_due(dry_run=a.dry_run)
    elif a.command == "queue":
        for x in sorted(sales.load_queue(), key=lambda x: (x.get("scheduled_at") or "~", x["day"])):
            when = (x.get("scheduled_at") or "未予約")[:16]
            print(f"{x['status']:<9} {when:<16} {x['channel']:<7} {x['text'][:50].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
