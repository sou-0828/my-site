"""検品担当：執筆とは別のAIが「AIっぽい言い回し」だけを人間の文章に直す。

内容・構成・事実には触らせないため、モデルには「置換リスト」だけを返させ、
本文への適用はプログラム側で行う。置換リストに無い部分は1文字も変わらない。
"""
from __future__ import annotations

from pydantic import BaseModel

from . import llm, storage
from .writer import PAYWALL

SYSTEM = """あなたは日本語の校閲者です。仕事は1つだけ：
「AIが書いたとすぐ分かる言い回し」を、同じ意味の自然な人間の書き言葉に置き換えること。

直す対象の例:
- 「〜ではないでしょうか」「〜と言えるでしょう」「〜することが重要です」の多用
- 「さあ、〜しましょう！」「いかがでしたか？」「結論から言うと」の機械的な定型
- 「〜において」「〜を活用することで」「多岐にわたる」「シームレスに」などの硬い翻訳調
- 同じ語尾が3回以上続く箇所、不自然な三点セットの列挙（AとBとCで〜）
- 「まず」「次に」「最後に」が機械的に並ぶ箇所、過剰な太字・絵文字・感嘆符
- 中身のない締めの一文（「ぜひ参考にしてください」等）

やってはいけないこと:
- 主張・事実・数字・手順・構成・見出しを変える
- 文章を足す、削って短くする（言い回しの置換に必要な範囲を除く）
- 書き手の癖や口語表現を「正しく」直す
- `<!-- ここから有料 -->` と `[[図: ...]]` に触れる

各修正は、本文中にそのまま存在する短い一節（before、1文以内）と、置き換え後（after）で返します。
before は本文と1文字も違わないこと。AIっぽさが無ければ edits は空で構いません。
"""


class Edit(BaseModel):
    before: str
    after: str
    reason: str


class Review(BaseModel):
    edits: list[Edit]


def apply_edits(text: str, edits: list[Edit]) -> tuple[str, list[dict]]:
    log = []
    for e in edits:
        status = "applied"
        if not e.before or e.before == e.after:
            status = "skipped: empty or no-op"
        elif len(e.before) > 200:
            status = "skipped: too long (内容変更の恐れ)"
        elif PAYWALL in e.before or "[[図" in e.before or e.before.lstrip().startswith("#"):
            status = "skipped: protected (有料ライン/図/見出し)"
        elif e.before not in text:
            status = "skipped: not found"
        else:
            text = text.replace(e.before, e.after, 1)
        log.append({**e.model_dump(), "status": status})
    return text, log


def run(day: str | None = None) -> str:
    cfg = storage.config()
    d = storage.day_dir(day)
    draft_path = d / "draft.md"
    if not draft_path.exists():
        raise SystemExit("先に write を実行してください")
    draft = draft_path.read_text(encoding="utf-8")

    review = llm.ask_json(
        model=cfg["models"]["reviewer"],  # 執筆担当とは別のモデル
        system=SYSTEM,
        prompt=f"<article>\n{draft}\n</article>\n\nAIっぽい言い回しの置換リストを返してください。",
        schema=Review,
        effort="medium",
    )
    fixed, log = apply_edits(draft, review.edits)
    (d / "reviewed.md").write_text(fixed, encoding="utf-8")
    storage.write_json(d / "review_log.json", log)
    n = sum(1 for x in log if x["status"] == "applied")
    print(f"[review] {n}/{len(log)} 箇所を修正")
    return fixed
