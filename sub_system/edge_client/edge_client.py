import sounddevice as sd
import soundfile as sf
import numpy as np
from contextlib import contextmanager
import os
import sys
import requests
import socketio
import time
import uuid
import logging
import json
from datetime import datetime
import hashlib

# 設置日誌
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sio = socketio.Client(logger=True, engineio_logger=True)


class AudioRecorder:
    """
    音頻錄製器類別，用於管理音頻設備、錄音、上傳等操作。
    """

    def __init__(self, config_file):
        """
        初始化 AudioRecorder 實例。

        :param config_file: 配置文件的路徑
        """
        self.RESPEAKER_RATE = 16000
        self.RESPEAKER_CHANNELS = 1
        self.WAVE_OUTPUT_FILENAME = "output.wav"
        # self.SERVER_URL = "http://163.18.22.51:88/"  # 伺服器的 IP 和端口
        self.SERVER_URL = "http://127.0.0.1:5000"  # 伺服器的 IP 和端口
        self.CONFIG_FILE = config_file
        self.TEMP_WAV_DIR = "temp_wav"
        self.device_id = None
        self.device_name = None
        self.status = "IDLE"  # 可能的狀態: IDLE, RECORDING, OFFLINE

        self.load_config()
        self.create_temp_wav_dir()
        self.list_audio_devices()

    def create_temp_wav_dir(self):
        """創建臨時 WAV 文件目錄"""
        try:
            os.makedirs(self.TEMP_WAV_DIR, exist_ok=True)
            logger.info(f"已創建或驗證臨時 WAV 目錄: {self.TEMP_WAV_DIR}")
        except Exception as e:
            logger.error(f"創建臨時 WAV 目錄時發生錯誤: {str(e)}")

    def load_config(self):
        """從配置文件加載設備 ID 和名稱"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.device_id = config.get('device_id')
                    self.device_name = config.get('device_name')
                logger.info(f"已加載配置: ID={self.device_id}, 名稱={self.device_name}")
            else:
                logger.warning(f"配置文件 {self.CONFIG_FILE} 不存在，使用預設值")
                self.device_name = f"Device_{uuid.uuid4().hex[:8]}"
        except Exception as e:
            logger.error(f"加載配置時發生錯誤: {str(e)}")
            self.device_name = f"Device_{uuid.uuid4().hex[:8]}"

    def save_config(self):
        """保存設備 ID 和名稱到配置文件"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump({
                    'device_id': self.device_id,
                    'device_name': self.device_name
                }, f)
            logger.info(f"已保存配置: ID={self.device_id}, 名稱={self.device_name}")
        except Exception as e:
            logger.error(f"保存配置時發生錯誤: {str(e)}")

    @staticmethod
    def calculate_file_hash(file_path):
        """計算文件的 SHA-256 哈希值"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    @contextmanager
    def ignore_alsa_errors():
        """忽略 ALSA 錯誤的上下文管理器"""
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        sys.stderr.flush()
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)

    def list_audio_devices(self):
        """列出可用的音頻設備"""
        logger.info("可用的音頻設備：")
        logger.info(sd.query_devices())

    def record_audio(self, duration, samplerate, channels):
        """
        錄製音頻。

        :param duration: 錄音時長（秒）
        :param samplerate: 採樣率
        :param channels: 聲道數
        :return: 錄音文件名，如果錄音失敗則返回 None
        """
        try:
            self.status = "RECORDING"
            sio.emit('update_status', {'device_id': self.device_id, 'status': self.status})
            logger.info("* 開始錄音")

            with self.ignore_alsa_errors():
                logger.debug(f"開始錄音：duration={duration}, samplerate={samplerate}, channels={channels}")
                recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels)
                sd.wait()

            logger.info("* 錄音完成")
            logger.info(f"* 錄音數組形狀: {recording.shape}")
            logger.info(f"* 實際錄製的聲道數: {recording.shape[1] if len(recording.shape) > 1 else 1}")

            filename = os.path.join(self.TEMP_WAV_DIR,
                                    f"{self.device_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
            sf.write(filename, recording, samplerate)
            logger.info(f"* 音頻已保存至 {filename}")

            data, saved_samplerate = sf.read(filename)
            logger.info(f"* 保存的文件聲道數: {data.shape[1] if len(data.shape) > 1 else 1}")
            logger.info(f"* 保存的文件採樣率: {saved_samplerate}")

            self.status = "IDLE"
            sio.emit('update_status', {'device_id': self.device_id, 'status': self.status})
            return filename
        except Exception as e:
            logger.error(f"錄音過程中發生錯誤: {str(e)}")
            self.status = "IDLE"
            sio.emit('update_status', {'device_id': self.device_id, 'status': self.status})
            return None

    def upload_audio(self, filename, duration):
        """
        上傳音頻文件到伺服器。

        :param filename: 要上傳的音頻文件名
        :param duration: 錄音時長
        """
        try:
            logger.info("* 開始上傳音頻文件")
            url = f"{self.SERVER_URL}/upload_recording"

            # 計算文件大小和哈希值
            file_size = os.path.getsize(filename)
            file_hash = self.calculate_file_hash(filename)

            with open(filename, 'rb') as f:
                files = {'file': f}
                data = {
                    'duration': duration,
                    'device_id': self.device_id,
                    'file_size': file_size,
                    'file_hash': file_hash
                }
                response = requests.post(url, files=files, data=data)

            if response.status_code == 200:
                logger.info("* 上傳完成且服務器驗證通過")
            else:
                logger.error(f"* 上傳失敗：{response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"* 上傳失敗：{e}")
        except Exception as e:
            logger.error(f"上傳音頻時發生錯誤: {str(e)}")

    def connect_to_server(self):
        """連接到伺服器，使用指數退避重試機制"""
        retry_delay = 5  # 初始重試延遲（秒）
        max_retry_delay = 60  # 最大重試延遲（秒）

        while True:
            try:
                sio.connect(self.SERVER_URL)
                logger.info("已連接伺服器")
                self.register_device()
                return  # 連接成功，退出循環
            except socketio.exceptions.ConnectionError as e:
                logger.error(f"連接錯誤: {e}")
                self.status = "OFFLINE"
                logger.info(f"等待 {retry_delay} 秒後重試...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # 指數退避
            except Exception as e:
                logger.error(f"連接伺服器時發生意外錯誤: {str(e)}")
                time.sleep(retry_delay)

    def register_device(self):
        """向伺服器註冊設備"""
        try:
            if self.device_id:
                sio.emit('register_device', {'client_id': self.device_id, 'device_name': self.device_name})
            else:
                sio.emit('request_id')
            self.status = "IDLE"
            sio.emit('update_status', {'device_id': self.device_id, 'status': self.status})
            logger.info(f"設備已註冊。ID: {self.device_id}, 名稱: {self.device_name}")
        except Exception as e:
            logger.error(f"註冊設備時發生錯誤: {str(e)}")

    def run(self):
        """運行音頻錄製器的主循環"""
        while True:
            try:
                self.connect_to_server()
                sio.wait()  # 等待直到斷開連接
            except Exception as e:
                logger.error(f"主循環中發生錯誤: {str(e)}")
            logger.info("與伺服器斷開連接，準備重新連接...")
            time.sleep(5)  # 等待一段時間後重新連接


# SocketIO 事件處理函數
@sio.on('connect')
def on_connect():
    logger.info("已連接到伺服器")
    recorder.register_device()


@sio.on('disconnect')
def on_disconnect():
    logger.info("與伺服器斷開連接")
    recorder.status = "OFFLINE"


@sio.event
def connect_error(data):
    logger.error(f"連接失敗: {data}")
    recorder.status = "OFFLINE"


@sio.event
def assign_id(data):
    try:
        if not recorder.device_id:
            recorder.device_id = data['client_id']
            recorder.save_config()
            logger.info(f"已分配 ID: {recorder.device_id}")
            sio.emit('register_device', {'client_id': recorder.device_id, 'device_name': recorder.device_name})
    except Exception as e:
        logger.error(f"分配 ID 時發生錯誤: {str(e)}")


@sio.on('record')
def on_record(data):
    try:
        logger.info(f"收到錄音命令: {data}")
        duration = data['duration']
        device_index = 1  # 假設使用索引 1 的設備

        with AudioRecorder.ignore_alsa_errors():
            device_info = sd.query_devices(device_index, 'input')
            if device_info is None:
                logger.error(f"* 錯誤: 未找到索引為 {device_index} 的設備")
                return

            logger.info(f"* 使用設備: {device_info['name']}")

            actual_samplerate = int(device_info['default_samplerate'])

        filename = recorder.record_audio(duration, actual_samplerate, recorder.RESPEAKER_CHANNELS)
        if filename:
            recorder.upload_audio(filename, duration)
    except Exception as e:
        logger.error(f"處理錄音命令時發生錯誤: {str(e)}")


@sio.on('update_device_name')
def on_update_device_name(data):
    try:
        if data['device_id'] == recorder.device_id:
            recorder.device_name = data['device_name']
            recorder.save_config()
            logger.info(f"已更新設備名稱為: {recorder.device_name}")
    except Exception as e:
        logger.error(f"更新設備名稱時發生錯誤: {str(e)}")


@sio.on('update_devices')
def on_update_devices(data):
    try:
        for device in data['devices']:
            if device['id'] == recorder.device_id and device['name'] != recorder.device_name:
                recorder.device_name = device['name']
                recorder.save_config()
                logger.info(f"已從伺服器同步設備名稱: {recorder.device_name}")
    except Exception as e:
        logger.error(f"更新設備列表時發生錯誤: {str(e)}")


if __name__ == "__main__":
    config_file = "device_config.json"  # 設定配置文件名稱
    recorder = AudioRecorder(config_file)
    while True:
        try:
            recorder.run()
        except Exception as e:
            logger.error(f"主程序運行時發生錯誤: {str(e)}", exc_info=True)
            logger.info("5秒後嘗試重新啟動程序...")
            time.sleep(5)