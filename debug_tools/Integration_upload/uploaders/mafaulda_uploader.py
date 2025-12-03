"""
MAFAULDA 資料集上傳器
處理機械故障診斷資料集的上傳
"""

from __future__ import annotations

import logging
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.base_uploader import BaseBatchUploader
from ..config.mafaulda_config import MAFAULDAUploadConfig


class MAFAULDABatchUploader(BaseBatchUploader):
    """MAFAULDA 資料集批次上傳器"""

    def __init__(self, logger: logging.Logger) -> None:
        """初始化 MAFAULDA 上傳器"""
        super().__init__(
            config_class=MAFAULDAUploadConfig,
            logger=logger,
            dataset_name="MAFAULDA"
        )
        # 額外統計
        self.stats['filtered_invalid_label'] = 0

    def scan_directory(self) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        掃描 MAFAULDA 資料夾
        解析複雜的路徑結構以提取故障類型和層級資訊

        Returns:
            List of (file_path, label, path_metadata) tuples
        """
        self.logger.info(f"掃描資料夾：{self.config.UPLOAD_DIRECTORY}")

        directory_path = Path(self.config.UPLOAD_DIRECTORY)
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]] = []

        # 遞迴掃描
        for ext in self.config.SUPPORTED_FORMATS:
            for file_path in directory_path.rglob(f"*{ext}"):
                if file_path.is_file():
                    label, path_metadata = self._analyze_file_path(file_path)
                    if label == 'unknown':
                        try:
                            rel_path = file_path.relative_to(directory_path)
                        except ValueError:
                            rel_path = file_path
                        self.logger.warning(
                            f"忽略未在 LABEL_FOLDERS 設定中的子資料夾檔案：{rel_path}"
                        )
                        self.stats['filtered_invalid_label'] += 1
                        continue

                    dataset_files.append((file_path, label, path_metadata))

        self.logger.info(f"找到 {len(dataset_files)} 個資料檔案")
        return dataset_files

    def _analyze_file_path(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        從路徑解析 MAFAULDA 資料的標籤與層級資訊
        路徑範例：imbalance/6g/13.9264.csv

        Args:
            file_path: 檔案路徑

        Returns:
            (label, path_metadata) tuple
        """
        base_path = Path(self.config.UPLOAD_DIRECTORY)
        try:
            relative = file_path.relative_to(base_path)
        except ValueError:
            relative = file_path

        parts = relative.parts
        folder_map = {
            folder_name.lower(): label_key
            for label_key, folder_name in self.config.LABEL_FOLDERS.items()
        }

        label = 'unknown'
        if parts:
            label = folder_map.get(parts[0].lower(), 'unknown')

        # 提取故障層級（排除第一層和檔名）
        fault_hierarchy = list(parts[1:-1]) if len(parts) > 1 else []

        metadata: Dict[str, Any] = {
            'relative_path': str(relative).replace("\\", "/"),
        }
        if label != 'unknown':
            metadata['fault_type'] = label

        if fault_hierarchy:
            metadata['fault_hierarchy'] = fault_hierarchy
            # 只有 1 層時：fault_condition = 該層，不記錄 fault_variant
            # 有 2 層或更多時：fault_variant = 第一層，fault_condition = 最後一層
            if len(fault_hierarchy) == 1:
                metadata['fault_condition'] = fault_hierarchy[0]
            else:
                metadata['fault_variant'] = fault_hierarchy[0]
                metadata['fault_condition'] = fault_hierarchy[-1]

        # 從檔名提取轉速資訊
        metadata.update(self._extract_rotational_speed(file_path))
        return label, metadata

    @staticmethod
    def _extract_rotational_speed(file_path: Path) -> Dict[str, Optional[float]]:
        """從檔案名稱推算轉速資訊 (e.g. 13.5168 -> 811 rpm)"""
        metadata: Dict[str, Optional[float]] = {}
        stem = file_path.stem
        try:
            frequency_hz = float(stem.replace('_', '.'))
            metadata['rotational_frequency_hz'] = frequency_hz
            metadata['rotational_speed_rpm'] = frequency_hz * 60.0
        except ValueError:
            # 檔名不是數值時忽略即可
            pass
        return metadata

    def get_file_metadata(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        取得 MAFAULDA CSV 檔案元數據

        Args:
            file_path: 檔案路徑
            label: 標籤
            path_metadata: 路徑元數據

        Returns:
            檔案元數據字典
        """
        metadata: Dict[str, Any] = {
            'file_size': file_path.stat().st_size,
            'sample_rate_hz': self.config.CSV_CONFIG.get('sample_rate_hz'),
        }

        # 合併路徑元數據
        if path_metadata:
            metadata.update(path_metadata)

        # 解析 CSV 檔案
        csv_metadata = self._get_csv_metadata(file_path)
        metadata.update(csv_metadata)

        # 計算 duration（如果尚未計算）
        if metadata.get('duration') is None and metadata.get('num_samples') and metadata.get('sample_rate_hz'):
            metadata['duration'] = metadata['num_samples'] / metadata['sample_rate_hz']

        return metadata

    def _get_csv_metadata(self, file_path: Path) -> Dict[str, Any]:
        """解析 CSV 檔案的取樣點數與欄位數"""
        num_samples = 0
        num_channels: Optional[int] = None

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if num_channels is None:
                        num_channels = len(stripped.split(','))
                    num_samples += 1
        except Exception as e:
            self.logger.warning(f"無法解析 CSV 檔案 {file_path.name}：{e}")
            return {
                'num_samples': None,
                'num_channels': num_channels,
                'duration': None
            }

        metadata: Dict[str, Any] = {
            'num_samples': num_samples,
            'num_channels': num_channels,
        }

        sample_rate = self.config.CSV_CONFIG.get('sample_rate_hz')
        if sample_rate and num_samples:
            metadata['duration'] = num_samples / sample_rate
        else:
            metadata['duration'] = None

        # 驗證欄位數
        expected_channels = self.config.CSV_CONFIG.get('expected_channels')
        if expected_channels and num_channels and num_channels != expected_channels:
            self.logger.warning(
                f"CSV 欄位數異常 {file_path.name}：期望 {expected_channels}，實際 {num_channels}"
            )

        return metadata

    def build_info_features(
        self,
        label: str,
        file_hash: str,
        file_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立 MAFAULDA 資料集的 info_features

        Args:
            label: 標籤
            file_hash: 檔案雜湊值
            file_metadata: 檔案元數據

        Returns:
            info_features 字典
        """
        # 提取 MAFAULDA 特定元數據
        mafaulda_metadata: Dict[str, Any] = {
            'fault_type': file_metadata.get('fault_type'),
            'relative_path': file_metadata.get('relative_path'),
        }

        # 添加可選欄位
        if 'fault_variant' in file_metadata:
            mafaulda_metadata['fault_variant'] = file_metadata['fault_variant']
        if 'fault_condition' in file_metadata:
            mafaulda_metadata['fault_condition'] = file_metadata['fault_condition']
        if 'fault_hierarchy' in file_metadata:
            mafaulda_metadata['fault_hierarchy'] = file_metadata['fault_hierarchy']
        if 'rotational_frequency_hz' in file_metadata:
            mafaulda_metadata['rotational_frequency_hz'] = file_metadata['rotational_frequency_hz']
        if 'rotational_speed_rpm' in file_metadata:
            mafaulda_metadata['rotational_speed_rpm'] = file_metadata['rotational_speed_rpm']

        info_features: Dict[str, Any] = {
            "dataset_UUID": self.config.DATASET_CONFIG['dataset_UUID'],
            "device_id": f'Mafaulda_{label.upper()}',
            "testing": False,
            "obj_ID": self.config.DATASET_CONFIG['obj_ID'],
            "upload_complete": True,
            "file_hash": file_hash,
            "file_size": file_metadata.get('file_size'),
            "duration": file_metadata.get('duration'),
            "label": label,
            "sample_rate": file_metadata.get('sample_rate_hz'),
            "channels": file_metadata.get('num_channels'),
            "raw_format": "CSV",
            "mafaulda_metadata": mafaulda_metadata,
        }

        # 添加 target_channel
        target_channel = self.config.ANALYSIS_CONFIG.get('target_channel')
        if target_channel is not None:
            info_features['target_channel'] = target_channel

        return info_features

    def _apply_label_limit(
        self,
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]]
    ) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        依設定限制每個標籤的檔案數量，並在不同 fault_variant 間均勻採樣

        Args:
            dataset_files: 檔案列表

        Returns:
            過濾後的檔案列表
        """
        limit = self.config.UPLOAD_BEHAVIOR.get('per_label_limit', 0)
        if not isinstance(limit, int) or limit <= 0:
            return dataset_files

        self.logger.info(f"套用標籤上限：每個標籤最多 {limit} 個檔案")

        # 依標籤建立 fault_variant -> 檔案索引的映射（維持原始順序）
        label_variant_map: Dict[str, OrderedDict[str, List[int]]] = {}
        for idx, (file_path, label, path_metadata) in enumerate(dataset_files):
            # 使用 fault_variant 或 fault_condition 或 'default' 作為分組鍵
            variant_key = 'default'
            if path_metadata:
                variant_key = path_metadata.get('fault_variant') or path_metadata.get('fault_condition') or 'default'

            if label not in label_variant_map:
                label_variant_map[label] = OrderedDict()

            variant_entries = label_variant_map[label].setdefault(variant_key, [])
            variant_entries.append(idx)

        selected_indices = set()

        for label, variants in label_variant_map.items():
            # Round-robin 選擇
            variant_queues = {v: deque(indices) for v, indices in variants.items()}
            count = 0

            while count < limit and variant_queues:
                for variant_key in list(variant_queues.keys()):
                    if count >= limit:
                        break
                    queue = variant_queues[variant_key]
                    if queue:
                        selected_indices.add(queue.popleft())
                        count += 1
                    if not queue:
                        del variant_queues[variant_key]

        # 重建檔案列表（保持原始順序）
        filtered = [dataset_files[idx] for idx in sorted(selected_indices)]

        if filtered != dataset_files:
            self.logger.info(f"已套用每個標籤上限（{limit}），保留 {len(filtered)} 個檔案。")

        return filtered
