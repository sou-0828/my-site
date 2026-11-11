"""執筆担当：売れたnoteとセールスレターのデータを使って本文を書く。"""
from __future__ import annotations

import json

from . import llm, storage

PAYWALL = "<!-- ここから有料 -->"

SYSTEM = """あなたはnote販売会社の執筆担当です。
<sold_notes> は実際に売れたnote、<letters> は実際に成約したセールスレターです。
構成・語り口・無料部分での引き込み方・有料ラインの置き方を、内容をコピーせずに学んで書きます。

書き方のルール:
- 書き手本人の一人称で、具体的な体験・数字・失敗を入れる（材料にない数字は「〇〇」と置き、捏造しない）
- 無料部分は「悩みの言語化 → 結論の一部 → 有料部分で手に入るもの」で終え、買う理由を作る
- 有料部分は手順・テンプレ・実例など、読んだその日に使えるものにする
- 見出しは ## と ### を使う。図解を入れたい箇所には [[図: 図の内容を一文で]] と書く（最大3つ）
- 出力は Markdown の本文のみ。前置きや後書きは書かない
"""


def run(day: str | None = None) -> str:
    cfg = storage.config()
    c = cfg["company"]
    d = storage.day_dir(day)
    plan = storage.read_json(d / "plan.json")
    if plan is None:
        raise SystemExit("先に plan を実行してください")
    pick = plan["proposals"][plan["pick_index"]]

    notes = storage.read_docs("notes") or "（売れたnoteのデータ未登録）"
    letters = storage.read_docs("letters") or "（セールスレターのデータ未登録）"

    body = llm.ask_text(
        model=cfg["models"]["main"],
        system=SYSTEM,
        prompt=(
            f"<sold_notes>\n{notes}\n</sold_notes>\n\n<letters>\n{letters}\n</letters>\n\n"
            f"書き手: {c['persona']}\n想定読者: {c['reader']}\n\n"
            f"<proposal>\n{json.dumps(pick, ensure_ascii=False, indent=2)}\n</proposal>\n\n"
            f"この企画のnoteを書いてください。1行目は `# タイトル`。"
            f"無料部分と有料部分の境目に `{PAYWALL}` を1行だけ入れてください。"
            "全体で8,000〜12,000字を目安にします。"
        ),
        effort="high",
    )
    if PAYWALL not in body:
        print("[write] 警告: 有料ラインが入っていません。手動で確認してください")
    (d / "draft.md").write_text(body, encoding="utf-8")
    print(f"[write] 下書き {len(body)} 字")
    return body
