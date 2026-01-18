"""
Analysis Service Test Configuration

Fixtures specific to analysis_service module testing
"""
import os
import sys
import pytest
from typing import Generator, Dict, Any
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANALYSIS_SERVICE_PATH = os.path.join(PROJECT_ROOT, 'sub_system', 'analysis_service')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, ANALYSIS_SERVICE_PATH)


@pytest.fixture
def mock_analysis_pipeline():
    """
    Mock AnalysisPipeline for testing

    Usage:
        def test_analysis(mock_analysis_pipeline):
            result = mock_analysis_pipeline.process(task_data)
    """
    pipeline = MagicMock()

    def process(recording_data, config, model_cache=None):
        return {
            'status': 'success',
            'results': {
                'classification': 'normal',
                'confidence': 0.95,
            },
            'processed_at': datetime.now(timezone.utc).isoformat(),
        }

    pipeline.process = process
    pipeline.steps = ['step0_converter', 'step1_slicer', 'step2_leaf', 'step3_classifier']

    return pipeline


@pytest.fixture
def mock_model_cache():
    """
    Mock ModelCacheManager for testing

    Usage:
        def test_model_loading(mock_model_cache):
            model = mock_model_cache.get_model('config-001', 'onnx_model')
    """
    cache = MagicMock()
    cache._cached_models = {}

    def get_model(config_id: str, model_key: str):
        cache_key = f"{config_id}:{model_key}"
        if cache_key not in cache._cached_models:
            cache._cached_models[cache_key] = MagicMock(name=f'MockModel_{cache_key}')
        return cache._cached_models[cache_key]

    def download_model(file_id: str, destination: str):
        return True

    def clear_cache():
        cache._cached_models.clear()

    cache.get_model = get_model
    cache.download_model = download_model
    cache.clear_cache = clear_cache

    return cache


@pytest.fixture
def mock_node_manager():
    """
    Mock MongoDBNodeManager for testing

    Usage:
        def test_node_registration(mock_node_manager):
            mock_node_manager.register_node()
    """
    manager = MagicMock()
    manager.node_id = 'test-node-001'
    manager.capabilities = ['audio_classification', 'anomaly_detection']
    manager.current_tasks = 0
    manager.max_tasks = 4

    def register_node():
        return True

    def update_heartbeat():
        return True

    def update_task_count(delta: int):
        manager.current_tasks = max(0, manager.current_tasks + delta)
        return True

    def unregister_node():
        return True

    manager.register_node = register_node
    manager.update_heartbeat = update_heartbeat
    manager.update_task_count = update_task_count
    manager.unregister_node = unregister_node

    return manager


@pytest.fixture
def mock_gridfs_analysis_handler(mock_gridfs_handler):
    """
    Mock GridFS handler for analysis service

    Extends base mock_gridfs_handler with analysis-specific methods
    """
    handler = mock_gridfs_handler

    def get_recording_file(recording_id: str):
        # Return mock audio content
        return b'mock audio content'

    def store_result(result_data: bytes, metadata: Dict[str, Any]):
        return handler.put(result_data, **metadata)

    handler.get_recording_file = get_recording_file
    handler.store_result = store_result

    return handler


@pytest.fixture
def sample_analysis_task() -> Dict[str, Any]:
    """Sample analysis task data"""
    return {
        'task_id': 'task-analysis-001',
        'recording_id': 'rec-001',
        'analyze_uuid': 'uuid-001-002-003',
        'config_id': 'audio-classification-001',
        'analysis_method_id': 'audio_classification',
        'mongodb_instance': 'default',
        'priority': 5,
        'retry_count': 0,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_recording_for_analysis() -> Dict[str, Any]:
    """Sample recording document for analysis"""
    return {
        '_id': 'rec-analysis-001',
        'recording_uuid': 'uuid-001-002-003',
        'device_id': 'device-001',
        'filename': 'recording.wav',
        'file_id': 'gridfs-file-001',
        'sample_rate': 16000,
        'channels': 1,
        'duration': 10.0,
        'analysis_status': 'pending',
    }


@pytest.fixture
def sample_analysis_result() -> Dict[str, Any]:
    """Sample analysis result"""
    return {
        'recording_id': 'rec-001',
        'task_id': 'task-001',
        'analysis_method': 'audio_classification',
        'results': {
            'classification': 'normal',
            'confidence': 0.95,
            'predictions': [
                {'label': 'normal', 'score': 0.95},
                {'label': 'anomaly', 'score': 0.05},
            ],
        },
        'processing_time_ms': 1234,
        'completed_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def analysis_configs_in_db(mock_get_db, sample_analysis_config):
    """Pre-populate database with analysis configurations"""
    configs_collection = mock_get_db['analysis_configs']

    configs_collection.insert_one(sample_analysis_config)

    # Add alternative config
    alt_config = sample_analysis_config.copy()
    alt_config['config_id'] = 'anomaly-detection-001'
    alt_config['config_name'] = 'Anomaly Detection'
    alt_config['analysis_method_id'] = 'anomaly_detection'
    configs_collection.insert_one(alt_config)

    return mock_get_db


@pytest.fixture
def task_logs_collection(mock_get_db):
    """Get task execution logs collection"""
    return mock_get_db['task_execution_logs']


@pytest.fixture
def node_status_collection(mock_get_db):
    """Get node status collection"""
    return mock_get_db['node_status']
