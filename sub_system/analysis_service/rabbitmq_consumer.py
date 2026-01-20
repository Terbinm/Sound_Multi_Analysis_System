"""
RabbitMQ 任務消費者
從 RabbitMQ 消費分析任務並執行
"""
import logging
import json
import pika
from typing import Optional, Callable
from threading import Thread, Lock
import time

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """RabbitMQ 消費者類"""

    def __init__(self, config: dict, callback: Callable):
        """
        初始化

        Args:
            config: RabbitMQ 配置
            callback: 任務處理回調函數，接收 (task_data) -> bool
        """
        self.config = config
        self.callback = callback
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._consumer_tag: Optional[str] = None
        self.running = False
        self._lock = Lock()

    def connect(self, max_retries: int = None, retry_delay: int = None):
        """
        建立連接（含重試機制）

        Args:
            max_retries: 最大重試次數，預設從配置讀取
            retry_delay: 重試延遲（秒），預設從配置讀取

        Returns:
            bool: 連接是否成功
        """
        max_retries = max_retries or self.config.get('max_connect_retries', 10)
        retry_delay = retry_delay or self.config.get('connect_retry_delay', 5)
        max_retry_delay = self.config.get('max_retry_delay', 60)

        for attempt in range(max_retries):
            try:
                # 連接參數
                credentials = pika.PlainCredentials(
                    self.config['username'],
                    self.config['password']
                )

                parameters = pika.ConnectionParameters(
                    host=self.config['host'],
                    port=self.config['port'],
                    virtual_host=self.config.get('virtual_host', '/'),
                    credentials=credentials,
                    heartbeat=self.config.get('heartbeat', 60),
                    blocked_connection_timeout=self.config.get('blocked_connection_timeout', 300),
                    connection_attempts=3,
                    retry_delay=2,
                    socket_timeout=self.config.get('connection_timeout', 10)
                )

                # 建立連接
                self._connection = pika.BlockingConnection(parameters)
                self._channel = self._connection.channel()

                # 確保 exchange / queue 存在
                self._setup_infrastructure()

                # 設置 QoS (每次只處理一個任務)
                self._channel.basic_qos(
                    prefetch_count=self.config.get('prefetch_count', 1)
                )

                logger.info(f"RabbitMQ 連接成功: {self.config['host']}:{self.config['port']}")
                return True

            except pika.exceptions.AMQPConnectionError as e:
                # 連接錯誤，可重試
                if attempt < max_retries - 1:
                    current_delay = min(retry_delay * (2 ** attempt), max_retry_delay)
                    logger.warning(
                        f"RabbitMQ 連接失敗 (嘗試 {attempt + 1}/{max_retries}): {e}. "
                        f"等待 {current_delay} 秒後重試..."
                    )
                    time.sleep(current_delay)
                else:
                    logger.error(f"RabbitMQ 連接失敗，已達最大重試次數: {e}")
                    return False

            except pika.exceptions.AuthenticationError as e:
                # 認證錯誤，不重試
                logger.error(f"RabbitMQ 認證失敗: {e}")
                return False

            except Exception as e:
                logger.error(
                    f"RabbitMQ 連接發生未預期錯誤 (嘗試 {attempt + 1}/{max_retries}): {e}",
                    exc_info=True
                )
                if attempt < max_retries - 1:
                    current_delay = min(retry_delay * (2 ** attempt), max_retry_delay)
                    logger.info(f"等待 {current_delay} 秒後重試...")
                    time.sleep(current_delay)
                else:
                    return False

        return False

    def _setup_infrastructure(self):
        """確保 exchange、queue、綁定存在"""
        try:
            exchange = self.config.get('exchange')
            queue = self.config.get('queue')
            routing_key = self.config.get('routing_key')

            if not queue:
                raise ValueError("RabbitMQ queue 名稱未設定")

            if exchange:
                self._channel.exchange_declare(
                    exchange=exchange,
                    exchange_type='topic',
                    durable=True
                )

            queue_arguments = {}
            message_ttl = self.config.get('message_ttl_ms')
            if message_ttl:
                queue_arguments['x-message-ttl'] = message_ttl

            self._channel.queue_declare(
                queue=queue,
                durable=True,
                arguments=queue_arguments or None
            )

            if exchange and routing_key:
                self._channel.queue_bind(
                    queue=queue,
                    exchange=exchange,
                    routing_key=routing_key
                )

            logger.info(f"RabbitMQ 队列已就緒: exchange={exchange}, queue={queue}")

        except Exception as e:
            logger.error(f"初始化 RabbitMQ 隊列失敗: {e}")
            raise

    def start_consuming(self):
        """開始消費任務"""
        try:
            if not self._channel:
                if not self.connect():
                    return False

            logger.info(f"開始消費任務: {self.config['queue']}")
            self.running = True

            # 註冊消費者
            self._consumer_tag = self._channel.basic_consume(
                queue=self.config['queue'],
                on_message_callback=self._on_message,
                auto_ack=False
            )

            # 開始消費（阻塞）
            try:
                self._channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("收到停止信號，停止消費")
                self.stop_consuming()

            return True

        except Exception as e:
            logger.error(f"開始消費任務失敗: {e}", exc_info=True)
            return False

    def stop_consuming(self):
        """停止消費任務"""
        try:
            logger.info("停止消費任務...")
            self.running = False

            if self._channel and self._consumer_tag:
                self._channel.basic_cancel(self._consumer_tag)
                self._channel.stop_consuming()

            if self._connection and not self._connection.is_closed:
                self._connection.close()

            logger.info("已停止消費任務")

        except Exception as e:
            logger.error(f"停止消費任務失敗: {e}")

    def _on_message(self, channel, method, properties, body):
        """處理接收到的消息"""
        task_data = None

        try:
            # 解析任務數據
            task_data = json.loads(body)
            task_id = task_data.get('task_id', 'unknown')

            logger.info(f"收到任務: {task_id}")
            logger.debug(f"任務內容: {task_data}")

            # 執行任務（通過回調）
            success = self.callback(task_data)

            if success:
                # 確認消息
                channel.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"任務完成: {task_id}")
            else:
                # 拒絕消息，重新入隊
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True
                )
                logger.error(f"任務失敗，重新入隊: {task_id}")

        except json.JSONDecodeError as e:
            logger.error(f"解析任務數據失敗: {e}")
            # 拒絕無效消息，不重新入隊
            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=False
            )

        except Exception as e:
            logger.error(f"處理任務失敗: {e}", exc_info=True)

            # 檢查重試次數
            retry_count = task_data.get('retry_count', 0) if task_data else 0
            max_retries = self.config.get('max_retries', 3)

            if retry_count < max_retries:
                # 重新入隊
                logger.info(f"任務重試 ({retry_count + 1}/{max_retries})")
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True
                )
            else:
                # 超過重試次數，拒絕消息
                logger.error(f"任務超過最大重試次數，丟棄")
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=False
                )

    def start_in_thread(self) -> Thread:
        """在新線程中啟動消費者"""
        thread = Thread(
            target=self.start_consuming,
            daemon=True,
            name='RabbitMQConsumer'
        )
        thread.start()
        return thread


class RetryableConsumer:
    """支持自動重連的消費者"""

    def __init__(self, config: dict, callback: Callable):
        """初始化"""
        self.config = config
        self.callback = callback
        self.consumer: Optional[RabbitMQConsumer] = None
        self.running = False

    def start(self):
        """啟動消費者（支持自動重連）"""
        self.running = True
        retry_delay = self.config.get('connect_retry_delay', 5)
        max_retry_delay = self.config.get('max_retry_delay', 60)

        while self.running:
            try:
                logger.info("啟動 RabbitMQ 消費者...")

                # 創建消費者
                self.consumer = RabbitMQConsumer(self.config, self.callback)

                # 嘗試連接（connect() 已包含重試機制）
                if self.consumer.connect():
                    # 連接成功後重置重試延遲
                    retry_delay = self.config.get('connect_retry_delay', 5)
                    # 開始消費
                    self.consumer.start_consuming()
                else:
                    raise Exception("無法建立 RabbitMQ 連接")

                # 如果正常退出，跳出循環
                if not self.running:
                    break

            except KeyboardInterrupt:
                logger.info("收到停止信號")
                self.stop()
                break

            except Exception as e:
                logger.error(f"消費者異常退出: {e}", exc_info=True)

                if self.running:
                    logger.info(f"等待 {retry_delay} 秒後重試...")
                    time.sleep(retry_delay)

                    # 指數退避
                    retry_delay = min(retry_delay * 2, max_retry_delay)

    def stop(self):
        """停止消費者"""
        logger.info("停止消費者...")
        self.running = False

        if self.consumer:
            self.consumer.stop_consuming()

    def start_in_thread(self) -> Thread:
        """在新線程中啟動"""
        thread = Thread(
            target=self.start,
            daemon=True,
            name='RetryableConsumer'
        )
        thread.start()
        return thread
