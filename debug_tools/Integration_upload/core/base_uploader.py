"""
批次上傳器基礎類別
定義上傳流程的模板方法和抽象介面
"""

from __future__ import annotations

import json
import logging
import random
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from tqdm import tqdm

from .mongodb_handler import MongoDBUploader
from .utils import calculate_file_hash, to_json_serializable
from .routing_trigger import RoutingTrigger


class BaseBatchUploader(ABC):
    """
    批次上傳器的抽象基礎類別
    使用模板方法模式定義上傳流程
    """

    def __init__(
        self,
        config_class: type,
        logger: logging.Logger,
        dataset_name: str
    ) -> None:
        """
        初始化批次上傳器

        Args:
            config_class: 配置類別
            logger: 日誌記錄器
            dataset_name: 資料集名稱（用於識別）
        """
        self.config = config_class
        self.logger = logger
        self.dataset_name = dataset_name

        # 初始化 MongoDB 上傳器
        self.uploader = MongoDBUploader(
            mongodb_config=self.config.MONGODB_CONFIG,
            use_gridfs=self.config.USE_GRIDFS,
            logger=self.logger
        )

        # 初始化統計資料
        self.stats: Dict[str, Any] = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'labels': {},
            'failed_files': [],
        }

        # 初始化路由觸發器
        routing_config = self.config.ROUTING_TRIGGER
        self.routing_trigger_enabled = routing_config.get('enabled', True)
        self.routing_trigger = None
        self.pending_triggers: List[str] = []  # 待批次觸發的 UUID 列表

        if self.routing_trigger_enabled and routing_config.get('router_ids'):
            try:
                self.routing_trigger = RoutingTrigger(
                    state_management_url=routing_config['state_management_url'],
                    router_ids=routing_config['router_ids'],
                    sequential=routing_config.get('sequential', True),
                    retry_attempts=routing_config.get('retry_attempts', 3),
                    retry_delay=routing_config.get('retry_delay', 2),
                    logger=self.logger
                )
                self.logger.info(
                    f"路由觸發器已啟用 (Router IDs: {routing_config['router_ids']})"
                )
            except Exception as e:
                self.logger.warning(f"無法初始化路由觸發器: {e}")
                self.routing_trigger_enabled = False

        # 載入進度
        self.progress = self._load_progress()
        self.logger.info(f"{self.dataset_name} 批次上傳器已完成初始化。")

    def _handle_routing_trigger(self, analyze_uuid: str) -> None:
        """
        處理路由觸發

        Args:
            analyze_uuid: 上傳成功的 UUID
        """
        if not self.routing_trigger_enabled or not self.routing_trigger:
            return

        routing_config = self.config.ROUTING_TRIGGER

        # 如果啟用批次觸發，先收集 UUID
        if routing_config.get('batch_trigger', False):
            self.pending_triggers.append(analyze_uuid)
            return

        # 立即觸發
        if routing_config.get('trigger_on_completion', True):
            try:
                self.routing_trigger.trigger(analyze_uuid)
            except Exception as e:
                self.logger.error(f"觸發路由任務失敗 ({analyze_uuid}): {e}")

    def _flush_pending_triggers(self) -> None:
        """批次觸發所有待處理的任務"""
        if not self.pending_triggers or not self.routing_trigger:
            return

        self.logger.info(f"開始批次觸發 {len(self.pending_triggers)} 個任務...")
        try:
            self.routing_trigger.trigger_batch(self.pending_triggers)
        except Exception as e:
            self.logger.error(f"批次觸發失敗: {e}")
        finally:
            self.pending_triggers.clear()

    def _load_progress(self) -> Dict[str, Any]:
        """載入上傳進度"""
        progress_path = Path(self.config.PROGRESS_FILE)
        progress_path.parent.mkdir(parents=True, exist_ok=True)

        if progress_path.exists():
            try:
                with progress_path.open('r', encoding='utf-8') as handle:
                    data = json.load(handle)
                    # 確保有 dataset 區分
                    if 'datasets' not in data:
                        # 舊格式轉換
                        data = {
                            'datasets': {
                                self.dataset_name: {'uploaded_files': data.get('uploaded_files', [])}
                            }
                        }
                    if self.dataset_name not in data['datasets']:
                        data['datasets'][self.dataset_name] = {'uploaded_files': []}
                    return data['datasets'][self.dataset_name]
            except Exception as exc:
                self.logger.warning(f"無法載入進度檔案：{exc}")

        return {'uploaded_files': []}

    def _save_progress(self) -> None:
        """儲存上傳進度"""
        try:
            progress_path = Path(self.config.PROGRESS_FILE)
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            # 讀取完整進度（包含所有資料集）
            full_progress = {'datasets': {}}
            if progress_path.exists():
                try:
                    with progress_path.open('r', encoding='utf-8') as handle:
                        full_progress = json.load(handle)
                        if 'datasets' not in full_progress:
                            full_progress = {'datasets': {}}
                except Exception:
                    pass

            # 更新當前資料集的進度
            full_progress['datasets'][self.dataset_name] = self.progress

            # 寫入檔案
            with progress_path.open('w', encoding='utf-8') as handle:
                json.dump(full_progress, handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.logger.warning(f"無法寫入進度檔案：{exc}")

    @abstractmethod
    def scan_directory(self) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        掃描資料夾並返回檔案列表
        由子類別實現，根據不同資料集的目錄結構解析

        Returns:
            List of (file_path, label, metadata) tuples
            metadata 可包含從路徑解析的資訊
        """
        pass

    @abstractmethod
    def get_file_metadata(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        取得檔案元數據
        由子類別實現，根據不同資料集的檔案格式解析

        Args:
            file_path: 檔案路徑
            label: 標籤
            path_metadata: 從路徑解析的元數據

        Returns:
            檔案元數據字典
        """
        pass

    @abstractmethod
    def build_info_features(
        self,
        label: str,
        file_hash: str,
        file_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立 info_features 字典
        由子類別實現，根據不同資料集的需求構建

        Args:
            label: 標籤
            file_hash: 檔案雜湊值
            file_metadata: 檔案元數據

        Returns:
            info_features 字典
        """
        pass

    def _apply_label_limit(
        self,
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]]
    ) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        套用每個標籤的數量限制
        子類別可覆寫此方法以實現更複雜的採樣策略

        Args:
            dataset_files: 檔案列表

        Returns:
            過濾後的檔案列表
        """
        limit = self.config.UPLOAD_BEHAVIOR.get('per_label_limit', 0)
        if not isinstance(limit, int) or limit <= 0:
            return dataset_files

        label_counts: Dict[str, int] = {}
        filtered: List[Tuple[Path, str, Optional[Dict[str, Any]]]] = []

        for file_path, label, metadata in dataset_files:
            count = label_counts.get(label, 0)
            if count >= limit:
                continue

            label_counts[label] = count + 1
            filtered.append((file_path, label, metadata))

        if filtered != dataset_files:
            self.logger.info(f"已套用每個標籤上限（{limit}），保留 {len(filtered)} 個檔案。")

        return filtered

    def upload_single_file(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        上傳單一檔案

        Args:
            file_path: 檔案路徑
            label: 標籤
            path_metadata: 從路徑解析的元數據

        Returns:
            是否成功
        """
        try:
            file_hash = calculate_file_hash(file_path)

            # 檢查是否已上傳
            if self.config.UPLOAD_BEHAVIOR['skip_existing']:
                if file_hash in self.progress['uploaded_files']:
                    self.logger.debug(f"進度檔案顯示已上傳，略過：{file_path.name}")
                    self.stats['skipped'] += 1
                    return True

                if self.uploader.file_exists(
                    file_hash,
                    self.config.UPLOAD_BEHAVIOR['check_duplicates']
                ):
                    self.logger.debug(f"資料庫中已存在相同檔案，略過：{file_path.name}")
                    self.progress['uploaded_files'].append(file_hash)
                    self._save_progress()
                    self.stats['skipped'] += 1
                    return True

            # 取得檔案元數據
            file_metadata = self.get_file_metadata(file_path, label, path_metadata)

            # 重試邏輯
            for attempt in range(self.config.UPLOAD_BEHAVIOR['retry_attempts']):
                # 建立 info_features
                info_features = self.build_info_features(label, file_hash, file_metadata)

                # 上傳檔案
                analyze_uuid = self.uploader.upload_file(
                    file_path=file_path,
                    label=label,
                    file_hash=file_hash,
                    info_features=info_features,
                    gridfs_metadata=file_metadata.get('gridfs_metadata')
                )

                if analyze_uuid:
                    self.logger.info(f"已上傳 {file_path.name}（標籤：{label}）")
                    self.stats['success'] += 1
                    self.stats['labels'][label] = self.stats['labels'].get(label, 0) + 1
                    self.progress['uploaded_files'].append(file_hash)
                    self._save_progress()

                    # 觸發路由任務（如果啟用）
                    self._handle_routing_trigger(analyze_uuid)

                    return True

                if attempt < self.config.UPLOAD_BEHAVIOR['retry_attempts'] - 1:
                    time.sleep(self.config.UPLOAD_BEHAVIOR['retry_delay'])

            self.logger.error(f"多次重試後仍無法上傳：{file_path.name}")
            self.stats['failed'] += 1
            self.stats['failed_files'].append(str(file_path))
            return False

        except Exception as exc:
            self.logger.error(f"上傳 {file_path.name} 時發生未預期的錯誤：{exc}")
            self.stats['failed'] += 1
            self.stats['failed_files'].append(str(file_path))
            return False

    def _generate_dry_run_samples(
        self,
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]]
    ) -> None:
        """生成 dry-run 預覽檔案"""
        preview_config = self.config.DRY_RUN_PREVIEW
        if not preview_config.get('enable_preview', True):
            self.logger.info("[模擬上傳] 已停用預覽輸出。")
            return

        # 按標籤分組
        label_entries: Dict[str, List[Tuple[Path, Optional[Dict[str, Any]]]]] = {}
        for file_path, label, metadata in dataset_files:
            label_entries.setdefault(label, []).append((file_path, metadata))

        if not label_entries:
            self.logger.info("[模擬上傳] 沒有找到可預覽的檔案。")
            return

        # 建立預覽目錄
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        preview_root = Path(preview_config.get('output_directory', 'reports/dry_run_previews'))
        if not preview_root.is_absolute():
            preview_root = Path(__file__).parent.parent / preview_root

        preview_directory = preview_root / f"dry_run_{self.dataset_name}_{timestamp}"
        preview_directory.mkdir(parents=True, exist_ok=True)

        # 為每個標籤生成預覽
        for label, candidates in sorted(label_entries.items()):
            try:
                sample_path, path_metadata = random.choice(candidates)
                file_hash = calculate_file_hash(sample_path)
                file_metadata = self.get_file_metadata(sample_path, label, path_metadata)
                info_features = self.build_info_features(label, file_hash, file_metadata)

                preview_payload = {
                    'dataset': self.dataset_name,
                    'label': label,
                    'source_file': str(sample_path),
                    'file_hash': file_hash,
                    'file_metadata': file_metadata,
                    'info_features': to_json_serializable(info_features),
                }

                output_filename = f"{label}_{sample_path.stem[:20]}.json"
                output_path = preview_directory / output_filename

                with output_path.open('w', encoding='utf-8') as handle:
                    json.dump(preview_payload, handle, indent=2, ensure_ascii=False)

                self.logger.info(f"[模擬上傳] 已輸出預覽檔案：{output_path}")

            except Exception as exc:
                self.logger.error(f"[模擬上傳] 產生標籤 {label} 的預覽失敗：{exc}")

        self.logger.info(f"[模擬上傳] 預覽檔案儲存於：{preview_directory}")

    def batch_upload(self, dry_run: bool = False) -> None:
        """執行批次上傳"""
        self.logger.info("=" * 60)
        self.logger.info(f"開始執行 {self.dataset_name} 批次上傳")
        self.logger.info("=" * 60)

        # 掃描資料夾
        dataset_files = self.scan_directory()
        if not dataset_files:
            self.logger.warning("沒有找到任何檔案。")
            return

        # 套用標籤限制
        dataset_files = self._apply_label_limit(dataset_files)
        if not dataset_files:
            self.logger.warning("每個標籤的上限設定讓所有檔案都被排除，沒有可上傳的項目。")
            return

        self.stats['total'] = len(dataset_files)

        # 統計標籤分佈
        label_counts: Dict[str, int] = {}
        for _, label, _ in dataset_files:
            label_counts[label] = label_counts.get(label, 0) + 1

        self.logger.info("檔案分佈：")
        for label, count in sorted(label_counts.items()):
            self.logger.info(f"  - {label}：{count} 個檔案")

        # Dry-run 模式
        if dry_run:
            self.logger.info("[模擬上傳] 不會實際上傳任何檔案。")
            self._generate_dry_run_samples(dataset_files)
            return

        # 開始上傳
        self.logger.info("正在上傳檔案……")

        concurrent = self.config.UPLOAD_BEHAVIOR['concurrent_uploads']
        if concurrent > 1:
            with ThreadPoolExecutor(max_workers=concurrent) as executor:
                futures = {
                    executor.submit(self.upload_single_file, file_path, label, metadata): (file_path, label)
                    for file_path, label, metadata in dataset_files
                }

                with tqdm(total=len(dataset_files), desc=f"{self.dataset_name} 上傳進度") as progress_bar:
                    for future in as_completed(futures):
                        future.result()
                        progress_bar.update(1)
        else:
            with tqdm(dataset_files, desc=f"{self.dataset_name} 上傳進度") as progress_bar:
                for file_path, label, metadata in progress_bar:
                    self.upload_single_file(file_path, label, metadata)
                    progress_bar.set_postfix({
                        '成功': self.stats['success'],
                        '失敗': self.stats['failed'],
                        '跳過': self.stats['skipped'],
                    })

        # 批次觸發待處理的任務（如果啟用批次模式）
        self._flush_pending_triggers()

        self._print_summary()
        self._save_report()

    def _print_summary(self) -> None:
        """顯示上傳摘要"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"{self.dataset_name} 批次上傳完成")
        self.logger.info("=" * 60)
        self.logger.info(f"總計：{self.stats['total']} 筆檔案")
        self.logger.info(f"成功：{self.stats['success']} 筆檔案")
        self.logger.info(f"失敗：{self.stats['failed']} 筆檔案")
        self.logger.info(f"跳過：{self.stats['skipped']} 筆檔案")

        if self.stats['labels']:
            self.logger.info("\n各標籤統計：")
            for label, count in sorted(self.stats['labels'].items()):
                self.logger.info(f"  {label}：{count} 筆")
        else:
            self.logger.info("\n各標籤統計：尚無資料")

        if self.stats['failed_files']:
            self.logger.info("\n失敗檔案列表：")
            for file_path in self.stats['failed_files'][:10]:
                self.logger.info(f"  - {file_path}")
            remaining = len(self.stats['failed_files']) - 10
            if remaining > 0:
                self.logger.info(f"  … 還有 {remaining} 筆")

    def _save_report(self) -> None:
        """儲存上傳報告"""
        if not self.config.REPORT_OUTPUT['save_report']:
            return

        try:
            report_dir = Path(self.config.REPORT_OUTPUT['report_directory'])
            report_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = report_dir / f"upload_report_{self.dataset_name}_{timestamp}.json"

            report_payload = {
                'dataset': self.dataset_name,
                'timestamp': timestamp,
                'upload_directory': str(self.config.UPLOAD_DIRECTORY),
                'statistics': {
                    'total': self.stats['total'],
                    'success': self.stats['success'],
                    'failed': self.stats['failed'],
                    'skipped': self.stats['skipped'],
                    'labels': dict(sorted(self.stats['labels'].items())),
                    'failed_files': self.stats['failed_files'],
                },
                'config_snapshot': self.config.get_config_summary(),
            }

            with report_file.open('w', encoding='utf-8') as handle:
                json.dump(report_payload, handle, indent=2, ensure_ascii=False)

            self.logger.info(f"已儲存報告檔案：{report_file}")

        except Exception as exc:
            self.logger.error(f"寫入報告失敗：{exc}")

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資料"""
        return self.stats.copy()

    def cleanup(self) -> None:
        """清理資源"""
        self.uploader.close()
