"""测试替身：确定性、零依赖的字符袋向量（dim=256）。

用途与边界，必须说清楚：
- 它**不是**语义模型，不能证明检索质量。真实语义质量只能由 bge-m3 的真机 e2e 证明。
- 它保留"字面越接近、余弦越接近"的几何性质，因此能验证检索链路本身：
  chunk → 本地 Qdrant → payload 回查 PG → 过滤 → 排序 → 权限。
- 生产代码路径（SentenceTransformerProvider）不参与这些测试。
"""

from __future__ import annotations

import math


class CharBagEmbeddingProvider:
    def __init__(self, dimension: int = 256, model_name: str | None = None) -> None:
        self._dimension = dimension
        self._model_name = model_name or f"test-charbag-{self._dimension}"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self._dimension
            for ch in text.lower():
                if ch.isspace():
                    continue
                vec[ord(ch) % self._dimension] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out
