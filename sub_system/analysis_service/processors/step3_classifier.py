# processors/step3_classifier.py - 分類器（適配簡化格式）

import numpy as np
import pickle
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from utils.logger import logger


class AudioClassifier:
    """音訊分類器（支援 RF 模型）"""

    def __init__(self, classification_config: Dict[str, Any]):
        """初始化分類器"""
        self.config = dict(classification_config)
        self.method = self.config['method']
        self.scaler = None
        self.metadata = None

        logger.info(f"分類器初始化: method={self.method}")

        # 載入模型（如果路徑已設定）
        self._apply_method_and_model()

    def apply_config(self, classification_config: Dict[str, Any]):
        """更新分類配置並視需要重新載入模型"""
        if not isinstance(classification_config, dict):
            return
        self.config.update(classification_config)
        self._apply_method_and_model()

    def _apply_method_and_model(self):
        """根據 use_model/support_list 決定實際使用的分類策略並載入模型"""
        support_list = self.config.get('support_list') or ['random', 'rf_model']
        requested_method = self.config.get('method') or support_list[0]
        if requested_method not in support_list:
            logger.warning(f"不支援的分類方法 {requested_method}，改用 {support_list[0]}")
            requested_method = support_list[0]

        use_model = bool(self.config.get('use_model'))
        model_path = self.config.get('model_path')

        # 如果要求模型且路徑有效，載入模型；否則退回隨機
        if use_model and model_path and os.path.exists(model_path):
            self._load_model(model_path)
            self.method = 'rf_model'
        elif use_model and model_path and not os.path.exists(model_path):
            logger.warning(f"模型路徑無效: {model_path}，將改用隨機分類")
            self.scaler = None
            self.metadata = None
            self.method = 'random'
        else:
            self.scaler = None
            self.metadata = None
            # 未啟用模型但要求 rf_model，直接改用隨機並提示
            if requested_method == 'rf_model':
                logger.warning(f"未啟用模型，分類將改用隨機模式{self.method}")
                self.method = 'random'
            else:
                self.method = requested_method if requested_method in support_list else 'random'

        # 若最終使用隨機模式，給出明確警告以便觀察
        if self.method == 'random':
            random_reason = None
            if use_model and model_path and not os.path.exists(model_path):
                random_reason = f"模型路徑無效: {model_path}"
            elif use_model and not model_path:
                random_reason = "未提供模型路徑"
            elif use_model and requested_method == 'rf_model' and not getattr(self, 'model', None):
                random_reason = "模型未載入成功"
            elif not use_model and requested_method == 'rf_model':
                random_reason = "未啟用模型 (use_model=False)"
            elif requested_method == 'random':
                random_reason = "配置指定隨機模式"

            logger.warning(f"分類器使用隨機模式：{random_reason or '未載入模型'}")

    def _load_model(self, model_dir: str):
        """
        載入 RF 分類模型

        Args:
            model_dir: 模型目錄路徑
        """
        try:
            model_dir = Path(model_dir)

            # 載入模型
            model_path = model_dir / 'rf_classifier.pkl'
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"✓ 模型載入成功: {model_path}")

            # 載入 Scaler
            scaler_path = model_dir / 'feature_scaler.pkl'
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info(f"✓ Scaler 載入成功: {scaler_path}")

            # 載入元資料
            metadata_path = model_dir / 'model_metadata.json'
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f"✓ 元資料載入成功")
                logger.info(f"  - 訓練日期: {self.metadata.get('training_date', 'Unknown')}")
                logger.info(f"  - 特徵聚合: {self.metadata.get('aggregation', 'Unknown')}")

        except Exception as e:
            logger.error(f"模型載入失敗: {e}")
            logger.warning("將使用隨機分類模式")

    def classify(self, features_data: List[List[float]]) -> Dict[str, Any]:
        """
        對所有切片進行分類（適配新格式）

        Args:
            features_data: LEAF 特徵向量列表 [[feat1], [feat2], ...]

        Returns:
            分類結果字典（統一格式）
        """
        try:
            logger.debug(f"開始分類: {len(features_data)} 個切片")

            model = getattr(self, 'model', None)
            if self.method == 'rf_model' and model is not None:
                return self._model_classify(features_data)
            else:
                # 任何使用隨機模式的情況皆發出警告
                warn_reason = "配置指定隨機模式"
                use_model = bool(self.config.get('use_model'))
                model_path = self.config.get('model_path')
                requested_method = self.config.get('method')
                if use_model and model_path and not os.path.exists(model_path):
                    warn_reason = f"模型路徑無效: {model_path}"
                elif use_model and not model_path:
                    warn_reason = "未提供模型路徑"
                elif use_model and requested_method == 'rf_model' and model is None:
                    warn_reason = "模型未載入成功"
                elif not use_model and requested_method == 'rf_model':
                    warn_reason = "未啟用模型 (use_model=False)"
                logger.warning(f"分類使用隨機模式：{warn_reason}")
                return self._random_classify_all(features_data)

        except Exception as e:
            logger.error(f"分類失敗: {e}")
            return {
                'features_data': [],
                'processor_metadata': {
                    'method': self.method,
                    'error': str(e)
                }
            }

    def _model_classify(self, features_data: List[List[float]]) -> Dict[str, Any]:
        """
        使用 RF 模型進行分類

        Args:
            features_data: LEAF 特徵向量列表

        Returns:
            分類結果（統一格式）
        """
        try:
            # 過濾有效特徵（非零向量）
            valid_features = []
            valid_indices = []

            for idx, feature_vector in enumerate(features_data):
                # 檢查是否為零向量
                if feature_vector and sum(abs(x) for x in feature_vector) > 0:
                    valid_features.append(feature_vector)
                    valid_indices.append(idx)

            if not valid_features:
                logger.error("沒有有效的特徵向量")
                return self._random_classify_all(features_data)

            # 聚合特徵（根據訓練時的設定）
            aggregation = self.metadata.get('aggregation', 'mean') if self.metadata else 'mean'
            feature_vectors = np.array(valid_features)
            aggregated_feature = self._aggregate_features(feature_vectors, aggregation)

            # 重塑為 (1, n_features)
            aggregated_feature = aggregated_feature.reshape(1, -1)

            # 標準化（如果有 scaler）
            if self.scaler is not None:
                aggregated_feature = self.scaler.transform(aggregated_feature)

            # 預測
            model = getattr(self, 'model', None)
            prediction_class = model.predict(aggregated_feature)[0]
            prediction_proba = model.predict_proba(aggregated_feature)[0]

            # 解碼標籤
            label_decoder = self.metadata.get('label_decoder', {0: 'normal', 1: 'abnormal'})
            if isinstance(label_decoder, dict):
                # 處理 JSON 中字串鍵的情況
                label_decoder = {int(k) if k.isdigit() else k: v for k, v in label_decoder.items()}

            predicted_label = label_decoder.get(int(prediction_class), 'unknown')
            confidence = float(prediction_proba[int(prediction_class)])

            # 為每個切片建立預測結果
            predictions = []
            for idx in range(len(features_data)):
                if idx in valid_indices:
                    prediction = {
                        'segment_id': idx + 1,
                        'prediction': predicted_label,
                        'confidence': confidence,
                        'proba_normal': float(prediction_proba[0]),
                        'proba_abnormal': float(prediction_proba[1])
                    }
                else:
                    prediction = {
                        'segment_id': idx + 1,
                        'prediction': 'unknown',
                        'confidence': 0.0,
                        'error': '特徵無效'
                    }
                predictions.append(prediction)

            # 統計結果
            summary = self._calculate_summary(predictions)

            # processor_metadata（統一格式）
            processor_metadata = {
                'method': 'rf_model',
                'model_type': 'RandomForest',
                'aggregation': aggregation,
                'feature_normalized': self.scaler is not None,
                'total_segments': summary['total_segments'],
                'normal_count': summary['normal_count'],
                'abnormal_count': summary['abnormal_count'],
                'unknown_count': summary['unknown_count'],
                'normal_percentage': summary['normal_percentage'],
                'abnormal_percentage': summary['abnormal_percentage'],
                'final_prediction': summary['final_prediction'],
                'average_confidence': summary['average_confidence']
            }

            result = {
                'features_data': predictions,
                'processor_metadata': processor_metadata
            }

            logger.info(f"分類完成: {summary['final_prediction']} (信心度: {confidence:.3f})")

            return result

        except Exception as e:
            logger.error(f"模型分類失敗: {e}")
            logger.warning("降級至隨機分類")
            return self._random_classify_all(features_data)

    def _aggregate_features(self, features: np.ndarray, method: str) -> np.ndarray:
        """
        聚合多個切片的特徵

        Args:
            features: (n_segments, feature_dim)
            method: 聚合方式

        Returns:
            聚合後的特徵向量
        """
        if method == 'mean':
            return np.mean(features, axis=0)
        elif method == 'max':
            return np.max(features, axis=0)
        elif method == 'median':
            return np.median(features, axis=0)
        elif method == 'all':
            mean_feat = np.mean(features, axis=0)
            std_feat = np.std(features, axis=0)
            max_feat = np.max(features, axis=0)
            min_feat = np.min(features, axis=0)
            return np.concatenate([mean_feat, std_feat, max_feat, min_feat])
        else:
            return np.mean(features, axis=0)

    def _random_classify_all(self, features_data: List[List[float]]) -> Dict[str, Any]:
        """
        隨機分類所有切片

        Args:
            features_data: 特徵向量列表

        Returns:
            分類結果（統一格式）
        """
        logger.warning("分類使用隨機模式：已進入隨機分類流程")
        predictions = []

        for idx, feature_vector in enumerate(features_data):
            # 檢查是否為零向量
            if not feature_vector or sum(abs(x) for x in feature_vector) == 0:
                prediction = {
                    'segment_id': idx + 1,
                    'prediction': 'unknown',
                    'confidence': 0.0,
                    'error': '特徵無效'
                }
            else:
                prediction = self._random_classify_single(idx + 1)

            predictions.append(prediction)

        summary = self._calculate_summary(predictions)

        # processor_metadata（統一格式）
        processor_metadata = {
            'method': 'random',
            'total_segments': summary['total_segments'],
            'normal_count': summary['normal_count'],
            'abnormal_count': summary['abnormal_count'],
            'unknown_count': summary['unknown_count'],
            'normal_percentage': summary['normal_percentage'],
            'abnormal_percentage': summary['abnormal_percentage'],
            'final_prediction': summary['final_prediction'],
            'average_confidence': summary['average_confidence']
        }

        result = {
            'features_data': predictions,
            'processor_metadata': processor_metadata
        }

        logger.info(f"分類完成: {summary['final_prediction']} "
                    f"(正常: {summary['normal_count']}, 異常: {summary['abnormal_count']})")

        return result

    def _random_classify_single(self, segment_id: int) -> Dict[str, Any]:
        """
        隨機分類單個切片

        Args:
            segment_id: 切片 ID

        Returns:
            預測結果
        """
        is_normal = np.random.random() < self.config['normal_probability']

        prediction = {
            'segment_id': segment_id,
            'prediction': 'normal' if is_normal else 'abnormal',
            'confidence': np.random.uniform(0.6, 0.95)
        }

        return prediction

    def _calculate_summary(self, predictions: List[Dict]) -> Dict[str, Any]:
        """
        計算分類結果摘要

        Args:
            predictions: 預測結果列表

        Returns:
            摘要統計
        """
        total = len(predictions)

        if total == 0:
            return {
                'total_segments': 0,
                'normal_count': 0,
                'abnormal_count': 0,
                'unknown_count': 0,
                'normal_percentage': 0.0,
                'abnormal_percentage': 0.0,
                'final_prediction': 'unknown',
                'average_confidence': 0.0
            }

        # 統計各類別數量
        normal_count = sum(1 for p in predictions if p['prediction'] == 'normal')
        abnormal_count = sum(1 for p in predictions if p['prediction'] == 'abnormal')
        unknown_count = sum(1 for p in predictions if p['prediction'] == 'unknown')

        # 計算百分比
        normal_percentage = (normal_count / total) * 100
        abnormal_percentage = (abnormal_count / total) * 100

        # 決定最終判斷
        if abnormal_count > normal_count:
            final_prediction = 'abnormal'
        elif normal_count > abnormal_count:
            final_prediction = 'normal'
        else:
            final_prediction = 'uncertain'

        # 計算平均信心度
        confidences = [p['confidence'] for p in predictions if 'confidence' in p and p['confidence'] > 0]
        avg_confidence = np.mean(confidences) if confidences else 0.0

        summary = {
            'total_segments': total,
            'normal_count': normal_count,
            'abnormal_count': abnormal_count,
            'unknown_count': unknown_count,
            'normal_percentage': round(normal_percentage, 2),
            'abnormal_percentage': round(abnormal_percentage, 2),
            'final_prediction': final_prediction,
            'average_confidence': round(float(avg_confidence), 3)
        }

        return summary

    def set_model(self, model_path: str):
        """
        設定模型路徑並重新載入

        Args:
            model_path: 模型目錄路徑
        """
        self.config['model_path'] = model_path
        self._load_model(model_path)
        if getattr(self, 'model', None) is not None:
            self.method = 'rf_model'
        logger.info(f"模型已更新: {model_path}")
