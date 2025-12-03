"""
CPC 資料集上傳器
處理工廠環境音訊資料集的上傳
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import soundfile as sf

from ..core.base_uploader import BaseBatchUploader
from ..config.cpc_config import CPCUploadConfig


class CPCBatchUploader(BaseBatchUploader):
    """CPC 資料集批次上傳器"""

    def __init__(self, logger: logging.Logger) -> None:
        """初始化 CPC 上傳器"""
        super().__init__(
            config_class=CPCUploadConfig,
            logger=logger,
            dataset_name="CPC"
        )
        self.default_label = CPCUploadConfig.DEFAULT_LABEL

    def scan_directory(self) -> List[Tuple[Path, str, Optional[Dict[str, Any]]]]:
        """
        掃描 CPC 資料夾
        CPC 資料夾結構簡單，所有檔案使用相同標籤

        Returns:
            List of (file_path, label, None) tuples
        """
        directory_path = Path(self.config.UPLOAD_DIRECTORY)
        self.logger.info(f"正在掃描資料夾：{directory_path}")

        if not directory_path.is_dir():
            self.logger.error(f"找不到上傳資料夾：{directory_path}")
            return []

        files: List[Tuple[Path, str, Optional[Dict[str, Any]]]] = []
        for ext in self.config.SUPPORTED_FORMATS:
            for file_path in directory_path.rglob(f"*{ext}"):
                if file_path.is_file():
                    label = self._determine_label(file_path)
                    files.append((file_path, label, None))

        self.logger.info(f"共找到 {len(files)} 個音訊檔案。")
        return files

    def _determine_label(self, file_path: Path) -> str:
        """
        確定檔案標籤
        CPC 檔案可能在子資料夾中，檢查路徑是否包含 LABEL_FOLDERS

        Args:
            file_path: 檔案路徑

        Returns:
            標籤字串
        """
        path_parts = [part.lower() for part in file_path.parts]
        for label, folder_name in self.config.LABEL_FOLDERS.items():
            if folder_name.lower() in path_parts:
                return label
        return self.default_label

    def get_file_metadata(
        self,
        file_path: Path,
        label: str,
        path_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        取得 CPC 音訊檔案元數據

        Args:
            file_path: 檔案路徑
            label: 標籤
            path_metadata: 路徑元數據（CPC 不使用）

        Returns:
            檔案元數據字典
        """
        metadata: Dict[str, Any] = {
            'file_size': file_path.stat().st_size,
            'duration': None,
            'sample_rate': None,
            'channels': None,
            'subtype': None,
            'format': None,
        }

        try:
            info = sf.info(str(file_path))
            metadata.update({
                'duration': float(info.duration),
                'sample_rate': info.samplerate,
                'channels': info.channels,
                'subtype': info.subtype,
                'format': info.format,
            })
        except Exception as exc:
            self.logger.warning(f"無法讀取音訊中繼資料 {file_path.name}：{exc}")

        # 驗證取樣率
        expected_rate = self.config.AUDIO_CONFIG.get('expected_sample_rate_hz')
        if expected_rate and metadata['sample_rate'] and metadata['sample_rate'] != expected_rate:
            self.logger.warning(
                f"取樣率不符 {file_path.name}：預期 {expected_rate} Hz，實際 {metadata['sample_rate']} Hz"
            )

        # 驗證聲道數
        if self.config.AUDIO_CONFIG.get('allow_mono_only', False) and metadata['channels']:
            if metadata['channels'] != 1:
                self.logger.warning(
                    f"偵測到非單聲道檔案：{file_path.name}（{metadata['channels']} 聲道）"
                )

        return metadata

    def build_info_features(
        self,
        label: str,
        file_hash: str,
        file_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立 CPC 資料集的 info_features

        Args:
            label: 標籤
            file_hash: 檔案雜湊值
            file_metadata: 檔案元數據

        Returns:
            info_features 字典
        """
        info_features: Dict[str, Any] = {
            "dataset_UUID": self.config.DATASET_CONFIG['dataset_UUID'],
            "device_id": self.config.DEVICE_ID,
            "testing": False,
            "obj_ID": self.config.DATASET_CONFIG['obj_ID'],
            "upload_complete": True,
            "file_hash": file_hash,
            "file_size": file_metadata.get('file_size'),
            "duration": file_metadata.get('duration'),
            "label": label,
            "sample_rate": file_metadata.get('sample_rate'),
            "channels": file_metadata.get('channels'),
            "raw_format": file_metadata.get('format'),
            "cpc_metadata": {
                "subtype": file_metadata.get('subtype'),
            },
        }

        # 添加 target_channel
        if self.config.TARGET_CHANNEL is not None:
            info_features['target_channel'] = self.config.TARGET_CHANNEL

        return info_features
