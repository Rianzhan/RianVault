"""原文切分（chunking）。

约束：
- 只做"按自然边界切"，绝不改写、摘要、翻译正文 —— 否则就不是第一手材料了。
- token 只是估算（中文 roughly 1 字 ≈ 1 token，西文按词估），目的是控制 embedding 输入长度，
  不追求与分词器完全一致；因此 chunk 可以略微超出预算，但不能失控。
- 切片必须能还原原文（测试里用去空白比对兜底），禁止丢字。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 句子/段落边界：中文句末标点 + 换行 + 西文句末标点
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+|\.(?=\s)")
_WORD = re.compile(r"[A-Za-z0-9]+")


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：CJK 按字计，ASCII 词按 1.3 估，其余标点忽略。"""
    tokens = 0
    for ch in text:
        if ord(ch) > 0x2E7F:  # CJK / 全角等宽字符
            tokens += 1
    tokens += int(len(_WORD.findall(text)) * 1.3)
    return max(tokens, 1 if text.strip() else 0)


@dataclass(frozen=True)
class Chunk:
    message_id: str
    conversation_id: str
    chunk_index: int
    text: str
    token_estimate: int


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def chunk_message(
    message_id: str,
    conversation_id: str,
    content_text: str,
    *,
    max_tokens: int = 600,
) -> list[Chunk]:
    """把一条消息切成一个或多个 chunk；短消息返回单 chunk（index 0）。"""
    if not content_text or not content_text.strip():
        return []

    pieces = _split_sentences(content_text)
    total = estimate_tokens(content_text)
    if total <= max_tokens:
        return [
            Chunk(
                message_id=message_id,
                conversation_id=conversation_id,
                chunk_index=0,
                text=content_text.strip(),
                token_estimate=total,
            )
        ]

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_tokens = 0
    for piece in pieces:
        piece_tokens = estimate_tokens(piece)
        # 单句本身就超预算：按字硬切（保底，避免无限增大）
        if piece_tokens > max_tokens:
            if buf:
                chunks.append(_join(buf))
                buf = []
                buf_tokens = 0
            chunks.extend(_hard_split(piece, max_tokens))
            continue
        if buf_tokens + piece_tokens > max_tokens and buf:
            chunks.append(_join(buf))
            buf = []
            buf_tokens = 0
        buf.append(piece)
        buf_tokens += piece_tokens
    if buf:
        chunks.append(_join(buf))

    return [
        Chunk(
            message_id=message_id,
            conversation_id=conversation_id,
            chunk_index=i,
            text=t.strip(),
            token_estimate=estimate_tokens(t),
        )
        for i, t in enumerate(chunks)
        if t.strip()
    ]


def _join(pieces: list[str]) -> str:
    """中文不用空格连接（避免无意义空格污染正文），西文按原习惯空格连接。"""
    if not pieces:
        return ""
    return "".join(pieces) if _is_cjk(pieces[0]) else " ".join(pieces)


def _is_cjk(s: str) -> bool:
    return bool(s) and ord(s[0]) > 0x2E7F


def _hard_split(piece: str, max_tokens: int) -> list[str]:
    """单句过长时按估算预算硬切成若干段（最后一段可能略短）。"""
    out: list[str] = [piece[i : i + max_tokens] for i in range(0, len(piece), max_tokens)]
    return [s for s in out if s.strip()]
