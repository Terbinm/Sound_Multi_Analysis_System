"""
RabbitMQ Fixtures for Testing

Provides fixtures for:
- RabbitMQPublisher mocking
- Consumer mocking
- Message handling
"""
import pytest
import json
from typing import Dict, Any, List, Generator, Optional, Callable
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from CI_test.mocks.mock_rabbitmq import (
    MockChannel,
    MockConnection,
    MockMessage,
    MockBasicProperties,
    MockQueue,
)


@pytest.fixture
def mock_rabbitmq_channel() -> MockChannel:
    """
    Create a mock RabbitMQ channel

    Usage:
        def test_publish(mock_rabbitmq_channel):
            mock_rabbitmq_channel.basic_publish('exchange', 'key', b'message')
    """
    return MockChannel()


@pytest.fixture
def mock_rabbitmq_connection(mock_rabbitmq_channel: MockChannel) -> MockConnection:
    """
    Create a mock RabbitMQ connection

    Usage:
        def test_connection(mock_rabbitmq_connection):
            channel = mock_rabbitmq_connection.channel()
    """
    return MockConnection(mock_rabbitmq_channel)


@pytest.fixture
def mock_rabbitmq_publisher(
    mock_rabbitmq_connection: MockConnection
) -> Generator[MagicMock, None, None]:
    """
    Mock RabbitMQPublisher class

    Usage:
        def test_publish_task(mock_rabbitmq_publisher):
            result = mock_rabbitmq_publisher.publish_task({'task': 'data'})
            assert result is True
    """
    publisher = MagicMock()
    publisher._connection = mock_rabbitmq_connection
    publisher._channel = mock_rabbitmq_connection.get_primary_channel()
    publisher._lock = MagicMock()
    publisher._published_messages = []

    def publish_task(task_data: Dict[str, Any], routing_key: str = 'analysis.task') -> bool:
        try:
            body = json.dumps(task_data).encode('utf-8')
            properties = MockBasicProperties(
                delivery_mode=2,  # Persistent
                content_type='application/json',
            )
            publisher._channel.basic_publish(
                exchange='analysis_exchange',
                routing_key=routing_key,
                body=body,
                properties=properties,
            )
            publisher._published_messages.append({
                'task_data': task_data,
                'routing_key': routing_key,
                'timestamp': datetime.now(timezone.utc),
            })
            return True
        except Exception:
            return False

    def close():
        publisher._connection.close()

    def get_published_messages():
        return publisher._published_messages[:]

    publisher.publish_task = publish_task
    publisher.close = close
    publisher.get_published_messages = get_published_messages

    # Patch the actual publisher
    with patch('core.state_management.utils.rabbitmq_handler.RabbitMQPublisher', return_value=publisher):
        yield publisher


@pytest.fixture
def mock_rabbitmq_consumer() -> Generator[MagicMock, None, None]:
    """
    Mock RabbitMQ consumer for analysis service

    Usage:
        def test_consume(mock_rabbitmq_consumer):
            mock_rabbitmq_consumer.register_callback(handler)
            mock_rabbitmq_consumer.start()
    """
    consumer = MagicMock()
    consumer._is_running = False
    consumer._callbacks = []
    consumer._messages = []

    def register_callback(callback: Callable[[Dict[str, Any]], bool]):
        consumer._callbacks.append(callback)

    def start():
        consumer._is_running = True

    def stop():
        consumer._is_running = False

    def is_running():
        return consumer._is_running

    def simulate_message(message_data: Dict[str, Any]) -> bool:
        """Simulate receiving a message (for testing)"""
        consumer._messages.append(message_data)
        for callback in consumer._callbacks:
            try:
                result = callback(message_data)
                if result:
                    return True
            except Exception:
                pass
        return False

    consumer.register_callback = register_callback
    consumer.start = start
    consumer.stop = stop
    consumer.is_running = is_running
    consumer.simulate_message = simulate_message

    yield consumer


@pytest.fixture
def sample_task_messages() -> List[Dict[str, Any]]:
    """
    Sample task messages for testing consumer

    Returns a list of sample analysis task messages
    """
    now = datetime.now(timezone.utc).isoformat()

    return [
        {
            'task_id': 'task-001',
            'recording_id': 'rec-001',
            'analyze_uuid': 'uuid-001',
            'config_id': 'config-001',
            'analysis_method_id': 'audio_classification',
            'mongodb_instance': 'default',
            'priority': 5,
            'created_at': now,
        },
        {
            'task_id': 'task-002',
            'recording_id': 'rec-002',
            'analyze_uuid': 'uuid-002',
            'config_id': 'config-002',
            'analysis_method_id': 'anomaly_detection',
            'mongodb_instance': 'default',
            'priority': 10,
            'created_at': now,
        },
        {
            'task_id': 'task-003',
            'recording_id': 'rec-003',
            'analyze_uuid': 'uuid-003',
            'config_id': 'config-001',
            'analysis_method_id': 'audio_classification',
            'mongodb_instance': 'custom-instance',
            'priority': 3,
            'created_at': now,
        },
    ]


@pytest.fixture
def configured_rabbitmq_channel(mock_rabbitmq_channel: MockChannel) -> MockChannel:
    """
    RabbitMQ channel with pre-configured queues and exchanges

    Sets up the standard analysis queue infrastructure
    """
    # Declare exchanges
    mock_rabbitmq_channel.exchange_declare(
        exchange='analysis_exchange',
        exchange_type='topic',
        durable=True,
    )

    # Declare queues
    mock_rabbitmq_channel.queue_declare(
        queue='analysis_queue',
        durable=True,
    )

    mock_rabbitmq_channel.queue_declare(
        queue='high_priority_queue',
        durable=True,
    )

    # Bind queues
    mock_rabbitmq_channel.queue_bind(
        queue='analysis_queue',
        exchange='analysis_exchange',
        routing_key='analysis.task',
    )

    mock_rabbitmq_channel.queue_bind(
        queue='high_priority_queue',
        exchange='analysis_exchange',
        routing_key='analysis.task.high',
    )

    return mock_rabbitmq_channel


@pytest.fixture
def rabbitmq_with_messages(
    configured_rabbitmq_channel: MockChannel,
    sample_task_messages: List[Dict[str, Any]]
) -> MockChannel:
    """
    RabbitMQ channel with pre-populated messages

    Usage:
        def test_consume_messages(rabbitmq_with_messages):
            # Messages are already in the queue
            result = rabbitmq_with_messages.basic_get('analysis_queue')
    """
    for message in sample_task_messages:
        body = json.dumps(message).encode('utf-8')
        configured_rabbitmq_channel.basic_publish(
            exchange='analysis_exchange',
            routing_key='analysis.task',
            body=body,
            properties=MockBasicProperties(delivery_mode=2),
        )

    return configured_rabbitmq_channel
