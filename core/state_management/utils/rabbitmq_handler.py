"""
RabbitMQ 發布工具
負責建立連線、宣告交換器/佇列並發布任務
"""
import json
import logging
from threading import Lock
from typing import Dict, Any, Optional

import pika

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """RabbitMQ 任務發布器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._lock = Lock()

    def _connect(self):
        """建立連線並準備交換器/佇列"""
        credentials = pika.PlainCredentials(
            self.config['username'],
            self.config['password']
        )

        parameters = pika.ConnectionParameters(
            host=self.config['host'],
            port=self.config['port'],
            virtual_host=self.config.get('virtual_host', '/'),
            credentials=credentials,
            heartbeat=self.config.get('heartbeat', 600),
            blocked_connection_timeout=self.config.get('blocked_timeout', 300)
        )

        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        self._setup_infrastructure()

    def _setup_infrastructure(self):
        """確保交換器與佇列存在"""
        exchange = self.config.get('exchange')
        queue = self.config.get('queue')
        binding_key = self.config.get('routing_key_binding', 'analysis.#')

        if not queue:
            raise ValueError("RabbitMQ queue 名稱未設定")

        queue_arguments = {}
        message_ttl = self.config.get('message_ttl_ms')
        if message_ttl:
            queue_arguments['x-message-ttl'] = message_ttl

        if exchange:
            self._channel.exchange_declare(
                exchange=exchange,
                exchange_type='topic',
                durable=True
            )

        self._channel.queue_declare(
            queue=queue,
            durable=True,
            arguments=queue_arguments or None
        )

        if exchange and binding_key:
            self._channel.queue_bind(
                queue=queue,
                exchange=exchange,
                routing_key=binding_key
            )

    def _ensure_channel(self):
        """確保連線與 channel 可用"""
        if (
            self._connection is None
            or self._connection.is_closed
            or self._channel is None
            or self._channel.is_closed
        ):
            self._connect()

    def publish_task(
        self,
        task_data: Dict[str, Any],
        routing_key: str
    ) -> bool:
        """發布任務到 RabbitMQ"""
        try:
            with self._lock:
                self._ensure_channel()

                properties = pika.BasicProperties(
                    delivery_mode=2,  # 持久化
                    content_type='application/json'
                )

                body = json.dumps(task_data, default=str)
                exchange = self.config.get('exchange', '')

                self._channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=properties,
                    mandatory=False
                )

            logger.info(
                f"RabbitMQ 已發布任務: {task_data.get('task_id', 'unknown')} "
                f"(routing_key={routing_key})"
            )
            return True

        except Exception as e:
            logger.error(f"RabbitMQ 發布任務失敗: {e}", exc_info=True)
            self._reset()
            return False

    def _reset(self):
        """關閉連線以便下次重連"""
        try:
            if self._channel and not self._channel.is_closed:
                self._channel.close()
        except Exception:
            pass

        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
        except Exception:
            pass

        self._channel = None
        self._connection = None

    def close(self):
        """主動關閉連線"""
        self._reset()
