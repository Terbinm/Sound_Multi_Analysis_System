"""
MIMII 資料集上傳器
處理機器異音檢測資料集的上傳
"""

from __future__ import annotations

import logging
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import soundfile as sf

from ..core.base_uploader import BaseBatchUploader
from ..config.mimii_config import MIMIIUploadConfig


class MIMIIBatchUploader(BaseBatchUploader):
    """MIMII 資料集批次上傳器"""

    def __init__(self, logger: logging.Logger) -> None:
        """初始化 MIMII 上傳器"""
        super().__init__(
            config_class=MIMIIUploadConfig,
            logger=logger,
            dataset_name="MIMII"
        )
        # 額外統計
        self.stats['filtered_invalid_label'] = 0

    def scan_directory(self) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        掃描 MIMII 資料夾，並且依照 MACHINE_TYPES 過濾機器類型。
        """
        self.logger.info(f"掃描資料夾：{self.config.UPLOAD_DIRECTORY}")

        directory_path = Path(self.config.UPLOAD_DIRECTORY)
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]] = []

        allowed_types = [m.lower() for m in self.config.MACHINE_TYPES]

        # 遞迴掃描
        for ext in self.config.SUPPORTED_FORMATS:
            for file_path in directory_path.rglob(f"*{ext}"):
                if not file_path.is_file():
                    continue

                # 取得 path metadata（含 machine_type）
                label, path_metadata = self._analyze_file_path(file_path)

                # 若找不到標籤 → 原本邏輯
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

                # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
                # 新增：機器類型過濾（重點！）
                # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
                machine_type = path_metadata.get("machine_type", None)

                if machine_type is None or machine_type.lower() not in allowed_types:
                    # 不在指定 MACHINE_TYPES → 跳過
                    continue
                # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

                dataset_files.append((file_path, label, path_metadata))

        self.logger.info(f"找到 {len(dataset_files)} 個音頻檔案")
        return dataset_files

    def _analyze_file_path(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        從路徑解析 MIMII 資料的參數
        路徑範例：6_dB_pump/pump/id_02/normal/00000001.wav
        提取：SNR(6_dB), machine_type(pump), obj_ID(id_02), label(normal), file_id(00000001)

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

        # 初始化元數據
        metadata: Dict[str, Any] = {
            'relative_path': str(relative).replace("\\", "/"),
        }

        label = 'unknown'

        # MIMII 路徑結構：{snr}_{machine_type}/{machine_type}/{obj_ID}/{label}/{filename}
        if len(parts) >= 4:
            # 第一層：提取 SNR 和機器類型
            first_level = parts[0]  # e.g., "6_dB_pump"

            # 解析 SNR 和機器類型
            for machine_type in self.config.MACHINE_TYPES:
                if machine_type in first_level.lower():
                    metadata['machine_type'] = machine_type
                    # 提取 SNR（移除機器類型部分）
                    snr_part = first_level.replace(f"_{machine_type}", "").replace(f"{machine_type}", "")
                    if snr_part:
                        metadata['snr'] = snr_part.strip('_')
                    break

            # 第三層：obj_ID
            if len(parts) >= 3 and parts[2].startswith('id_'):
                metadata['obj_ID'] = parts[2]

            # 第四層：標籤
            if len(parts) >= 4:
                label_folder = parts[3].lower()
                for label_key, folder_name in self.config.LABEL_FOLDERS.items():
                    if folder_name.lower() == label_folder:
                        label = label_key
                        break

        # 從檔案名稱提取序號
        filename = file_path.stem
        try:
            file_id_number = int(filename)
            metadata['file_id_number'] = file_id_number
        except ValueError:
            # 檔名不是純數字，忽略
            pass

        return label, metadata

    def get_file_metadata(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        取得 MIMII 音訊檔案元數據

        Args:
            file_path: 檔案路徑
            label: 標籤
            path_metadata: 路徑元數據

        Returns:
            檔案元數據字典
        """
        metadata: Dict[str, Any] = {
            'file_size': file_path.stat().st_size,
        }

        # 合併路徑元數據
        if path_metadata:
            metadata.update(path_metadata)

        # 獲取音頻資訊
        try:
            info = sf.info(str(file_path))
            metadata['duration'] = info.duration
            metadata['sample_rate'] = info.samplerate
            metadata['channels'] = info.channels
            metadata['raw_format'] = info.format
        except Exception as e:
            self.logger.warning(f"無法讀取音頻資訊 {file_path.name}：{e}")
            metadata['duration'] = 0.0
            metadata['sample_rate'] = None
            metadata['channels'] = None
            metadata['raw_format'] = None

        return metadata

    def build_info_features(
        self,
        label: str,
        file_hash: str,
        file_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立 MIMII 資料集的 info_features

        Args:
            label: 標籤
            file_hash: 檔案雜湊值
            file_metadata: 檔案元數據

        Returns:
            info_features 字典
        """
        # 提取 MIMII 特定元數據
        mimii_metadata: Dict[str, Any] = {
            'fault_type': label,  # MIMII 使用 label 作為 fault_type
            'relative_path': file_metadata.get('relative_path'),
        }

        # 添加可選欄位
        if 'snr' in file_metadata:
            mimii_metadata['snr'] = file_metadata['snr']
        if 'machine_type' in file_metadata:
            mimii_metadata['machine_type'] = file_metadata['machine_type']
        if 'obj_ID' in file_metadata:
            mimii_metadata['obj_ID'] = file_metadata['obj_ID']
        if 'file_id_number' in file_metadata:
            mimii_metadata['file_id_number'] = file_metadata['file_id_number']

        # obj_ID 從元數據提取
        obj_id = file_metadata.get('obj_ID', '-1')

        info_features: Dict[str, Any] = {
            "dataset_UUID": self.config.DATASET_CONFIG['dataset_UUID'],
            "device_id": f"Mimii_{label.upper()}",
            "testing": False,
            "obj_ID": obj_id,
            "upload_complete": True,
            "file_hash": file_hash,
            "file_size": file_metadata.get('file_size'),
            "duration": file_metadata.get('duration'),
            "label": label,
            "sample_rate": file_metadata.get('sample_rate'),
            "channels": file_metadata.get('channels'),
            "raw_format": file_metadata.get('raw_format'),
            "mimii_metadata": mimii_metadata,
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
        依設定限制每個標籤的檔案數量，並在不同資料夾間均勻採樣

        Args:
            dataset_files: 檔案列表

        Returns:
            過濾後的檔案列表
        """
        limit = self.config.UPLOAD_BEHAVIOR.get('per_label_limit', 0)
        if not isinstance(limit, int) or limit <= 0:
            return dataset_files

        self.logger.info(f"套用標籤上限：每個標籤最多 {limit} 個檔案")

        # 依標籤和資料夾分組
        label_folder_map: Dict[str, OrderedDict[str, List[int]]] = {}
        for idx, (file_path, label, path_metadata) in enumerate(dataset_files):
            # 使用相對路徑的父資料夾作為分組鍵
            folder_key = str(file_path.parent)

            if label not in label_folder_map:
                label_folder_map[label] = OrderedDict()

            folder_entries = label_folder_map[label].setdefault(folder_key, [])
            folder_entries.append(idx)

        selected_indices = set()

        for label, folders in label_folder_map.items():
            # Round-robin 選擇
            folder_queues = {f: deque(indices) for f, indices in folders.items()}
            count = 0

            while count < limit and folder_queues:
                for folder_key in list(folder_queues.keys()):
                    if count >= limit:
                        break
                    queue = folder_queues[folder_key]
                    if queue:
                        selected_indices.add(queue.popleft())
                        count += 1
                    if not queue:
                        del folder_queues[folder_key]

        # 重建檔案列表（保持原始順序）
        filtered = [dataset_files[idx] for idx in sorted(selected_indices)]

        if filtered != dataset_files:
            self.logger.info(f"已套用每個標籤上限（{limit}），保留 {len(filtered)} 個檔案。")

        return filtered
