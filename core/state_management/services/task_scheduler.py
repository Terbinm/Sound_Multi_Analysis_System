"""
任務調度器（已重構）
原輪詢機制已移除，改為事件驅動模式
任務派送現在透過 API 觸發（參考 utils.task_dispatcher.TaskDispatcher）

保留此類作為服務框架，未來可擴展其他背景任務
"""
import logging
import time
from typing import Dict, Callable, Any
from threading import Thread

from config import get_config

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    任務調度器類（已重構為被動模式）

    注意：
    - 輪詢機制已移除
    - 任務派送改由 TaskDispatcher 透過 API 觸發
    - 此類保留作為未來擴展其他背景服務的框架
    """

    def __init__(self):
        """初始化"""
        self.config = get_config()
        self.running = False
        self.background_tasks: Dict[str, Dict[str, Any]] = {}

        logger.info("TaskScheduler 已初始化（被動模式，無輪詢）")

    def start(self):
        """
        啟動調度器

        注意：由於輪詢機制已移除，此方法僅保持調度器運行狀態
        可用於未來註冊其他背景任務
        """
        try:
            logger.info("啟動任務調度器（被動模式）...")
            self.running = True

            # 檢查是否有註冊的背景任務
            if not self.background_tasks:
                logger.info(
                    "沒有註冊的背景任務。"
                    "任務派送將透過 API (/api/routing/trigger) 觸發。"
                )
            else:
                logger.info(f"已註冊 {len(self.background_tasks)} 個背景任務")
                for task_name in self.background_tasks.keys():
                    logger.info(f"  - {task_name}")

            # 保持運行
            while self.running:
                time.sleep(10)

                # 檢查背景任務狀態
                self._check_background_tasks()

        except KeyboardInterrupt:
            logger.info("任務調度器收到停止信號")
            self.stop()
        except Exception as e:
            logger.error(f"任務調度器錯誤: {e}", exc_info=True)
            self.stop()

    def stop(self):
        """停止調度器"""
        logger.info("停止任務調度器...")
        self.running = False

        # 停止所有背景任務
        for task_name, task_info in self.background_tasks.items():
            thread = task_info.get('thread')
            if thread and thread.is_alive():
                logger.info(f"等待背景任務停止: {task_name}")
                thread.join(timeout=5)

        self.background_tasks.clear()
        logger.info("任務調度器已停止")

    def register_background_task(
        self,
        task_name: str,
        task_func: Callable,
        interval: int = 60,
        args: tuple = (),
        kwargs: dict = None
    ):
        """
        註冊背景任務

        Args:
            task_name: 任務名稱
            task_func: 任務函數
            interval: 執行間隔（秒）
            args: 函數參數
            kwargs: 函數關鍵字參數
        """
        if kwargs is None:
            kwargs = {}

        if task_name in self.background_tasks:
            logger.warning(f"背景任務已存在，將覆蓋: {task_name}")

        def task_wrapper():
            """任務包裝器"""
            logger.info(f"背景任務啟動: {task_name}")
            while self.running:
                try:
                    task_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"背景任務執行失敗 ({task_name}): {e}", exc_info=True)

                time.sleep(interval)

            logger.info(f"背景任務停止: {task_name}")

        # 創建並啟動執行緒
        thread = Thread(
            target=task_wrapper,
            daemon=True,
            name=f"BgTask-{task_name}"
        )

        self.background_tasks[task_name] = {
            'thread': thread,
            'func': task_func,
            'interval': interval,
            'started': False
        }

        # 如果調度器已運行，立即啟動任務
        if self.running:
            thread.start()
            self.background_tasks[task_name]['started'] = True
            logger.info(f"背景任務已啟動: {task_name}")

    def unregister_background_task(self, task_name: str) -> bool:
        """
        移除背景任務

        Args:
            task_name: 任務名稱

        Returns:
            是否成功移除
        """
        if task_name not in self.background_tasks:
            logger.warning(f"背景任務不存在: {task_name}")
            return False

        task_info = self.background_tasks[task_name]
        thread = task_info.get('thread')

        # 等待執行緒停止
        if thread and thread.is_alive():
            logger.info(f"等待背景任務停止: {task_name}")
            thread.join(timeout=5)

        del self.background_tasks[task_name]
        logger.info(f"背景任務已移除: {task_name}")
        return True

    def _check_background_tasks(self):
        """檢查背景任務狀態"""
        for task_name, task_info in list(self.background_tasks.items()):
            thread = task_info.get('thread')

            # 如果執行緒未啟動，啟動它
            if not task_info.get('started', False):
                if not thread.is_alive():
                    thread.start()
                    task_info['started'] = True
                    logger.info(f"背景任務已啟動: {task_name}")

            # 如果執行緒已停止，記錄警告
            elif not thread.is_alive():
                logger.warning(f"背景任務已停止: {task_name}")


# 遺留兼容性支援（避免現有代碼報錯）
def publish_task(*args, **kwargs):
    """
    遺留函數：RabbitMQ 已移除，此函數僅保留以避免舊代碼導致崩潰。
    """
    logger.warning(
        "TaskScheduler.publish_task 已廢棄，RabbitMQ 已移除；請使用 TaskDispatcher 取得任務資訊。"
    )
    return False
