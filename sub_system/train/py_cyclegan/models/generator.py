"""
Generator Network for CycleGAN

处理 40 维 LEAF 特征的生成器网络
使用 ResNet 架构保持特征信息
"""

import torch
import torch.nn as nn
from typing import List


class ResidualBlock(nn.Module):
    """残差块，用于保持特征信息"""

    def __init__(self, dim: int, dropout: float = 0.1):
        super().__init__()

        self.block = nn.Sequential(
            nn.Linear(dim, dim),
            nn.BatchNorm1d(dim),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Dropout(dropout),
            nn.Linear(dim, dim),
            nn.BatchNorm1d(dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.block(x)


class Generator(nn.Module):
    """
    生成器网络：将一个域的 LEAF 特征映射到另一个域

    架构：
        输入 (40) → Encoder → ResNet Blocks → Decoder → 输出 (40)

    Args:
        input_dim: 输入特征维度（默认 40）
        hidden_dims: 隐藏层维度列表
        n_residual_blocks: 残差块数量
        dropout: Dropout 概率
        use_batch_norm: 是否使用 Batch Normalization
    """

    def __init__(
        self,
        input_dim: int = 40,
        hidden_dims: List[int] = [128, 256, 128],
        n_residual_blocks: int = 3,
        dropout: float = 0.1,
        use_batch_norm: bool = True,
    ):
        super().__init__()

        self.input_dim = input_dim
        self.hidden_dims = hidden_dims
        self.n_residual_blocks = n_residual_blocks

        # Encoder: 逐步增加维度
        encoder_layers = []
        current_dim = input_dim

        for hidden_dim in hidden_dims:
            encoder_layers.extend([
                nn.Linear(current_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim) if use_batch_norm else nn.Identity(),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Dropout(dropout),
            ])
            current_dim = hidden_dim

        self.encoder = nn.Sequential(*encoder_layers)

        # ResNet Blocks: 在高维空间进行特征变换
        residual_layers = []
        for _ in range(n_residual_blocks):
            residual_layers.append(ResidualBlock(current_dim, dropout))

        self.residual_blocks = nn.Sequential(*residual_layers)

        # Decoder: 逐步减少维度
        decoder_layers = []
        for hidden_dim in reversed(hidden_dims[:-1]):
            decoder_layers.extend([
                nn.Linear(current_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim) if use_batch_norm else nn.Identity(),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Dropout(dropout),
            ])
            current_dim = hidden_dim

        # 最后一层：映射回输入维度
        decoder_layers.extend([
            nn.Linear(current_dim, input_dim),
            nn.Tanh(),  # 输出范围 [-1, 1]
        ])

        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播

        Args:
            x: 输入特征 (batch_size, input_dim) 或 (batch_size, seq_len, input_dim)

        Returns:
            生成的特征，形状与输入相同
        """
        # 处理序列输入
        is_sequence = (x.dim() == 3)
        if is_sequence:
            batch_size, seq_len, feat_dim = x.shape
            x = x.reshape(batch_size * seq_len, feat_dim)

        # Encoder
        x = self.encoder(x)

        # ResNet Blocks
        x = self.residual_blocks(x)

        # Decoder
        x = self.decoder(x)

        # 恢复序列形状
        if is_sequence:
            x = x.reshape(batch_size, seq_len, -1)

        return x

    def __repr__(self) -> str:
        return (
            f"Generator(\n"
            f"  input_dim={self.input_dim},\n"
            f"  hidden_dims={self.hidden_dims},\n"
            f"  n_residual_blocks={self.n_residual_blocks}\n"
            f")"
        )


if __name__ == "__main__":
    # 测试生成器
    model = Generator(input_dim=40, hidden_dims=[128, 256, 128], n_residual_blocks=3)

    # 单个样本测试
    x = torch.randn(8, 40)
    y = model(x)
    print(f"Single sample - Input shape: {x.shape}, Output shape: {y.shape}")

    # 序列测试
    x_seq = torch.randn(8, 50, 40)  # (batch, seq_len, feat_dim)
    y_seq = model(x_seq)
    print(f"Sequence - Input shape: {x_seq.shape}, Output shape: {y_seq.shape}")

    # 计算参数量
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nTotal parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}")
