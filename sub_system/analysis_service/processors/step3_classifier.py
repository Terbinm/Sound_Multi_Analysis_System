# processors/step3_classifier.py - ??????????蝛???????

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pickle

from sub_system.train.py_cyclegan.inference import CycleGANConverter
from sub_system.train.RF.inference import RFClassifier
from utils.logger import logger


def _get_project_root() -> Path:
    """
    本地開發：step3_classifier.py 在 sub_system/analysis_service/processors/，需要往上 3 層
    Docker：step3_classifier.py 在 /app/processors/，需要往上 1 層到 /app
    """
    file_path = Path(__file__).resolve()
    # Docker 環境：檔案在 /app/processors/step3_classifier.py
    if file_path.parent.parent == Path("/app"):
        return file_path.parent.parent  # /app
    # 本地開發：檔案在 sub_system/analysis_service/processors/step3_classifier.py
    try:
        return file_path.parents[3]
    except IndexError:
        return file_path.parent.parent


PROJECT_ROOT = _get_project_root()
DEFAULT_RF_MODEL_DIR = PROJECT_ROOT / "sub_system" / "train" / "RF" / "models"
DEFAULT_CYCLEGAN_CKPT = (
    PROJECT_ROOT / "sub_system" / "train" / "py_cyclegan" / "checkpoints" / "last.ckpt"
)
DEFAULT_CYCLEGAN_NORMALIZATION = (
    PROJECT_ROOT
    / "sub_system"
    / "train"
    / "py_cyclegan"
    / "checkpoints"
    / "normalization_params.json"
)


class AudioClassifier:
    """音訊分類器（支援 RF、CycleGAN模型）"""

    def __init__(self, classification_config: Dict[str, Any], model_cache=None):
        """
        初始化分類器

        Args:
            classification_config: 分類配置字典
            model_cache: ModelCacheManager 實例（可選）
        """
        self.config = dict(classification_config)
        self.model_cache = model_cache

        if 'model_path' not in self.config:
            self.config['model_path'] = str(DEFAULT_RF_MODEL_DIR)

        # 支援 default_method 和 method 兩種配置方式
        self.method = self.config.get('method') or self.config.get('default_method', 'random')
        self.scaler = None
        self.metadata = None
        self.cyclegan_converter: Optional[CycleGANConverter] = None
        self.rf_classifier: Optional[RFClassifier] = None
        self.rf_aggregation: Optional[str] = None

        logger.info(f"分類器初始化: method={self.method}")

        # 載入模型（如果路徑已設定）
        self._apply_method_and_model()


    def apply_config(self, classification_config: Dict[str, Any]):
        """更新分類配置並視需要重新載入模型"""
        if not isinstance(classification_config, dict):
            return
        self.config.update(classification_config)
        if 'model_path' not in self.config:
            self.config['model_path'] = str(DEFAULT_RF_MODEL_DIR)
        self._apply_method_and_model()

    def apply_config_with_models(self, full_config: Dict[str, Any], local_paths: Dict[str, Any] = None):
        """
        使用完整配置和已下載的模型路徑套用設定

        Args:
            full_config: 完整的分析配置，包含 model_files
            local_paths: ModelCacheManager.ensure_models_for_config() 返回的本地路徑映射
        """
        if not isinstance(full_config, dict):
            return

        model_files = full_config.get('model_files', {})
        classification_method = model_files.get('classification_method', 'random')
        parameters = full_config.get('parameters', {})
        classification_params = parameters.get('classification', {})

        # 更新配置
        self.config.update(classification_params)
        self.config['method'] = classification_method

        # 如果是 random 方法，不需要模型
        if classification_method == 'random':
            self.config['use_model'] = False
            self._apply_method_and_model()
            logger.info("Using random classification (no model required)")
            return

        # 使用已下載的模型路徑
        if local_paths:
            self.config['use_model'] = True

            if classification_method == 'cyclegan_rf':
                if 'cyclegan_checkpoint' in local_paths:
                    self.config['cyclegan_checkpoint'] = str(local_paths['cyclegan_checkpoint'])
                if 'rf_model' in local_paths:
                    rf_model_path = local_paths['rf_model']
                    self.config['model_path'] = str(rf_model_path.parent)
                    self.config['rf_model_file'] = str(rf_model_path)  # 完整模型檔案路徑
                if 'cyclegan_normalization' in local_paths:
                    self.config['cyclegan_normalization_path'] = str(local_paths['cyclegan_normalization'])
                if 'rf_metadata' in local_paths:
                    self.config['metadata_path'] = str(local_paths['rf_metadata'])
                    logger.info(f"設置 rf_metadata 路徑 (cyclegan_rf): {self.config['metadata_path']}")

            elif classification_method == 'rf_model':
                if 'rf_model' in local_paths:
                    rf_model_path = local_paths['rf_model']
                    self.config['model_path'] = str(rf_model_path.parent)
                    self.config['rf_model_file'] = str(rf_model_path)  # 完整模型檔案路徑
                if 'rf_scaler' in local_paths:
                    self.config['scaler_path'] = str(local_paths['rf_scaler'])
                if 'rf_metadata' in local_paths:
                    self.config['metadata_path'] = str(local_paths['rf_metadata'])
                    logger.info(f"設置 metadata_path: {self.config['metadata_path']}")

            logger.info(f"Applied model paths for method={classification_method}: {list(local_paths.keys())}")

        self._apply_method_and_model()




    def _apply_method_and_model(self):
        support_list = self.config.get('support_list') or ['random', 'rf_model', 'cyclegan_rf']
        # 支援 method 和 default_method 兩種配置方式
        requested_method = self.config.get('method') or self.config.get('default_method') or support_list[0]
        if requested_method not in support_list:
            logger.warning(f"不支援的分類方法 {requested_method}，改用 {support_list[0]}")
            requested_method = support_list[0]

        use_model = bool(self.config.get('use_model'))
        model_path = self._normalize_training_path(
            self.config.get('model_path'),
            DEFAULT_RF_MODEL_DIR
        )
        if model_path:
            self.config['model_path'] = model_path
        self.cyclegan_converter = None
        self.rf_classifier = None
        self.rf_aggregation = None

        if requested_method == 'cyclegan_rf' and use_model:
            try:
                self._load_cyclegan_rf()
                self.method = 'cyclegan_rf'
                return
            except Exception as exc:
                logger.error(f'CycleGAN+RF initialization failed: {exc}')
                requested_method = 'rf_model'

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
            if requested_method in ('rf_model', 'cyclegan_rf'):
                logger.warning(f'未啟用模型，分類將改用隨機模式{requested_method})')
                self.method = 'random'
            else:
                self.method = requested_method if requested_method in support_list else 'random'

        if self.method == 'random':
            random_reason = None
            if use_model and model_path and not os.path.exists(model_path):
                random_reason = f'模型路徑無效: {model_path}'
            elif use_model and not model_path:
                random_reason = '未提供模型路徑'
            elif requested_method == 'rf_model' and not getattr(self, 'model', None):
                random_reason = 'RF 模型未載入成功'
            elif requested_method == 'cyclegan_rf' and (not self.cyclegan_converter or not self.rf_classifier):
                random_reason = 'CycleGAN 模型未載入成功'
            elif not use_model and requested_method in ('rf_model', 'cyclegan_rf'):
                random_reason = '配置指定隨機模式'
            elif requested_method == 'random':
                random_reason = 'configuration requested random mode'
            logger.warning(f'Random classifier is used: {random_reason or "unknown reason"}')

    def _load_cyclegan_rf(self):
        model_dir = self._normalize_training_path(
            self.config.get('model_path'),
            DEFAULT_RF_MODEL_DIR
        ) or str(DEFAULT_RF_MODEL_DIR)
        self.config['model_path'] = model_dir
        logger.debug(f"[Step 3] 載入 CycleGAN+RF: model_dir={model_dir}")
        cyclegan_cfg = self.config.get('cyclegan', {}) or {}
        rf_cfg = self.config.get('rf', {}) or {}

        checkpoint = (
            self.config.get('cyclegan_checkpoint')
            or cyclegan_cfg.get('checkpoint')
            or str(DEFAULT_CYCLEGAN_CKPT)
        )
        checkpoint = self._normalize_training_path(checkpoint, DEFAULT_CYCLEGAN_CKPT)
        if checkpoint:
            self.config['cyclegan_checkpoint'] = checkpoint
        normalization_path = (
            self.config.get('cyclegan_normalization_path')
            or cyclegan_cfg.get('normalization_path')
            or str(DEFAULT_CYCLEGAN_NORMALIZATION)
        )
        normalization_path = self._normalize_training_path(
            normalization_path,
            DEFAULT_CYCLEGAN_NORMALIZATION
        )
        if normalization_path:
            self.config['cyclegan_normalization_path'] = normalization_path
        direction = (
            self.config.get('cyclegan_direction')
            or cyclegan_cfg.get('direction')
            or 'AB'
        )
        apply_norm = self.config.get('apply_normalization')
        if apply_norm is None:
            apply_norm = cyclegan_cfg.get('apply_normalization', True)
        else:
            apply_norm = bool(apply_norm)
        device = (
            self.config.get('cyclegan_device')
            or cyclegan_cfg.get('device')
            or 'cpu'
        )

        scaler_path = (
            self.config.get('scaler_path')
            or rf_cfg.get('scaler_path')
        )
        scaler_path = self._normalize_training_path(scaler_path, None)

        # 取得 metadata 路徑（可能與 model_dir 不同）
        metadata_path = (
            self.config.get('metadata_path')
            or rf_cfg.get('metadata_path')
        )
        metadata_path = self._normalize_training_path(metadata_path, None)

        aggregation_override = (
            self.config.get('rf_aggregation')
            or rf_cfg.get('aggregation')
        )

        self.cyclegan_converter = CycleGANConverter(
            checkpoint_path=checkpoint,
            direction=direction,
            normalization_path=normalization_path,
            apply_normalization=bool(apply_norm),
            device=device,
        )

        # 取得完整的模型檔案路徑
        rf_model_file = self.config.get('rf_model_file')
        self.rf_classifier = RFClassifier(
            model_dir,
            scaler_path=scaler_path,
            metadata_path=metadata_path,
            model_file=rf_model_file  # 傳遞完整模型檔案路徑
        )
        self.metadata = getattr(self.rf_classifier, 'metadata', None)
        self.model = None
        self.scaler = None
        self.rf_aggregation = aggregation_override

    def _load_model(self, model_dir: str):
        """
        載入 RF 分類模型

        Args:
            model_dir: 模型目錄路徑
        """
        try:
            model_dir_path = Path(model_dir)

            # 必須從配置中指定完整模型檔案路徑
            rf_model_file = self.config.get('rf_model_file')

            if not rf_model_file:
                raise FileNotFoundError(
                    f"未指定 RF 模型檔案路徑。請確認配置中包含 rf_model_file。"
                    f"目錄: {model_dir_path}"
                )

            model_path = Path(rf_model_file)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"RF 模型檔案不存在: {model_path}"
                )

            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"✓ 模型載入成功: {model_path}")

            # 優先使用配置中指定的 metadata 路徑（用戶上傳的檔案）
            config_metadata_path = self.config.get('metadata_path')
            if config_metadata_path and Path(config_metadata_path).exists():
                metadata_path = Path(config_metadata_path)
            else:
                # 備用：嘗試模型目錄下的 metadata 檔案
                metadata_path = model_dir_path / 'model_metadata.json'

            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f"✓ 元資料載入成功: {metadata_path}")
                logger.info(f"  - 訓練日期: {self.metadata.get('training_date', 'Unknown')}")
                logger.info(f"  - 特徵聚合: {self.metadata.get('aggregation', 'Unknown')}")
            else:
                self.metadata = {}
                logger.warning(f"元資料檔案不存在: {metadata_path}，使用預設值")
        except Exception as e:
            logger.error(f"模型載入失敗: {e}")
            logger.warning("將使用隨機分類模式")
            self.model = None
            self.scaler = None
            self.metadata = None

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
            logger.debug(
                f"[Step 3] 分類配置: method={self.method}, "
                f"model_path={self.config.get('model_path', '無')}, "
                f"輸入切片數={len(features_data)}"
            )

            if (
                self.method == 'cyclegan_rf'
                and self.cyclegan_converter is not None
                and self.rf_classifier is not None
            ):
                return self._cyclegan_rf_classify(features_data)

            model = getattr(self, 'model', None)
            if self.method == 'rf_model' and model is not None:
                return self._model_classify(features_data)
            else:
                logger.warning(f"!!!分類使用隨機模式!!!")
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

            # 聚合方式（根據訓練時的設定）
            aggregation = self.metadata.get('aggregation', 'mean') if self.metadata else 'mean'
            feature_vectors = np.array(valid_features)
            logger.debug(f"[Step 3] RF 分類配置: 有效特徵={len(valid_features)}/{len(features_data)}, 聚合方式={aggregation}")

            # 解碼標籤
            label_decoder = (self.metadata or {}).get('label_decoder', {0: 'normal', 1: 'abnormal'})
            if isinstance(label_decoder, dict):
                # 處理 JSON 中字串鍵的情況（JSON 的鍵一定是字串）
                label_decoder = {
                    int(k) if isinstance(k, str) and k.isdigit() else k: v
                    for k, v in label_decoder.items()
                }

            model = getattr(self, 'model', None)
            predictions = []

            if aggregation == 'segments':
                # segments 模式：每個 segment 單獨預測
                all_classes = model.predict(feature_vectors)
                all_probas = model.predict_proba(feature_vectors)

                # 統計預測分布
                normal_cnt = sum(1 for c in all_classes if c == 0)
                abnormal_cnt = sum(1 for c in all_classes if c == 1)
                logger.info(f"Segments 預測分布: normal={normal_cnt}, abnormal={abnormal_cnt}, total={len(all_classes)}")

                valid_pointer = 0
                for idx in range(len(features_data)):
                    if idx in valid_indices:
                        pred_class = int(all_classes[valid_pointer])
                        pred_proba = all_probas[valid_pointer]
                        predicted_label = label_decoder.get(pred_class, 'unknown')
                        confidence = float(pred_proba[pred_class])

                        prediction = {
                            'segment_id': idx + 1,
                            'prediction': predicted_label,
                            'confidence': confidence,
                            'proba_normal': float(pred_proba[0]),
                            'proba_abnormal': float(pred_proba[1])
                        }
                        valid_pointer += 1
                    else:
                        prediction = {
                            'segment_id': idx + 1,
                            'prediction': 'unknown',
                            'confidence': 0.0,
                            'error': '特徵無效'
                        }
                    predictions.append(prediction)
            else:
                # 其他聚合模式：先聚合再預測
                aggregated_feature = self._aggregate_features(feature_vectors, aggregation)
                aggregated_feature = aggregated_feature.reshape(1, -1)

                prediction_class = model.predict(aggregated_feature)[0]
                prediction_proba = model.predict_proba(aggregated_feature)[0]

                predicted_label = label_decoder.get(int(prediction_class), 'unknown')
                confidence = float(prediction_proba[int(prediction_class)])

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

            logger.info(f"分類完成: {summary['final_prediction']} (信心度: {summary['average_confidence']:.3f})")

            return result

        except Exception as e:
            logger.error(f"模型分類失敗: {e}")
            logger.warning("降級至隨機分類")
            return self._random_classify_all(features_data)


    def _cyclegan_rf_classify(self, features_data: List[List[float]]) -> Dict[str, Any]:
        if not self.cyclegan_converter or not self.rf_classifier:
            logger.error("CycleGAN+RF 管線尚未初始化")
            return self._random_classify_all(features_data)

        logger.debug(
            f"[Step 3] CycleGAN+RF 分類開始: "
            f"輸入切片數={len(features_data)}, "
            f"CycleGAN direction={getattr(self.cyclegan_converter, 'direction', 'N/A')}"
        )

        feature_matrix = self._prepare_feature_matrix(features_data)
        if feature_matrix.size == 0:
            logger.error("無法取得有效特徵，無法執行 CycleGAN+RF 推論")
            return self._random_classify_all(features_data)

        logger.debug(f"[Step 3] CycleGAN 轉換前特徵矩陣: shape={feature_matrix.shape}")
        converted_features = self.cyclegan_converter.convert(feature_matrix)
        logger.debug(f"[Step 3] CycleGAN 轉換後特徵矩陣: shape={converted_features.shape}")

        aggregation = self.rf_aggregation or getattr(self.rf_classifier, 'aggregation', None)
        logger.debug(f"[Step 3] RF 預測開始: aggregation={aggregation}")
        rf_result = self.rf_classifier.predict(converted_features, aggregation=aggregation)
        predictions = rf_result['predictions']
        summary = rf_result['summary']

        processor_metadata = {
            'method': 'cyclegan_rf',
            'model_type': 'CycleGAN+RF',
            'rf_model_path': self.config.get('model_path'),
            'aggregation': aggregation,
            'cycle_direction': getattr(self.cyclegan_converter, 'direction', None),
            'cyclegan_checkpoint': str(getattr(self.cyclegan_converter, 'checkpoint_path', '')),
            'apply_normalization': getattr(self.cyclegan_converter, 'apply_normalization', True),
            'total_segments': summary['total_segments'],
            'normal_count': summary['normal_count'],
            'abnormal_count': summary['abnormal_count'],
            'unknown_count': summary['unknown_count'],
            'normal_percentage': summary['normal_percentage'],
            'abnormal_percentage': summary['abnormal_percentage'],
            'final_prediction': summary['final_prediction'],
            'average_confidence': summary['average_confidence'],
        }

        logger.info(
            f"CycleGAN+RF 分類完成: {summary['final_prediction']} "
            f"(avg_信心度:={summary['average_confidence']:.3f})"
        )

        return {
            'features_data': predictions,
            'processor_metadata': processor_metadata
        }

    def _prepare_feature_matrix(self, features_data: List[List[float]]) -> np.ndarray:
        feature_dim = 0
        if self.metadata:
            feature_dim = int(self.metadata.get('feature_dim', 0) or 0)
        if feature_dim <= 0:
            for vec in features_data:
                if isinstance(vec, (list, tuple, np.ndarray)) and len(vec) > 0:
                    feature_dim = len(vec)
                    break
        if feature_dim <= 0:
            feature_dim = 40

        rows = []
        for feature_vector in features_data:
            arr = np.zeros(feature_dim, dtype=np.float32)
            if isinstance(feature_vector, (list, tuple, np.ndarray)):
                vec = np.asarray(feature_vector, dtype=np.float32).flatten()
                length = min(feature_dim, vec.size)
                if length > 0:
                    arr[:length] = vec[:length]
            rows.append(arr)

        if not rows:
            return np.zeros((0, feature_dim), dtype=np.float32)
        result = np.vstack(rows)
        logger.debug(f"[Step 3] 特徵矩陣準備完成: 輸入={len(features_data)}個切片, 輸出形狀={result.shape}, 特徵維度={feature_dim}")
        return result

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

    def _normalize_training_path(
        self,
        path_value: Optional[str],
        default: Optional[Path] = None
    ) -> Optional[str]:
        """
        確保訓練資源路徑存在；若使用舊的 /train/... 實際會自動插入 sub_system。
        """
        candidate = self._prepare_candidate_path(path_value)
        resolved = self._try_resolve_training_path(candidate)
        if resolved:
            return str(resolved)

        if default is not None:
            default_candidate = self._prepare_candidate_path(str(default))
            resolved_default = self._try_resolve_training_path(default_candidate)
            if resolved_default:
                if candidate and resolved_default != candidate:
                    logger.warning(
                        f"路徑不存在 {candidate}，改用預設: {resolved_default}"
                    )
                return str(resolved_default)

        return str(candidate) if candidate else None

    def _prepare_candidate_path(self, value: Optional[str]) -> Optional[Path]:
        if not value:
            return None
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).absolute()
        return candidate

    def _try_resolve_training_path(self, candidate: Optional[Path]) -> Optional[Path]:
        if candidate is None:
            return None
        if candidate.exists():
            return candidate

        parts_lower = {part.lower() for part in candidate.parts}
        if 'sub_system' not in parts_lower:
            try:
                rel = candidate.relative_to(PROJECT_ROOT)
            except ValueError:
                rel = None
            if rel:
                patched = (PROJECT_ROOT / 'sub_system' / rel).absolute()
                if patched.exists():
                    logger.warning(f"自動修正路徑: {candidate} -> {patched}")
                    return patched
        return None

