"""予約投稿の実行係：時刻が来たポストを X / Threads に投稿する（cron で数分おきに呼ぶ）。"""
from __future__ import annotations

import os
import time
from datetime import datetime

import requests

from . import storage
from .sales import load_queue, save_queue


def post_x(text: str) -> str:
    from requests_oauthlib import OAuth1

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    r = requests.post("https://api.x.com/2/tweets", json={"text": text}, auth=auth, timeout=30)
    r.raise_for_status()
    return f"https://x.com/i/web/status/{r.json()['data']['id']}"


def post_threads(text: str) -> str:
    uid = os.environ["THREADS_USER_ID"]
    token = os.environ["THREADS_ACCESS_TOKEN"]
    base = f"https://graph.threads.net/v1.0/{uid}"
    r = requests.post(f"{base}/threads", params={"media_type": "TEXT", "text": text, "access_token": token}, timeout=30)
    r.raise_for_status()
    creation_id = r.json()["id"]
    for attempt in range(5):  # コンテナ準備待ち
        time.sleep(3 * (attempt + 1))
        r = requests.post(f"{base}/threads_publish", params={"creation_id": creation_id, "access_token": token}, timeout=30)
        if r.ok:
            return f"threads:{r.json()['id']}"
    r.raise_for_status()
    return ""


SENDERS = {"x": post_x, "threads": post_threads}


def publish_due(dry_run: bool = False) -> int:
    q = load_queue()
    now = storage.now_jst()
    sent = 0
    for x in sorted(q, key=lambda x: x.get("scheduled_at") or ""):
        if x["status"] != "scheduled" or datetime.fromisoformat(x["scheduled_at"]) > now:
            continue
        if dry_run:
            print(f"[publish] (dry-run) {x['channel']}: {x['text'][:40]}…")
            continue
        try:
            x["posted_url"] = SENDERS[x["channel"]](x["text"])
            x["status"] = "posted"
            x["posted_at"] = now.isoformat()
            sent += 1
            print(f"[publish] {x['channel']} 投稿 → {x['posted_url']}")
        except Exception as e:  # 1件失敗しても残りは続ける
            x["status"] = "failed"
            x["error"] = str(e)[:500]
            print(f"[publish] {x['channel']} 失敗: {e}")
        save_queue(q)  # 途中で落ちても二重投稿しないよう毎回保存
    return sent
