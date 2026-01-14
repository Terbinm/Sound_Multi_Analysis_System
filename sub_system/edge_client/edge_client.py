"""
邊緣客戶端主程式

負責與伺服器通訊、接收錄音命令、執行錄音並上傳
支援 Windows 和 Linux 跨平台
"""
import os
import sys
import time
import logging
import threading
import requests
import socketio
from datetime import datetime

from audio_manager import AudioManager
from config_manager import ConfigManager

# 設置日誌（使用 sys.stdout 避免所有日誌都顯示為紅色）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class EdgeClient:
    """邊緣客戶端"""

    def __init__(self, config_path: str = 'device_config.json'):
        """
        初始化邊緣客戶端

        Args:
            config_path: 配置檔案路徑
        """
        # 載入配置
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load()  # 從文件載入配置

        # 初始化音訊管理器
        self.audio_manager = AudioManager(temp_dir=self.config.temp_wav_dir)

        # SocketIO 客戶端
        # 注意：禁用自動重連，由主迴圈手動控制重連，避免兩套機制衝突
        self.sio = socketio.Client(
            logger=True,
            engineio_logger=False,
            reconnection=False  # 禁用自動重連，使用手動重連
        )

        # 狀態
        self.status = 'IDLE'  # IDLE / RECORDING / OFFLINE
        self.current_recording_uuid = None
        self._heartbeat_thread = None
        self._heartbeat_stop_event = threading.Event()
        self._connected = False

        # 註冊事件處理器
        self._register_event_handlers()

        logger.info(f"邊緣客戶端初始化完成: device_id={self.config.device_id}, name={self.config.device_name}")

    def _register_event_handlers(self):
        """註冊 WebSocket 事件處理器"""

        @self.sio.on('connect')
        def on_connect():
            """連線成功"""
            logger.info("已連線至伺服器")
            self._connected = True
            self.status = 'IDLE'
            self._register_device()
            self._start_heartbeat()

        @self.sio.on('disconnect')
        def on_disconnect():
            """斷線事件處理"""
            logger.warning("收到 disconnect 事件 - 與伺服器斷開連線")
            self._connected = False
            self.status = 'OFFLINE'
            self._stop_heartbeat()
            logger.info("已清理連線狀態，等待主迴圈重新連線")

        @self.sio.on('connect_error')
        def on_connect_error(data):
            """連線錯誤"""
            logger.error(f"連線錯誤: {data}")
            self._connected = False
            self.status = 'OFFLINE'

        # ==================== 新事件 ====================

        @self.sio.on('edge.registered')
        def on_edge_registered(data):
            """設備註冊成功"""
            try:
                device_id = data.get('device_id')
                if device_id and device_id != self.config.device_id:
                    # 伺服器分配了新的 device_id
                    self.config.device_id = device_id
                    self.config_manager.save()
                    logger.info(f"已獲得伺服器分配的 device_id: {device_id}")
                else:
                    logger.info("設備註冊成功")
            except Exception as e:
                logger.error(f"處理註冊回應時發生錯誤: {e}")

        @self.sio.on('edge.error')
        def on_edge_error(data):
            """處理伺服器錯誤事件"""
            try:
                error = data.get('error', '未知錯誤')
                message = data.get('message', '')
                logger.error(f"伺服器錯誤: {error} - {message}")
            except Exception as e:
                logger.error(f"處理錯誤事件時發生錯誤: {e}")

        @self.sio.on('edge.record')
        def on_edge_record(data):
            """接收錄音命令"""
            try:
                logger.info(f"收到錄音命令: {data}")
                self._handle_record_command(data)
            except Exception as e:
                logger.error(f"處理錄音命令時發生錯誤: {e}", exc_info=True)

        @self.sio.on('edge.stop')
        def on_edge_stop(data):
            """接收停止錄音命令"""
            try:
                logger.info(f"收到停止錄音命令: {data}")
                # 目前的實作使用 sounddevice 的阻塞式錄音，無法中途停止
                # 未來可考慮使用串流方式實作可中斷的錄音
                logger.warning("目前不支援中途停止錄音")
            except Exception as e:
                logger.error(f"處理停止錄音命令時發生錯誤: {e}")

        @self.sio.on('edge.query_audio_devices')
        def on_query_audio_devices(data):
            """查詢音訊設備"""
            try:
                logger.info(f"收到查詢音訊設備請求: {data}")
                request_id = data.get('request_id')

                # 取得音訊設備列表
                devices = self.audio_manager.list_devices_as_dict()

                # 回應伺服器
                self.sio.emit('edge.audio_devices_response', {
                    'device_id': self.config.device_id,
                    'request_id': request_id,
                    'devices': devices
                })
                logger.info(f"已回應音訊設備查詢，共 {len(devices)} 個設備")

            except Exception as e:
                logger.error(f"處理查詢音訊設備時發生錯誤: {e}", exc_info=True)

        @self.sio.on('edge.update_config')
        def on_update_config(data):
            """更新配置"""
            try:
                logger.info(f"收到配置更新: {data}")

                # 更新設備名稱
                if 'device_name' in data:
                    self.config.device_name = data['device_name']

                # 更新音訊配置
                if 'audio_config' in data:
                    audio_cfg = data['audio_config']
                    if 'default_device_index' in audio_cfg:
                        self.config.audio_config.default_device_index = audio_cfg['default_device_index']
                    if 'channels' in audio_cfg:
                        self.config.audio_config.channels = audio_cfg['channels']
                    if 'sample_rate' in audio_cfg:
                        self.config.audio_config.sample_rate = audio_cfg['sample_rate']
                    if 'bit_depth' in audio_cfg:
                        self.config.audio_config.bit_depth = audio_cfg['bit_depth']

                # 儲存配置
                self.config_manager.save()
                logger.info("配置已更新並儲存")

            except Exception as e:
                logger.error(f"處理配置更新時發生錯誤: {e}", exc_info=True)

    def _register_device(self):
        """向伺服器註冊設備"""
        try:
            # 取得音訊設備列表
            audio_devices = self.audio_manager.list_devices_as_dict()

            # 發送註冊請求
            register_data = {
                'device_id': self.config.device_id,
                'device_name': self.config.device_name,
                'platform': sys.platform,
                'audio_config': {
                    'default_device_index': self.config.audio_config.default_device_index,
                    'channels': self.config.audio_config.channels,
                    'sample_rate': self.config.audio_config.sample_rate,
                    'bit_depth': self.config.audio_config.bit_depth,
                    'available_devices': audio_devices
                }
            }

            self.sio.emit('edge.register', register_data)
            logger.info(f"已發送設備註冊請求: device_id={self.config.device_id}")

        except Exception as e:
            logger.error(f"註冊設備時發生錯誤: {e}", exc_info=True)

    def _start_heartbeat(self):
        """啟動心跳執行緒"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.debug("心跳執行緒已啟動")

    def _stop_heartbeat(self):
        """停止心跳執行緒"""
        self._heartbeat_stop_event.set()
        logger.debug("心跳執行緒已停止")

    def _heartbeat_loop(self):
        """心跳迴圈"""
        consecutive_failures = 0
        max_failures = 3

        # 等待連線穩定（避免競態條件）
        time.sleep(1)

        while not self._heartbeat_stop_event.is_set():
            try:
                # 關鍵：檢查 SocketIO 實際連線狀態
                if not self.sio.connected:
                    logger.warning("SocketIO 連線已中斷，停止心跳執行緒")
                    self._connected = False
                    break

                # 只在已連線且有有效 device_id 時才發送心跳
                if self._connected and self.config.device_id:
                    heartbeat_data = {
                        'device_id': self.config.device_id,
                        'status': self.status,
                        'current_recording': self.current_recording_uuid,
                        'timestamp': datetime.now().isoformat()
                    }
                    self.sio.emit('edge.heartbeat', heartbeat_data)
                    logger.debug(f"已發送心跳: status={self.status}")
                    consecutive_failures = 0  # 重置失敗計數

                elif self._connected and not self.config.device_id:
                    logger.debug("等待伺服器分配 device_id，暫不發送心跳")

            except Exception as e:
                logger.error(f"發送心跳時發生錯誤: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    logger.error(f"連續 {max_failures} 次心跳失敗，標記為斷線")
                    self._connected = False
                    break

            # 等待下一次心跳
            self._heartbeat_stop_event.wait(self.config.heartbeat_interval)

        logger.info("心跳執行緒結束")

    def _handle_record_command(self, data: dict):
        """
        處理錄音命令

        Args:
            data: 錄音參數
        """
        if self.status == 'RECORDING':
            logger.warning("設備正在錄音中，忽略此次錄音命令")
            return

        # 解析參數
        duration = data.get('duration', 10)
        channels = data.get('channels', self.config.audio_config.channels)
        sample_rate = data.get('sample_rate', self.config.audio_config.sample_rate)
        device_index = data.get('device_index', self.config.audio_config.default_device_index)
        recording_uuid = data.get('recording_uuid')

        # 更新狀態
        self.status = 'RECORDING'
        self.current_recording_uuid = recording_uuid

        # 通知伺服器錄音開始
        self.sio.emit('edge.recording_started', {
            'device_id': self.config.device_id,
            'recording_uuid': recording_uuid
        })

        # 舊版狀態更新（向後相容）
        self.sio.emit('update_status', {
            'device_id': self.config.device_id,
            'status': 'RECORDING'
        })

        try:
            # 定義進度回調
            def progress_callback(progress_percent):
                if self._connected:
                    self.sio.emit('edge.recording_progress', {
                        'device_id': self.config.device_id,
                        'recording_uuid': recording_uuid,
                        'progress_percent': progress_percent
                    })

            # 執行錄音
            logger.info(f"開始錄音: duration={duration}s, channels={channels}, "
                       f"sample_rate={sample_rate}, device_index={device_index}")

            filename = self.audio_manager.record(
                duration=duration,
                sample_rate=sample_rate,
                channels=channels,
                device_index=device_index,
                device_name=self.config.device_name,
                progress_callback=progress_callback
            )

            if filename:
                # 取得檔案資訊
                file_info = self.audio_manager.get_file_info(filename)

                logger.info(f"錄音完成: {filename}")

                # 通知伺服器錄音完成
                self.sio.emit('edge.recording_completed', {
                    'device_id': self.config.device_id,
                    'recording_uuid': recording_uuid,
                    'filename': file_info.get('filename'),
                    'file_size': file_info.get('file_size'),
                    'file_hash': file_info.get('file_hash'),
                    'actual_duration': file_info.get('actual_duration')
                })

                # 上傳檔案
                self._upload_recording(filename, duration, recording_uuid)

            else:
                # 錄音失敗
                logger.error("錄音失敗")
                self.sio.emit('edge.recording_failed', {
                    'device_id': self.config.device_id,
                    'recording_uuid': recording_uuid,
                    'error': '錄音失敗'
                })

        except Exception as e:
            logger.error(f"錄音過程中發生錯誤: {e}", exc_info=True)
            self.sio.emit('edge.recording_failed', {
                'device_id': self.config.device_id,
                'recording_uuid': recording_uuid,
                'error': str(e)
            })

        finally:
            # 恢復狀態
            self.status = 'IDLE'
            self.current_recording_uuid = None

            # 舊版狀態更新（向後相容）
            self.sio.emit('update_status', {
                'device_id': self.config.device_id,
                'status': 'IDLE'
            })

    def _upload_recording(self, filename: str, duration: float, recording_uuid: str = None):
        """
        上傳錄音檔案

        Args:
            filename: 檔案路徑
            duration: 錄音時長
            recording_uuid: 錄音 UUID
        """
        try:
            logger.info(f"開始上傳錄音檔案: {filename}")

            url = f"{self.config.server_url}/api/edge-devices/upload_recording"

            # 取得檔案資訊
            file_info = self.audio_manager.get_file_info(filename)

            with open(filename, 'rb') as f:
                files = {'file': f}
                data = {
                    'duration': duration,
                    'device_id': self.config.device_id,
                    'file_size': file_info.get('file_size', 0),
                    'file_hash': file_info.get('file_hash', ''),
                    'recording_uuid': recording_uuid or ''
                }

                response = requests.post(url, files=files, data=data, timeout=60)

            if response.status_code == 200:
                logger.info("上傳完成且伺服器驗證通過")
            else:
                logger.error(f"上傳失敗: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            logger.error("上傳逾時")
        except requests.exceptions.RequestException as e:
            logger.error(f"上傳失敗: {e}")
        except Exception as e:
            logger.error(f"上傳錄音時發生錯誤: {e}", exc_info=True)

    def connect(self):
        """連線至伺服器"""
        retry_delay = self.config.reconnect_delay
        max_delay = self.config.max_reconnect_delay

        while True:
            try:
                # 確保先斷開舊連線
                if self.sio.connected:
                    logger.debug("發現舊連線存在，先斷開...")
                    try:
                        self.sio.disconnect()
                        time.sleep(0.5)
                    except Exception:
                        pass

                logger.info(f"嘗試連線至伺服器: {self.config.server_url}")
                self.sio.connect(self.config.server_url, wait_timeout=10)
                return  # 連線成功

            except socketio.exceptions.ConnectionError as e:
                error_str = str(e)
                if "Already connected" in error_str:
                    # 強制重建連線
                    logger.warning("偵測到殘留連線，強制重建...")
                    try:
                        self.sio.disconnect()
                        time.sleep(1)
                    except Exception:
                        pass
                else:
                    logger.error(f"連線錯誤: {e}")
                    self.status = 'OFFLINE'
                    logger.info(f"等待 {retry_delay} 秒後重試...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

            except Exception as e:
                logger.error(f"連線時發生意外錯誤: {e}")
                time.sleep(retry_delay)

    def run(self):
        """執行客戶端主迴圈"""
        while True:
            try:
                self.connect()

                # 改用主動監控取代 sio.wait()，以便更及時檢測斷線
                while True:
                    time.sleep(5)  # 每 5 秒檢查一次連線狀態

                    # 檢查 SocketIO 實際連線狀態
                    if not self.sio.connected:
                        logger.warning("檢測到 SocketIO 已斷線")
                        break

                    # 檢查內部連線狀態（可能被心跳執行緒設為 False）
                    if not self._connected:
                        logger.warning("內部連線狀態顯示已斷線")
                        break

            except KeyboardInterrupt:
                logger.info("收到中斷訊號，正在關閉...")
                break

            except Exception as e:
                logger.error(f"主迴圈發生錯誤: {e}", exc_info=True)

            # 確保清理狀態
            self._connected = False
            self._stop_heartbeat()

            # 確保 SocketIO 也斷開，避免 "Already connected" 錯誤
            if self.sio.connected:
                try:
                    self.sio.disconnect()
                    logger.debug("已主動斷開 SocketIO 連線")
                except Exception as e:
                    logger.debug(f"斷開 SocketIO 時發生錯誤（可忽略）: {e}")

            logger.info("與伺服器斷開連線，準備重新連線...")
            time.sleep(self.config.reconnect_delay)

    def close(self):
        """關閉客戶端"""
        self._stop_heartbeat()
        if self.sio.connected:
            self.sio.disconnect()
        logger.info("邊緣客戶端已關閉")


def main():
    """主程式進入點"""
    # 取得配置檔案路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'device_config.json')

    # 建立並執行客戶端
    client = EdgeClient(config_path)

    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("程式被使用者中斷")
    finally:
        client.close()


if __name__ == "__main__":
    main()
