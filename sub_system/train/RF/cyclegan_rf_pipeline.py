"""
cyclegan_rf_pipeline

�Τ@�Ӿ�s���C���� maintain ���� combine_cyclegan_rf CLI �M���O Step3 ���ާ@�X���Φh���X.
�������Ʀ������ sub_system.train.py_cyclegan.inference �P sub_system.train.RF.inference�A�o��ɮפN�u�쥻���N�X�B��.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from sub_system.train.py_cyclegan.inference import CycleGANConverter
from sub_system.train.RF.inference import RFClassifier


class CycleganRFEngine:
    """�ϥ� CycleGANConverter + RFClassifier �����y�{����w���������C"""

    def __init__(
        self,
        rf_model_dir: Path | str,
        cyclegan_checkpoint: Optional[Path | str] = None,
        direction: str = "AB",
        normalization_path: Optional[Path | str] = None,
        apply_normalization: bool = True,
        scaler_path: Optional[Path | str] = None,
        aggregation_override: Optional[str] = None,
    ):
        self.rf = RFClassifier(rf_model_dir, scaler_path=scaler_path)
        self.aggregation_override = aggregation_override

        self.converter: Optional[CycleGANConverter] = None
        if cyclegan_checkpoint:
            self.converter = CycleGANConverter(
                checkpoint_path=cyclegan_checkpoint,
                direction=direction,
                normalization_path=normalization_path,
                apply_normalization=apply_normalization,
            )

    @property
    def metadata(self) -> Dict[str, Any]:
        return getattr(self.rf, "metadata", {})

    def run(self, features: np.ndarray, keep_raw_result: bool = False) -> Dict[str, Any]:
        """�۰ʶ��u convert + RF predict �A�^�Ǿs�u�榡���G�C"""
        features = np.asarray(features, dtype=np.float32)
        if features.ndim != 2:
            raise ValueError(f"features �����O (T, F) �榡�A�ثe shape={features.shape}")

        if self.converter:
            converted = self.converter.convert(features)
        else:
            converted = features

        converted_result = self.rf.predict(converted, aggregation=self.aggregation_override)
        raw_result = None
        if keep_raw_result:
            raw_result = self.rf.predict(features, aggregation=self.aggregation_override)

        return {
            "converted": converted_result,
            "raw": raw_result,
            "converted_features": converted,
        }
