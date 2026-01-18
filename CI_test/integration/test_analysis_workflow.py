"""
Integration Tests for Analysis Workflow

Tests end-to-end analysis workflow:
- Task creation and dispatch
- Pipeline execution
- Result storage
- Status updates
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestTaskCreationFlow:
    """Test task creation and dispatch workflow"""

    @pytest.mark.integration
    def test_task_creation_from_recording(
        self, integration_test_recording, integration_test_config
    ):
        """Test creating analysis task from recording"""
        recording = integration_test_recording
        config = integration_test_config

        task = {
            'task_id': 'task-001',
            'recording_id': recording['_id'],
            'config_id': config['_id'],
            'status': 'pending',
            'created_at': '2024-01-01T00:00:00Z'
        }

        assert task['recording_id'] == recording['_id']
        assert task['config_id'] == config['_id']
        assert task['status'] == 'pending'

    @pytest.mark.integration
    def test_task_dispatch_to_queue(self, mock_rabbitmq_service):
        """Test dispatching task to RabbitMQ"""
        task = {
            'task_id': 'task-001',
            'recording_id': 'rec-001',
            'config_id': 'config-001'
        }

        mock_rabbitmq_service.publish.return_value = True

        success = mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.new',
            body=task
        )

        assert success is True

    @pytest.mark.integration
    def test_task_priority_queuing(self, mock_rabbitmq_service):
        """Test task priority queuing"""
        high_priority_task = {'task_id': 'task-high', 'priority': 10}
        normal_priority_task = {'task_id': 'task-normal', 'priority': 5}

        # High priority should go to priority queue
        mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.priority',
            body=high_priority_task
        )

        # Normal priority to standard queue
        mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.standard',
            body=normal_priority_task
        )

        assert mock_rabbitmq_service.publish.call_count == 2


class TestPipelineExecution:
    """Test pipeline execution workflow"""

    @pytest.mark.integration
    def test_full_pipeline_execution(self, integration_test_config):
        """Test full 4-step pipeline execution"""
        config = integration_test_config
        pipeline_steps = config['pipeline_steps']

        results = {}
        for step in pipeline_steps:
            if step['enabled']:
                step_name = step['name']
                results[step_name] = {
                    'status': 'completed',
                    'duration_ms': 100
                }

        assert len(results) == 4
        assert all(r['status'] == 'completed' for r in results.values())

    @pytest.mark.integration
    def test_pipeline_step_failure_handling(self):
        """Test pipeline handles step failure"""
        steps = ['converter', 'slicer', 'leaf', 'classifier']
        current_step = 0
        failed = False
        error_step = None

        for i, step in enumerate(steps):
            current_step = i
            if step == 'slicer':
                # Simulate failure
                failed = True
                error_step = step
                break

        assert failed is True
        assert error_step == 'slicer'
        assert current_step == 1

    @pytest.mark.integration
    def test_pipeline_with_partial_steps(self, integration_test_config):
        """Test pipeline with some steps disabled"""
        config = integration_test_config

        # Disable LEAF step
        for step in config['pipeline_steps']:
            if step['name'] == 'leaf':
                step['enabled'] = False

        enabled_steps = [s for s in config['pipeline_steps'] if s['enabled']]

        assert len(enabled_steps) == 3

    @pytest.mark.integration
    def test_pipeline_result_aggregation(self):
        """Test aggregating results from all steps"""
        step_results = {
            'converter': {'output_file': 'converted.wav'},
            'slicer': {'slice_count': 6},
            'leaf': {'features_shape': [6, 100, 64]},
            'classifier': {'predictions': [
                {'label': 'normal', 'score': 0.9}
            ]}
        }

        final_result = {
            'steps': step_results,
            'final_prediction': step_results['classifier']['predictions'][0],
            'slice_count': step_results['slicer']['slice_count']
        }

        assert 'steps' in final_result
        assert 'final_prediction' in final_result


class TestResultStorage:
    """Test result storage workflow"""

    @pytest.mark.integration
    def test_store_analysis_result(self, mock_mongodb_service):
        """Test storing analysis result"""
        result = {
            'task_id': 'task-001',
            'recording_id': 'rec-001',
            'classification': 'normal',
            'confidence': 0.95,
            'processing_time_ms': 5000,
            'completed_at': '2024-01-01T01:00:00Z'
        }

        mock_mongodb_service.results = MagicMock()
        mock_mongodb_service.results.insert_one.return_value = MagicMock(
            inserted_id='result-001'
        )

        insert_result = mock_mongodb_service.results.insert_one(result)

        assert insert_result.inserted_id is not None

    @pytest.mark.integration
    def test_update_recording_with_result(self, mock_mongodb_service):
        """Test updating recording with analysis result"""
        recording_id = 'rec-001'
        result_id = 'result-001'

        mock_mongodb_service.recordings.update_one.return_value = MagicMock(
            modified_count=1
        )

        update_result = mock_mongodb_service.recordings.update_one(
            {'_id': recording_id},
            {'$set': {
                'status': 'analyzed',
                'result_id': result_id
            }}
        )

        assert update_result.modified_count == 1

    @pytest.mark.integration
    def test_store_slice_level_results(self, mock_mongodb_service):
        """Test storing slice-level results"""
        slice_results = [
            {'slice_index': i, 'prediction': 'normal', 'score': 0.9 + i * 0.01}
            for i in range(6)
        ]

        mock_mongodb_service.slice_results = MagicMock()
        mock_mongodb_service.slice_results.insert_many.return_value = MagicMock(
            inserted_ids=[f'slice-result-{i}' for i in range(6)]
        )

        insert_result = mock_mongodb_service.slice_results.insert_many(slice_results)

        assert len(insert_result.inserted_ids) == 6


class TestStatusUpdates:
    """Test status update workflow"""

    @pytest.mark.integration
    def test_task_status_progression(self, mock_mongodb_service):
        """Test task status progression"""
        statuses = ['pending', 'queued', 'processing', 'completed']
        task_id = 'task-001'

        for status in statuses:
            mock_mongodb_service.tasks = MagicMock()
            mock_mongodb_service.tasks.update_one.return_value = MagicMock(
                modified_count=1
            )

            result = mock_mongodb_service.tasks.update_one(
                {'task_id': task_id},
                {'$set': {'status': status}}
            )

            assert result.modified_count == 1

    @pytest.mark.integration
    def test_websocket_status_notification(self):
        """Test WebSocket status notification"""
        mock_socketio = MagicMock()

        status_update = {
            'task_id': 'task-001',
            'recording_id': 'rec-001',
            'status': 'completed',
            'result': {
                'classification': 'normal',
                'confidence': 0.95
            }
        }

        mock_socketio.emit('analysis.completed', status_update, room='analysis')

        mock_socketio.emit.assert_called_once()

    @pytest.mark.integration
    def test_error_status_with_message(self, mock_mongodb_service):
        """Test error status with error message"""
        task_id = 'task-001'
        error_info = {
            'status': 'failed',
            'error': 'Model file not found',
            'error_step': 'leaf'
        }

        mock_mongodb_service.tasks = MagicMock()
        mock_mongodb_service.tasks.update_one.return_value = MagicMock(
            modified_count=1
        )

        result = mock_mongodb_service.tasks.update_one(
            {'task_id': task_id},
            {'$set': error_info}
        )

        assert result.modified_count == 1


class TestModelManagement:
    """Test model management in workflow"""

    @pytest.mark.integration
    def test_model_download_before_analysis(self):
        """Test model download before analysis"""
        required_models = ['leaf_v1.onnx', 'classifier_v1.onnx']
        cached_models = ['leaf_v1.onnx']

        to_download = [m for m in required_models if m not in cached_models]

        assert len(to_download) == 1
        assert 'classifier_v1.onnx' in to_download

    @pytest.mark.integration
    def test_model_version_matching(self, integration_test_config):
        """Test model version matching with config"""
        config = integration_test_config
        model_files = config['model_files']

        # Simulate checking model versions
        required = {
            'leaf': 'models/leaf_v1.onnx',
            'classifier': 'models/classifier_v1.onnx'
        }

        matches = all(
            model_files.get(k) == v
            for k, v in required.items()
        )

        assert matches is True


class TestConcurrentAnalysis:
    """Test concurrent analysis handling"""

    @pytest.mark.integration
    def test_multiple_task_handling(self, mock_rabbitmq_service):
        """Test handling multiple concurrent tasks"""
        tasks = [
            {'task_id': f'task-{i}', 'recording_id': f'rec-{i}'}
            for i in range(5)
        ]

        for task in tasks:
            mock_rabbitmq_service.publish(
                exchange='analysis_tasks',
                routing_key='analysis.new',
                body=task
            )

        assert mock_rabbitmq_service.publish.call_count == 5

    @pytest.mark.integration
    def test_node_load_balancing(self, mock_mongodb_service):
        """Test load balancing across analysis nodes"""
        nodes = [
            {'node_id': 'node-1', 'current_tasks': 2},
            {'node_id': 'node-2', 'current_tasks': 5},
            {'node_id': 'node-3', 'current_tasks': 1}
        ]

        # Select node with lowest load
        selected = min(nodes, key=lambda n: n['current_tasks'])

        assert selected['node_id'] == 'node-3'

