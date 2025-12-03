"""
Loss Functions for CycleGAN
"""

import torch
import torch.nn as nn


class CycleLoss(nn.Module):
    """Cycle Consistency Loss"""

    def __init__(self, lambda_cycle: float = 10.0):
        super().__init__()
        self.lambda_cycle = lambda_cycle
        self.criterion = nn.L1Loss()

    def forward(self, real: torch.Tensor, reconstructed: torch.Tensor) -> torch.Tensor:
        return self.lambda_cycle * self.criterion(reconstructed, real)


class AdversarialLoss(nn.Module):
    """Adversarial Loss (LSGAN)"""

    def __init__(self):
        super().__init__()
        self.criterion = nn.MSELoss()

    def forward(
        self, pred: torch.Tensor, is_real: bool = True
    ) -> torch.Tensor:
        if is_real:
            target = torch.ones_like(pred)
        else:
            target = torch.zeros_like(pred)
        return self.criterion(pred, target)


class IdentityLoss(nn.Module):
    """Identity Loss"""

    def __init__(self, lambda_identity: float = 5.0):
        super().__init__()
        self.lambda_identity = lambda_identity
        self.criterion = nn.L1Loss()

    def forward(self, real: torch.Tensor, identity: torch.Tensor) -> torch.Tensor:
        return self.lambda_identity * self.criterion(identity, real)
