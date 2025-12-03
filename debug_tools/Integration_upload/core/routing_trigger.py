"""
路由規則觸發器
上傳完成後自動觸發狀態管理系統的任務派送 API
"""
import time
import logging
from typing import List, Dict, Any, Optional
import requests


class RoutingTrigger:
    """路由規則觸發器"""

    def __init__(
        self,
        state_management_url: str,
        router_ids: List[str],
        sequential: bool = True,
        retry_attempts: int = 3,
        retry_delay: int = 2,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化觸發器

        Args:
            state_management_url: 狀態管理系統 URL
            router_ids: router ID 列表
            sequential: 是否依序執行
            retry_attempts: 重試次數
            retry_delay: 重試延遲（秒）
            logger: 日誌記錄器
        """
        self.state_management_url = state_management_url.rstrip('/')
        self.router_ids = router_ids
        self.sequential = sequential
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)

        self.trigger_endpoint = f"{self.state_management_url}/api/routing/trigger"

        # 統計
        self.stats = {
            'total_triggered': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }

    def trigger(self, analyze_uuid: str) -> bool:
        """
        觸發單個任務

        Args:
            analyze_uuid: 分析資料的 UUID

        Returns:
            是否成功
        """
        if not self.router_ids:
            self.logger.warning(f"未設定 router_ids，跳過觸發: {analyze_uuid}")
            self.stats['skipped'] += 1
            return False

        self.stats['total_triggered'] += 1

        payload = {
            'analyze_uuid': analyze_uuid,
            'router_ids': self.router_ids,
            'sequential': self.sequential
        }

        for attempt in range(1, self.retry_attempts + 1):
            try:
                self.logger.debug(
                    f"觸發任務 ({attempt}/{self.retry_attempts}): "
                    f"{analyze_uuid} -> {self.router_ids}"
                )

                response = requests.post(
                    self.trigger_endpoint,
                    json=payload,
                    timeout=10
                )

                if response.status_code in [200, 201]:
                    result = response.json()
                    if result.get('success'):
                        self.logger.info(
                            f"✓ 任務觸發成功: {analyze_uuid} "
                            f"(創建 {result.get('data', {}).get('task_count', 0)} 個任務)"
                        )
                        self.stats['success'] += 1
                        return True
                    else:
                        self.logger.error(
                            f"任務觸發失敗: {analyze_uuid} - "
                            f"{result.get('error', '未知錯誤')}"
                        )
                else:
                    self.logger.error(
                        f"API 請求失敗 ({response.status_code}): "
                        f"{analyze_uuid} - {response.text}"
                    )

            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"觸發超時 (嘗試 {attempt}/{self.retry_attempts}): {analyze_uuid}"
                )
            except requests.exceptions.ConnectionError:
                self.logger.error(
                    f"無法連接到狀態管理系統: {self.state_management_url}"
                )
                break  # 連線錯誤不重試
            except Exception as e:
                self.logger.error(
                    f"觸發異常 (嘗試 {attempt}/{self.retry_attempts}): "
                    f"{analyze_uuid} - {e}"
                )

            # 如果不是最後一次嘗試，等待後重試
            if attempt < self.retry_attempts:
                time.sleep(self.retry_delay)

        # 所有嘗試失敗
        self.logger.error(f"✗ 任務觸發失敗（已用盡 {self.retry_attempts} 次嘗試）: {analyze_uuid}")
        self.stats['failed'] += 1
        return False

    def trigger_batch(self, analyze_uuids: List[str]) -> Dict[str, Any]:
        """
        批次觸發多個任務

        Args:
            analyze_uuids: UUID 列表

        Returns:
            統計結果
        """
        self.logger.info(f"開始批次觸發 {len(analyze_uuids)} 個任務...")

        for uuid in analyze_uuids:
            self.trigger(uuid)

        self.logger.info(
            f"批次觸發完成: 成功 {self.stats['success']}, "
            f"失敗 {self.stats['failed']}, "
            f"跳過 {self.stats['skipped']}"
        )

        return self.get_stats()

    def get_stats(self) -> Dict[str, int]:
        """獲取統計資訊"""
        return self.stats.copy()

    def reset_stats(self):
        """重置統計"""
        self.stats = {
            'total_triggered': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
