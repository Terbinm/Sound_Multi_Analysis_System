# analysis_pipeline.py - 分析流程管理器（加入 Step 0 轉檔 + TDMS 支援）

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import os
import traceback
from pathlib import Path
from bson.objectid import ObjectId

from config import SERVICE_CONFIG, USE_GRIDFS, AUDIO_CONFIG, CONVERSION_CONFIG, LEAF_CONFIG, CLASSIFICATION_CONFIG
from utils.logger import logger
from utils.mongodb_handler import MongoDBHandler, StepNames
from processors.step0_converter import AudioConverter
from processors.step1_slicer import AudioSlicer
from processors.step2_leaf import LEAFFeatureExtractor
from processors.step2_statistical_features import StatisticalFeatureExtractor
from processors.step3_classifier import AudioClassifier
from gridfs_handler import AnalysisGridFSHandler


class AnalysisPipeline:
    """分析流程管理器（支援 GridFS + 簡化格式 + Step 0 轉檔）"""

    def __init__(self, mongodb_handler: MongoDBHandler):
        """
        初始化分析流程

        Args:
            mongodb_handler: MongoDB 處理器
        """
        self.mongodb = mongodb_handler
        self.config = SERVICE_CONFIG
        self.use_gridfs = USE_GRIDFS

        # 初始化 GridFS Handler（如果啟用）
        if self.use_gridfs:
            self.gridfs_handler = AnalysisGridFSHandler(mongodb_handler.mongo_client)
            logger.info("✓ GridFS 模式已啟用")
        else:
            self.gridfs_handler = None
            logger.info("✓ 本地檔案模式")

        # 初始化處理器
        try:
            self.converter = AudioConverter(AUDIO_CONFIG, CONVERSION_CONFIG)
            self.slicer = AudioSlicer(AUDIO_CONFIG)
            self.leaf_extractor = LEAFFeatureExtractor(LEAF_CONFIG, AUDIO_CONFIG)
            self.stat_extractor = StatisticalFeatureExtractor(sample_rate=10000)
            self.classifier = AudioClassifier(CLASSIFICATION_CONFIG)
            self.current_config = {
                "audio": dict(AUDIO_CONFIG),
                "conversion": dict(CONVERSION_CONFIG),
                "leaf": dict(LEAF_CONFIG),
                "classification": dict(CLASSIFICATION_CONFIG),
                "input": {"format": "wav"},
                "feature": {"method": "leaf"},
                "tdms": {"channels": ["Ch0-T1", "Ch1-T5", "Ch4-T3"], "tdms_sample_rate": 10000, "slice_duration": 1.5},
                "aggregation": {
                    "ratio_threshold": 0.3,
                    "consecutive_threshold": 5,
                    "probability_threshold": 0.6,
                    "mean_threshold": 0.5
                }
            }
            logger.info("✓ 所有處理器初始化成功 (使用預設配置)")
        except Exception as e:
            logger.error(f"✗ 處理器初始化失敗: {e}")
            raise

    def apply_runtime_config(self, parameters: Optional[Dict[str, Any]]):
        """
        套用 analysis_configs.parameters 內容到處理器，保持型別安全。
        """
        merged = {
            "audio": dict(AUDIO_CONFIG),
            "conversion": dict(CONVERSION_CONFIG),
            "leaf": dict(LEAF_CONFIG),
            "classification": dict(CLASSIFICATION_CONFIG),
            "input": {"format": "wav"},
            "feature": {"method": "leaf"},
            "tdms": {"channels": ["Ch0-T1", "Ch1-T5", "Ch4-T3"], "tdms_sample_rate": 10000, "slice_duration": 1.5},
            "aggregation": {
                "ratio_threshold": 0.3,
                "consecutive_threshold": 5,
                "probability_threshold": 0.6,
                "mean_threshold": 0.5
            }
        }

        def merge_section(target: Dict[str, Any], incoming: Dict[str, Any]):
            if not isinstance(incoming, dict):
                return target
            for k, v in incoming.items():
                if k not in target:
                    # 允許新增未定義的鍵
                    target[k] = v
                    continue
                if isinstance(target[k], dict) and isinstance(v, dict):
                    target[k] = merge_section(dict(target[k]), v)
                elif isinstance(target[k], list):
                    if isinstance(v, list):
                        target[k] = v
                elif isinstance(target[k], bool):
                    target[k] = bool(v)
                elif isinstance(target[k], (int, float)):
                    try:
                        target[k] = type(target[k])(v)
                    except Exception:
                        target[k] = target[k]
                else:
                    target[k] = v
            return target

        if isinstance(parameters, dict):
            merge_section(merged["audio"], parameters.get("audio", {}))
            merge_section(merged["conversion"], parameters.get("conversion", {}))
            merge_section(merged["leaf"], parameters.get("leaf", {}))
            merge_section(merged["classification"], parameters.get("classification", {}))
            merge_section(merged["input"], parameters.get("input", {}))
            merge_section(merged["feature"], parameters.get("feature", {}))
            merge_section(merged["tdms"], parameters.get("tdms", {}))
            merge_section(merged["aggregation"], parameters.get("aggregation", {}))

        # 套用到各處理器
        self.converter.apply_config(merged["audio"], merged["conversion"])
        self.slicer.apply_config(merged["audio"])
        self.leaf_extractor.apply_config(merged["leaf"], merged["audio"])
        self.stat_extractor.apply_config({"sample_rate": merged["tdms"].get("tdms_sample_rate", 10000)})
        self.classifier.apply_config(merged["classification"])
        self.current_config = merged
        logger.info("✓ 已套用 runtime 配置到處理器")

    def apply_runtime_config_with_models(self, full_config: Dict[str, Any], local_paths: Dict[str, Any] = None):
        """
        套用配置並處理模型載入

        Args:
            full_config: 完整的分析配置，包含 parameters 和 model_files
            local_paths: ModelCacheManager.ensure_models_for_config() 返回的本地路徑映射
        """
        parameters = full_config.get('parameters', {})

        # 先套用基礎配置
        merged = {
            "audio": dict(AUDIO_CONFIG),
            "conversion": dict(CONVERSION_CONFIG),
            "leaf": dict(LEAF_CONFIG),
            "classification": dict(CLASSIFICATION_CONFIG),
            "input": {"format": "wav"},
            "feature": {"method": "leaf"},
            "tdms": {"channels": ["Ch0-T1", "Ch1-T5", "Ch4-T3"], "tdms_sample_rate": 10000, "slice_duration": 1.5},
            "aggregation": {
                "ratio_threshold": 0.3,
                "consecutive_threshold": 5,
                "probability_threshold": 0.6,
                "mean_threshold": 0.5
            }
        }

        def merge_section(target: Dict[str, Any], incoming: Dict[str, Any]):
            if not isinstance(incoming, dict):
                return target
            for k, v in incoming.items():
                if k not in target:
                    # 允許新增未定義的鍵
                    target[k] = v
                    continue
                if isinstance(target[k], dict) and isinstance(v, dict):
                    target[k] = merge_section(dict(target[k]), v)
                elif isinstance(target[k], list):
                    if isinstance(v, list):
                        target[k] = v
                elif isinstance(target[k], bool):
                    target[k] = bool(v)
                elif isinstance(target[k], (int, float)):
                    try:
                        target[k] = type(target[k])(v)
                    except Exception:
                        target[k] = target[k]
                else:
                    target[k] = v
            return target

        if isinstance(parameters, dict):
            merge_section(merged["audio"], parameters.get("audio", {}))
            merge_section(merged["conversion"], parameters.get("conversion", {}))
            merge_section(merged["leaf"], parameters.get("leaf", {}))
            merge_section(merged["classification"], parameters.get("classification", {}))
            merge_section(merged["input"], parameters.get("input", {}))
            merge_section(merged["feature"], parameters.get("feature", {}))
            merge_section(merged["tdms"], parameters.get("tdms", {}))
            merge_section(merged["aggregation"], parameters.get("aggregation", {}))

        # 套用到音訊處理器
        self.converter.apply_config(merged["audio"], merged["conversion"])
        self.slicer.apply_config(merged["audio"])
        self.leaf_extractor.apply_config(merged["leaf"], merged["audio"])
        self.stat_extractor.apply_config({"sample_rate": merged["tdms"].get("tdms_sample_rate", 10000)})

        # 套用到分類器（包含模型路徑）
        self.classifier.apply_config_with_models(full_config, local_paths)

        self.current_config = merged
        logger.info("✓ 已套用 runtime 配置和模型到處理器")

    def process_record(self, record: Dict[str, Any], task_context: Optional[Dict[str, Any]] = None) -> bool:
        """
        處理單一記錄的完整流程

        Args:
            record: MongoDB 記錄
            task_context: 由任務派送帶入的上下文（router/config/node 等）

        Returns:
            是否處理成功
        """
        analyze_uuid = record.get('AnalyzeUUID', 'UNKNOWN')
        converted_file_path = None  # 轉檔後的檔案路徑（用於最後清理）
        analysis_id: Optional[str] = None

        try:
            logger.info("=" * 60)
            logger.info(f"開始處理記錄: {analyze_uuid}")

            # ✅ 先嘗試認領記錄
            if not self.mongodb.try_claim_record(analyze_uuid):
                logger.info(f"記錄已被其他 Worker 處理,跳過: {analyze_uuid}")
                return True  # 不算失敗

            # 檢查記錄是否已處理
            if self._is_already_processed(record):
                logger.info(f"記錄已處理，跳過: {analyze_uuid}")
                return True

            info_features = record.get('info_features', {}) if isinstance(record, dict) else {}
            target_channels = info_features.get('target_channel', [])

            # 建立新的分析 run（支援多次分析）
            analysis_context = self._build_analysis_context(record, target_channels, task_context)
            run_info = self.mongodb.start_analysis_run(analyze_uuid, analysis_context, record)
            if not run_info:
                self._mark_error(analyze_uuid, "初始化分析任務失敗", analysis_id=None)
                return False
            analysis_id = run_info['analysis_id']

            # 重新讀取最新記錄，確保 analyze_features 結構同步
            record = self.mongodb.get_record_by_uuid(analyze_uuid) or record

            # Step 0: 獲取檔案並判斷是否需要轉檔
            audio_data, temp_file_path = self._get_audio_file(record)
            if audio_data is None and temp_file_path is None:
                self._mark_error(analyze_uuid, "無法獲取音頻檔案", analysis_id=analysis_id)
                return False

            # 判斷輸入格式和處理流程
            input_format = self._get_input_format(temp_file_path)
            feature_method = self.current_config.get('feature', {}).get('method', 'leaf')

            # TDMS 專用流程
            if input_format == 'tdms':
                try:
                    result = self._execute_tdms_pipeline(
                        analyze_uuid, temp_file_path, record, analysis_id, task_context
                    )
                    if result:
                        logger.debug(f"✓ TDMS 記錄處理完成: {analyze_uuid}")
                    return result
                finally:
                    # 清理臨時檔案
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                            logger.debug(f"已清理臨時檔案: {temp_file_path}")
                        except Exception as e:
                            logger.warning(f"清理臨時檔案失敗: {e}")

            # 標準 WAV/CSV 流程
            needs_conversion = self.converter.needs_conversion(temp_file_path)

            working_file_path = self._execute_step0(
                analyze_uuid,
                temp_file_path,
                record,
                analysis_id,
                needs_conversion
            )

            if not working_file_path:
                return False

            if needs_conversion:
                converted_file_path = working_file_path

            try:
                # Step 1: 音訊切割（傳入 target_channels）
                if not self._execute_step1(analyze_uuid, working_file_path, target_channels, analysis_id):
                    return False

                # Step 2: 特徵提取（根據配置選擇 LEAF 或統計特徵）
                if feature_method == 'statistical':
                    if not self._execute_step2_statistical(analyze_uuid, working_file_path, analysis_id):
                        return False
                else:
                    if not self._execute_step2(analyze_uuid, working_file_path, analysis_id):
                        return False

                # Step 3: 分類
                if not self._execute_step3(analyze_uuid, analysis_id):
                    return False

                logger.debug(f"✓ 記錄處理完成: {analyze_uuid}")
                return True

            finally:
                # 清理原始臨時檔案
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        logger.debug(f"已清理原始臨時檔案: {temp_file_path}")
                    except Exception as e:
                        logger.warning(f"清理原始臨時檔案失敗: {e}")

                # 清理轉檔後的臨時檔案
                if converted_file_path and converted_file_path != temp_file_path:
                    self.converter.cleanup_temp_file(converted_file_path)

        except Exception as e:
            logger.error(f"✗ 記錄處理失敗 {analyze_uuid}: {e}")
            logger.error(traceback.format_exc())
            self._mark_error(analyze_uuid, f"處理異常: {str(e)}", analysis_id=analysis_id)
            return False

    def _is_already_processed(self, record: Dict) -> bool:
        """
        檢查記錄是否已處理（檢查是否有正在進行的分析）

        Args:
            record: MongoDB 記錄

        Returns:
            是否已處理或正在處理中
        """
        analyze_features = record.get('analyze_features', {})
        if not isinstance(analyze_features, dict):
            return False

        # 如果有 active_analysis_id，表示正在處理中
        # 這種情況應該讓 try_claim_record() 處理
        active_analysis_id = analyze_features.get('active_analysis_id')
        if active_analysis_id:
            return True  # 已有正在進行的分析

        return False

    def _get_audio_file(self, record: Dict) -> tuple[Optional[bytes], Optional[str]]:
        """
        獲取音頻檔案（從 GridFS 或本地）

        Args:
            record: MongoDB 記錄

        Returns:
            (音頻數據, 臨時檔案路徑) 元組
        """
        try:
            files = record.get('files', {}).get('raw', {})

            if self.use_gridfs:
                # 從 GridFS 讀取
                file_id = files.get('fileId')
                if not file_id:
                    logger.error("記錄中沒有 GridFS fileId")
                    return None, None

                # 處理不同格式的 ObjectId
                if isinstance(file_id, dict) and '$oid' in file_id:
                    file_id = ObjectId(file_id['$oid'])
                elif isinstance(file_id, str):
                    file_id = ObjectId(file_id)

                logger.debug(f"從 GridFS 讀取檔案 (ID: {file_id})")

                # 檢查檔案是否存在
                if not self.gridfs_handler.file_exists(file_id):
                    logger.error(f"GridFS 檔案不存在 (ID: {file_id})")
                    return None, None

                # 下載檔案
                audio_data = self.gridfs_handler.download_file(file_id)
                if not audio_data:
                    logger.error(f"從 GridFS 下載檔案失敗 (ID: {file_id})")
                    return None, None

                # 獲取原始檔案名稱和副檔名
                file_info = self.gridfs_handler.get_file_info(file_id)
                original_filename = file_info.get('filename', 'audio.wav')
                file_extension = os.path.splitext(original_filename)[1] or '.wav'

                # 創建臨時檔案（保留原始副檔名）
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
                temp_file.write(audio_data)
                temp_file.close()

                logger.debug(f"✓ 從 GridFS 讀取檔案成功，創建臨時檔案: {temp_file.name}")
                return audio_data, temp_file.name

            else:
                # 從本地檔案系統讀取（向後相容）
                from config import UPLOAD_FOLDER

                info_features = record.get('info_features', {})
                filepath = info_features.get('filepath')

                if not filepath:
                    filename = files.get('filename')
                    if filename:
                        filepath = os.path.join(UPLOAD_FOLDER, filename)

                if filepath and os.path.exists(filepath):
                    logger.info(f"從本地讀取檔案: {filepath}")
                    with open(filepath, 'rb') as f:
                        audio_data = f.read()
                    return audio_data, filepath
                else:
                    logger.error(f"本地檔案不存在: {filepath}")
                    return None, None

        except Exception as e:
            logger.error(f"獲取音頻檔案失敗: {e}")
            logger.error(traceback.format_exc())
            return None, None

    def _build_analysis_context(self, record: Dict[str, Any], target_channels: list,
                                task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """建立此次分析的上下文資訊"""
        files = record.get('files', {}).get('raw', {})
        info_features = record.get('info_features', {}) or {}
        task_ctx = task_context or {}
        metadata = task_ctx.get('metadata', {})

        routing_rule = {
            'rule_id': task_ctx.get('rule_id') or metadata.get('rule_id'),
            'rule_name': task_ctx.get('rule_name') or metadata.get('rule_name'),
            'router_id': task_ctx.get('router_id') or metadata.get('router_id'),
            'sequence_order': task_ctx.get('sequence_order') or metadata.get('sequence_order')
        }
        analysis_config = {
            'config_id': task_ctx.get('config_id'),
            'config_name': task_ctx.get('config_name'),
            'analysis_method_id': task_ctx.get('analysis_method_id'),
            'analysis_method_name': task_ctx.get('analysis_method_name') or task_ctx.get('analysis_method_id'),
            'mongodb_instance': task_ctx.get('mongodb_instance')
        }
        node_info = task_ctx.get('node_info', {}) or {}

        context = {
            'requested_by': info_features.get('requested_by', 'system'),
            'request_source': info_features.get('request_source', 'auto_on_upload'),
            'target_channels': target_channels or [],
            'source_filename': files.get('filename'),
            'dataset_uuid': info_features.get('dataset_UUID') or info_features.get('dataset_uuid'),
            'pipeline_version': self.config.get('version', 'default'),
            'use_gridfs': self.use_gridfs,
            'task_id': task_ctx.get('task_id'),
            'routing_rule': routing_rule,
            'analysis_config': analysis_config,
            'node': {
                'node_id': task_ctx.get('node_id'),
                'info': node_info
            }
        }

        # 移除空值，保持結構精簡且可動態擴充
        def _prune_empty(obj):
            if isinstance(obj, dict):
                return {k: _prune_empty(v) for k, v in obj.items() if v is not None and v != {} and v != []}
            return obj

        return _prune_empty(context)

    @staticmethod
    def _get_run_from_record(record: Dict[str, Any], analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """從記錄中取得指定 analysis_id 的 run"""
        analyze_features = record.get('analyze_features')

        if isinstance(analyze_features, dict):
            runs = analyze_features.get('runs', {})
            if isinstance(runs, dict):
                # 新格式：dict
                if analysis_id and analysis_id in runs:
                    return runs[analysis_id]
                # 如果沒有指定 analysis_id，返回最新的
                if runs:
                    return list(runs.values())[-1]
            elif isinstance(runs, list):
                # 舊格式：list（向後相容）
                if analysis_id:
                    for run in runs:
                        if run.get('analysis_id') == analysis_id:
                            return run
                if runs:
                    return runs[-1]
        elif isinstance(analyze_features, list):
            # 向後相容：以舊格式包裝成單一 run
            return {
                'analysis_id': analysis_id or 'legacy',
                'steps': analyze_features,
                'analysis_summary': record.get('analysis_summary', {})
            }

        return None

    @staticmethod
    def _find_step_in_run(run: Optional[Dict[str, Any]], step_name: str) -> Optional[Dict[str, Any]]:
        """在 run 中搜尋指定步驟（使用步驟名稱）"""
        if not run:
            return None

        steps = run.get('steps', {})
        if isinstance(steps, dict):
            # 新格式：使用 step name 作為 key
            return steps.get(step_name)
        elif isinstance(steps, list):
            # 舊格式：list（向後相容）
            for step in steps:
                if step.get('features_name') == step_name:
                    return step
        return None

    def _get_input_format(self, filepath: str) -> str:
        """
        根據檔案副檔名判斷輸入格式

        Args:
            filepath: 檔案路徑

        Returns:
            輸入格式: 'wav', 'csv', 'tdms'
        """
        ext = Path(filepath).suffix.lower()
        if ext == '.tdms':
            return 'tdms'
        elif ext == '.csv':
            return 'csv'
        else:
            return 'wav'

    def _execute_tdms_pipeline(
        self,
        analyze_uuid: str,
        filepath: str,
        record: Dict[str, Any],
        analysis_id: str,
        task_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        執行 TDMS 專用分析流程（多通道支援）

        流程：
        1. 讀取 TDMS 多個通道
        2. 各通道切片（不重疊）
        3. 所有切片統一提取統計特徵（12維）
        4. RF 分類
        5. 聚合所有通道的所有切片結果

        訓練時每個通道的每個片段是獨立樣本，預測時也要保持一致。
        例如：3 通道 × 40 片段 = 120 個預測，最後聚合判斷。

        Args:
            analyze_uuid: 記錄 UUID
            filepath: TDMS 檔案路徑
            record: MongoDB 記錄
            analysis_id: 分析 run ID
            task_context: 任務上下文

        Returns:
            是否成功
        """
        try:
            logger.info(f"[TDMS Pipeline] 開始處理 TDMS 檔案（多通道）: {filepath}")

            # 取得 TDMS 配置
            tdms_config = self.current_config.get('tdms', {})
            channels = tdms_config.get('channels', ['Ch0-T1', 'Ch1-T5', 'Ch4-T3'])
            sample_rate = tdms_config.get('tdms_sample_rate', 10000)
            slice_duration = tdms_config.get('slice_duration', 1.5)

            # Step 0: 讀取 TDMS 多通道
            logger.debug(f"[TDMS Step 0] 讀取 TDMS 多通道: channels={channels}")
            channel_signals = self.converter.load_tdms_multi_channel(filepath, channels=channels)

            if not channel_signals:
                error_msg = f"TDMS 檔案讀取失敗，無有效通道 (channels={channels})"
                logger.error(f"[TDMS Step 0] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            # 計算總採樣點數（取最長通道）
            total_samples = max(len(sig) for sig in channel_signals.values())

            # 記錄 Step 0 結果
            step0_info = {
                'needs_conversion': False,
                'conversion_state': 'tdms_loaded',
                'original_format': '.tdms',
                'original_path': filepath,
                'tdms_channels': list(channel_signals.keys()),
                'tdms_channels_requested': channels,
                'tdms_sample_rate': sample_rate,
                'signal_length': total_samples,
                'signal_duration_seconds': total_samples / sample_rate,
                'channels_loaded': len(channel_signals)
            }
            self.mongodb.save_conversion_results(
                analyze_uuid, step0_info, analysis_id=analysis_id, conversion_state='tdms_loaded'
            )
            logger.debug(
                f"[TDMS Step 0] ✓ TDMS 多通道讀取成功: {len(channel_signals)} 通道, "
                f"最長 {total_samples} 採樣點, {total_samples/sample_rate:.2f}秒"
            )

            # Step 1: 各通道切片，收集所有切片
            logger.debug(f"[TDMS Step 1] 多通道切片: duration={slice_duration}s, sample_rate={sample_rate}Hz")
            all_slices = []  # 所有通道的所有切片（含 data）
            slice_records = []  # 儲存用（不含 numpy array）

            for ch_name, signal in channel_signals.items():
                ch_slices = self.slicer.slice_signal(
                    signal,
                    slice_duration=slice_duration,
                    sample_rate=sample_rate,
                    overlap=False
                )

                if not ch_slices:
                    logger.warning(f"[TDMS Step 1] 通道 '{ch_name}' 切片失敗，跳過")
                    continue

                for s in ch_slices:
                    # 加入通道資訊
                    s['channel'] = ch_name
                    all_slices.append(s)

                    # 記錄用（不含 numpy array）
                    slice_records.append({
                        'selec': s['selec'],
                        'start': s['start'],
                        'end': s['end'],
                        'sample_start': s['sample_start'],
                        'sample_end': s['sample_end'],
                        'channel': ch_name
                    })

                logger.debug(f"[TDMS Step 1] 通道 '{ch_name}': {len(ch_slices)} 個切片")

            if not all_slices:
                error_msg = "TDMS 所有通道切片失敗"
                logger.error(f"[TDMS Step 1] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            self.mongodb.save_slice_results(analyze_uuid, slice_records, analysis_id=analysis_id)
            logger.debug(f"[TDMS Step 1] ✓ 多通道切片完成: {len(all_slices)} 個切片（來自 {len(channel_signals)} 通道）")

            # Step 2: 統計特徵提取（所有切片統一處理）
            logger.debug(f"[TDMS Step 2] 提取統計特徵...")
            self.stat_extractor.apply_config({'sample_rate': sample_rate})
            features_data = self.stat_extractor.extract_features(all_slices)

            if not features_data:
                error_msg = "統計特徵提取失敗"
                logger.error(f"[TDMS Step 2] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            # 儲存特徵
            processor_metadata = self.stat_extractor.get_feature_info()
            processor_metadata['total_slices'] = len(all_slices)
            processor_metadata['channels_used'] = list(channel_signals.keys())
            self.mongodb.save_leaf_features(
                analyze_uuid, features_data, processor_metadata, analysis_id=analysis_id
            )
            logger.debug(
                f"[TDMS Step 2] ✓ 統計特徵提取完成: {len(features_data)} 個切片 x {processor_metadata['feature_dim']} 維"
            )

            # Step 3: 分類（所有切片的預測結果一起聚合）
            logger.debug(f"[TDMS Step 3] 開始分類...")
            classification_results = self.classifier.classify(features_data)

            # 應用預測結果聚合
            aggregation_method = self.current_config.get('classification', {}).get('rf_aggregation', 'combined')
            if aggregation_method in ['ratio', 'consecutive', 'combined', 'strict', 'mean']:
                predictions = classification_results.get('features_data', [])
                aggregation_config = self.current_config.get('aggregation', {})
                aggregated = self.classifier.aggregate_segment_predictions(
                    predictions, method=aggregation_method, config=aggregation_config
                )
                # 更新 processor_metadata 中的聚合資訊
                classification_results['processor_metadata'].update({
                    'aggregation_method': aggregation_method,
                    'final_prediction': aggregated['final_prediction'],
                    'aggregation_confidence': aggregated['confidence'],
                    'abnormal_ratio': aggregated.get('abnormal_ratio', 0),
                    'total_segments': len(predictions),
                    'channels_count': len(channel_signals)
                })

            self.mongodb.save_classification_results(
                analyze_uuid, classification_results, analysis_id=analysis_id
            )

            processor_metadata = classification_results.get('processor_metadata', {})
            logger.info(
                f"[TDMS Step 3] ✓ 分類完成: {processor_metadata.get('final_prediction', 'unknown')} "
                f"(正常: {processor_metadata.get('normal_count', 0)}, "
                f"異常: {processor_metadata.get('abnormal_count', 0)}, "
                f"總切片: {processor_metadata.get('total_segments', len(all_slices))}, "
                f"通道: {len(channel_signals)})"
            )

            return True

        except Exception as e:
            logger.error(f"[TDMS Pipeline] 執行失敗: {e}")
            logger.error(traceback.format_exc())
            self._mark_error(analyze_uuid, f"TDMS 處理異常: {str(e)}", analysis_id=analysis_id)
            return False

    def _execute_step2_statistical(self, analyze_uuid: str, filepath: str, analysis_id: str) -> bool:
        """
        執行 Step 2: 統計特徵提取（用於非 TDMS 檔案但選擇統計特徵的情況）

        Args:
            analyze_uuid: 記錄 UUID
            filepath: 音頻檔案路徑
            analysis_id: 分析 run ID

        Returns:
            是否成功
        """
        try:
            logger.debug(f"[Step 2] 開始統計特徵提取...")

            # 獲取切割結果
            record = self.mongodb.get_record_by_uuid(analyze_uuid)
            if not record:
                logger.error(f"[Step 2] 無法獲取記錄")
                self._mark_error(analyze_uuid, "無法重新讀取記錄", analysis_id=analysis_id)
                return False

            run_doc = self._get_run_from_record(record, analysis_id)
            slice_step = self._find_step_in_run(run_doc, StepNames.AUDIO_SLICING)

            if not slice_step:
                logger.error(f"[Step 2] 無切割資料")
                self._mark_error(analyze_uuid, "找不到切割結果", analysis_id=analysis_id)
                return False

            slice_data = slice_step.get('features_data', [])
            if not slice_data:
                logger.error(f"[Step 2] 切割資料為空")
                self._mark_error(analyze_uuid, "切割資料為空", analysis_id=analysis_id)
                return False

            # 從檔案讀取並切片
            import librosa
            audio, sr = librosa.load(filepath, sr=self.current_config['audio']['sample_rate'], mono=True)

            # 根據切片資訊提取訊號片段
            slices = []
            for seg in slice_data:
                start_sample = int(seg['start'] * sr)
                end_sample = int(seg['end'] * sr)
                if end_sample <= len(audio):
                    slices.append({'data': audio[start_sample:end_sample]})

            # 提取統計特徵
            self.stat_extractor.apply_config({'sample_rate': sr})
            features_data = self.stat_extractor.extract_features(slices)

            if not features_data:
                error_msg = "統計特徵提取失敗"
                logger.error(f"[Step 2] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            # 儲存特徵
            processor_metadata = self.stat_extractor.get_feature_info()
            success = self.mongodb.save_leaf_features(
                analyze_uuid, features_data, processor_metadata, analysis_id=analysis_id
            )

            if success:
                logger.debug(
                    f"[Step 2] ✓ 統計特徵提取完成: {len(features_data)} 個切片 (feature_dim={processor_metadata['feature_dim']})"
                )
                return True
            else:
                logger.error(f"[Step 2] ✗ 儲存統計特徵失敗")
                return False

        except Exception as e:
            logger.error(f"[Step 2] 統計特徵執行失敗: {e}")
            self._mark_error(analyze_uuid, f"Step 2 異常: {str(e)}", analysis_id=analysis_id)
            return False

    @staticmethod
    def _extract_source_sample_rate(record: Dict[str, Any]) -> Optional[int]:
        """
        從記錄中推斷來源採樣率

        Args:
            record: MongoDB 記錄

        Returns:
            採樣率（Hz）或 None
        """
        info_features = record.get('info_features', {}) if isinstance(record, dict) else {}

        candidates = [
            info_features.get('sample_rate'),
            info_features.get('sample_rate_hz'),
        ]

        nested_keys = [
            ('mafaulda_metadata', 'sample_rate_hz'),
            ('audio_metadata', 'sample_rate'),
            ('metadata', 'sample_rate'),
        ]

        for path in nested_keys:
            current = info_features
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            candidates.append(current)

        for candidate in candidates:
            if isinstance(candidate, (int, float)) and candidate > 0:
                return int(candidate)
            if isinstance(candidate, str):
                try:
                    value = float(candidate.strip())
                    if value > 0:
                        return int(value)
                except (ValueError, AttributeError):
                    continue

        return None

    def _execute_step0(self, analyze_uuid: str, filepath: str, record: Dict[str, Any],
                       analysis_id: str,
                       needs_conversion: bool) -> Optional[str]:
        """
        執行 Step 0: 音訊轉檔（CSV -> WAV，或 Pass 記錄）

        Args:
            analyze_uuid: 記錄 UUID
            filepath: 原始檔案路徑
            record: MongoDB 記錄（用於推斷來源採樣率）
            analysis_id: 分析 run ID
            needs_conversion: 是否需要實際轉檔

        Returns:
            供後續步驟使用的檔案路徑，若失敗則回傳 None
        """
        try:
            logger.debug(f"[Step 0] 開始音訊轉檔/對齊流程...")

            source_sample_rate = self._extract_source_sample_rate(record)
            if source_sample_rate:
                logger.debug(f"[Step 0] 偵測來源採樣率: {source_sample_rate}Hz")

            if needs_conversion:
                converted_path = self.converter.convert_to_wav(
                    filepath,
                    sample_rate=source_sample_rate
                )

                if not converted_path:
                    error_msg = "音訊轉檔失敗"
                    logger.error(f"[Step 0] {error_msg}")
                    self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                    return None

                conversion_info = self.converter.get_conversion_info(
                    filepath,
                    converted_path,
                    sample_rate=source_sample_rate
                )
                conversion_info['original_path'] = filepath
                conversion_info['needs_conversion'] = True
                if source_sample_rate:
                    conversion_info['source_sample_rate'] = int(source_sample_rate)
                conversion_info['conversion_state'] = 'completed'

                success = self.mongodb.save_conversion_results(
                    analyze_uuid,
                    conversion_info,
                    analysis_id=analysis_id,
                    conversion_state='completed'
                )

                if success:
                    logger.debug(f"[Step 0] ✓ 音訊轉檔完成: {conversion_info.get('original_format')} -> WAV")
                    return converted_path

                logger.error(f"[Step 0] ✗ 儲存轉檔結果失敗")
                return None

            # 不需轉檔，仍建立 Pass 記錄
            conversion_info = {
                'needs_conversion': False,
                'conversion_state': 'pass',
                'original_format': os.path.splitext(filepath)[1] or '',
                'original_path': filepath,
                'message': '原始檔案已符合目標格式，記錄 Pass 以對齊步驟',
                'source_sample_rate': source_sample_rate
            }
            success = self.mongodb.save_conversion_results(
                analyze_uuid,
                conversion_info,
                analysis_id=analysis_id,
                conversion_state='pass'
            )

            if success:
                logger.debug("[Step 0] ✓ 無需轉檔，已記錄 Pass")
                return filepath

            logger.error(f"[Step 0] ✗ 儲存 Pass 結果失敗")
            return None

        except Exception as e:
            logger.error(f"[Step 0] 執行失敗: {e}")
            self._mark_error(analyze_uuid, f"Step 0 異常: {str(e)}", analysis_id=analysis_id)
            return None

    def _execute_step1(self, analyze_uuid: str, filepath: str, target_channels: list,
                       analysis_id: str) -> bool:
        """
        執行 Step 1: 音訊切割

        Args:
            analyze_uuid: 記錄 UUID
            filepath: 音頻檔案路徑（可能是原始檔案或轉檔後檔案）
            target_channels: 目標音軌列表
            analysis_id: 分析 run ID

        Returns:
            是否成功
        """
        try:
            logger.debug(f"[Step 1] 開始音訊切割...")
            logger.debug(f"[Step 1] 目標音軌: {target_channels if target_channels else '預設'}")

            # 執行切割（傳入 target_channels）
            segments = self.slicer.slice_audio(filepath, target_channels)

            if not segments:
                error_msg = "音訊切割失敗或無有效切片"
                logger.error(f"[Step 1] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            # 儲存切割結果
            success = self.mongodb.save_slice_results(analyze_uuid, segments, analysis_id=analysis_id)

            if success:
                logger.debug(f"[Step 1] ✓ 音訊切割完成: {len(segments)} 個切片")
                return True
            else:
                logger.error(f"[Step 1] ✗ 儲存切割結果失敗")
                return False

        except Exception as e:
            logger.error(f"[Step 1] 執行失敗: {e}")
            self._mark_error(analyze_uuid, f"Step 1 異常: {str(e)}", analysis_id=analysis_id)
            return False

    def _execute_step2(self, analyze_uuid: str, filepath: str,
                       analysis_id: str) -> bool:
        """
        執行 Step 2: LEAF 特徵提取（簡化格式）

        Args:
            analyze_uuid: 記錄 UUID
            filepath: 音頻檔案路徑（可能是轉檔後的臨時檔案）
            analysis_id: 分析 run ID

        Returns:
            是否成功
        """
        try:
            logger.debug(f"[Step 2] 開始 LEAF 特徵提取...")

            # 獲取切割結果
            record = self.mongodb.get_record_by_uuid(analyze_uuid)
            if not record:
                logger.error(f"[Step 2] 無法獲取記錄")
                self._mark_error(analyze_uuid, "無法重新讀取記錄", analysis_id=analysis_id)
                return False

            run_doc = self._get_run_from_record(record, analysis_id)
            slice_step = self._find_step_in_run(run_doc, StepNames.AUDIO_SLICING)

            if not slice_step:
                logger.error(f"[Step 2] 無切割資料")
                self._mark_error(analyze_uuid, "找不到切割結果", analysis_id=analysis_id)
                return False

            slice_data = slice_step.get('features_data', [])
            if not slice_data:
                logger.error(f"[Step 2] 切割資料為空")
                self._mark_error(analyze_uuid, "切割資料為空", analysis_id=analysis_id)
                return False

            # 提取特徵（使用檔案路徑）- 返回簡化格式 [[feat1], [feat2], ...]
            features_data = self.leaf_extractor.extract_features(filepath, slice_data)

            if not features_data:
                error_msg = "LEAF 特徵提取失敗"
                logger.error(f"[Step 2] {error_msg}")
                self._mark_error(analyze_uuid, error_msg, analysis_id=analysis_id)
                return False

            # 儲存特徵（簡化格式）
            processor_metadata = self.leaf_extractor.get_feature_info()
            success = self.mongodb.save_leaf_features(
                analyze_uuid, features_data, processor_metadata, analysis_id=analysis_id
            )

            if success:
                feature_dim = processor_metadata.get('feature_dim', processor_metadata.get('n_filters', 'unknown'))
                logger.debug(
                    f"[Step 2] ✓ LEAF 特徵提取完成: {len(features_data)} 個切片 (feature_dim={feature_dim})"
                )
                return True
            else:
                logger.error(f"[Step 2] ✗ 儲存 LEAF 特徵失敗")
                return False

        except Exception as e:
            logger.error(f"[Step 2] 執行失敗: {e}")
            self._mark_error(analyze_uuid, f"Step 2 異常: {str(e)}", analysis_id=analysis_id)
            return False

    def _execute_step3(self, analyze_uuid: str, analysis_id: str) -> bool:
        """
        執行 Step 3: 分類（適配簡化格式）

        Args:
            analyze_uuid: 記錄 UUID
            analysis_id: 分析 run ID

        Returns:
            是否成功
        """
        try:
            logger.debug(f"[Step 3] 開始分類...")

            # 獲取 LEAF 特徵
            record = self.mongodb.get_record_by_uuid(analyze_uuid)
            if not record:
                logger.error(f"[Step 3] 無法獲取記錄")
                self._mark_error(analyze_uuid, "無法重新讀取記錄", analysis_id=analysis_id)
                return False

            run_doc = self._get_run_from_record(record, analysis_id)
            leaf_step = self._find_step_in_run(run_doc, StepNames.LEAF_FEATURES)

            if not leaf_step:
                logger.error(f"[Step 3] 無 LEAF 特徵資料")
                self._mark_error(analyze_uuid, "找不到 LEAF 特徵資料", analysis_id=analysis_id)
                return False

            # 簡化格式: features_data 直接是 [[feat1], [feat2], ...]
            leaf_data = leaf_step.get('features_data', [])
            if not leaf_data:
                logger.error(f"[Step 3] LEAF 特徵資料為空")
                self._mark_error(analyze_uuid, "LEAF 特徵資料為空", analysis_id=analysis_id)
                return False

            # 執行分類（傳入簡化格式）
            classification_results = self.classifier.classify(leaf_data)

            # 儲存分類結果（統一格式）
            success = self.mongodb.save_classification_results(
                analyze_uuid,
                classification_results,
                analysis_id=analysis_id
            )

            if success:
                processor_metadata = classification_results.get('processor_metadata', {})
                logger.debug(
                    f"[Step 3] ✓ 分類完成: {processor_metadata.get('final_prediction', 'unknown')} "
                    f"(正常: {processor_metadata.get('normal_count', 0)}, "
                    f"異常: {processor_metadata.get('abnormal_count', 0)})"
                )
                return True
            else:
                logger.error(f"[Step 3] ✗ 儲存分類結果失敗")
                return False

        except Exception as e:
            logger.error(f"[Step 3] 執行失敗: {e}")
            self._mark_error(analyze_uuid, f"Step 3 異常: {str(e)}", analysis_id=analysis_id)
            return False

    def _mark_error(self, analyze_uuid: str, error_message: str,
                    analysis_id: Optional[str] = None):
        """
        標記記錄為錯誤狀態

        Args:
            analyze_uuid: 記錄 UUID
            error_message: 錯誤訊息
            analysis_id: 分析 run ID
        """
        try:
            if analysis_id:
                # 標記指定 run 的錯誤
                current_time = datetime.now(timezone.utc)
                self.mongodb.collection.update_one(
                    {'AnalyzeUUID': analyze_uuid},
                    {
                        '$set': {
                            f'analyze_features.runs.{analysis_id}.error_message': error_message,
                            f'analyze_features.runs.{analysis_id}.completed_at': current_time,
                            'analyze_features.active_analysis_id': None,  # 釋放鎖
                            'updated_at': current_time
                        }
                    }
                )
            logger.error(f"已標記錯誤: {analyze_uuid} - {error_message}")
        except Exception as e:
            logger.error(f"標記錯誤失敗: {e}")

    def cleanup(self):
        """清理資源"""
        try:
            if hasattr(self, 'leaf_extractor'):
                self.leaf_extractor.cleanup()
            if hasattr(self, 'gridfs_handler') and self.gridfs_handler:
                self.gridfs_handler.close()
            logger.info("分析流程資源已清理")
        except Exception as e:
            logger.error(f"清理資源失敗: {e}")
