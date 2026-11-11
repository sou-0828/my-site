"""全担当が共通で使う Claude 呼び出しヘルパー。"""
from __future__ import annotations

from typing import Any, Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_client: Optional[anthropic.Anthropic] = None

FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}


class LLMError(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY などを環境から解決
    return _client


def _stream(**kwargs: Any):
    with client().beta.messages.stream(
        betas=[FALLBACK_BETA],
        fallbacks="default",  # 安全側で断られた場合はサーバー側で別モデルに切り替える
        thinking={"type": "adaptive"},
        **kwargs,
    ) as stream:
        return stream.get_final_message()


def _check(msg) -> None:
    if msg.stop_reason == "refusal":
        cat = msg.stop_details.category if msg.stop_details else None
        raise LLMError(f"モデルが応答を拒否しました (category={cat})")
    if msg.stop_reason == "max_tokens":
        raise LLMError("出力が max_tokens に達して途中で切れました")


def text_of(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def ask_text(
    *,
    model: str,
    system: str,
    prompt: str,
    effort: str = "high",
    web_search: bool = False,
    max_tokens: int = 64000,
) -> str:
    """自由記述で答えさせる。web_search=True ならサーバー側のWeb検索を使わせる。"""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    tools = [WEB_SEARCH_TOOL] if web_search else []
    for _ in range(6):  # pause_turn の再開上限
        msg = _stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": effort},
        )
        if msg.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": msg.content}]
            continue
        _check(msg)
        return text_of(msg)
    raise LLMError("Web検索が規定回数内に終わりませんでした")


def ask_json(
    *,
    model: str,
    system: str,
    prompt: str,
    schema: Type[T],
    effort: str = "high",
    max_tokens: int = 64000,
) -> T:
    """Pydantic モデルの形で必ず返させる（構造化出力）。"""
    msg = _stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
        output_config={"effort": effort},
    )
    _check(msg)
    parsed = msg.parsed_output
    if parsed is None:
        raise LLMError("構造化出力を解析できませんでした")
    return parsed
