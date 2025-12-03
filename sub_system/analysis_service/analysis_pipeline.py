# analysis_pipeline.py - 分析流程管理器（加入 Step 0 轉檔）

from typing import Dict, Any, Optional
from datetime import datetime
import os
import traceback
from bson.objectid import ObjectId

from config import SERVICE_CONFIG, USE_GRIDFS
from utils.logger import logger
from utils.mongodb_handler import MongoDBHandler, StepNames
from processors.step0_converter import AudioConverter
from processors.step1_slicer import AudioSlicer
from processors.step2_leaf import LEAFFeatureExtractor
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
            self.converter = AudioConverter()
            self.slicer = AudioSlicer()
            self.leaf_extractor = LEAFFeatureExtractor()
            self.classifier = AudioClassifier()
            logger.info("✓ 所有處理器初始化成功")
        except Exception as e:
            logger.error(f"✗ 處理器初始化失敗: {e}")
            raise

    def process_record(self, record: Dict[str, Any]) -> bool:
        """
        處理單一記錄的完整流程

        Args:
            record: MongoDB 記錄

        Returns:
            是否處理成功
        """
        analyze_uuid = record.get('AnalyzeUUID', 'UNKNOWN')
        converted_file_path = None  # 轉檔後的檔案路徑（用於最後清理）
        analysis_id: Optional[str] = None

        try:
            logger.info("=" * 60)
            logger.info(f"開始處理記錄: {analyze_uuid}")
            logger.info("=" * 60)

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
            analysis_context = self._build_analysis_context(record, target_channels)
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

            # 判斷是否需要轉檔
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

                # Step 2: LEAF 特徵提取
                if not self._execute_step2(analyze_uuid, working_file_path, analysis_id):
                    return False

                # Step 3: 分類
                if not self._execute_step3(analyze_uuid, analysis_id):
                    return False

                logger.info(f"✓ 記錄處理完成: {analyze_uuid}")
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

                logger.info(f"從 GridFS 讀取檔案 (ID: {file_id})")

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

                logger.info(f"✓ 從 GridFS 讀取檔案成功，創建臨時檔案: {temp_file.name}")
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

    def _build_analysis_context(self, record: Dict[str, Any], target_channels: list) -> Dict[str, Any]:
        """建立此次分析的上下文資訊"""
        files = record.get('files', {}).get('raw', {})
        info_features = record.get('info_features', {}) or {}

        return {
            'requested_by': info_features.get('requested_by', 'system'),
            'request_source': info_features.get('request_source', 'auto_on_upload'),
            'target_channels': target_channels or [],
            'source_filename': files.get('filename'),
            'dataset_uuid': info_features.get('dataset_UUID') or info_features.get('dataset_uuid'),
            'pipeline_version': self.config.get('version', 'default'),
            'use_gridfs': self.use_gridfs
        }

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
            logger.info(f"[Step 0] 開始音訊轉檔/對齊流程...")

            source_sample_rate = self._extract_source_sample_rate(record)
            if source_sample_rate:
                logger.info(f"[Step 0] 偵測來源採樣率: {source_sample_rate}Hz")

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
                    logger.info(f"[Step 0] ✓ 音訊轉檔完成: {conversion_info.get('original_format')} -> WAV")
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
                logger.info("[Step 0] ✓ 無需轉檔，已記錄 Pass")
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
            logger.info(f"[Step 1] 開始音訊切割...")
            logger.info(f"[Step 1] 目標音軌: {target_channels if target_channels else '預設'}")

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
                logger.info(f"[Step 1] ✓ 音訊切割完成: {len(segments)} 個切片")
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
            logger.info(f"[Step 2] 開始 LEAF 特徵提取...")

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
                logger.info(
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
            logger.info(f"[Step 3] 開始分類...")

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
                logger.info(
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
                current_time = datetime.utcnow()
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
