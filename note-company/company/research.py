"""リサーチ担当：毎朝、X と Threads から伸びているポストと売れているテーマを集める。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests
from pydantic import BaseModel

from . import llm, storage


# ---------- 収集 ----------

def fetch_x(keyword: str, max_results: int, min_likes: int) -> list[dict]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(
        "https://api.x.com/2/tweets/search/recent",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "query": f"{keyword} -is:retweet -is:reply lang:ja",
            "max_results": max(10, min(max_results, 100)),
            "sort_order": "relevancy",
            "start_time": start,
            "tweet.fields": "public_metrics,created_at,author_id",
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[research] X検索失敗 {keyword}: {r.status_code} {r.text[:200]}")
        return []
    out = []
    for t in r.json().get("data", []):
        m = t.get("public_metrics", {})
        if m.get("like_count", 0) < min_likes:
            continue
        out.append({
            "platform": "x",
            "keyword": keyword,
            "text": t["text"],
            "likes": m.get("like_count", 0),
            "reposts": m.get("retweet_count", 0),
            "bookmarks": m.get("bookmark_count", 0),
            "url": f"https://x.com/i/web/status/{t['id']}",
        })
    return out


def fetch_threads(keyword: str, max_results: int) -> list[dict]:
    token = os.getenv("THREADS_ACCESS_TOKEN")
    if not token:
        return []
    r = requests.get(
        "https://graph.threads.net/v1.0/keyword_search",
        params={
            "q": keyword,
            "search_type": "TOP",  # 人気順
            "fields": "id,text,permalink,timestamp,username",
            "limit": min(max_results, 100),
            "access_token": token,
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[research] Threads検索失敗 {keyword}: {r.status_code} {r.text[:200]}")
        return []
    return [
        {"platform": "threads", "keyword": keyword, "text": p.get("text", ""), "url": p.get("permalink")}
        for p in r.json().get("data", [])
        if p.get("text")
    ]


def web_scan(cfg: dict) -> str:
    """API キーが無くても動くよう、Web検索で売れ筋・話題を補完する。"""
    c = cfg["company"]
    return llm.ask_text(
        model=cfg["models"]["main"],
        system="あなたはnote販売会社のリサーチ担当です。事実と出典URLだけを箇条書きで報告し、推測は推測と明記します。",
        prompt=(
            f"今日は{storage.today()}です。ジャンル「{c['genre']}」について、直近1週間で\n"
            "1) noteで売れている・話題の有料note（タイトル、価格、なぜ売れているか）\n"
            "2) X や Threads で伸びている投稿の傾向・テーマ\n"
            "を Web 検索で調べ、出典URL付きで報告してください。"
        ),
        web_search=True,
        effort="medium",
    )


# ---------- 分析 ----------

class HotPost(BaseModel):
    platform: str
    summary: str
    why_it_works: str
    url: str


class Theme(BaseModel):
    theme: str
    evidence: str
    buying_motive: str
    score: int  # 1-10 売れそう度


class ResearchReport(BaseModel):
    hot_posts: list[HotPost]
    themes: list[Theme]
    winning_hooks: list[str]
    notes: str


def run(day: str | None = None) -> ResearchReport:
    cfg = storage.config()
    rc = cfg["research"]
    d = storage.day_dir(day)

    posts: list[dict] = []
    for kw in rc["keywords"]:
        posts += fetch_x(kw, rc["max_per_keyword"], rc["min_likes"])
        posts += fetch_threads(kw, rc["max_per_keyword"])
    posts.sort(key=lambda p: p.get("likes", 0), reverse=True)
    storage.write_json(d / "research_raw.json", posts)
    print(f"[research] 収集ポスト {len(posts)} 件")

    web = web_scan(cfg)
    (d / "research_web.md").write_text(web, encoding="utf-8")

    c = cfg["company"]
    posts_txt = "\n".join(
        f"- [{p['platform']}] likes={p.get('likes', '?')} {p['url']}\n  {p['text'][:300]}" for p in posts[:150]
    ) or "（API未設定のため収集ポストなし）"
    report = llm.ask_json(
        model=cfg["models"]["main"],
        system="あなたはnote販売会社のリサーチ担当です。データから「売れるテーマ」と「伸びる型」を抽出します。",
        prompt=(
            f"ジャンル: {c['genre']}\n想定読者: {c['reader']}\n\n"
            f"<sns_posts>\n{posts_txt}\n</sns_posts>\n\n<web_research>\n{web}\n</web_research>\n\n"
            "上の材料から、伸びているポスト上位（最大10件）、売れそうなテーマ（最大8件、score降順）、"
            "冒頭1行目で使われている勝ちパターン（フック）を抽出してください。根拠のない数字は作らないでください。"
        ),
        schema=ResearchReport,
        effort="medium",
    )
    storage.write_json(d / "research.json", report)
    print(f"[research] テーマ {len(report.themes)} 件を抽出")
    return report
