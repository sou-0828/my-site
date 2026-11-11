"""デザイン担当：表紙と記事内の図解画像を作る。

Claude が HTML/CSS でデザインし、ヘッドレスブラウザ（Playwright）で PNG に書き出す。
表紙は note 推奨サイズ 1280x670。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel

from . import llm, storage

FIG_RE = re.compile(r"\[\[図:\s*(.+?)\]\]")

SYSTEM = """あなたはnote販売会社のデザイン担当です。
表紙と記事内の図解を、1枚ずつ完結した HTML（<!doctype html> から始まる、CSS は <style> 内）で作ります。

ルール:
- <head> に <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet"> を入れ、font-family は 'Noto Sans JP', sans-serif
- body は margin:0、指定サイズちょうど（表紙 1280x670、図解 1280x720）、はみ出し禁止
- 外部画像・JavaScript は使わない。図形は CSS か インライン SVG で描く
- 表紙: タイトルの核になる短いコピー（最大20字程度）を極太で大きく。サブコピー1行。配色は2〜3色。
  スマホのタイムラインで縮小されても読めること
- 図解: 本文の該当箇所の内容を、ステップ図・比較表・ビフォーアフターなど一目で分かる形にする。文字は最小28px
"""


class Figure(BaseModel):
    index: int
    alt: str
    html: str


class Design(BaseModel):
    cover_alt: str
    cover_html: str
    figures: list[Figure]


def render(items: list[tuple[str, int, int, Path]]) -> None:
    from playwright.sync_api import sync_playwright

    exe = os.getenv("CHROMIUM_PATH")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for html, w, h, out in items:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            page.set_content(html, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
        browser.close()


def run(day: str | None = None) -> str:
    cfg = storage.config()
    d = storage.day_dir(day)
    src = d / "reviewed.md"
    if not src.exists():
        raise SystemExit("先に review を実行してください")
    article = src.read_text(encoding="utf-8")
    plan = storage.read_json(d / "plan.json")
    pick = plan["proposals"][plan["pick_index"]]
    markers = FIG_RE.findall(article)

    fig_list = "\n".join(f"{i}. {m}" for i, m in enumerate(markers)) or "（図解なし）"
    design = llm.ask_json(
        model=cfg["models"]["main"],
        system=SYSTEM,
        prompt=(
            f"タイトル: {pick['title']}\nサブタイトル: {pick['subtitle']}\n読者: {pick['target_reader']}\n\n"
            f"<article>\n{article}\n</article>\n\n"
            f"表紙1枚と、次の図解（index を合わせる）を作ってください:\n{fig_list}"
        ),
        schema=Design,
        effort="medium",
    )

    img = d / "images"
    jobs = [(design.cover_html, 1280, 670, img / "cover.png")]
    alts: dict[int, str] = {}
    for f in design.figures:
        if 0 <= f.index < len(markers):
            jobs.append((f.html, 1280, 720, img / f"fig-{f.index + 1}.png"))
            alts[f.index] = f.alt
    for html, _, _, out in jobs:
        out.with_suffix(".html").parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".html").write_text(html, encoding="utf-8")  # 後から手直しできるよう保存
    render(jobs)

    counter = iter(range(len(markers)))

    def repl(m: re.Match) -> str:
        i = next(counter)
        return f"![{alts[i]}](images/fig-{i + 1}.png)" if i in alts else m.group(0)

    final = FIG_RE.sub(repl, article)
    (d / "article.md").write_text(final, encoding="utf-8")
    print(f"[design] 表紙 + 図解 {len(alts)} 枚 → {img}")
    return final
