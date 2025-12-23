from __future__ import annotations

"""
py_cyclegan.inference

提供 CycleGANConverter，讓其他模組可以載入 CycleGAN checkpoint，
並將 (T, F) 特徵轉換到目標 domain，輸出 numpy 或 torch tensor，
方便 CLI 與資料庫流程使用。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch

try:
    from sub_system.train.py_cyclegan.models.cyclegan_module import CycleGANModule
except Exception:  # pragma: no cover - import 失敗時僅記錄
    CycleGANModule = None  # type: ignore


def _default_project_root() -> Path:
    """回傳預設專案根目錄，用於統一尋找共用資源。"""
    return Path(__file__).resolve().parents[3]


def _load_normalization(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """載入 normalization_params.json，失敗時回傳 None。"""
    if not path:
        return None
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


@dataclass
class CycleGANConverter:
    """負責 CycleGAN checkpoint 的載入與特徵轉換。"""

    checkpoint_path: Path | str
    direction: str = "AB"
    normalization_path: Optional[Path | str] = None
    apply_normalization: bool = True
    device: str = "cpu"

    def __post_init__(self) -> None:
        if CycleGANModule is None:
            raise RuntimeError("無法載入 CycleGANModule，請確認 PyTorch Lightning 依賴是否已安裝。")

        self.checkpoint_path = Path(self.checkpoint_path).resolve()
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"找不到 CycleGAN checkpoint: {self.checkpoint_path}")

        self.device = self._resolve_device(self.device)
        self.model = CycleGANModule.load_from_checkpoint(
            str(self.checkpoint_path), map_location=self.device
        )
        self.model.eval()

        if self.normalization_path is None:
            self.normalization_path = self._auto_find_normalization()

        self.normalization: Optional[Dict[str, Any]] = _load_normalization(
            Path(self.normalization_path) if self.normalization_path else None
        )

    def _resolve_device(self, requested: str) -> str:
        if requested.lower() == "cuda" and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _auto_find_normalization(self) -> Optional[Path]:
        """自動尋找 normalization_params.json，找到時回傳路徑。"""
        candidates = [
            self.checkpoint_path.parent / "normalization_params.json",
            _default_project_root()
            / "sub_system"
            / "train"
            / "py_cyclegan"
            / "checkpoints"
            / "normalization_params.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def convert(self, features: np.ndarray) -> np.ndarray:
        """將 (T, F) numpy array 轉換到另一個 domain。"""
        if features.ndim != 2:
            raise ValueError(f"features 必須是 (T, F) 形狀，實際 shape={features.shape}")

        tensor = torch.tensor(features, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            if self.direction.upper() == "AB":
                converted = self.model.convert_A_to_B(tensor)
            else:
                converted = self.model.convert_B_to_A(tensor)

        converted_np = converted.squeeze(0).cpu().numpy()

        if self.apply_normalization and self.normalization:
            key = "b" if self.direction.upper() == "AB" else "a"
            mean_key = f"mean_{key}"
            std_key = f"std_{key}"
            if mean_key in self.normalization and std_key in self.normalization:
                mean = np.asarray(self.normalization[mean_key], dtype=np.float32)
                std = np.asarray(self.normalization[std_key], dtype=np.float32)
                converted_np = converted_np * std + mean

        return converted_np
