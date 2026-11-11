"""社長（オーケストレーター）。

使い方:
  python -m company daily              # 毎朝: リサーチ→企画→執筆→検品→デザイン→営業(下書き)
  python -m company research|plan|write|review|design|sales [--day YYYY-MM-DD]
  python -m company launch --day YYYY-MM-DD --url https://note.com/...   # note公開後、営業ポストを予約確定
  python -m company publish-due [--dry-run]                              # 時刻が来た予約ポストを投稿
  python -m company queue                                                # 予約状況を表示
  python -m company start                                                # 常駐: 毎朝の制作と予約投稿を自動で回す
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback

from . import designer, planner, publisher, research, reviewer, sales, storage, writer

STEPS = {
    "research": research.run,
    "plan": planner.run,
    "write": writer.run,
    "review": reviewer.run,
    "design": designer.run,
    "sales": sales.run,
}


def run_daily(day: str | None = None, start: str | None = None) -> None:
    names = list(STEPS)
    if start:
        names = names[names.index(start):]
    for name in names:
        print(f"\n===== {name} =====")
        STEPS[name](day)
    day = day or storage.today()
    print(f"\n✅ 完成: {storage.day_dir(day) / 'article.md'}")
    print(f"   noteに公開したら: python -m company launch --day {day} --url <noteのURL>")


def start_loop() -> None:
    """PCで起動しっぱなしにする。毎朝の制作ラインと予約投稿をこのプロセスが回す。"""
    sc = storage.config()["schedule"]
    h, m = map(int, sc["daily_at"].split(":"))
    every = max(1, int(sc["publish_every_min"])) * 60
    marker = storage.STATE / "last_daily.txt"
    print(f"🏢 note会社 営業中（制作 {sc['daily_at']} / 投稿チェック {every // 60}分おき）  Ctrl+C で終了")
    last_publish = 0.0
    while True:
        now = storage.now_jst()
        day = now.strftime("%Y-%m-%d")
        done = marker.read_text().strip() if marker.exists() else ""
        if (now.hour, now.minute) >= (h, m) and done != day:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(day)  # 失敗しても同じ日に何度も課金しないよう先に記録
            try:
                run_daily(day)
            except BaseException as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                traceback.print_exc()
                print(f"❌ 制作ラインが失敗しました。手動で再開: python -m company daily --day {day} --from <担当>")
        if time.time() - last_publish >= every:
            last_publish = time.time()
            try:
                publisher.publish_due()
            except Exception:
                traceback.print_exc()
        time.sleep(30)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="company")
    ap.add_argument("command", choices=[*STEPS, "daily", "launch", "publish-due", "queue", "start"])
    ap.add_argument("--day", default=None, help="対象日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--url", default=None, help="launch: 公開したnoteのURL")
    ap.add_argument("--from", dest="start", default=None, choices=list(STEPS), help="daily: 途中の担当から再開")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    storage.load_env()

    if a.command == "start":
        start_loop()
    elif a.command == "daily":
        run_daily(a.day, a.start)
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
