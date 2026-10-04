from __future__ import annotations

from ..config import Settings
from .base import ModelProvider


def build_provider(settings: Settings, n_nodes: int) -> ModelProvider:
    if settings.model_provider == "mock":
        from .mock_provider import MockProvider
        return MockProvider(n_nodes)
    from .gnn_provider import GnnProvider
    return GnnProvider(settings.ml_dir, settings.model_path, n_nodes)
