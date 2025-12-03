"""
Discriminator Network for CycleGAN

判别 40 维 LEAF 特征的真伪
使用多层感知器架构
"""

import torch
import torch.nn as nn
from typing import List


class Discriminator(nn.Module):
    """
    判别器网络：判断输入特征是真实的还是生成的

    架构：
        输入 (40) → 多层 MLP → 输出 (1)

    Args:
        input_dim: 输入特征维度（默认 40）
        hidden_dims: 隐藏层维度列表
        dropout: Dropout 概率
        use_batch_norm: 是否使用 Batch Normalization
    """

    def __init__(
        self,
        input_dim: int = 40,
        hidden_dims: List[int] = [128, 256, 128],
        dropout: float = 0.2,
        use_batch_norm: bool = True,
    ):
        super().__init__()

        self.input_dim = input_dim
        self.hidden_dims = hidden_dims

        layers = []
        current_dim = input_dim

        # 构建多层判别网络
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(current_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim) if use_batch_norm else nn.Identity(),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Dropout(dropout),
            ])
            current_dim = hidden_dim

        # 最后一层：输出真假概率
        layers.append(nn.Linear(current_dim, 1))

        # ⭐⭐⭐ 必須加這句（你原本少了）
        self.model = nn.Sequential(*layers)


    def forward(self, x: torch.Tensor) -> torch.Tensor:
        is_sequence = (x.dim() == 3)

        if is_sequence:
            batch_size, seq_len, feat_dim = x.shape
            x = x.reshape(batch_size * seq_len, feat_dim)

        out = self.model(x)

        if is_sequence:
            out = out.reshape(batch_size, seq_len, -1)

        return out






    def extract_features(self, x: torch.Tensor):
        """
        回傳中間層 feature maps（用於 Feature Matching Loss）
        """
        features = []
        out = x

        for layer in self.model:
            if isinstance(layer, nn.Linear):
                if out.dim() == 3:
                    B, T, F = out.shape
                    out = out.reshape(B * T, F)
                    out = layer(out)
                    out = out.reshape(B, T, -1)
                else:
                    out = layer(out)



            elif isinstance(layer, nn.BatchNorm1d):

                if out.dim() == 3:
                    out = out.transpose(1, 2)
                    out = layer(out)
                    out = out.transpose(1, 2)
                else:
                    out = layer(out)
            features.append(out)
        return features







    def __repr__(self) -> str:
        return (
            f"Discriminator(\n"
            f"  input_dim={self.input_dim},\n"
            f"  hidden_dims={self.hidden_dims}\n"
            f")"
        )


class PatchDiscriminator(nn.Module):
    """
    PatchGAN 判别器：对序列特征的局部区域进行判别

    适用于序列特征，在时间维度上进行局部判别

    Args:
        input_dim: 输入特征维度
        hidden_dims: 隐藏层维度
        kernel_size: 卷积核大小（用于序列处理）
        stride: 卷积步长
    """

    def __init__(
        self,
        input_dim: int = 40,
        hidden_dims: List[int] = [64, 128, 256, 128],
        kernel_size: int = 3,
        stride: int = 2,
    ):
        super().__init__()

        layers = []
        current_dim = 1  # 输入通道数

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Conv1d(
                    current_dim,
                    hidden_dim,
                    kernel_size=kernel_size,
                    stride=stride,
                    padding=kernel_size // 2,
                ),
                nn.BatchNorm1d(hidden_dim),
                nn.LeakyReLU(0.2, inplace=True),
            ])
            current_dim = hidden_dim

        # 最后一层：输出判别结果
        layers.append(
            nn.Conv1d(
                current_dim,
                1,
                kernel_size=kernel_size,
                stride=1,
                padding=kernel_size // 2,
            )
        )

        self.model = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播

        Args:
            x: 输入特征 (batch_size, seq_len, feat_dim)

        Returns:
            判别结果 (batch_size, 1, patch_num)
        """
        # 调整维度：(batch, seq_len, feat_dim) → (batch, 1, seq_len * feat_dim)
        batch_size, seq_len, feat_dim = x.shape
        x = x.reshape(batch_size, 1, seq_len * feat_dim)

        # 卷积判别
        out = self.model(x)

        return out


if __name__ == "__main__":
    # 测试标准判别器
    print("=== Standard Discriminator ===")
    disc = Discriminator(input_dim=40, hidden_dims=[128, 256, 128])

    # 单个样本测试
    x = torch.randn(8, 40)
    y = disc(x)
    print(f"Single sample - Input shape: {x.shape}, Output shape: {y.shape}")

    # 序列测试
    x_seq = torch.randn(8, 50, 40)
    y_seq = disc(x_seq)
    print(f"Sequence - Input shape: {x_seq.shape}, Output shape: {y_seq.shape}")

    # 计算参数量
    total_params = sum(p.numel() for p in disc.parameters())
    print(f"Total parameters: {total_params:,}\n")

    # 测试 PatchGAN 判别器
    print("=== PatchGAN Discriminator ===")
    patch_disc = PatchDiscriminator(input_dim=40, hidden_dims=[64, 128, 256, 128])

    x_seq = torch.randn(8, 50, 40)
    y_patch = patch_disc(x_seq)
    print(f"Input shape: {x_seq.shape}, Output shape: {y_patch.shape}")

    total_params = sum(p.numel() for p in patch_disc.parameters())
    print(f"Total parameters: {total_params:,}")
