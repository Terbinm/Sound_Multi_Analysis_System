# processors/step1_slicer.py - 音訊切割處理器（支援指定音軌）

import librosa
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from config import UPLOAD_FOLDER
from utils.logger import logger
import os


class AudioSlicer:
    """音訊切割處理器"""

    def __init__(self, audio_config: Dict[str, Any]):
        """初始化切割器"""
        self.config = dict(audio_config)
        logger.info(f"AudioSlicer 初始化: duration={self.config['slice_duration']}s, "
                    f"interval={self.config['slice_interval']}s")

    def apply_config(self, audio_config: Dict[str, Any]):
        """更新音訊切割參數"""
        if not isinstance(audio_config, dict):
            return
        self.config.update(audio_config)
        logger.info(f"AudioSlicer 配置已更新: duration={self.config['slice_duration']}s, interval={self.config['slice_interval']}s")

    def slice_audio(self, filepath: str, target_channels: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        切割音訊檔案

        Args:
            filepath: 音訊檔案路徑
            target_channels: 目標音軌列表（從 info_features.target_channel 獲取）
                           如果為 None 或空列表，則使用配置檔中的預設值
                           如果配置檔也為空，則使用第一軌（index 0）

        Returns:
            切片資料列表，格式：
            [
                {
                    'selec': 切片編號,
                    'channel': 通道編號,
                    'start': 開始時間(秒),
                    'end': 結束時間(秒),
                    'bottom_freq': 最低頻率(kHz),
                    'top_freq': 最高頻率(kHz)
                },
                ...
            ]
        """
        try:
            # 檢查檔案是否存在
            if not os.path.exists(filepath):
                logger.error(f"檔案不存在: {filepath}")
                return []

            logger.debug(f"開始切割音訊: {filepath}")

            # 載入音訊
            audio, sr = librosa.load(
                filepath,
                sr=self.config['sample_rate'],
                mono=False
            )

            # 確保是多通道格式
            if audio.ndim == 1:
                audio = audio.reshape(1, -1)

            logger.debug(f"音訊載入成功: shape={audio.shape}, sr={sr}")

            # 決定要處理的音軌
            channels_to_process = self._determine_channels(audio.shape[0], target_channels)
            logger.debug(f"將處理以下音軌: {channels_to_process}")

            # 計算切割參數供日誌輸出
            slice_samples = int(self.config['slice_duration'] * sr)
            interval_samples = int(self.config['slice_interval'] * sr)
            total_samples = audio.shape[1]
            estimated_slices = max(0, (total_samples - slice_samples) // interval_samples + 1) * len(channels_to_process)
            logger.debug(
                f"[Step 1] 切割參數確認: "
                f"採樣率={sr}Hz, 總採樣點={total_samples}, "
                f"切片時長={self.config['slice_duration']}s ({slice_samples}採樣點), "
                f"切片間隔={self.config['slice_interval']}s ({interval_samples}採樣點), "
                f"預計切片數≈{estimated_slices}"
            )

            # 執行切割
            segments = self._perform_slicing(audio, sr, channels_to_process)

            logger.info(f"切割完成: 共 {len(segments)} 個切片")
            return segments

        except Exception as e:
            logger.error(f"音訊切割失敗 {filepath}: {e}")
            return []

    def _determine_channels(self, total_channels: int, target_channels: Optional[List[int]] = None) -> List[int]:
        """
        決定要處理的音軌

        優先順序:
        1. 使用 target_channels（從 info_features.target_channel）
        2. 使用配置檔中的預設值（config.AUDIO_CONFIG['channels']）
        3. 使用第一軌（index 0）

        Args:
            total_channels: 音訊檔案的總音軌數
            target_channels: 目標音軌列表

        Returns:
            要處理的音軌列表
        """
        # 優先使用傳入的 target_channels
        if target_channels and len(target_channels) > 0:
            # 過濾掉超出範圍的音軌
            valid_channels = [ch for ch in target_channels if 0 <= ch < total_channels]

            if not valid_channels:
                logger.warning(f"target_channels {target_channels} 全部超出範圍 [0, {total_channels}), 使用第一軌")
                return [0]

            if len(valid_channels) < len(target_channels):
                invalid_channels = set(target_channels) - set(valid_channels)
                logger.warning(f"部分音軌超出範圍被忽略: {invalid_channels}")

            return valid_channels

        # 其次使用配置檔中的預設值
        config_channels = self.config.get('channels', [])
        if config_channels and len(config_channels) > 0:
            valid_channels = [ch for ch in config_channels if 0 <= ch < total_channels]

            if valid_channels:
                logger.info(f"使用配置檔中的預設音軌: {valid_channels}")
                return valid_channels

        # 最後使用第一軌
        logger.info(f"使用預設第一軌 (index 0)")
        return [0]

    def _perform_slicing(self, audio: np.ndarray, sr: int, channels: List[int]) -> List[Dict[str, Any]]:
        """
        執行實際的切割操作

        Args:
            audio: 音訊資料 (channels, samples)
            sr: 採樣率
            channels: 要處理的音軌列表

        Returns:
            切片資料列表
        """
        segments = []
        duration = self.config['slice_duration']
        interval = self.config['slice_interval']

        # 計算樣本數
        slice_samples = int(duration * sr)
        interval_samples = int(interval * sr)

        # 對每個指定的通道進行切割
        for channel in channels:
            if channel >= audio.shape[0]:
                logger.warning(f"通道 {channel} 超出範圍，跳過")
                continue

            channel_audio = audio[channel]

            # 滑動視窗切割
            start_sample = 0
            selec_count = 1

            while start_sample + slice_samples <= len(channel_audio):
                end_sample = start_sample + slice_samples

                start_time = start_sample / sr
                end_time = end_sample / sr

                # 檢查最小長度
                if end_time - start_time >= self.config['min_segment_duration']:
                    segment_info = {
                        'selec': selec_count,
                        'channel': channel,
                        'start': round(start_time, 6),
                        'end': round(end_time, 6),
                        'bottom_freq': 0.002,  # kHz
                        'top_freq': round(sr / 2 / 1000, 3)  # kHz (Nyquist)
                    }
                    segments.append(segment_info)
                    selec_count += 1

                start_sample += interval_samples

        return segments

    def validate_filepath(self, filepath: str) -> bool:
        """
        驗證檔案路徑

        Args:
            filepath: 檔案路徑

        Returns:
            是否有效
        """
        # 檢查是否為絕對路徑
        if not os.path.isabs(filepath):
            # 嘗試從 UPLOAD_FOLDER 組合路徑
            filepath = os.path.join(UPLOAD_FOLDER, filepath)

        return os.path.exists(filepath) and os.path.isfile(filepath)

    def get_audio_info(self, filepath: str) -> Dict[str, Any]:
        """
        獲取音訊資訊

        Args:
            filepath: 音訊檔案路徑

        Returns:
            音訊資訊字典
        """
        try:
            audio, sr = librosa.load(filepath, sr=None, mono=False)

            if audio.ndim == 1:
                channels = 1
                duration = len(audio) / sr
            else:
                channels = audio.shape[0]
                duration = audio.shape[1] / sr

            logger.debug(f"[Step 1] 音訊資訊: 採樣率={sr}Hz, 通道={channels}, 時長={duration:.4f}秒, 採樣點={audio.shape[-1] if audio.ndim > 1 else len(audio)}")
            return {
                'sample_rate': sr,
                'channels': channels,
                'duration': round(duration, 3),
                'samples': audio.shape[-1] if audio.ndim > 1 else len(audio)
            }
        except Exception as e:
            logger.error(f"獲取音訊資訊失敗 {filepath}: {e}")
            return {}

    def slice_signal(
        self,
        signal: np.ndarray,
        slice_duration: Optional[float] = None,
        sample_rate: Optional[int] = None,
        overlap: bool = False
    ) -> List[Dict[str, Any]]:
        """
        直接對 numpy array 進行切片（用於 TDMS 訊號）

        與 slice_audio() 不同：
        - slice_audio(): 從檔案讀取 + librosa + 滑動窗口
        - slice_signal(): 直接對 array 切片 + 可選不重疊

        參考 Models_training/data_preprocessing/tdms_preprocessing/tdms_loader.py

        Args:
            signal: numpy array 訊號數據 (1D)
            slice_duration: 每個切片的時長（秒），預設使用配置中的值
            sample_rate: 取樣率（Hz），預設使用配置中的值
            overlap: 是否允許重疊，False 表示不重疊切片

        Returns:
            切片列表，格式：
            [
                {
                    'selec': 切片編號 (從 1 開始),
                    'data': numpy array 切片數據,
                    'start': 開始時間(秒),
                    'end': 結束時間(秒),
                    'sample_start': 開始採樣點,
                    'sample_end': 結束採樣點
                },
                ...
            ]
        """
        try:
            # 使用傳入參數或配置中的預設值
            duration = slice_duration if slice_duration is not None else self.config['slice_duration']
            sr = sample_rate if sample_rate is not None else self.config['sample_rate']

            # 計算每個切片的採樣點數
            slice_samples = int(duration * sr)

            # 決定步進大小
            if overlap:
                interval = self.config.get('slice_interval', duration)
                step_samples = int(interval * sr)
            else:
                step_samples = slice_samples  # 不重疊

            total_samples = len(signal)
            slices = []
            selec = 1

            logger.debug(
                f"[Step 1] 訊號切片參數: "
                f"總採樣點={total_samples}, 採樣率={sr}Hz, "
                f"切片時長={duration}s ({slice_samples}採樣點), "
                f"步進={step_samples}採樣點, 重疊={overlap}"
            )

            # 進行切片
            for start in range(0, total_samples - slice_samples + 1, step_samples):
                end = start + slice_samples

                slice_data = signal[start:end]

                slice_info = {
                    'selec': selec,
                    'data': slice_data,
                    'start': round(start / sr, 6),
                    'end': round(end / sr, 6),
                    'sample_start': start,
                    'sample_end': end
                }
                slices.append(slice_info)
                selec += 1

            logger.info(f"訊號切片完成: 共 {len(slices)} 個切片 (每片 {duration}s)")

            return slices

        except Exception as e:
            logger.error(f"訊號切片失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
