from __future__ import annotations

"""
RF.inference

提供 RFClassifier 以使用已訓練的模型進行預測。
支援 numpy 陣列 / float tensor，適用於 CLI / DB 流程。
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('analysis_service')


def aggregate_features(features: np.ndarray, method: Optional[str]) -> np.ndarray:
    """依聚合方式 (segments/mean/max/...) 將切片特徵整合成指定型態"""
    method = (method or "mean").lower()
    if method == "segments":
        return features
    if method == "mean":
        return np.mean(features, axis=0, keepdims=True)
    if method == "max":
        return np.max(features, axis=0, keepdims=True)
    if method == "median":
        return np.median(features, axis=0, keepdims=True)
    if method == "all":
        mean_feat = np.mean(features, axis=0, keepdims=True)
        std_feat = np.std(features, axis=0, keepdims=True)
        max_feat = np.max(features, axis=0, keepdims=True)
        min_feat = np.min(features, axis=0, keepdims=True)
        return np.concatenate([mean_feat, std_feat, max_feat, min_feat], axis=1)
    return np.mean(features, axis=0, keepdims=True)


def summarize_predictions(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """輸出 RF 逐片段預測的統計摘要"""
    total = len(predictions)
    if total == 0:
        return {
            "total_segments": 0,
            "normal_count": 0,
            "abnormal_count": 0,
            "unknown_count": 0,
            "normal_percentage": 0.0,
            "abnormal_percentage": 0.0,
            "final_prediction": "unknown",
            "average_confidence": 0.0,
        }

    normal_count = sum(1 for p in predictions if p["prediction"] == "normal")
    abnormal_count = sum(1 for p in predictions if p["prediction"] == "abnormal")
    unknown_count = sum(1 for p in predictions if p["prediction"] == "unknown")

    if abnormal_count > normal_count:
        final_prediction = "abnormal"
    elif normal_count > abnormal_count:
        final_prediction = "normal"
    else:
        final_prediction = "uncertain"

    confidences = [p.get("confidence", 0.0) for p in predictions if p.get("confidence", 0.0) > 0]
    avg_confidence = float(np.mean(confidences)) if confidences else 0.0

    return {
        "total_segments": total,
        "normal_count": normal_count,
        "abnormal_count": abnormal_count,
        "unknown_count": unknown_count,
        "normal_percentage": round((normal_count / total) * 100, 2) if total else 0.0,
        "abnormal_percentage": round((abnormal_count / total) * 100, 2) if total else 0.0,
        "final_prediction": final_prediction,
        "average_confidence": round(avg_confidence, 3),
    }


class RFClassifier:
    """提供 RandomForest 模型預測功能。"""

    def __init__(
        self,
        model_dir: Path | str,
        scaler_path: Optional[Path | str] = None,
        metadata_path: Optional[Path | str] = None,
        model_file: Optional[Path | str] = None
    ):
        self.model_dir = Path(model_dir).resolve()
        if not self.model_dir.exists():
            raise FileNotFoundError(f"找不到 RF 模型目錄: {self.model_dir}")

        # 必須指定模型檔案路徑
        if not model_file:
            raise FileNotFoundError(
                f"未指定 RF 模型檔案路徑 (model_file)。目錄: {self.model_dir}"
            )

        self.model_path = Path(model_file).resolve()
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"RF 模型檔案不存在: {self.model_path}"
            )

        logger.debug(f"[Step 3] RF 模型載入中: {self.model_path}")
        with self.model_path.open("rb") as f:
            self.model = pickle.load(f)

        # 優先使用傳入的 metadata_path，若無則嘗試 model_dir 下的檔案
        resolved_metadata_path: Optional[Path] = None
        if metadata_path:
            resolved_metadata_path = Path(metadata_path).resolve()
            if not resolved_metadata_path.exists():
                logger.warning(f"[Step 3] 指定的 RF 元資料路徑不存在: {resolved_metadata_path}")
                resolved_metadata_path = None

        if resolved_metadata_path is None:
            fallback_path = self.model_dir / "model_metadata.json"
            if fallback_path.exists():
                resolved_metadata_path = fallback_path

        if resolved_metadata_path and resolved_metadata_path.exists():
            with resolved_metadata_path.open("r", encoding="utf-8") as f:
                self.metadata = json.load(f)
            logger.debug(f"[Step 3] RF 元資料載入成功: {resolved_metadata_path}, aggregation={self.metadata.get('aggregation', 'mean')}")
        else:
            self.metadata = {}
            logger.warning("[Step 3] RF 元資料不存在，使用預設值（aggregation=mean, label_decoder=預設）")

        decoder = self.metadata.get("label_decoder", {0: "normal", 1: "abnormal"})
        self.label_decoder: Dict[Any, Any] = {}
        for k, v in decoder.items():
            try:
                key = int(k)
            except (ValueError, TypeError):
                key = k
            self.label_decoder[key] = v

        self.aggregation = (self.metadata.get("aggregation") or "mean").lower()
        self.scaler = None
        if scaler_path:
            scaler_file = Path(scaler_path).resolve()
            if scaler_file.exists():
                with scaler_file.open("rb") as f:
                    self.scaler = pickle.load(f)
                logger.debug(f"[Step 3] RF scaler 載入成功: {scaler_file}")

    def predict(
        self,
        features: np.ndarray,
        aggregation: Optional[str] = None,
        include_invalid: bool = True,
    ) -> Dict[str, Any]:
        """提供特徵並使用 RandomForest 模型進行預測。"""
        if features.ndim != 2:
            raise ValueError(f"features 必須是 2 維 (T, F)，目前 shape={features.shape}")

        total_segments = features.shape[0]
        valid_mask = np.any(np.abs(features) > 0, axis=1)
        valid_features = features[valid_mask]
        valid_count = int(np.sum(valid_mask))

        logger.debug(
            f"[Step 3] RF 預測開始: "
            f"總切片={total_segments}, 有效切片={valid_count}, "
            f"特徵維度={features.shape[1]}, "
            f"輸入值範圍=[{features.min():.4f}, {features.max():.4f}]"
        )

        if valid_features.size == 0:
            raise ValueError("沒有有效的特徵可供預測")

        X = valid_features
        if self.scaler is not None:
            X = self.scaler.transform(X)
            logger.debug(f"[Step 3] RF scaler 已套用: 縮放後值範圍=[{X.min():.4f}, {X.max():.4f}]")

        method = (aggregation or self.aggregation or "mean").lower()
        logger.debug(f"[Step 3] RF 聚合方式: {method}")
        predictions: List[Dict[str, Any]] = []

        if method == "segments":
            classes = self.model.predict(X)
            probas = self._predict_proba_safe(X)
            logger.debug(f"[Step 3] RF segments 模式預測完成: 預測數={len(classes)}")
            pointer = 0
            for idx in range(total_segments):
                if valid_mask[idx]:
                    predictions.append(self._build_prediction(idx, int(classes[pointer]), probas[pointer]))
                    pointer += 1
                elif include_invalid:
                    predictions.append(self._build_unknown(idx))
        else:
            aggregated = aggregate_features(X, method)
            logger.debug(f"[Step 3] RF 聚合後特徵: shape={aggregated.shape}")
            classes = self.model.predict(aggregated)
            probas = self._predict_proba_safe(aggregated)
            cls = int(classes[0])
            proba = probas[0]
            logger.debug(
                f"[Step 3] RF 預測結果: "
                f"class={cls} ({self.label_decoder.get(cls, 'unknown')}), "
                f"proba_normal={proba[0]:.4f}, proba_abnormal={proba[1]:.4f}"
            )
            for idx in range(total_segments):
                if valid_mask[idx]:
                    predictions.append(self._build_prediction(idx, cls, proba))
                elif include_invalid:
                    predictions.append(self._build_unknown(idx))

        summary = summarize_predictions(predictions)
        logger.debug(
            f"[Step 3] RF 預測統計: "
            f"normal={summary['normal_count']}, abnormal={summary['abnormal_count']}, "
            f"final={summary['final_prediction']}, confidence={summary['average_confidence']:.4f}"
        )
        return {
            "predictions": predictions,
            "summary": summary,
        }

    def _predict_proba_safe(self, features: np.ndarray) -> np.ndarray:
        if hasattr(self.model, "predict_proba"):
            return np.asarray(self.model.predict_proba(features), dtype=np.float32)
        return np.full((features.shape[0], 2), 0.5, dtype=np.float32)

    def _build_prediction(
        self, idx: int, prediction_index: int, probabilities: np.ndarray
    ) -> Dict[str, Any]:
        label = self.label_decoder.get(prediction_index, str(prediction_index))
        proba_normal = float(probabilities[0]) if probabilities.size > 0 else 0.0
        proba_abnormal = float(probabilities[1]) if probabilities.size > 1 else 1.0 - proba_normal
        confidence = (
            float(probabilities[prediction_index])
            if prediction_index < probabilities.size
            else max(float(proba_normal), float(proba_abnormal))
        )
        return {
            "segment_id": idx + 1,
            "prediction": label,
            "prediction_index": prediction_index,
            "confidence": confidence,
            "proba_normal": proba_normal,
            "proba_abnormal": proba_abnormal,
        }

    def _build_unknown(self, idx: int) -> Dict[str, Any]:
        return {
            "segment_id": idx + 1,
            "prediction": "unknown",
            "prediction_index": None,
            "confidence": 0.0,
            "proba_normal": 0.0,
            "proba_abnormal": 0.0,
            "error": "empty_feature",
        }
