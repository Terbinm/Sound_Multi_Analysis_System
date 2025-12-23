from __future__ import annotations

"""
RF.inference

���Ѥ@�ΧRFClassifier ��ϥ�已���p���榡�зǡA�ä��|�̷Ӧp�X��N�Q�ФW�[�����ϡC
���`�B�n numpy ���� float tensor���A���� CLI / DB ��k�C
"""

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


def aggregate_features(features: np.ndarray, method: Optional[str]) -> np.ndarray:
    """�̷Ӫ����y�覡�p�X segments�ӾǷj�C"""
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
    """�p�� RF ���զX�G�ΧP�����١C"""
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
    """�]�� RandomForest �зǪ��쐬���B���Ѹ�X�G�C"""

    def __init__(self, model_dir: Path | str, scaler_path: Optional[Path | str] = None):
        self.model_dir = Path(model_dir).resolve()
        if not self.model_dir.exists():
            raise FileNotFoundError(f"�䤣�� RF �ҫ���Ƨ�: {self.model_dir}")

        self.model_path = self.model_dir / "mimii_fan_rf_classifier.pkl"
        if not self.model_path.exists():
            raise FileNotFoundError(f"�䤣�� RF �ҫ��ɮ�: {self.model_path}")

        with self.model_path.open("rb") as f:
            self.model = pickle.load(f)

        metadata_path = self.model_dir / "model_metadata.json"
        if metadata_path.exists():
            with metadata_path.open("r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {}

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

    def predict(
        self,
        features: np.ndarray,
        aggregation: Optional[str] = None,
        include_invalid: bool = True,
    ) -> Dict[str, Any]:
        """���ѥS�x�p�� RandomForest �зǪ��G�C"""
        if features.ndim != 2:
            raise ValueError(f"features �����O 2 �� (T, F)�A�ثe shape={features.shape}")

        total_segments = features.shape[0]
        valid_mask = np.any(np.abs(features) > 0, axis=1)
        valid_features = features[valid_mask]
        if valid_features.size == 0:
            raise ValueError("�S�����Ī��S�x�i�ѹw��")

        X = valid_features
        if self.scaler is not None:
            X = self.scaler.transform(X)

        method = (aggregation or self.aggregation or "mean").lower()
        predictions: List[Dict[str, Any]] = []

        if method == "segments":
            classes = self.model.predict(X)
            probas = self._predict_proba_safe(X)
            pointer = 0
            for idx in range(total_segments):
                if valid_mask[idx]:
                    predictions.append(self._build_prediction(idx, int(classes[pointer]), probas[pointer]))
                    pointer += 1
                elif include_invalid:
                    predictions.append(self._build_unknown(idx))
        else:
            aggregated = aggregate_features(X, method)
            classes = self.model.predict(aggregated)
            probas = self._predict_proba_safe(aggregated)
            cls = int(classes[0])
            proba = probas[0]
            for idx in range(total_segments):
                if valid_mask[idx]:
                    predictions.append(self._build_prediction(idx, cls, proba))
                elif include_invalid:
                    predictions.append(self._build_unknown(idx))

        summary = summarize_predictions(predictions)
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
