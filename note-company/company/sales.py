"""営業担当：集客ポストを作り、予約投稿キューに入れる。

note には公式の投稿APIが無いため、note 本体の公開だけは人が行い、
`launch` で公開URLを渡した瞬間に営業ポストの予約が確定する。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel

from . import llm, storage

QUEUE = storage.STATE / "queue.json"
X_LIMIT = 140  # 日本語は1文字=2カウントのため実質140字
THREADS_LIMIT = 500
URL_TOKEN = "{NOTE_URL}"


class Post(BaseModel):
    kind: str  # teaser / value / launch / social_proof / reminder など
    x_text: str
    threads_text: str
    include_link: bool


class Campaign(BaseModel):
    strategy: str
    posts: list[Post]


def load_queue() -> list[dict]:
    return storage.read_json(QUEUE, [])


def save_queue(q: list[dict]) -> None:
    storage.write_json(QUEUE, q)


def run(day: str | None = None) -> Campaign:
    cfg = storage.config()
    c, sc = cfg["company"], cfg["sales"]
    day = day or storage.today()
    d = storage.day_dir(day)
    article = (d / "article.md").read_text(encoding="utf-8") if (d / "article.md").exists() else None
    if article is None:
        raise SystemExit("先に design を実行してください")
    research = storage.read_json(d / "research.json", {})
    plan = storage.read_json(d / "plan.json")
    pick = plan["proposals"][plan["pick_index"]]
    free_part = article.split("<!-- ここから有料 -->")[0]

    campaign = llm.ask_json(
        model=cfg["models"]["main"],
        system=(
            "あなたはnote販売会社の営業担当です。売り込み臭のない、読むだけで得をする投稿で興味を作り、"
            "最後にnoteへ誘導します。煽り・誇大表現・根拠のない実績の捏造は禁止。"
        ),
        prompt=(
            f"書き手: {c['persona']}\n読者: {c['reader']}\n"
            f"note: {pick['title']}（{pick['price_yen']}円）\n約束: {pick['promise']}\n\n"
            f"<free_part>\n{free_part}\n</free_part>\n\n"
            f"<winning_hooks>\n{json.dumps(research.get('winning_hooks', []), ensure_ascii=False)}\n</winning_hooks>\n\n"
            f"集客ポストを{sc['posts_per_note']}本、投稿順に作ってください。\n"
            f"- x_text は{X_LIMIT}字以内、threads_text は{THREADS_LIMIT}字以内（Threadsは改行多めで読みやすく）\n"
            f"- リンクを入れる投稿は include_link=true にし、本文中の入れたい位置に {URL_TOKEN} と書く（URL分の字数も考慮しX側は110字以内に）\n"
            "- 1本目は有益情報だけ（リンクなし）、後半ほど購入導線を強く。ハッシュタグは最大1個"
        ),
        schema=Campaign,
        effort="medium",
    )

    q = [x for x in load_queue() if not (x["day"] == day and x["status"] == "draft")]
    for i, p in enumerate(campaign.posts):
        for ch in sc["channels"]:
            text = p.x_text if ch == "x" else p.threads_text
            limit = X_LIMIT if ch == "x" else THREADS_LIMIT
            if len(text.replace(URL_TOKEN, "")) > limit:
                print(f"[sales] 警告: {ch} #{i + 1} が{limit}字を超えています。キュー上で修正してください")
            q.append({
                "id": uuid.uuid4().hex[:10],
                "day": day,
                "order": i,
                "kind": p.kind,
                "channel": ch,
                "text": text,
                "needs_url": p.include_link or URL_TOKEN in text,
                "status": "draft",
                "scheduled_at": None,
            })
    save_queue(q)
    storage.write_json(d / "sales.json", campaign)
    print(f"[sales] 集客ポスト {len(campaign.posts)} 本 × {len(sc['channels'])} チャネルを下書き登録")
    return campaign


def next_slots(n: int, slots: list[str], start: datetime) -> list[datetime]:
    out: list[datetime] = []
    day = start.date()
    while len(out) < n:
        for s in sorted(slots):
            h, m = map(int, s.split(":"))
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=storage.JST)
            if t > start and len(out) < n:
                out.append(t)
        day += timedelta(days=1)
    return out


def launch(day: str, note_url: str) -> None:
    """noteを公開したら呼ぶ：URLを差し込み、営業ポストの予約を確定する。"""
    cfg = storage.config()
    q = load_queue()
    drafts = sorted((x for x in q if x["day"] == day and x["status"] == "draft"), key=lambda x: x["order"])
    if not drafts:
        raise SystemExit(f"{day} の下書きポストがありません")
    orders = sorted({x["order"] for x in drafts})
    times = next_slots(len(orders), cfg["sales"]["slots"], storage.now_jst() + timedelta(minutes=10))
    when = dict(zip(orders, times))
    for x in drafts:
        x["text"] = x["text"].replace(URL_TOKEN, note_url)
        if x["needs_url"] and note_url not in x["text"]:
            x["text"] = f"{x['text']}\n{note_url}"
        x["scheduled_at"] = when[x["order"]].isoformat()
        x["status"] = "scheduled"
    save_queue(q)

    plan = storage.read_json(storage.day_dir(day) / "plan.json")
    pick = plan["proposals"][plan["pick_index"]] if plan else {}
    pub = storage.read_json(storage.STATE / "published.json", [])
    pub.append({"day": day, "title": pick.get("title"), "price_yen": pick.get("price_yen"), "url": note_url})
    storage.write_json(storage.STATE / "published.json", pub)
    for o in orders:
        print(f"[sales] #{o + 1} → {when[o].strftime('%m/%d %H:%M')} 予約")
