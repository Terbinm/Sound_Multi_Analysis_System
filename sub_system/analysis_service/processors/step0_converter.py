# processors/step0_converter.py - 音訊轉檔處理器

import numpy as np
import pandas as pd
import soundfile as sf
import os
import tempfile
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from utils.logger import logger

try:
    from nptdms import TdmsFile
    TDMS_AVAILABLE = True
except ImportError:
    TDMS_AVAILABLE = False
    logger.warning("nptdms 未安裝，TDMS 檔案讀取功能將無法使用")


class AudioConverter:
    """音訊轉檔處理器（支援 CSV 轉 WAV）"""

    def __init__(self, audio_config: Dict[str, Any], conversion_config: Dict[str, Any]):
        """初始化轉檔器"""
        self.config_audio = dict(audio_config)
        self.config_conversion = dict(conversion_config)
        self.sample_rate = self.config_audio['sample_rate']
        self.supported_input_formats = self._resolve_supported_formats(self.config_conversion.get('supported_input_formats'))
        logger.info(f"AudioConverter 初始化: default_sample_rate={self.sample_rate}Hz")

    def apply_config(self, audio_config: Dict[str, Any], conversion_config: Dict[str, Any]):
        """更新配置，避免意外覆寫 list 型別"""
        self.config_audio = {**self.config_audio, **(audio_config or {})}
        self.config_conversion = {**self.config_conversion, **(conversion_config or {})}
        self.sample_rate = self.config_audio.get('sample_rate', self.sample_rate)
        self.supported_input_formats = self._resolve_supported_formats(
            self.config_conversion.get('supported_input_formats', self.supported_input_formats)
        )
        logger.info(f"AudioConverter 配置已更新: sample_rate={self.sample_rate}, formats={self.supported_input_formats}")

    @staticmethod
    def _resolve_supported_formats(value: Any) -> list:
        if isinstance(value, list):
            return [str(v).lower() for v in value]
        return ['.wav', '.csv']

    def needs_conversion(self, filepath: str) -> bool:
        """
        判斷檔案是否需要轉檔

        Args:
            filepath: 檔案路徑

        Returns:
            是否需要轉檔
        """
        try:
            file_ext = Path(filepath).suffix.lower()

            if file_ext not in self.supported_input_formats:
                logger.warning(f"不支援的檔案格式: {file_ext} (允許: {self.supported_input_formats})")
                return False

            # 如果是 WAV 檔案，不需要轉檔
            if file_ext == '.wav':
                return False

            # 如果是 TDMS 檔案，不需要轉檔（直接讀取）
            if file_ext == '.tdms':
                return False

            # 如果是 CSV 檔案，需要轉檔
            if file_ext == '.csv':
                return True

            # 其他格式暫不支援
            logger.warning(f"不支援的檔案格式: {file_ext}")
            return False

        except Exception as e:
            logger.error(f"檢查檔案格式失敗 {filepath}: {e}")
            return False

    def convert_to_wav(self, filepath: str, sample_rate: Optional[int] = None) -> Optional[str]:
        """
        將檔案轉換為 WAV 格式

        Args:
            filepath: 原始檔案路徑
            sample_rate: 目標採樣率（若未提供則使用預設值）

        Returns:
            轉換後的 WAV 檔案路徑，或 None（如果失敗或不需轉換）
        """
        try:
            file_ext = Path(filepath).suffix.lower()

            # 如果已經是 WAV，直接返回
            if file_ext == '.wav':
                logger.info(f"檔案已是 WAV 格式，無需轉換: {filepath}")
                return filepath

            # CSV 轉 WAV
            if file_ext == '.csv':
                target_sample_rate = self._resolve_sample_rate(sample_rate)
                return self._convert_csv_to_wav(filepath, target_sample_rate)

            # 其他格式暫不支援
            logger.error(f"不支援的檔案格式: {file_ext}")
            return None

        except Exception as e:
            logger.error(f"轉檔失敗 {filepath}: {e}")
            return None

    def _resolve_sample_rate(self, sample_rate: Optional[int]) -> int:
        """解析目標採樣率，若未提供則使用預設值"""
        if isinstance(sample_rate, (int, float)) and sample_rate > 0:
            resolved = int(sample_rate)
            if resolved != self.sample_rate:
                logger.warning(f"無法推算採樣率，使用值: {resolved}Hz（預設 {self.sample_rate}Hz）")
            logger.debug(f"[Step 0] 採樣率解析: 請求={sample_rate} → 使用={resolved}Hz")
            return resolved
        logger.debug(f"[Step 0] 採樣率解析: 請求={sample_rate} → 使用預設={self.sample_rate}Hz")
        return self.sample_rate

    def _convert_csv_to_wav(self, csv_path: str, sample_rate: int) -> Optional[str]:
        """
        將 CSV 檔案轉換為 WAV 格式

        CSV 格式要求：
        - 每一列代表一個時間點的採樣
        - 每一欄代表一個音軌（channel）
        - 數值應為浮點數或整數，範圍在 -1.0 到 1.0 之間（如果超出會自動正規化）

        Args:
            csv_path: CSV 檔案路徑

        Returns:
            轉換後的 WAV 檔案路徑或 None
        """
        try:
            logger.info(f"開始轉換 CSV 到 WAV: {csv_path}")
            logger.debug(f"[Step 0] CSV→WAV 轉換開始: 目標採樣率={sample_rate}Hz, 來源={csv_path}")

            # 讀取 CSV 檔案
            df = pd.read_csv(csv_path, header=None)
            logger.debug(f"CSV 資料形狀: {df.shape}")

            # 轉換為 numpy 陣列
            audio_data = df.values.astype(np.float32)

            # 檢查資料形狀
            if audio_data.ndim == 1:
                # 單聲道：轉換為 (n_samples,) 格式
                audio_data = audio_data.flatten()
                n_channels = 1
                n_samples = len(audio_data)
            else:
                # 多聲道：轉換為 (n_samples, n_channels) 格式
                n_samples, n_channels = audio_data.shape

            logger.info(f"音訊資料: {n_samples} 採樣點, {n_channels} 聲道")

            # 檢查並正規化數值範圍
            max_val = np.abs(audio_data).max()
            if max_val > 1.0:
                logger.warning(f"音訊數值超出範圍 (max={max_val:.3f})，進行正規化")
                audio_data = audio_data / max_val

            # 建立臨時 WAV 檔案
            temp_wav = tempfile.NamedTemporaryFile(
                delete=False,
                suffix='.wav',
                dir=tempfile.gettempdir()
            )
            temp_wav_path = temp_wav.name
            temp_wav.close()

            # 寫入 WAV 檔案
            sf.write(temp_wav_path, audio_data, sample_rate)

            logger.info(f"✓ CSV 轉 WAV 成功: {temp_wav_path} (sample_rate={sample_rate}Hz)")

            # 返回轉換後的資訊
            return temp_wav_path

        except Exception as e:
            logger.error(f"CSV 轉 WAV 失敗 {csv_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_conversion_info(self, original_path: str, converted_path: str,
                            sample_rate: Optional[int] = None) -> Dict[str, Any]:
        """
        獲取轉檔資訊

        Args:
            original_path: 原始檔案路徑
            converted_path: 轉換後檔案路徑
            sample_rate: 轉檔時使用的採樣率

        Returns:
            轉檔資訊字典
        """
        try:
            original_size = os.path.getsize(original_path) if os.path.exists(original_path) else 0
            converted_size = os.path.getsize(converted_path) if os.path.exists(converted_path) else 0

            # 讀取轉換後的音訊資訊
            _, sr = sf.read(converted_path, frames=0)

            if isinstance(sr, (int, float)) and sr > 0:
                resolved_sample_rate = int(sr)
            else:
                resolved_sample_rate = self._resolve_sample_rate(sample_rate)

            return {
                'original_format': Path(original_path).suffix.lower(),
                'converted_format': '.wav',
                'original_size_bytes': original_size,
                'converted_size_bytes': converted_size,
                'sample_rate': resolved_sample_rate,
                'converted_path': converted_path
            }

        except Exception as e:
            logger.error(f"獲取轉檔資訊失敗: {e}")
            return {}

    def cleanup_temp_file(self, filepath: str):
        """
        清理臨時檔案

        Args:
            filepath: 要清理的檔案路徑
        """
        try:
            if filepath and os.path.exists(filepath):
                # 只清理臨時目錄中的檔案
                if tempfile.gettempdir() in filepath:
                    os.remove(filepath)
                    logger.debug(f"已清理臨時檔案: {filepath}")
        except Exception as e:
            logger.warning(f"清理臨時檔案失敗 {filepath}: {e}")

    def load_tdms_multi_channel(
        self,
        tdms_path: str,
        channels: List[str] = None,
        group_index: int = 0
    ) -> Dict[str, np.ndarray]:
        """
        讀取 TDMS 檔案多個通道

        參考 Models_training/data_preprocessing/tdms_preprocessing/tdms_loader.py

        Args:
            tdms_path: TDMS 檔案路徑
            channels: 通道名稱列表，預設為 ['Ch0-T1', 'Ch1-T5', 'Ch4-T3']
            group_index: 群組索引，預設為 0

        Returns:
            {通道名: numpy array 訊號數據} 字典，若全部失敗則返回空字典
        """
        if channels is None:
            channels = ['Ch0-T1', 'Ch1-T5', 'Ch4-T3']

        if not TDMS_AVAILABLE:
            logger.error("nptdms 未安裝，無法讀取 TDMS 檔案。請執行: pip install nptdms")
            return {}

        try:
            logger.info(f"開始讀取 TDMS 多通道: {tdms_path}, channels={channels}")

            tdms_file = TdmsFile.read(str(tdms_path))
            groups = tdms_file.groups()

            if not groups:
                logger.error(f"TDMS 檔案沒有群組: {tdms_path}")
                return {}

            if group_index >= len(groups):
                logger.error(f"群組索引超出範圍: {group_index} >= {len(groups)}")
                return {}

            group = groups[group_index]
            available_channels = {ch.name: ch for ch in group.channels()}

            if not available_channels:
                logger.error(f"群組 '{group.name}' 沒有通道")
                return {}

            logger.debug(f"可用通道: {list(available_channels.keys())}")

            # 讀取指定的多個通道
            result = {}
            for ch_name in channels:
                if ch_name in available_channels:
                    channel_data = available_channels[ch_name][:].astype(np.float32)
                    result[ch_name] = channel_data
                    logger.debug(f"✓ 讀取通道 '{ch_name}': {len(channel_data)} 採樣點")
                else:
                    logger.warning(f"找不到通道 '{ch_name}'，跳過")

            if result:
                logger.info(f"✓ TDMS 多通道讀取成功: {len(result)} 個通道")
            else:
                logger.error(f"所有指定通道都不存在: {channels}")
                logger.info(f"可用通道: {list(available_channels.keys())}")

            return result

        except Exception as e:
            logger.error(f"讀取 TDMS 多通道失敗 {tdms_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def load_tdms(
        self,
        tdms_path: str,
        channel: Union[int, str] = 5,
        group_index: int = 0
    ) -> Optional[np.ndarray]:
        """
        讀取 TDMS 檔案指定通道（向後相容）

        參考 Models_training/data_preprocessing/tdms_preprocessing/tdms_loader.py

        Args:
            tdms_path: TDMS 檔案路徑
            channel: 通道索引（int）或通道名稱（str），預設為 5
            group_index: 群組索引，預設為 0

        Returns:
            numpy array 訊號數據，或 None（如果失敗）
        """
        if not TDMS_AVAILABLE:
            logger.error("nptdms 未安裝，無法讀取 TDMS 檔案。請執行: pip install nptdms")
            return None

        try:
            logger.info(f"開始讀取 TDMS: {tdms_path}, channel={channel}")

            tdms_file = TdmsFile.read(str(tdms_path))
            groups = tdms_file.groups()

            if not groups:
                logger.error(f"TDMS 檔案沒有群組: {tdms_path}")
                return None

            if group_index >= len(groups):
                logger.error(f"群組索引超出範圍: {group_index} >= {len(groups)}")
                return None

            group = groups[group_index]
            channels = group.channels()

            if not channels:
                logger.error(f"群組 '{group.name}' 沒有通道")
                return None

            # 根據通道參數類型取得通道
            if isinstance(channel, int):
                # 通道索引
                if channel >= len(channels):
                    logger.error(f"通道索引超出範圍: {channel} >= {len(channels)}")
                    logger.info(f"可用通道: {[ch.name for ch in channels]}")
                    return None
                target_channel = channels[channel]
            else:
                # 通道名稱
                target_channel = None
                for ch in channels:
                    if ch.name == channel:
                        target_channel = ch
                        break
                if target_channel is None:
                    logger.error(f"找不到通道: {channel}")
                    logger.info(f"可用通道: {[ch.name for ch in channels]}")
                    return None

            # 讀取通道數據
            channel_data = target_channel[:].astype(np.float32)

            logger.info(f"✓ TDMS 讀取成功: channel='{target_channel.name}', samples={len(channel_data)}")

            return channel_data

        except Exception as e:
            logger.error(f"讀取 TDMS 失敗 {tdms_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_tdms_info(self, tdms_path: str) -> Optional[Dict[str, Any]]:
        """
        獲取 TDMS 檔案資訊

        Args:
            tdms_path: TDMS 檔案路徑

        Returns:
            包含群組和通道資訊的字典
        """
        if not TDMS_AVAILABLE:
            logger.error("nptdms 未安裝")
            return None

        try:
            tdms_file = TdmsFile.read(str(tdms_path))
            info = {
                'groups': [],
                'total_channels': 0
            }

            for group in tdms_file.groups():
                group_info = {
                    'name': group.name,
                    'channels': []
                }
                for ch in group.channels():
                    ch_info = {
                        'name': ch.name,
                        'dtype': str(ch.dtype) if hasattr(ch, 'dtype') else 'unknown',
                        'length': len(ch) if hasattr(ch, '__len__') else 0
                    }
                    group_info['channels'].append(ch_info)
                    info['total_channels'] += 1
                info['groups'].append(group_info)

            return info

        except Exception as e:
            logger.error(f"獲取 TDMS 資訊失敗: {e}")
            return None
