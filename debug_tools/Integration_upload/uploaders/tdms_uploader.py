"""
TDMS 資料集上傳器
處理沖壓模具振動訊號資料集的上傳
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.base_uploader import BaseBatchUploader
from ..config.tdms_config import TDMSUploadConfig


class TDMSBatchUploader(BaseBatchUploader):
    """TDMS 資料集批次上傳器"""

    def __init__(self, logger: logging.Logger) -> None:
        """初始化 TDMS 上傳器"""
        super().__init__(
            config_class=TDMSUploadConfig,
            logger=logger,
            dataset_name="TDMS"
        )

    def scan_directory(self) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        掃描 TDMS 資料夾

        TDMS 目錄結構：
        screw_raw_data/
        ├── 250516_產品編號/
        │   ├── sig_250516_0700.tdms
        │   └── ...

        Returns:
            [(file_path, label, metadata), ...]
        """
        self.logger.info(f"掃描資料夾：{self.config.UPLOAD_DIRECTORY}")

        directory_path = Path(self.config.UPLOAD_DIRECTORY)
        dataset_files: List[Tuple[Path, str, Optional[Dict[str, Any]]]] = []

        # 掃描所有 TDMS 檔案（排除 _index 檔案）
        for ext in self.config.SUPPORTED_FORMATS:
            for file_path in directory_path.rglob(f"*{ext}"):
                if not file_path.is_file():
                    continue
                # 排除 TDMS 索引檔案
                if '_index' in file_path.name:
                    continue

                # 解析路徑元數據
                label, path_metadata = self._analyze_file_path(file_path)
                dataset_files.append((file_path, label, path_metadata))

        self.logger.info(f"找到 {len(dataset_files)} 個 TDMS 檔案")
        return dataset_files

    def _analyze_file_path(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        從路徑解析 TDMS 資料的參數

        檔案格式: sig_YYMMDD_HHMM.tdms
        資料夾格式: YYMMDD_產品編號

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

        metadata: Dict[str, Any] = {
            'relative_path': str(relative).replace("\\", "/"),
        }

        # 使用預設標籤
        label = getattr(self.config, 'DEFAULT_LABEL', 'normal')

        # 從資料夾名稱解析日期和產品編號
        # 格式: YYMMDD_產品編號
        folder_name = file_path.parent.name
        if '_' in folder_name:
            parts = folder_name.split('_', 1)
            date_part = parts[0]
            product_id = parts[1] if len(parts) > 1 else ''

            metadata['date_folder'] = date_part
            metadata['product_id'] = product_id
            metadata['obj_ID'] = product_id if product_id else '-1'

        # 從檔案名稱解析時間戳
        # 格式: sig_YYMMDD_HHMM.tdms
        filename = file_path.stem
        parts = filename.split('_')

        if len(parts) >= 3 and parts[0] == 'sig':
            date_str = parts[1]  # YYMMDD
            time_str = parts[2]  # HHMM

            try:
                year = 2000 + int(date_str[:2])
                month = int(date_str[2:4])
                day = int(date_str[4:6])
                hour = int(time_str[:2])
                minute = int(time_str[2:4])

                timestamp = datetime(year, month, day, hour, minute)
                metadata['timestamp'] = timestamp.isoformat()
                metadata['recording_date'] = date_str
                metadata['recording_time'] = time_str
            except (ValueError, IndexError):
                pass

        return label, metadata

    def get_file_metadata(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        取得 TDMS 檔案元數據

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

        # 嘗試讀取 TDMS 檔案資訊
        try:
            from nptdms import TdmsFile

            tdms_file = TdmsFile.read(str(file_path))

            # 取得通道資訊
            channels = []
            total_samples = 0
            for group in tdms_file.groups():
                for channel in group.channels():
                    channel_info = {
                        'group': group.name,
                        'name': channel.name,
                        'samples': len(channel.data) if channel.data is not None else 0,
                    }
                    channels.append(channel_info)
                    if channel.data is not None:
                        total_samples = max(total_samples, len(channel.data))

            metadata['channels'] = channels
            metadata['channel_count'] = len(channels)
            metadata['total_samples'] = total_samples

            # 計算時長
            sample_rate = self.config.TDMS_CONFIG.get('sample_rate', 10000)
            if total_samples > 0:
                metadata['duration'] = total_samples / sample_rate
                metadata['sample_rate'] = sample_rate

        except ImportError:
            self.logger.warning("nptdms 未安裝，無法讀取 TDMS 檔案詳細資訊")
        except Exception as e:
            self.logger.warning(f"無法讀取 TDMS 檔案資訊 {file_path.name}：{e}")

        return metadata

    def build_info_features(
        self,
        label: str,
        file_hash: str,
        file_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立 TDMS 資料集的 info_features

        Args:
            label: 標籤
            file_hash: 檔案雜湊值
            file_metadata: 檔案元數據

        Returns:
            info_features 字典
        """
        # 提取 TDMS 特定元數據
        tdms_metadata: Dict[str, Any] = {
            'relative_path': file_metadata.get('relative_path'),
            'product_id': file_metadata.get('product_id'),
            'timestamp': file_metadata.get('timestamp'),
            'recording_date': file_metadata.get('recording_date'),
            'recording_time': file_metadata.get('recording_time'),
            'channel_count': file_metadata.get('channel_count'),
            'total_samples': file_metadata.get('total_samples'),
        }

        # obj_ID 從元數據提取
        obj_id = file_metadata.get('obj_ID', '-1')

        info_features: Dict[str, Any] = {
            "dataset_UUID": self.config.DATASET_CONFIG['dataset_UUID'],
            "device_id": f"TDMS_{label.upper()}",
            "testing": False,
            "obj_ID": obj_id,
            "upload_complete": True,
            "file_hash": file_hash,
            "file_size": file_metadata.get('file_size'),
            "duration": file_metadata.get('duration'),
            "label": label,
            "sample_rate": file_metadata.get('sample_rate'),
            "channels": file_metadata.get('channel_count'),
            "raw_format": "tdms",
            "tdms_metadata": tdms_metadata,
        }

        # 添加 target_channel
        target_channel = self.config.ANALYSIS_CONFIG.get('target_channel')
        if target_channel is not None:
            info_features['target_channel'] = target_channel

        return info_features
