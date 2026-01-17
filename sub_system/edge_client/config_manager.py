"""
配置管理模組

負責邊緣客戶端的配置載入、儲存和管理
"""
import os
import json
import uuid
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """音訊配置"""
    default_device_index: int = 0
    channels: int = 1
    sample_rate: int = 16000
    bit_depth: int = 16

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioConfig':
        return cls(
            default_device_index=data.get('default_device_index', 0),
            channels=data.get('channels', 1),
            sample_rate=data.get('sample_rate', 16000),
            bit_depth=data.get('bit_depth', 16)
        )


@dataclass
class EdgeClientConfig:
    """邊緣客戶端配置"""
    device_id: Optional[str] = None
    device_name: str = ""
    server_url: str = "http://163.18.22.52:55103"
    audio_config: AudioConfig = field(default_factory=AudioConfig)
    heartbeat_interval: int = 30
    reconnect_delay: int = 5
    max_reconnect_delay: int = 60
    temp_wav_dir: str = "temp_wav"

    def __post_init__(self):
        # 若無設備名稱，生成預設名稱
        if not self.device_name:
            self.device_name = f"Device_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'device_id': self.device_id,
            'device_name': self.device_name,
            'server_url': self.server_url,
            'audio_config': self.audio_config.to_dict(),
            'heartbeat_interval': self.heartbeat_interval,
            'reconnect_delay': self.reconnect_delay,
            'max_reconnect_delay': self.max_reconnect_delay,
            'temp_wav_dir': self.temp_wav_dir
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EdgeClientConfig':
        audio_config_data = data.get('audio_config', {})
        if isinstance(audio_config_data, dict):
            audio_config = AudioConfig.from_dict(audio_config_data)
        else:
            audio_config = AudioConfig()

        return cls(
            device_id=data.get('device_id'),
            device_name=data.get('device_name', ''),
            server_url=data.get('server_url', 'http://163.18.22.52:55103'),
            audio_config=audio_config,
            heartbeat_interval=data.get('heartbeat_interval', 30),
            reconnect_delay=data.get('reconnect_delay', 5),
            max_reconnect_delay=data.get('max_reconnect_delay', 60),
            temp_wav_dir=data.get('temp_wav_dir', 'temp_wav')
        )


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = 'device_config.json'):
        """
        初始化配置管理器

        Args:
            config_file: 配置檔案路徑
        """
        self.config_file = config_file
        self.config: EdgeClientConfig = EdgeClientConfig()
        logger.info(f"配置管理器初始化，配置檔案: {config_file}")

    def load(self) -> EdgeClientConfig:
        """
        從檔案載入配置

        Returns:
            載入的配置
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = EdgeClientConfig.from_dict(data)
                    logger.info(f"配置已載入: device_id={self.config.device_id}, device_name={self.config.device_name}")
            else:
                logger.warning(f"配置檔案不存在: {self.config_file}，使用預設配置")
                self.config = EdgeClientConfig()

        except json.JSONDecodeError as e:
            logger.error(f"配置檔案格式錯誤: {e}")
            self.config = EdgeClientConfig()

        except Exception as e:
            logger.error(f"載入配置失敗: {e}")
            self.config = EdgeClientConfig()

        return self.config

    def save(self) -> bool:
        """
        儲存配置到檔案

        Returns:
            是否成功
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"配置已儲存: {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"儲存配置失敗: {e}")
            return False

    def update(self, **kwargs) -> bool:
        """
        更新配置並儲存

        Args:
            **kwargs: 要更新的配置項

        Returns:
            是否成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.debug(f"配置已更新: {key} = {value}")
                else:
                    logger.warning(f"未知的配置項: {key}")

            return self.save()

        except Exception as e:
            logger.error(f"更新配置失敗: {e}")
            return False

    def update_audio_config(self, **kwargs) -> bool:
        """
        更新音訊配置

        Args:
            **kwargs: 要更新的音訊配置項

        Returns:
            是否成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.config.audio_config, key):
                    setattr(self.config.audio_config, key, value)
                    logger.debug(f"音訊配置已更新: {key} = {value}")

            return self.save()

        except Exception as e:
            logger.error(f"更新音訊配置失敗: {e}")
            return False

    def set_device_id(self, device_id: str) -> bool:
        """
        設定設備 ID

        Args:
            device_id: 設備 ID

        Returns:
            是否成功
        """
        self.config.device_id = device_id
        return self.save()

    def set_device_name(self, device_name: str) -> bool:
        """
        設定設備名稱

        Args:
            device_name: 設備名稱

        Returns:
            是否成功
        """
        self.config.device_name = device_name
        return self.save()

    def get_device_id(self) -> Optional[str]:
        """獲取設備 ID"""
        return self.config.device_id

    def get_device_name(self) -> str:
        """獲取設備名稱"""
        return self.config.device_name

    def get_server_url(self) -> str:
        """獲取伺服器 URL"""
        return self.config.server_url

    def get_audio_config(self) -> AudioConfig:
        """獲取音訊配置"""
        return self.config.audio_config

    def get_heartbeat_interval(self) -> int:
        """獲取心跳間隔"""
        return self.config.heartbeat_interval

    def get_reconnect_delay(self) -> int:
        """獲取重連延遲"""
        return self.config.reconnect_delay

    def get_max_reconnect_delay(self) -> int:
        """獲取最大重連延遲"""
        return self.config.max_reconnect_delay

    def get_temp_wav_dir(self) -> str:
        """獲取暫存目錄"""
        return self.config.temp_wav_dir

    def has_device_id(self) -> bool:
        """檢查是否有設備 ID"""
        return self.config.device_id is not None and len(self.config.device_id) > 0

    @staticmethod
    def load_from_env() -> Dict[str, Any]:
        """
        從環境變數載入配置覆蓋

        Returns:
            從環境變數獲取的配置字典
        """
        env_config = {}

        if os.getenv('EDGE_SERVER_URL'):
            env_config['server_url'] = os.getenv('EDGE_SERVER_URL')

        if os.getenv('EDGE_DEVICE_NAME'):
            env_config['device_name'] = os.getenv('EDGE_DEVICE_NAME')

        if os.getenv('EDGE_TEMP_WAV_DIR'):
            env_config['temp_wav_dir'] = os.getenv('EDGE_TEMP_WAV_DIR')

        if os.getenv('EDGE_HEARTBEAT_INTERVAL'):
            try:
                env_config['heartbeat_interval'] = int(os.getenv('EDGE_HEARTBEAT_INTERVAL'))
            except ValueError:
                pass

        return env_config

    def apply_env_overrides(self):
        """套用環境變數覆蓋"""
        env_config = self.load_from_env()

        for key, value in env_config.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"從環境變數覆蓋配置: {key}")

    def get_full_config(self) -> Dict[str, Any]:
        """獲取完整配置（字典格式）"""
        return self.config.to_dict()

    def validate(self) -> tuple:
        """
        驗證配置是否有效

        Returns:
            (是否有效, 錯誤訊息列表)
        """
        errors = []

        if not self.config.server_url:
            errors.append("伺服器 URL 不能為空")

        if not self.config.server_url.startswith(('http://', 'https://')):
            errors.append("伺服器 URL 必須以 http:// 或 https:// 開頭")

        if self.config.heartbeat_interval < 5:
            errors.append("心跳間隔不能少於 5 秒")

        if self.config.audio_config.channels < 1:
            errors.append("聲道數必須大於 0")

        if self.config.audio_config.sample_rate < 8000:
            errors.append("採樣率不能低於 8000 Hz")

        is_valid = len(errors) == 0
        return is_valid, errors
