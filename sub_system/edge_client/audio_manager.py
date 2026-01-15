"""
音訊設備管理模組

負責管理音訊設備的偵測、查詢和錄音操作
支援 Windows 和 Linux 跨平台
"""
import os
import sys
import logging
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import sounddevice as sd
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)


class AudioDevice:
    """音訊設備資訊"""

    def __init__(
        self,
        index: int,
        name: str,
        max_input_channels: int,
        max_output_channels: int,
        default_sample_rate: float
    ):
        self.index = index
        self.name = name
        self.max_input_channels = max_input_channels
        self.max_output_channels = max_output_channels
        self.default_sample_rate = default_sample_rate

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'index': self.index,
            'name': self.name,
            'max_input_channels': self.max_input_channels,
            'max_output_channels': self.max_output_channels,
            'default_sample_rate': self.default_sample_rate
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioDevice':
        """從字典建立"""
        return cls(
            index=data.get('index', 0),
            name=data.get('name', ''),
            max_input_channels=data.get('max_input_channels', 0),
            max_output_channels=data.get('max_output_channels', 0),
            default_sample_rate=data.get('default_sample_rate', 44100)
        )


class AudioManager:
    """音訊設備管理器"""

    def __init__(self, temp_dir: str = 'temp_wav'):
        """
        初始化音訊管理器

        Args:
            temp_dir: 暫存音訊檔案目錄
        """
        self.temp_dir = temp_dir
        self.platform = sys.platform
        self._ensure_temp_dir()
        logger.info(f"音訊管理器初始化完成，平台: {self.platform}")

    def _ensure_temp_dir(self):
        """確保暫存目錄存在"""
        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            logger.debug(f"暫存目錄已確認: {self.temp_dir}")
        except Exception as e:
            logger.error(f"建立暫存目錄失敗: {e}")

    @staticmethod
    @contextmanager
    def suppress_alsa_errors():
        """
        抑制 ALSA 錯誤訊息的上下文管理器

        僅在 Linux 系統有效，Windows 和 macOS 不需要此處理
        """
        # 僅在 Linux 系統上抑制 ALSA 錯誤
        if sys.platform == 'linux':
            devnull = None
            old_stderr = None
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                old_stderr = os.dup(2)
                sys.stderr.flush()
                os.dup2(devnull, 2)
                os.close(devnull)
                devnull = None
            except OSError:
                # stderr 重導向設定失敗，清理已開啟的資源
                if devnull is not None:
                    os.close(devnull)
                old_stderr = None

            try:
                yield
            finally:
                if old_stderr is not None:
                    try:
                        os.dup2(old_stderr, 2)
                        os.close(old_stderr)
                    except OSError:
                        pass
        else:
            yield

    def list_devices(self) -> List[AudioDevice]:
        """
        列出所有可用的音訊輸入設備

        Returns:
            音訊設備列表
        """
        devices = []
        try:
            with self.suppress_alsa_errors():
                device_list = sd.query_devices()

            for idx, dev in enumerate(device_list):
                # 僅列出有輸入通道的設備
                if dev.get('max_input_channels', 0) > 0:
                    devices.append(AudioDevice(
                        index=idx,
                        name=dev.get('name', f'Device {idx}'),
                        max_input_channels=dev.get('max_input_channels', 0),
                        max_output_channels=dev.get('max_output_channels', 0),
                        default_sample_rate=dev.get('default_samplerate', 44100)
                    ))

            logger.info(f"找到 {len(devices)} 個音訊輸入設備")

        except Exception as e:
            logger.error(f"列出音訊設備失敗: {e}")

        return devices

    def list_devices_as_dict(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的音訊輸入設備（字典格式）

        Returns:
            音訊設備字典列表
        """
        return [dev.to_dict() for dev in self.list_devices()]

    def get_device_info(self, device_index: int) -> Optional[AudioDevice]:
        """
        獲取指定設備的資訊

        Args:
            device_index: 設備索引

        Returns:
            設備資訊，失敗返回 None
        """
        try:
            with self.suppress_alsa_errors():
                dev = sd.query_devices(device_index, 'input')

            if dev:
                return AudioDevice(
                    index=device_index,
                    name=dev.get('name', f'Device {device_index}'),
                    max_input_channels=dev.get('max_input_channels', 0),
                    max_output_channels=dev.get('max_output_channels', 0),
                    default_sample_rate=dev.get('default_samplerate', 44100)
                )

        except Exception as e:
            logger.error(f"獲取設備資訊失敗 (index={device_index}): {e}")

        return None

    def validate_recording_config(
        self,
        device_index: int,
        channels: int,
        sample_rate: int
    ) -> tuple:
        """
        驗證錄音配置是否有效

        Args:
            device_index: 設備索引
            channels: 聲道數
            sample_rate: 採樣率

        Returns:
            (是否有效, 錯誤訊息或 None)
        """
        try:
            device = self.get_device_info(device_index)
            if not device:
                return False, f"設備索引 {device_index} 不存在"

            if channels > device.max_input_channels:
                return False, f"設備 '{device.name}' 最多支援 {device.max_input_channels} 聲道"

            if channels < 1:
                return False, "聲道數必須大於 0"

            if sample_rate < 8000 or sample_rate > 192000:
                return False, "採樣率必須在 8000-192000 Hz 之間"

            return True, None

        except Exception as e:
            return False, str(e)

    def record(
        self,
        duration: float,
        sample_rate: int = 16000,
        channels: int = 1,
        device_index: int = 0,
        device_name: str = 'Device',
        progress_callback=None
    ) -> Optional[str]:
        """
        執行錄音

        Args:
            duration: 錄音時長（秒）
            sample_rate: 採樣率
            channels: 聲道數
            device_index: 音訊設備索引
            device_name: 設備名稱（用於檔案命名）
            progress_callback: 進度回調函數 (progress_percent) -> None

        Returns:
            錄音檔案路徑，失敗返回 None
        """
        try:
            logger.info(f"開始錄音: duration={duration}s, rate={sample_rate}, channels={channels}, device={device_index}")

            # 驗證配置
            is_valid, error = self.validate_recording_config(device_index, channels, sample_rate)
            if not is_valid:
                logger.error(f"錄音配置無效: {error}")
                return None

            # 計算樣本數
            num_samples = int(duration * sample_rate)

            # 執行錄音
            with self.suppress_alsa_errors():
                logger.debug(f"使用設備 {device_index} 開始錄音...")

                # 若有進度回調，使用分塊錄音
                if progress_callback:
                    recording = self._record_with_progress(
                        duration=duration,
                        sample_rate=sample_rate,
                        channels=channels,
                        device_index=device_index,
                        progress_callback=progress_callback
                    )
                else:
                    # 直接錄音
                    recording = sd.rec(
                        num_samples,
                        samplerate=sample_rate,
                        channels=channels,
                        device=device_index,
                        dtype='float32'
                    )
                    sd.wait()

            if recording is None or len(recording) == 0:
                logger.error("錄音資料為空")
                return None

            logger.info(f"錄音完成，資料形狀: {recording.shape}")

            # 生成檔案名稱
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.temp_dir, f"{device_name}_{timestamp}.wav")

            # 儲存為 WAV 檔案
            sf.write(filename, recording, sample_rate)
            logger.info(f"錄音已儲存: {filename}")

            # 驗證檔案
            self._verify_recording(filename)

            return filename

        except Exception as e:
            logger.error(f"錄音失敗: {e}", exc_info=True)
            return None

    def _record_with_progress(
        self,
        duration: float,
        sample_rate: int,
        channels: int,
        device_index: int,
        progress_callback
    ) -> np.ndarray:
        """
        分塊錄音並回報進度

        Args:
            duration: 錄音時長（秒）
            sample_rate: 採樣率
            channels: 聲道數
            device_index: 設備索引
            progress_callback: 進度回調

        Returns:
            錄音資料
        """
        import threading
        import time

        num_samples = int(duration * sample_rate)
        recording = sd.rec(
            num_samples,
            samplerate=sample_rate,
            channels=channels,
            device=device_index,
            dtype='float32'
        )

        # 在背景執行緒中更新進度
        start_time = time.time()

        def update_progress():
            while not sd.get_stream().stopped:
                elapsed = time.time() - start_time
                progress = min(int((elapsed / duration) * 100), 99)
                try:
                    progress_callback(progress)
                except Exception:
                    pass
                time.sleep(0.5)

        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()

        sd.wait()

        # 最終進度
        try:
            progress_callback(100)
        except Exception:
            pass

        return recording

    def _verify_recording(self, filename: str):
        """
        驗證錄音檔案

        Args:
            filename: 檔案路徑
        """
        try:
            data, sample_rate = sf.read(filename)
            actual_channels = data.shape[1] if len(data.shape) > 1 else 1
            duration = len(data) / sample_rate

            logger.info(f"檔案驗證: 聲道數={actual_channels}, 採樣率={sample_rate}, 時長={duration:.2f}s")

        except Exception as e:
            logger.warning(f"驗證錄音檔案失敗: {e}")

    def get_default_device_index(self) -> int:
        """
        獲取預設輸入設備索引

        Returns:
            預設設備索引
        """
        try:
            with self.suppress_alsa_errors():
                default = sd.default.device[0]  # [input, output]
                if default is not None:
                    return default
        except Exception as e:
            logger.debug(f"獲取預設設備索引失敗: {e}")

        # 回退到第一個輸入設備
        devices = self.list_devices()
        if devices:
            return devices[0].index

        return 0

    def calculate_file_hash(self, filename: str) -> str:
        """
        計算檔案的 SHA-256 雜湊值

        Args:
            filename: 檔案路徑

        Returns:
            雜湊值字串
        """
        import hashlib

        sha256_hash = hashlib.sha256()
        try:
            with open(filename, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"計算檔案雜湊值失敗: {e}")
            return ""

    def get_file_info(self, filename: str) -> Dict[str, Any]:
        """
        獲取錄音檔案資訊

        Args:
            filename: 檔案路徑

        Returns:
            檔案資訊字典
        """
        try:
            file_size = os.path.getsize(filename)
            file_hash = self.calculate_file_hash(filename)

            data, sample_rate = sf.read(filename)
            actual_duration = len(data) / sample_rate

            return {
                'filename': os.path.basename(filename),
                'file_path': filename,
                'file_size': file_size,
                'file_hash': file_hash,
                'actual_duration': actual_duration,
                'sample_rate': sample_rate,
                'channels': data.shape[1] if len(data.shape) > 1 else 1
            }

        except Exception as e:
            logger.error(f"獲取檔案資訊失敗: {e}")
            return {}
