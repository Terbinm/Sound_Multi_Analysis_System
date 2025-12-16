"""Utility helpers for normalization and augmentation."""

from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np


def normalize_features(features: np.ndarray, mean: Optional[np.ndarray], std: Optional[np.ndarray]) -> np.ndarray:
    """標準化特徵."""
    if mean is None or std is None:
        return features
    return (features - mean) / (std + 1e-8)


def augment_features(features: np.ndarray, noise_std: float = 0.01, dropout_prob: float = 0.1) -> np.ndarray:
    """進行簡易數據增強。"""
    augmented = features.copy()
    if noise_std > 0:
        augmented += np.random.normal(0, noise_std, size=augmented.shape).astype(np.float32)
    if 0 < dropout_prob < 1:
        mask = np.random.rand(*augmented.shape) > dropout_prob
        augmented *= mask
    return augmented


class LEAFPreprocessor:
    """Handle normalization / augmentation for LEAF segments."""

    def __init__(
        self,
        *,
        normalize: bool = True,
        augment: bool = False,
        mean: Optional[np.ndarray] = None,
        std: Optional[np.ndarray] = None,
    ):
        self.normalize_enabled = normalize
        self.augment_enabled = augment
        self.mean = mean
        self.std = std

    def fit(self, samples: Iterable[np.ndarray]) -> None:
        """根據資料估計 mean/std。"""
        stacked = np.vstack(list(samples))
        self.mean = np.mean(stacked, axis=0)
        self.std = np.std(stacked, axis=0)

    def transform(self, features: np.ndarray) -> np.ndarray:
        result = np.asarray(features, dtype=np.float32)
        if self.normalize_enabled:
            result = normalize_features(result, self.mean, self.std)
        if self.augment_enabled:
            result = augment_features(result)
        return result

    def process_batch(self, features_list: List[np.ndarray]) -> List[np.ndarray]:
        """批次處理特徵列表。"""
        return [self.transform(features) for features in features_list]
