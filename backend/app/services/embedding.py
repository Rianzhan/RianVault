"""Embedding provider 抽象层。

硬性约束（数据主权）：
- 只做**本地**推理。任何把正文或向量发往第三方 API 的实现都不允许进入本仓库。
- 模型名只出现在配置里（settings.embedding_model），业务代码不得硬编码。
- provider 缺失依赖时必须抛出清晰错误，绝不退化成"假向量"假装成功。
"""

from __future__ import annotations

import threading
from typing import Protocol

from app.core.config import get_settings


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str:
        """权重标识（写进 chunk_index.embedding_model，用于判断是否需要重建索引）。"""

    @property
    def dimension(self) -> int:
        """向量维度（建集合时需要）。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """本地推理：批量文本 → 向量。不落日志、不联网。"""


class SentenceTransformerProvider:
    """本地 sentence-transformers 实现（默认 bge-m3，支持中英双语）。

    import 放在 __init__ 里：只有真正要建索引/检索时才加载 torch，
    普通 API 请求不会被这几个 GB 的依赖拖累。
    """

    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._device = device or settings.embedding_device
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        model = self._load()
        # sentence-transformers >= 6 重命名为 get_embedding_dimension
        new_getter = getattr(model, "get_embedding_dimension", None)
        getter = new_getter if new_getter is not None else model.get_sentence_embedding_dimension
        return int(getter())

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        settings = get_settings()
        vectors = self._load().encode(
            texts,
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, v)) for v in vectors]

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:  # pragma: no cover - 依赖缺失时才有
                raise RuntimeError(
                    "sentence-transformers 未安装，无法做本地向量化。"
                    "安装：pip install sentence-transformers（CPU 版 torch 见 README）。"
                    "为保证数据主权，不会退化为任何远端 embedding 服务。"
                ) from e
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model


PROVIDERS = {
    "sentence-transformers": SentenceTransformerProvider,
}

# 单例缓存：provider 实例上持有已加载的模型，每次 new 都会重新加载权重。
# 实测代价：本地缓存下每次约 5 秒 —— 检索慢、建索引慢的真凶就是这个。
_provider_cache: dict[tuple, EmbeddingProvider] = {}
_provider_lock = threading.Lock()


def reset_embedding_provider() -> None:
    """测试/换配置时清空缓存（正常运行时不需要）。"""
    with _provider_lock:
        _provider_cache.clear()


def get_embedding_provider(
    name: str | None = None,
    *,
    model_name: str | None = None,
    device: str | None = None,
) -> EmbeddingProvider:
    settings = get_settings()
    provider_key = name or settings.embedding_provider
    if provider_key not in PROVIDERS:
        raise ValueError(f"未知的 embedding provider: {provider_key}（可用：{sorted(PROVIDERS)}）")
    cls = PROVIDERS[provider_key]
    # 同一个 provider 但模型/设备不同 → 视为不同实例（模型权重不同）
    cache_key = (provider_key, model_name, device)
    with _provider_lock:
        cached = _provider_cache.get(cache_key)
        if cached is None:
            cached = cls(model_name=model_name, device=device)
            _provider_cache[cache_key] = cached
        return cached
