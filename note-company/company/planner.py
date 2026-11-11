"""企画担当：売れたデータと照らして「次に出すnote」を提案する。"""
from __future__ import annotations

import json

from pydantic import BaseModel

from . import llm, storage


class Proposal(BaseModel):
    title: str
    subtitle: str
    target_reader: str
    pain: str  # 読者の悩み
    promise: str  # 読むと手に入るもの
    price_yen: int
    why_now: str  # リサーチとの対応
    why_it_sells: str  # 過去の売上データとの対応
    outline: list[str]  # 見出し案
    free_part_ends_at: str  # どこまで無料で見せるか


class Plan(BaseModel):
    sales_insights: list[str]
    proposals: list[Proposal]
    pick_index: int  # 一番推す案（0始まり）
    pick_reason: str


def run(day: str | None = None) -> Plan:
    cfg = storage.config()
    c = cfg["company"]
    d = storage.day_dir(day)
    research = storage.read_json(d / "research.json")
    if research is None:
        raise SystemExit("先に research を実行してください")
    sales = storage.read_sales()
    past = storage.read_json(storage.STATE / "published.json", [])

    plan = llm.ask_json(
        model=cfg["models"]["main"],
        system=(
            "あなたはnote販売会社の企画担当です。勘ではなく、過去の売上データと今日のリサーチの"
            "両方に根拠がある企画だけを出します。過去に出したnoteと被る企画は避けます。"
        ),
        prompt=(
            f"ジャンル: {c['genre']}\n想定読者: {c['reader']}\n書き手: {c['persona']}\n\n"
            f"<sales_data>\n{json.dumps(sales, ensure_ascii=False)}\n</sales_data>\n\n"
            f"<today_research>\n{json.dumps(research, ensure_ascii=False)}\n</today_research>\n\n"
            f"<already_published>\n{json.dumps(past, ensure_ascii=False)}\n</already_published>\n\n"
            "1) 売上データから読み取れる「売れる条件」（価格帯・テーマ・タイトルの型・転換率など）を箇条書きに。\n"
            "2) 次に出すnoteを3案。それぞれ why_now にリサーチ側の根拠、why_it_sells に売上データ側の根拠を書く。\n"
            "3) 一番推す案を1つ選び理由を書く。売上データが無い場合はその旨を明記し、リサーチのみで判断する。"
        ),
        schema=Plan,
        effort="high",
    )
    plan.pick_index = max(0, min(plan.pick_index, len(plan.proposals) - 1))
    storage.write_json(d / "plan.json", plan)
    pick = plan.proposals[plan.pick_index]
    print(f"[plan] 採用案: {pick.title}（{pick.price_yen}円）")
    return plan
