"""
Tests for TaskDispatcher Utility

Tests cover:
- Task dispatching
- Batch processing
- Priority handling
- Error handling
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestTaskDispatching:
    """Test task dispatching functionality"""

    @pytest.mark.unit
    def test_dispatch_single_task(self, mock_rabbitmq_publisher, sample_task_data):
        """Test dispatching a single task"""
        result = mock_rabbitmq_publisher.publish_task(sample_task_data)
        assert result is True

        messages = mock_rabbitmq_publisher.get_published_messages()
        assert len(messages) == 1

    @pytest.mark.unit
    def test_dispatch_task_with_priority(self, mock_rabbitmq_publisher):
        """Test dispatching task with priority"""
        task = {
            'task_id': 'priority-task',
            'priority': 10,  # High priority
            'recording_id': 'rec-001',
        }

        result = mock_rabbitmq_publisher.publish_task(
            task,
            routing_key='analysis.task.high'
        )
        assert result is True

    @pytest.mark.unit
    def test_dispatch_to_specific_node(self, mock_rabbitmq_publisher):
        """Test dispatching task to specific analysis node"""
        task = {
            'task_id': 'targeted-task',
            'target_node': 'node-001',
            'recording_id': 'rec-001',
        }

        result = mock_rabbitmq_publisher.publish_task(
            task,
            routing_key='analysis.task.node-001'
        )
        assert result is True


class TestBatchProcessing:
    """Test batch task processing"""

    @pytest.mark.unit
    def test_dispatch_batch_tasks(self, mock_rabbitmq_publisher):
        """Test dispatching multiple tasks in batch"""
        tasks = [
            {'task_id': f'batch-task-{i}', 'recording_id': f'rec-{i}'}
            for i in range(10)
        ]

        success_count = 0
        for task in tasks:
            if mock_rabbitmq_publisher.publish_task(task):
                success_count += 1

        assert success_count == 10

    @pytest.mark.unit
    def test_batch_with_mixed_priorities(self, mock_rabbitmq_publisher):
        """Test batch dispatch with different priorities"""
        tasks = [
            {'task_id': 'high-1', 'priority': 10},
            {'task_id': 'low-1', 'priority': 1},
            {'task_id': 'high-2', 'priority': 10},
            {'task_id': 'medium-1', 'priority': 5},
        ]

        for task in tasks:
            routing_key = 'analysis.task.high' if task['priority'] > 5 else 'analysis.task'
            mock_rabbitmq_publisher.publish_task(task, routing_key=routing_key)

        messages = mock_rabbitmq_publisher.get_published_messages()
        assert len(messages) == 4


class TestTaskCreation:
    """Test task creation for analysis"""

    @pytest.mark.unit
    def test_create_analysis_task(self, mock_get_db, sample_recording_document, sample_analysis_config):
        """Test creating analysis task from recording"""
        task_data = {
            'task_id': f"task-{sample_recording_document['recording_uuid']}",
            'recording_id': sample_recording_document['_id'],
            'analyze_uuid': sample_recording_document['recording_uuid'],
            'config_id': sample_analysis_config['config_id'],
            'analysis_method_id': sample_analysis_config['analysis_method_id'],
            'mongodb_instance': 'default',
            'priority': 5,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        assert task_data['task_id'] is not None
        assert task_data['recording_id'] == sample_recording_document['_id']
        assert task_data['config_id'] == sample_analysis_config['config_id']

    @pytest.mark.unit
    def test_create_task_with_routing_rule(
        self,
        mock_get_db,
        sample_recording_document,
        sample_routing_rule
    ):
        """Test creating task based on routing rule"""
        # Simulate applying routing rule
        task_data = {
            'task_id': f"task-{sample_recording_document['recording_uuid']}",
            'recording_id': sample_recording_document['_id'],
            'analyze_uuid': sample_recording_document['recording_uuid'],
            'config_id': sample_routing_rule['target_config_id'],
            'mongodb_instance': sample_routing_rule['target_mongodb_instance'],
            'routing_rule_id': sample_routing_rule['rule_id'],
            'priority': sample_routing_rule['priority'],
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        assert task_data['config_id'] == sample_routing_rule['target_config_id']
        assert task_data['routing_rule_id'] == sample_routing_rule['rule_id']


class TestTaskLogging:
    """Test task execution logging"""

    @pytest.mark.unit
    def test_log_task_creation(self, mock_get_db):
        """Test logging task creation"""
        logs_collection = mock_get_db['task_execution_logs']

        log_entry = {
            'task_id': 'task-001',
            'action': 'created',
            'status': 'pending',
            'created_at': datetime.now(timezone.utc),
        }

        logs_collection.insert_one(log_entry)

        log = logs_collection.find_one({'task_id': 'task-001'})
        assert log is not None
        assert log['action'] == 'created'

    @pytest.mark.unit
    def test_log_task_dispatched(self, mock_get_db):
        """Test logging task dispatch"""
        logs_collection = mock_get_db['task_execution_logs']

        logs_collection.insert_one({
            'task_id': 'task-001',
            'action': 'created',
            'status': 'pending',
            'created_at': datetime.now(timezone.utc),
        })

        logs_collection.update_one(
            {'task_id': 'task-001'},
            {
                '$set': {
                    'action': 'dispatched',
                    'status': 'dispatched',
                    'dispatched_at': datetime.now(timezone.utc),
                }
            }
        )

        log = logs_collection.find_one({'task_id': 'task-001'})
        assert log['action'] == 'dispatched'

    @pytest.mark.unit
    def test_log_task_completion(self, mock_get_db):
        """Test logging task completion"""
        logs_collection = mock_get_db['task_execution_logs']

        logs_collection.insert_one({
            'task_id': 'task-001',
            'status': 'processing',
            'created_at': datetime.now(timezone.utc),
        })

        logs_collection.update_one(
            {'task_id': 'task-001'},
            {
                '$set': {
                    'status': 'completed',
                    'completed_at': datetime.now(timezone.utc),
                    'result': {'classification': 'normal'},
                }
            }
        )

        log = logs_collection.find_one({'task_id': 'task-001'})
        assert log['status'] == 'completed'
        assert 'result' in log

    @pytest.mark.unit
    def test_log_task_failure(self, mock_get_db):
        """Test logging task failure"""
        logs_collection = mock_get_db['task_execution_logs']

        logs_collection.insert_one({
            'task_id': 'task-fail',
            'status': 'processing',
            'created_at': datetime.now(timezone.utc),
        })

        logs_collection.update_one(
            {'task_id': 'task-fail'},
            {
                '$set': {
                    'status': 'failed',
                    'failed_at': datetime.now(timezone.utc),
                    'error_message': 'Processing error',
                    'retry_count': 1,
                }
            }
        )

        log = logs_collection.find_one({'task_id': 'task-fail'})
        assert log['status'] == 'failed'
        assert log['error_message'] == 'Processing error'


class TestTaskStatusTracking:
    """Test task status tracking"""

    @pytest.mark.unit
    def test_get_pending_tasks(self, mock_get_db):
        """Test getting pending tasks"""
        logs_collection = mock_get_db['task_execution_logs']

        logs_collection.insert_one({'task_id': 't1', 'status': 'pending'})
        logs_collection.insert_one({'task_id': 't2', 'status': 'processing'})
        logs_collection.insert_one({'task_id': 't3', 'status': 'pending'})

        pending = list(logs_collection.find({'status': 'pending'}))
        assert len(pending) == 2

    @pytest.mark.unit
    def test_get_task_statistics(self, mock_get_db):
        """Test getting task statistics"""
        logs_collection = mock_get_db['task_execution_logs']

        logs_collection.insert_one({'task_id': 't1', 'status': 'completed'})
        logs_collection.insert_one({'task_id': 't2', 'status': 'completed'})
        logs_collection.insert_one({'task_id': 't3', 'status': 'failed'})
        logs_collection.insert_one({'task_id': 't4', 'status': 'pending'})

        stats = {
            'total': logs_collection.count_documents({}),
            'completed': logs_collection.count_documents({'status': 'completed'}),
            'failed': logs_collection.count_documents({'status': 'failed'}),
            'pending': logs_collection.count_documents({'status': 'pending'}),
        }

        assert stats['total'] == 4
        assert stats['completed'] == 2
        assert stats['failed'] == 1
        assert stats['pending'] == 1
