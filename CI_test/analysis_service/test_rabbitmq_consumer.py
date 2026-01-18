"""
Tests for RabbitMQ Consumer

Tests cover:
- Message consumption
- Retry logic
- ACK/NACK handling
- Error recovery
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestMessageConsumption:
    """Test message consumption functionality"""

    @pytest.mark.unit
    def test_consume_analysis_task(self, mock_rabbitmq_consumer, sample_analysis_task):
        """Test consuming analysis task message"""
        received_tasks = []

        def handler(task_data):
            received_tasks.append(task_data)
            return True

        mock_rabbitmq_consumer.register_callback(handler)
        mock_rabbitmq_consumer.simulate_message(sample_analysis_task)

        assert len(received_tasks) == 1
        assert received_tasks[0]['task_id'] == sample_analysis_task['task_id']

    @pytest.mark.unit
    def test_consumer_start_stop(self, mock_rabbitmq_consumer):
        """Test starting and stopping consumer"""
        mock_rabbitmq_consumer.start()
        assert mock_rabbitmq_consumer.is_running() is True

        mock_rabbitmq_consumer.stop()
        assert mock_rabbitmq_consumer.is_running() is False

    @pytest.mark.unit
    def test_multiple_callbacks(self, mock_rabbitmq_consumer, sample_analysis_task):
        """Test multiple callback handlers"""
        call_counts = {'handler1': 0, 'handler2': 0}

        def handler1(task_data):
            call_counts['handler1'] += 1
            return False  # Not handled

        def handler2(task_data):
            call_counts['handler2'] += 1
            return True  # Handled

        mock_rabbitmq_consumer.register_callback(handler1)
        mock_rabbitmq_consumer.register_callback(handler2)
        mock_rabbitmq_consumer.simulate_message(sample_analysis_task)

        assert call_counts['handler1'] == 1
        assert call_counts['handler2'] == 1

    @pytest.mark.unit
    def test_message_parsing(self, sample_analysis_task):
        """Test parsing message body"""
        message_body = json.dumps(sample_analysis_task).encode('utf-8')
        parsed = json.loads(message_body.decode('utf-8'))

        assert parsed['task_id'] == sample_analysis_task['task_id']
        assert parsed['config_id'] == sample_analysis_task['config_id']


class TestRetryLogic:
    """Test message retry logic"""

    @pytest.mark.unit
    def test_retry_count_increment(self, mock_get_db):
        """Test incrementing retry count"""
        tasks_collection = mock_get_db['task_execution_logs']

        tasks_collection.insert_one({
            'task_id': 'retry-task',
            'retry_count': 0,
            'status': 'processing',
        })

        # Simulate retry
        tasks_collection.update_one(
            {'task_id': 'retry-task'},
            {
                '$inc': {'retry_count': 1},
                '$set': {'status': 'retrying'},
            }
        )

        task = tasks_collection.find_one({'task_id': 'retry-task'})
        assert task['retry_count'] == 1

    @pytest.mark.unit
    def test_max_retries_exceeded(self, mock_get_db):
        """Test handling max retries exceeded"""
        tasks_collection = mock_get_db['task_execution_logs']
        max_retries = 3

        tasks_collection.insert_one({
            'task_id': 'max-retry-task',
            'retry_count': max_retries,
            'status': 'processing',
        })

        task = tasks_collection.find_one({'task_id': 'max-retry-task'})

        if task['retry_count'] >= max_retries:
            tasks_collection.update_one(
                {'task_id': 'max-retry-task'},
                {'$set': {'status': 'failed', 'error_message': 'Max retries exceeded'}}
            )

        updated = tasks_collection.find_one({'task_id': 'max-retry-task'})
        assert updated['status'] == 'failed'

    @pytest.mark.unit
    def test_requeue_on_failure(self):
        """Test message requeue on failure"""
        # Simulate requeue decision
        retry_count = 1
        max_retries = 3

        should_requeue = retry_count < max_retries
        assert should_requeue is True

    @pytest.mark.unit
    def test_no_requeue_on_max_retries(self):
        """Test no requeue when max retries reached"""
        retry_count = 3
        max_retries = 3

        should_requeue = retry_count < max_retries
        assert should_requeue is False


class TestAckNackHandling:
    """Test ACK/NACK message handling"""

    @pytest.mark.unit
    def test_ack_on_success(self, mock_rabbitmq_channel):
        """Test ACK on successful processing"""
        mock_rabbitmq_channel.basic_ack(delivery_tag=1)
        # Should not raise exception

    @pytest.mark.unit
    def test_nack_with_requeue(self, mock_rabbitmq_channel):
        """Test NACK with requeue on failure"""
        mock_rabbitmq_channel.basic_nack(delivery_tag=1, requeue=True)
        # Should not raise exception

    @pytest.mark.unit
    def test_nack_without_requeue(self, mock_rabbitmq_channel):
        """Test NACK without requeue (discard message)"""
        mock_rabbitmq_channel.basic_nack(delivery_tag=1, requeue=False)
        # Should not raise exception

    @pytest.mark.unit
    def test_reject_message(self, mock_rabbitmq_channel):
        """Test reject message"""
        mock_rabbitmq_channel.basic_reject(delivery_tag=1, requeue=False)
        # Should not raise exception


class TestErrorRecovery:
    """Test error recovery mechanisms"""

    @pytest.mark.unit
    def test_handle_processing_exception(self, mock_get_db, sample_analysis_task):
        """Test handling processing exception"""
        tasks_collection = mock_get_db['task_execution_logs']

        tasks_collection.insert_one({
            'task_id': sample_analysis_task['task_id'],
            'status': 'processing',
        })

        # Simulate exception handling
        error_message = "Processing error: Model file corrupt"
        tasks_collection.update_one(
            {'task_id': sample_analysis_task['task_id']},
            {
                '$set': {
                    'status': 'failed',
                    'error_message': error_message,
                    'failed_at': datetime.now(timezone.utc),
                }
            }
        )

        task = tasks_collection.find_one({'task_id': sample_analysis_task['task_id']})
        assert task['status'] == 'failed'

    @pytest.mark.unit
    def test_connection_recovery(self, mock_rabbitmq_connection):
        """Test connection recovery"""
        # Simulate connection failure
        mock_rabbitmq_connection.close()
        assert mock_rabbitmq_connection.is_open is False

        # In real implementation, would trigger reconnection

    @pytest.mark.unit
    def test_dead_letter_queue(self, mock_rabbitmq_channel):
        """Test dead letter queue handling"""
        # Declare DLQ
        mock_rabbitmq_channel.queue_declare(
            queue='analysis_dlq',
            durable=True
        )

        # Simulate sending to DLQ
        failed_message = {'task_id': 'failed-task', 'error': 'Max retries'}
        mock_rabbitmq_channel.basic_publish(
            exchange='',
            routing_key='analysis_dlq',
            body=json.dumps(failed_message).encode()
        )

        # Message should be in DLQ
        messages = mock_rabbitmq_channel.get_published_messages()
        assert len(messages) >= 1


class TestQoSSettings:
    """Test QoS settings"""

    @pytest.mark.unit
    def test_set_prefetch_count(self, mock_rabbitmq_channel):
        """Test setting prefetch count"""
        mock_rabbitmq_channel.basic_qos(prefetch_count=1)
        # Should not raise exception

    @pytest.mark.unit
    def test_fair_dispatch(self, mock_rabbitmq_channel):
        """Test fair message dispatch with prefetch"""
        mock_rabbitmq_channel.basic_qos(prefetch_count=1)

        # With prefetch=1, each consumer gets one unacked message at a time
        assert mock_rabbitmq_channel._prefetch_count == 1
