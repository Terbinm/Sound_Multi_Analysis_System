"""
Mock RabbitMQ classes for testing

Provides comprehensive mocking of pika classes including:
- BlockingConnection
- Channel
- Message handling
- Basic properties
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class MockBasicProperties:
    """Mock pika.BasicProperties"""
    content_type: Optional[str] = None
    content_encoding: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    delivery_mode: Optional[int] = None  # 1=transient, 2=persistent
    priority: Optional[int] = None
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    expiration: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: Optional[int] = None
    type: Optional[str] = None
    user_id: Optional[str] = None
    app_id: Optional[str] = None
    cluster_id: Optional[str] = None


@dataclass
class MockDeliveryInfo:
    """Mock delivery info for message consumption"""
    consumer_tag: str = ''
    delivery_tag: int = 0
    redelivered: bool = False
    exchange: str = ''
    routing_key: str = ''


@dataclass
class MockMessage:
    """
    Represents a message in the mock queue

    Attributes:
        body: Message body (bytes)
        properties: Message properties
        delivery_info: Delivery information
        timestamp: When message was published
        acknowledged: Whether message has been ACKed
    """
    body: bytes
    properties: MockBasicProperties = field(default_factory=MockBasicProperties)
    delivery_info: MockDeliveryInfo = field(default_factory=MockDeliveryInfo)
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    nacked: bool = False
    requeued: bool = False

    @property
    def routing_key(self) -> str:
        return self.delivery_info.routing_key


class MockQueue:
    """Mock RabbitMQ Queue"""

    def __init__(self, name: str, durable: bool = False, exclusive: bool = False,
                 auto_delete: bool = False, arguments: Optional[Dict] = None):
        self.name = name
        self.durable = durable
        self.exclusive = exclusive
        self.auto_delete = auto_delete
        self.arguments = arguments or {}
        self._messages: List[MockMessage] = []
        self._consumers: Dict[str, Callable] = {}
        self._delivery_tag_counter = 0
        self._lock = threading.Lock()

    def put(self, message: MockMessage) -> None:
        """Add message to queue"""
        with self._lock:
            self._delivery_tag_counter += 1
            message.delivery_info.delivery_tag = self._delivery_tag_counter
            self._messages.append(message)

    def get(self) -> Optional[MockMessage]:
        """Get message from queue (non-blocking)"""
        with self._lock:
            if self._messages:
                return self._messages.pop(0)
        return None

    def peek(self) -> Optional[MockMessage]:
        """Peek at next message without removing"""
        with self._lock:
            if self._messages:
                return self._messages[0]
        return None

    def message_count(self) -> int:
        """Get number of messages in queue"""
        with self._lock:
            return len(self._messages)

    def consumer_count(self) -> int:
        """Get number of consumers"""
        return len(self._consumers)

    def add_consumer(self, consumer_tag: str, callback: Callable) -> None:
        """Add a consumer"""
        self._consumers[consumer_tag] = callback

    def remove_consumer(self, consumer_tag: str) -> None:
        """Remove a consumer"""
        self._consumers.pop(consumer_tag, None)

    def clear(self) -> int:
        """Clear all messages"""
        with self._lock:
            count = len(self._messages)
            self._messages.clear()
            return count


class MockExchange:
    """Mock RabbitMQ Exchange"""

    def __init__(self, name: str, exchange_type: str = 'direct',
                 durable: bool = False, auto_delete: bool = False,
                 arguments: Optional[Dict] = None):
        self.name = name
        self.exchange_type = exchange_type
        self.durable = durable
        self.auto_delete = auto_delete
        self.arguments = arguments or {}
        self._bindings: List[Tuple[str, str]] = []  # (queue_name, routing_key)

    def bind(self, queue_name: str, routing_key: str) -> None:
        """Bind queue to exchange"""
        self._bindings.append((queue_name, routing_key))

    def unbind(self, queue_name: str, routing_key: str) -> None:
        """Unbind queue from exchange"""
        try:
            self._bindings.remove((queue_name, routing_key))
        except ValueError:
            pass

    def get_bound_queues(self, routing_key: str) -> List[str]:
        """Get queues bound with routing key (considering exchange type)"""
        bound = []
        for queue_name, bound_key in self._bindings:
            if self.exchange_type == 'fanout':
                bound.append(queue_name)
            elif self.exchange_type == 'direct':
                if bound_key == routing_key:
                    bound.append(queue_name)
            elif self.exchange_type == 'topic':
                if self._match_topic(bound_key, routing_key):
                    bound.append(queue_name)
        return bound

    def _match_topic(self, pattern: str, routing_key: str) -> bool:
        """Match topic pattern against routing key"""
        pattern_parts = pattern.split('.')
        key_parts = routing_key.split('.')

        i = j = 0
        while i < len(pattern_parts) and j < len(key_parts):
            if pattern_parts[i] == '#':
                if i == len(pattern_parts) - 1:
                    return True
                i += 1
                while j < len(key_parts):
                    if self._match_topic('.'.join(pattern_parts[i:]), '.'.join(key_parts[j:])):
                        return True
                    j += 1
                return False
            elif pattern_parts[i] == '*':
                i += 1
                j += 1
            elif pattern_parts[i] == key_parts[j]:
                i += 1
                j += 1
            else:
                return False

        return i == len(pattern_parts) and j == len(key_parts)


class MockChannel:
    """
    Mock RabbitMQ Channel

    Provides:
    - Queue declaration and management
    - Exchange declaration and management
    - Message publishing and consuming
    - Acknowledgement handling
    """

    def __init__(self):
        self._queues: Dict[str, MockQueue] = {}
        self._exchanges: Dict[str, MockExchange] = {}
        self._consumer_callbacks: Dict[str, Tuple[str, Callable]] = {}  # consumer_tag -> (queue, callback)
        self._published_messages: List[MockMessage] = []
        self._prefetch_count = 0
        self._is_open = True
        self._consumer_tag_counter = 0
        self._lock = threading.Lock()

        # Create default exchange
        self._exchanges[''] = MockExchange('', 'direct')

    @property
    def is_open(self) -> bool:
        return self._is_open

    def close(self) -> None:
        """Close the channel"""
        self._is_open = False

    # Queue operations
    def queue_declare(self, queue: str = '', durable: bool = False,
                      exclusive: bool = False, auto_delete: bool = False,
                      arguments: Optional[Dict] = None, passive: bool = False) -> 'MockQueueDeclareOk':
        """Declare a queue"""
        if not queue:
            queue = f'amq.gen-{uuid.uuid4().hex[:20]}'

        with self._lock:
            if queue not in self._queues:
                self._queues[queue] = MockQueue(
                    queue, durable, exclusive, auto_delete, arguments
                )

        return MockQueueDeclareOk(queue, self._queues[queue].message_count(), 0)

    def queue_bind(self, queue: str, exchange: str, routing_key: str = '',
                   arguments: Optional[Dict] = None) -> None:
        """Bind queue to exchange"""
        if exchange in self._exchanges:
            self._exchanges[exchange].bind(queue, routing_key)

    def queue_unbind(self, queue: str, exchange: str, routing_key: str = '',
                     arguments: Optional[Dict] = None) -> None:
        """Unbind queue from exchange"""
        if exchange in self._exchanges:
            self._exchanges[exchange].unbind(queue, routing_key)

    def queue_purge(self, queue: str) -> 'MockQueuePurgeOk':
        """Purge queue"""
        with self._lock:
            if queue in self._queues:
                count = self._queues[queue].clear()
                return MockQueuePurgeOk(count)
        return MockQueuePurgeOk(0)

    def queue_delete(self, queue: str, if_unused: bool = False,
                     if_empty: bool = False) -> 'MockQueueDeleteOk':
        """Delete queue"""
        with self._lock:
            if queue in self._queues:
                count = self._queues[queue].message_count()
                del self._queues[queue]
                return MockQueueDeleteOk(count)
        return MockQueueDeleteOk(0)

    # Exchange operations
    def exchange_declare(self, exchange: str, exchange_type: str = 'direct',
                         durable: bool = False, auto_delete: bool = False,
                         arguments: Optional[Dict] = None, passive: bool = False) -> None:
        """Declare an exchange"""
        with self._lock:
            if exchange not in self._exchanges:
                self._exchanges[exchange] = MockExchange(
                    exchange, exchange_type, durable, auto_delete, arguments
                )

    def exchange_delete(self, exchange: str, if_unused: bool = False) -> None:
        """Delete exchange"""
        with self._lock:
            self._exchanges.pop(exchange, None)

    # Publishing
    def basic_publish(self, exchange: str, routing_key: str, body: bytes,
                      properties: Optional[MockBasicProperties] = None,
                      mandatory: bool = False) -> None:
        """Publish a message"""
        properties = properties or MockBasicProperties()

        message = MockMessage(
            body=body,
            properties=properties,
            delivery_info=MockDeliveryInfo(
                exchange=exchange,
                routing_key=routing_key,
            )
        )

        self._published_messages.append(message)

        # Route message to queues
        target_exchange = self._exchanges.get(exchange, self._exchanges.get(''))
        if target_exchange:
            queue_names = target_exchange.get_bound_queues(routing_key)
            for queue_name in queue_names:
                if queue_name in self._queues:
                    self._queues[queue_name].put(message)

        # Direct queue publish (empty exchange)
        if not exchange and routing_key in self._queues:
            self._queues[routing_key].put(message)

    # Consuming
    def basic_consume(self, queue: str, on_message_callback: Callable,
                      auto_ack: bool = False, exclusive: bool = False,
                      consumer_tag: str = '', arguments: Optional[Dict] = None) -> str:
        """Start consuming from queue"""
        if not consumer_tag:
            self._consumer_tag_counter += 1
            consumer_tag = f'ctag-{self._consumer_tag_counter}'

        self._consumer_callbacks[consumer_tag] = (queue, on_message_callback)

        if queue in self._queues:
            self._queues[queue].add_consumer(consumer_tag, on_message_callback)

        return consumer_tag

    def basic_cancel(self, consumer_tag: str) -> None:
        """Cancel consumer"""
        if consumer_tag in self._consumer_callbacks:
            queue_name, _ = self._consumer_callbacks.pop(consumer_tag)
            if queue_name in self._queues:
                self._queues[queue_name].remove_consumer(consumer_tag)

    def basic_get(self, queue: str, auto_ack: bool = False) -> Optional[Tuple[MockDeliveryInfo, MockBasicProperties, bytes]]:
        """Get a message from queue"""
        with self._lock:
            if queue in self._queues:
                message = self._queues[queue].get()
                if message:
                    return (message.delivery_info, message.properties, message.body)
        return None

    def basic_ack(self, delivery_tag: int, multiple: bool = False) -> None:
        """Acknowledge message"""
        # In real implementation, this would mark message as acknowledged
        pass

    def basic_nack(self, delivery_tag: int, multiple: bool = False,
                   requeue: bool = True) -> None:
        """Negative acknowledge message"""
        pass

    def basic_reject(self, delivery_tag: int, requeue: bool = True) -> None:
        """Reject message"""
        pass

    def basic_qos(self, prefetch_size: int = 0, prefetch_count: int = 0,
                  global_qos: bool = False) -> None:
        """Set QoS parameters"""
        self._prefetch_count = prefetch_count

    # Transaction support
    def tx_select(self) -> None:
        """Enable transactions"""
        pass

    def tx_commit(self) -> None:
        """Commit transaction"""
        pass

    def tx_rollback(self) -> None:
        """Rollback transaction"""
        pass

    # Confirm mode
    def confirm_delivery(self) -> None:
        """Enable publisher confirms"""
        pass

    # Testing helpers
    def get_published_messages(self) -> List[MockMessage]:
        """Get all published messages (for testing)"""
        return self._published_messages[:]

    def clear_published_messages(self) -> None:
        """Clear published messages (for testing)"""
        self._published_messages.clear()

    def get_queue(self, queue_name: str) -> Optional[MockQueue]:
        """Get queue by name (for testing)"""
        return self._queues.get(queue_name)

    def deliver_messages(self, queue: str, max_messages: int = -1) -> int:
        """Deliver messages to consumers (for testing)"""
        if queue not in self._queues:
            return 0

        delivered = 0
        mock_queue = self._queues[queue]

        while True:
            if max_messages >= 0 and delivered >= max_messages:
                break

            message = mock_queue.get()
            if not message:
                break

            # Find consumer and deliver
            for consumer_tag, (q_name, callback) in self._consumer_callbacks.items():
                if q_name == queue:
                    callback(self, message.delivery_info, message.properties, message.body)
                    delivered += 1
                    break

        return delivered


@dataclass
class MockQueueDeclareOk:
    """Result of queue_declare"""
    queue: str = ''
    message_count: int = 0
    consumer_count: int = 0

    @property
    def method(self):
        return self


@dataclass
class MockQueuePurgeOk:
    """Result of queue_purge"""
    message_count: int = 0


@dataclass
class MockQueueDeleteOk:
    """Result of queue_delete"""
    message_count: int = 0


class MockConnection:
    """
    Mock RabbitMQ BlockingConnection

    Provides:
    - Channel creation
    - Connection state management
    - Process data events (for testing)
    """

    def __init__(self, channel: Optional[MockChannel] = None):
        self._channel = channel or MockChannel()
        self._is_open = True
        self._channels: List[MockChannel] = [self._channel]

    @property
    def is_open(self) -> bool:
        return self._is_open

    def channel(self) -> MockChannel:
        """Create a channel"""
        new_channel = MockChannel()
        self._channels.append(new_channel)
        return new_channel

    def close(self) -> None:
        """Close connection"""
        self._is_open = False
        for ch in self._channels:
            ch.close()

    def process_data_events(self, time_limit: float = 0) -> None:
        """Process data events (for testing)"""
        # In real implementation, this would process network I/O
        time.sleep(min(time_limit, 0.1) if time_limit else 0.01)

    def sleep(self, duration: float) -> None:
        """Sleep while processing events"""
        time.sleep(duration)

    # Testing helpers
    def get_primary_channel(self) -> MockChannel:
        """Get primary channel (for testing)"""
        return self._channel


class MockConnectionParameters:
    """Mock pika.ConnectionParameters"""

    def __init__(self, host: str = 'localhost', port: int = 5672,
                 virtual_host: str = '/', credentials: Any = None,
                 heartbeat: int = 600, blocked_connection_timeout: float = 300,
                 **kwargs):
        self.host = host
        self.port = port
        self.virtual_host = virtual_host
        self.credentials = credentials
        self.heartbeat = heartbeat
        self.blocked_connection_timeout = blocked_connection_timeout


class MockPlainCredentials:
    """Mock pika.PlainCredentials"""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
