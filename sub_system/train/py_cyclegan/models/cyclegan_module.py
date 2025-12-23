"""
CycleGAN PyTorch Lightning Module

完整的 CycleGAN 训练逻辑
包含：
- 双向生成器（G_AB, G_BA）
- 双向判别器（D_A, D_B）
- Cycle Consistency Loss
- Adversarial Loss
- Identity Loss
"""

import torch
import torchaudio
import torch.nn as nn
import pytorch_lightning as pl
from typing import Dict, Tuple, Optional, Any
import torch.nn.functional as F

from .generator import Generator
from .discriminator import Discriminator


class CycleGANModule(pl.LightningModule):
    """
    CycleGAN Lightning 模块

    用于无监督的域适应，将 Domain A 的 LEAF 特征转换到 Domain B

    Args:
        input_dim: 特征维度（默认 40）
        generator_config: 生成器配置
        discriminator_config: 判别器配置
        learning_rate: 学习率
        beta1: Adam 优化器的 beta1
        beta2: Adam 优化器的 beta2
        lambda_cycle: Cycle consistency loss 权重
        lambda_identity: Identity loss 权重
        use_identity_loss: 是否使用 Identity loss
    """

    def __init__(
        self,
        input_dim: int = 40,
        generator_config: Optional[Dict[str, Any]] = None,
        discriminator_config: Optional[Dict[str, Any]] = None,
        lr_g: float = 0.0001,
        lr_d: float = 0.0001,

        beta1: float = 0.5,
        beta2: float = 0.999,

        lambda_cycle: float = 12.0,

        lambda_identity: float = 6.0,

        lambda_fm: float = 1.0,

        use_identity_loss: bool = True,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.lr_g = lr_g
        self.lr_d = lr_d

        # 自动优化设置
        self.automatic_optimization = False

        # 配置
        gen_config = generator_config or {
            "input_dim": input_dim,
            "hidden_dims": [128, 256, 128],
            "n_residual_blocks": 3,
            "dropout": 0.1,
        }

        disc_config = discriminator_config or {
            "input_dim": input_dim,
            "hidden_dims": [128, 256, 128],
            "dropout": 0.2,
        }

        # 生成器：A → B 和 B → A
        self.generator_AB = Generator(**gen_config)
        self.generator_BA = Generator(**gen_config)

        # 判别器：判别 A 和 B
        self.discriminator_A = Discriminator(**disc_config)
        self.discriminator_B = Discriminator(**disc_config)

        # 损失函数##
        self.criterion_GAN = nn.MSELoss()  # 對抗損失(生成器 & 判別器)
        self.criterion_cycle = nn.L1Loss()  # 循環一致損失(生成器)
        self.criterion_identity = nn.L1Loss() # 身份損失(生成器)(保留音色等結構)

        # ----- 新增的 loss 與超參數 -----
        self.criterion_fm = nn.L1Loss()  # Feature-Matching L1
        self.lambda_fm = lambda_fm

        # 参数
        self.beta1 = beta1
        self.beta2 = beta2
        self.lambda_cycle = lambda_cycle
        self.lambda_identity = lambda_identity
        self.use_identity_loss = use_identity_loss


    def forward(self, x: torch.Tensor, direction: str = "AB") -> torch.Tensor:
        """
        前向传播

        Args:
            x: 输入特征
            direction: "AB" 或 "BA"

        Returns:
            转换后的特征
        """
        if direction == "AB":
            return self.generator_AB(x)
        elif direction == "BA":
            return self.generator_BA(x)
        else:
            raise ValueError(f"Invalid direction: {direction}")



    def training_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int):
        """训练步骤"""
        real_A, real_B = batch

        # 获取优化器
        opt_g, opt_d_A, opt_d_B = self.optimizers()

        # ================== 训练生成器 ==================
        self.toggle_optimizer(opt_g)

        # Identity loss     身份損失##
        loss_identity = torch.tensor(0.0, device=self.device)
        if self.use_identity_loss:
            # G_BA(A) 应该接近 A
            identity_A = self.generator_BA(real_A)
            loss_identity_A = self.criterion_identity(identity_A, real_A)

            # G_AB(B) 应该接近 B
            identity_B = self.generator_AB(real_B)
            loss_identity_B = self.criterion_identity(identity_B, real_B)

            loss_identity = (loss_identity_A + loss_identity_B) / 2

        # GAN loss    對抗損失(生成器 & 判別器)##
        fake_B = self.generator_AB(real_A)
        pred_fake_B = self.discriminator_B(fake_B)
        loss_GAN_AB = self.criterion_GAN(
            pred_fake_B, torch.ones_like(pred_fake_B)
        )
        fake_A = self.generator_BA(real_B)
        pred_fake_A = self.discriminator_A(fake_A)
        loss_GAN_BA = self.criterion_GAN(
            pred_fake_A, torch.ones_like(pred_fake_A)
        )

        # Cycle consistency loss   循環一致損失##
        recovered_A = self.generator_BA(fake_B)
        loss_cycle_A = self.criterion_cycle(recovered_A, real_A)
        recovered_B = self.generator_AB(fake_A)
        loss_cycle_B = self.criterion_cycle(recovered_B, real_B)


        # -----------------------------------------
        # Feature Matching Loss（用中間層特徵）
        # -----------------------------------------
        feat_real_B = self.discriminator_B.extract_features(real_B)
        feat_fake_B = self.discriminator_B.extract_features(fake_B)
        feat_real_A = self.discriminator_A.extract_features(real_A)
        feat_fake_A = self.discriminator_A.extract_features(fake_A)



        def _compute_fm(fr_list, ff_list):
            fm_losses = []
            for real_f, fake_f in zip(fr_list, ff_list):
                fm_losses.append(self.criterion_fm(fake_f, real_f.detach()))
            return sum(fm_losses) / max(1, len(fm_losses))

        loss_fm = (
                          _compute_fm(feat_real_A, feat_fake_A) +
                          _compute_fm(feat_real_B, feat_fake_B)
                  ) / 2




        # 總生成器損失相加##
        loss_G = (
                loss_GAN_AB
                + loss_GAN_BA
                + self.lambda_cycle * (loss_cycle_A + loss_cycle_B)
                + self.lambda_identity * loss_identity
                + self.lambda_fm * loss_fm
        )



        self.manual_backward(loss_G)
        opt_g.step()
        opt_g.zero_grad()
        self.untoggle_optimizer(opt_g)

        # ================== 训练判别器 A ==================
        self.toggle_optimizer(opt_d_A)

        # Real loss
        pred_real_A = self.discriminator_A(real_A)
        loss_D_real_A = self.criterion_GAN(
            pred_real_A, torch.ones_like(pred_real_A)
        )

        # Fake loss
        pred_fake_A = self.discriminator_A(fake_A.detach())
        loss_D_fake_A = self.criterion_GAN(
            pred_fake_A, torch.zeros_like(pred_fake_A)
        )

        # 总判别器 A 损失
        loss_D_A = (loss_D_real_A + loss_D_fake_A) / 2

        self.manual_backward(loss_D_A)
        opt_d_A.step()
        opt_d_A.zero_grad()
        self.untoggle_optimizer(opt_d_A)

        # ================== 训练判别器 B ==================
        self.toggle_optimizer(opt_d_B)

        # Real loss
        pred_real_B = self.discriminator_B(real_B)
        loss_D_real_B = self.criterion_GAN(
            pred_real_B, torch.ones_like(pred_real_B)
        )

        # Fake loss
        pred_fake_B = self.discriminator_B(fake_B.detach())
        loss_D_fake_B = self.criterion_GAN(
            pred_fake_B, torch.zeros_like(pred_fake_B)
        )

        # 总判别器 B 损失
        loss_D_B = (loss_D_real_B + loss_D_fake_B) / 2

        self.manual_backward(loss_D_B)
        opt_d_B.step()
        opt_d_B.zero_grad()
        self.untoggle_optimizer(opt_d_B)

        # ================== 记录损失 ==================
        self.log_dict(
            {
                "loss/G_total": loss_G,
                "loss/G_GAN_AB": loss_GAN_AB,
                "loss/G_GAN_BA": loss_GAN_BA,
                "loss/G_cycle_A": loss_cycle_A,
                "loss/G_cycle_B": loss_cycle_B,
                "loss/G_identity": loss_identity,
                "loss/D_A": loss_D_A,
                "loss/D_B": loss_D_B,
                "loss/fm": loss_fm,
            },
            prog_bar=True,
            on_step=True,
            on_epoch=True,
        )

    def validation_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int
    ):
        """验证步骤"""
        real_A, real_B = batch

        # 生成假样本
        fake_B = self.generator_AB(real_A)
        fake_A = self.generator_BA(real_B)

        # Cycle consistency
        recovered_A = self.generator_BA(fake_B)
        recovered_B = self.generator_AB(fake_A)

        # 计算损失
        loss_cycle_A = self.criterion_cycle(recovered_A, real_A)
        loss_cycle_B = self.criterion_cycle(recovered_B, real_B)

        # GAN loss
        pred_fake_B = self.discriminator_B(fake_B)
        loss_GAN_AB = self.criterion_GAN(
            pred_fake_B, torch.ones_like(pred_fake_B)
        )

        pred_fake_A = self.discriminator_A(fake_A)
        loss_GAN_BA = self.criterion_GAN(
            pred_fake_A, torch.ones_like(pred_fake_A)
        )

        # 记录验证损失
        self.log_dict(
            {
                "val/cycle_A": loss_cycle_A,
                "val/cycle_B": loss_cycle_B,
                "val/GAN_AB": loss_GAN_AB,
                "val/GAN_BA": loss_GAN_BA,
            },
            prog_bar=True,
            on_epoch=True,
        )

    def configure_optimizers(self):
        """配置优化器"""
        # 使用獨立學習率（完全不綁 self.lr）
        lr_g = self.lr_g
        lr_d = self.lr_d
        print("Using lr_g =", lr_g)
        print("Using lr_d =", lr_d)

        params_G = list(self.generator_AB.parameters()) + \
                   list(self.generator_BA.parameters())

        # 生成器優化器
        opt_g = torch.optim.Adam(
            params_G, lr=lr_g, betas=(self.beta1, self.beta2)
        )

        # 判別器 A
        opt_d_A = torch.optim.Adam(
            self.discriminator_A.parameters(),
            lr=lr_d,
            betas=(self.beta1, self.beta2),
        )

        # 判別器 B
        opt_d_B = torch.optim.Adam(
            self.discriminator_B.parameters(),
            lr=lr_d,
            betas=(self.beta1, self.beta2),
        )

        return [opt_g, opt_d_A, opt_d_B], []




    def convert_A_to_B(self, features_A: torch.Tensor) -> torch.Tensor:
        """将 Domain A 的特征转换到 Domain B"""
        self.eval()
        with torch.no_grad():
            return self.generator_AB(features_A)

    def convert_B_to_A(self, features_B: torch.Tensor) -> torch.Tensor:
        """将 Domain B 的特征转换到 Domain A"""
        self.eval()
        with torch.no_grad():
            return self.generator_BA(features_B)


if __name__ == "__main__":
    # 测试 CycleGAN 模块
    model = CycleGANModule(
        input_dim=40,
        lambda_cycle=10.0,
        lambda_identity=5.0,
    )

    # 测试前向传播
    x_A = torch.randn(8, 50, 40)
    x_B = torch.randn(8, 50, 40)

    fake_B = model.convert_A_to_B(x_A)
    fake_A = model.convert_B_to_A(x_B)

    print(f"Input A shape: {x_A.shape}, Generated B shape: {fake_B.shape}")
    print(f"Input B shape: {x_B.shape}, Generated A shape: {fake_A.shape}")

    # 计算总参数量
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nTotal parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}")
