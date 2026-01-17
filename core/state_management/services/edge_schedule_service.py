"""
邊緣設備排程服務

使用 APScheduler 管理邊緣設備的排程錄音任務
"""
import logging
import uuid
from datetime import datetime, time
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

from models.edge_device import EdgeDevice
from config import get_config

logger = logging.getLogger(__name__)


class EdgeScheduleService:
    """邊緣設備排程服務"""

    def __init__(self):
        """初始化排程服務"""
        self.scheduler: Optional[BackgroundScheduler] = None
        self.edge_device_manager = None  # 延遲注入
        self._active_jobs: Dict[str, str] = {}  # device_id -> job_id
        logger.info("邊緣設備排程服務初始化")

    def init(self, edge_device_manager):
        """
        初始化排程服務

        Args:
            edge_device_manager: EdgeDeviceManager instance
        """
        self.edge_device_manager = edge_device_manager

        # 建立排程器
        self.scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={
                'coalesce': True,  # 合併錯過的任務
                'max_instances': 1  # 每個任務最多同時執行一個instance
            }
        )

        logger.info("邊緣設備排程服務已初始化")

    def start(self):
        """啟動排程服務"""
        if not self.scheduler:
            logger.error("排程器未初始化")
            return

        if self.scheduler.running:
            logger.warning("排程服務已在運行中")
            return

        # 載入所有已啟用排程的設備
        self._load_all_schedules()

        # 啟動排程器
        self.scheduler.start()
        logger.info("邊緣設備排程服務已啟動")

    def stop(self):
        """停止排程服務"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("邊緣設備排程服務已停止")

    def _load_all_schedules(self):
        """載入所有已啟用排程的設備"""
        try:
            devices = EdgeDevice.get_all()

            for device in devices:
                schedule_config = device.get('schedule_config', {})
                if schedule_config.get('enabled'):
                    self.add_device_schedule(
                        device_id=device.get('device_id'),
                        interval_seconds=schedule_config.get('interval_seconds', 3600),
                        duration_seconds=schedule_config.get('duration_seconds', 60),
                        start_time=schedule_config.get('start_time'),
                        end_time=schedule_config.get('end_time')
                    )

            logger.info(f"已載入 {len(self._active_jobs)} 個設備排程")

        except Exception as e:
            logger.error(f"載入設備排程失敗: {e}", exc_info=True)

    def add_device_schedule(
        self,
        device_id: str,
        interval_seconds: int = 3600,
        duration_seconds: int = 60,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> bool:
        """
        新增設備排程

        Args:
            device_id: 設備 ID
            interval_seconds: 間隔秒數
            duration_seconds: 錄音時長（秒）
            start_time: 每日開始時間（HH:MM 格式）
            end_time: 每日結束時間（HH:MM 格式）

        Returns:
            是否成功
        """
        if not self.scheduler:
            logger.error("排程器未初始化")
            return False

        try:
            # 移除現有的排程（若存在）
            self.remove_device_schedule(device_id)

            job_id = f"edge_recording_{device_id}"

            # 建立排程任務
            self.scheduler.add_job(
                func=self._trigger_recording,
                trigger=IntervalTrigger(seconds=interval_seconds),
                id=job_id,
                args=[device_id, duration_seconds, start_time, end_time],
                name=f"Edge Recording - {device_id}",
                replace_existing=True
            )

            self._active_jobs[device_id] = job_id
            logger.info(f"已新增設備 {device_id} 的排程: 每 {interval_seconds} 秒錄音 {duration_seconds} 秒")

            return True

        except Exception as e:
            logger.error(f"新增設備排程失敗 ({device_id}): {e}", exc_info=True)
            return False

    def remove_device_schedule(self, device_id: str) -> bool:
        """
        移除設備排程

        Args:
            device_id: 設備 ID

        Returns:
            是否成功
        """
        if not self.scheduler:
            return False

        try:
            job_id = self._active_jobs.get(device_id)
            if job_id:
                try:
                    self.scheduler.remove_job(job_id)
                except JobLookupError:
                    pass  # 任務已不存在

                del self._active_jobs[device_id]
                logger.info(f"已移除設備 {device_id} 的排程")

            return True

        except Exception as e:
            logger.error(f"移除設備排程失敗 ({device_id}): {e}", exc_info=True)
            return False

    def update_device_schedule(
        self,
        device_id: str,
        interval_seconds: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> bool:
        """
        更新設備排程

        Args:
            device_id: 設備 ID
            interval_seconds: 間隔秒數（可選）
            duration_seconds: 錄音時長（可選）
            start_time: 每日開始時間（可選）
            end_time: 每日結束時間（可選）

        Returns:
            是否成功
        """
        try:
            # 獲取設備當前配置
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return False

            schedule_config = device.get('schedule_config', {})

            # 使用新值或保留舊值
            new_interval = interval_seconds if interval_seconds is not None else schedule_config.get('interval_seconds', 3600)
            new_duration = duration_seconds if duration_seconds is not None else schedule_config.get('duration_seconds', 60)
            new_start = start_time if start_time is not None else schedule_config.get('start_time')
            new_end = end_time if end_time is not None else schedule_config.get('end_time')

            # 重新建立排程
            return self.add_device_schedule(
                device_id=device_id,
                interval_seconds=new_interval,
                duration_seconds=new_duration,
                start_time=new_start,
                end_time=new_end
            )

        except Exception as e:
            logger.error(f"更新設備排程失敗 ({device_id}): {e}", exc_info=True)
            return False

    def _trigger_recording(
        self,
        device_id: str,
        duration_seconds: int,
        start_time: Optional[str],
        end_time: Optional[str]
    ):
        """
        觸發錄音

        Args:
            device_id: 設備 ID
            duration_seconds: 錄音時長（秒）
            start_time: 每日開始時間
            end_time: 每日結束時間
        """
        try:
            # 檢查是否在時間範圍內
            if not self._is_within_time_range(start_time, end_time):
                logger.debug(f"設備 {device_id} 不在排程時間範圍內，跳過本次錄音")
                return

            # 檢查設備是否在線
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.warning(f"排程觸發但設備不存在: {device_id}")
                return

            if device.get('status') == 'offline':
                logger.warning(f"排程觸發但設備離線: {device_id}")
                return

            if device.get('status') == 'recording':
                logger.warning(f"排程觸發但設備正在錄音中: {device_id}")
                return

            # 獲取設備音訊配置
            audio_config = device.get('audio_config', {})

            # 錄音參數
            recording_params = {
                'duration': duration_seconds,
                'channels': audio_config.get('channels', 1),
                'sample_rate': audio_config.get('sample_rate', 16000),
                'device_index': audio_config.get('default_device_index', 0),
                'bit_depth': audio_config.get('bit_depth', 16)
            }

            # 生成錄音 UUID
            recording_uuid = str(uuid.uuid4())

            # 發送錄音命令
            if self.edge_device_manager:
                result = self.edge_device_manager.send_record_command(
                    device_id=device_id,
                    duration=duration_seconds,
                    channels=recording_params['channels'],
                    sample_rate=recording_params['sample_rate'],
                    device_index=recording_params['device_index'],
                    bit_depth=recording_params['bit_depth'],
                    recording_uuid=recording_uuid
                )

                if result:
                    logger.info(f"排程錄音已觸發: 設備 {device_id}, recording_uuid: {recording_uuid}")
                else:
                    logger.error(f"排程錄音觸發失敗: 設備 {device_id}")
            else:
                logger.error("EdgeDeviceManager 未注入")

        except Exception as e:
            logger.error(f"排程觸發錄音失敗 ({device_id}): {e}", exc_info=True)

    def _is_within_time_range(
        self,
        start_time: Optional[str],
        end_time: Optional[str]
    ) -> bool:
        """
        檢查當前時間是否在指定範圍內

        Args:
            start_time: 開始時間（HH:MM 格式）
            end_time: 結束時間（HH:MM 格式）

        Returns:
            是否在範圍內
        """
        if not start_time and not end_time:
            return True  # 沒有設定時間限制

        try:
            now = datetime.now().time()

            if start_time:
                start_parts = start_time.split(':')
                start = time(int(start_parts[0]), int(start_parts[1]))
            else:
                start = time(0, 0)

            if end_time:
                end_parts = end_time.split(':')
                end = time(int(end_parts[0]), int(end_parts[1]))
            else:
                end = time(23, 59, 59)

            # 處理跨日情況（如 22:00 - 06:00）
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end

        except Exception as e:
            logger.error(f"解析時間範圍失敗: {e}")
            return True  # 解析失敗時允許執行

    def get_device_schedule_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取設備的排程資訊

        Args:
            device_id: 設備 ID

        Returns:
            排程資訊字典
        """
        try:
            job_id = self._active_jobs.get(device_id)
            if not job_id or not self.scheduler:
                return None

            job = self.scheduler.get_job(job_id)
            if not job:
                return None

            return {
                'device_id': device_id,
                'job_id': job_id,
                'next_run_time': job.next_run_time,
                'is_running': True
            }

        except Exception as e:
            logger.error(f"獲取設備排程資訊失敗 ({device_id}): {e}")
            return None

    def get_all_schedules_info(self) -> Dict[str, Any]:
        """
        獲取所有排程資訊

        Returns:
            所有排程資訊
        """
        schedules = {}
        for device_id, job_id in self._active_jobs.items():
            info = self.get_device_schedule_info(device_id)
            if info:
                schedules[device_id] = info

        return {
            'total_schedules': len(schedules),
            'schedules': schedules
        }

    def trigger_immediate_recording(self, device_id: str) -> Optional[str]:
        """
        立即觸發一次錄音（不等待排程）

        Args:
            device_id: 設備 ID

        Returns:
            錄音 UUID，失敗返回 None
        """
        try:
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return None

            schedule_config = device.get('schedule_config', {})
            duration_seconds = schedule_config.get('duration_seconds', 60)

            # 直接觸發錄音（忽略時間限制）
            audio_config = device.get('audio_config', {})
            recording_params = {
                'duration': duration_seconds,
                'channels': audio_config.get('channels', 1),
                'sample_rate': audio_config.get('sample_rate', 16000),
                'device_index': audio_config.get('default_device_index', 0),
                'bit_depth': audio_config.get('bit_depth', 16)
            }

            # 生成錄音 UUID
            recording_uuid = str(uuid.uuid4())

            if self.edge_device_manager:
                result = self.edge_device_manager.send_record_command(
                    device_id=device_id,
                    duration=duration_seconds,
                    channels=recording_params['channels'],
                    sample_rate=recording_params['sample_rate'],
                    device_index=recording_params['device_index'],
                    bit_depth=recording_params['bit_depth'],
                    recording_uuid=recording_uuid
                )

                if result:
                    return recording_uuid

            return None

        except Exception as e:
            logger.error(f"立即觸發錄音失敗 ({device_id}): {e}", exc_info=True)
            return None


# 全局排程服務instance
edge_schedule_service = EdgeScheduleService()
