"""
LEAF Feature Dataset for CycleGAN

处理两个域的 LEAF 特征数据集
"""

import torch
from torch.utils.data import Dataset
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class LEAFDomainDataset(Dataset):
    """
    LEAF 特征双域数据集

    用于 CycleGAN 训练，包含来自两个不同域的 LEAF 特征

    Args:
        domain_a_features: Domain A 的特征列表
        domain_b_features: Domain B 的特征列表
        normalize: 是否标准化特征
        augment: 是否进行数据增强
        max_sequence_length: 最大序列长度（超过则截断，不足则填充）
    """

    def __init__(
        self,
        domain_a_features: List[np.ndarray],
        domain_b_features: List[np.ndarray],
        normalize: bool = True,
        augment: bool = False,
        max_sequence_length: Optional[int] = None,
    ):
        super().__init__()

        self.domain_a_features = domain_a_features
        self.domain_b_features = domain_b_features
        self.normalize = normalize
        self.augment = augment
        self.max_sequence_length = max_sequence_length

        # 统计信息
        self.len_a = len(domain_a_features)
        self.len_b = len(domain_b_features)

        logger.info(
            f"Dataset initialized: Domain A={self.len_a} samples, "
            f"Domain B={self.len_b} samples"
        )

        # 计算归一化参数
        if self.normalize:
            self._compute_normalization_params()

    def _compute_normalization_params(self):
        """计算特征的均值和标准差 - 使用统一归一化"""
        all_features_a = np.vstack(self.domain_a_features)
        all_features_b = np.vstack(self.domain_b_features)

        self.mean_a = np.mean(all_features_a, axis=0)
        self.std_a = np.std(all_features_a, axis=0) + 1e-8
        self.mean_b = np.mean(all_features_b, axis=0)
        self.std_b = np.std(all_features_b, axis=0) + 1e-8

        logger.info(
            "Domain A stats: mean=%.4f, std=%.4f, min=%.4f, max=%.4f",
            all_features_a.mean(),
            all_features_a.std(),
            all_features_a.min(),
            all_features_a.max(),
        )
        logger.info(
            "Domain B stats: mean=%.4f, std=%.4f, min=%.4f, max=%.4f",
            all_features_b.mean(),
            all_features_b.std(),
            all_features_b.min(),
            all_features_b.max(),
        )

    def _normalize(
        self, features: np.ndarray, mean: np.ndarray, std: np.ndarray
    ) -> np.ndarray:
        """标准化特征"""
        return (features - mean) / std

    def _augment(self, features: np.ndarray) -> np.ndarray:
        """数据增强"""
        # 添加高斯噪声
        if np.random.random() < 0.5:
            noise = np.random.normal(0, 0.01, features.shape)
            features = features + noise

        # 特征 dropout（随机将部分特征置零）
        if np.random.random() < 0.3:
            mask = np.random.random(features.shape) > 0.1
            features = features * mask

        return features

    def _process_sequence(self, features: np.ndarray) -> np.ndarray:
        """处理序列长度"""
        if self.max_sequence_length is None:
            return features

        seq_len = len(features)

        if seq_len > self.max_sequence_length:
            # 截断
            features = features[: self.max_sequence_length]
        elif seq_len < self.max_sequence_length:
            # 填充（使用零填充）
            pad_len = self.max_sequence_length - seq_len
            pad = np.zeros((pad_len, features.shape[1]))
            features = np.vstack([features, pad])

        return features

    def __len__(self) -> int:
        """数据集大小取两个域的最大值"""
        return max(self.len_a, self.len_b)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        获取一对样本

        Returns:
            (features_a, features_b): 两个域的特征张量
        """
        # 循环采样（如果一个域的样本数少，则循环使用）
        idx_a = index % self.len_a
        idx_b = index % self.len_b

        # 获取特征
        features_a = self.domain_a_features[idx_a].copy()
        features_b = self.domain_b_features[idx_b].copy()

        # 处理序列长度
        features_a = self._process_sequence(features_a)
        features_b = self._process_sequence(features_b)

        # 标准化
        if self.normalize:
            features_a = self._normalize(features_a, self.mean_a, self.std_a)
            features_b = self._normalize(features_b, self.mean_b, self.std_b)

        # 数据增强
        if self.augment:
            features_a = self._augment(features_a)
            features_b = self._augment(features_b)

        # 转换为 Tensor
        features_a = torch.FloatTensor(features_a)
        features_b = torch.FloatTensor(features_b)

        return features_a, features_b

    def get_normalization_params(self) -> Dict[str, np.ndarray]:
        """获取归一化参数"""
        if not self.normalize:
            return {}

        return {
            "mean_a": self.mean_a,
            "std_a": self.std_a,
            "mean_b": self.mean_b,
            "std_b": self.std_b,
        }


class UnpairedLEAFDataset(Dataset):
    """
    非配对 LEAF 数据集（单域）

    用于推理和转换

    Args:
        features: LEAF 特征列表
        mean: 均值（用于标准化）
        std: 标准差（用于标准化）
        normalize: 是否标准化
    """

    def __init__(
        self,
        features: List[np.ndarray],
        mean: Optional[np.ndarray] = None,
        std: Optional[np.ndarray] = None,
        normalize: bool = True,
    ):
        super().__init__()

        self.features = features
        self.normalize = normalize
        self.mean = mean
        self.std = std

        if normalize and (mean is None or std is None):
            self._compute_stats()

    def _compute_stats(self):
        """计算统计量"""
        all_features = np.vstack(self.features)
        self.mean = np.mean(all_features, axis=0)
        self.std = np.std(all_features, axis=0) + 1e-8

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, index: int) -> torch.Tensor:
        features = self.features[index].copy()

        # 标准化
        if self.normalize:
            features = (features - self.mean) / self.std

        return torch.FloatTensor(features)


if __name__ == "__main__":
    # 测试数据集
    # 创建模拟数据
    np.random.seed(42)

    # Domain A: 100 个样本，每个样本 50 帧，40 维特征
    domain_a_features = [np.random.randn(50, 40) for _ in range(100)]

    # Domain B: 80 个样本
    domain_b_features = [np.random.randn(45, 40) for _ in range(80)]

    # 创建数据集
    dataset = LEAFDomainDataset(
        domain_a_features,
        domain_b_features,
        normalize=True,
        augment=True,
        max_sequence_length=60,
    )

    print(f"Dataset length: {len(dataset)}")

    # 获取一个样本
    feat_a, feat_b = dataset[0]
    print(f"Feature A shape: {feat_a.shape}")
    print(f"Feature B shape: {feat_b.shape}")

    # 查看归一化参数
    norm_params = dataset.get_normalization_params()
    print(f"Normalization params keys: {norm_params.keys()}")
