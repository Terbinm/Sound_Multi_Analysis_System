"""
Configuration Fixtures for Testing

Provides fixtures for:
- Application configuration mocking
- Analysis configuration samples
- Routing rule configuration
- Edge client configuration
"""
import pytest
from typing import Dict, Any, List, Generator
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """
    Mock application configuration

    Returns a dictionary matching the config structure used in the application
    """
    return {
        # Flask settings
        'FLASK_ENV': 'testing',
        'FLASK_DEBUG': False,
        'SECRET_KEY': 'test-secret-key',
        'TESTING': True,

        # Web server
        'WEB_HOST': '0.0.0.0',
        'WEB_PORT': 55103,

        # MongoDB settings
        'MONGODB_HOST': 'localhost',
        'MONGODB_PORT': 27017,
        'MONGODB_DATABASE': 'test_sound_analysis',
        'MONGODB_USERNAME': 'test_user',
        'MONGODB_PASSWORD': 'test_password',
        'MONGODB_AUTH_SOURCE': 'admin',

        # RabbitMQ settings
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': 5672,
        'RABBITMQ_USERNAME': 'test_user',
        'RABBITMQ_PASSWORD': 'test_password',
        'RABBITMQ_VHOST': 'test_vhost',
        'RABBITMQ_QUEUE_NAME': 'test_analysis_queue',
        'RABBITMQ_EXCHANGE_NAME': 'test_analysis_exchange',

        # File paths
        'UPLOAD_FOLDER': 'uploads',
        'TEMP_FOLDER': 'temp',
        'LOG_FOLDER': 'logs',

        # Analysis settings
        'MAX_ANALYSIS_WORKERS': 4,
        'ANALYSIS_TIMEOUT': 300,

        # WebSocket settings
        'WEBSOCKET_PING_INTERVAL': 25,
        'WEBSOCKET_PING_TIMEOUT': 60,
    }


@pytest.fixture
def patched_config(mock_config: Dict[str, Any]):
    """
    Patch config.get_config() to return mock configuration

    Usage:
        def test_with_config(patched_config):
            from config import get_config
            config = get_config()  # Returns mock_config
    """
    def get_config_side_effect(key: str = None, default: Any = None) -> Any:
        if key is None:
            return mock_config
        return mock_config.get(key, default)

    with patch('core.state_management.utils.config.get_config', side_effect=get_config_side_effect):
        yield mock_config


@pytest.fixture
def mock_analysis_config() -> Dict[str, Any]:
    """
    Complete mock analysis configuration

    Matches the AnalysisConfig model structure
    """
    now = datetime.now(timezone.utc)

    return {
        'config_id': 'config-test-001',
        'config_name': 'Test Audio Classification Config',
        'analysis_method_id': 'audio_classification',
        'description': 'Configuration for testing audio classification pipeline',
        'parameters': {
            'slice_duration': 10.0,
            'overlap': 0.5,
            'sample_rate': 16000,
            'n_mels': 64,
            'n_fft': 512,
            'hop_length': 256,
            'window_size': 0.025,
            'window_stride': 0.01,
            'use_gpu': False,
        },
        'model_files': {
            'classification_method': 'onnx',
            'onnx_model': {
                'file_id': 'gridfs-model-001',
                'filename': 'classifier_v1.onnx',
                'version': '1.0.0',
                'uploaded_at': now.isoformat(),
            },
            'label_mapping': {
                'file_id': 'gridfs-labels-001',
                'filename': 'labels.json',
            },
        },
        'enabled': True,
        'is_system': False,
        'created_at': now,
        'updated_at': now,
        'created_by': 'test_user',
    }


@pytest.fixture
def mock_routing_rule_config() -> Dict[str, Any]:
    """
    Mock routing rule configuration

    Matches the RoutingRule model structure
    """
    now = datetime.now(timezone.utc)

    return {
        'rule_id': 'rule-test-001',
        'rule_name': 'Test Default Routing Rule',
        'description': 'Route all audio files to classification',
        'conditions': {
            'device_id': {'$regex': '.*'},
            'file_type': {'$in': ['wav', 'mp3', 'flac']},
        },
        'target_config_id': 'config-test-001',
        'target_mongodb_instance': 'default',
        'priority': 100,
        'enabled': True,
        'created_at': now,
        'updated_at': now,
    }


@pytest.fixture
def mock_edge_config() -> Dict[str, Any]:
    """
    Mock edge client configuration

    Matches the edge client device_config.json structure
    """
    return {
        'device_id': 'test-edge-device-001',
        'device_name': 'Test_Edge_Device',
        'server_url': 'http://localhost:55103',
        'audio_config': {
            'default_device_index': 0,
            'channels': 1,
            'sample_rate': 16000,
            'bit_depth': 16,
            'chunk_duration': 1.0,
        },
        'heartbeat_interval': 30,
        'reconnect_delay': 5,
        'max_reconnect_delay': 60,
        'temp_wav_dir': 'temp_wav',
        'log_config': {
            'log_dir': 'logs',
            'max_file_size_mb': 10,
            'backup_count': 5,
            'log_level': 'INFO',
        },
        'storage_cleanup': {
            'enabled': True,
            'max_size_gb': 20.0,
            'threshold_percent': 90.0,
            'target_percent': 70.0,
            'interval_seconds': 3600,
        },
        'multi_backend': {
            'enabled': False,
            'backends': [
                {
                    'id': 'primary',
                    'url': 'http://localhost:55103',
                    'enabled': True,
                    'is_primary': True,
                },
            ],
            'dedup_seconds': 5.0,
            'upload_strategy': 'primary_first',
        },
    }


@pytest.fixture
def mock_mongodb_instance_config() -> Dict[str, Any]:
    """
    Mock MongoDB instance configuration

    Matches the MongoDBInstance model structure
    """
    now = datetime.now(timezone.utc)

    return {
        'instance_id': 'test-mongo-001',
        'instance_name': 'Test MongoDB Instance',
        'description': 'MongoDB instance for testing',
        'host': 'localhost',
        'port': 27017,
        'username': 'test_user',
        'password': 'test_password',
        'database': 'test_recordings',
        'collection': 'recordings',
        'auth_source': 'admin',
        'enabled': True,
        'is_system': False,
        'created_at': now,
        'updated_at': now,
    }


@pytest.fixture
def multiple_analysis_configs() -> List[Dict[str, Any]]:
    """
    Multiple analysis configurations for testing

    Returns configs for different analysis methods
    """
    now = datetime.now(timezone.utc)

    return [
        {
            'config_id': 'audio-class-001',
            'config_name': 'Audio Classification',
            'analysis_method_id': 'audio_classification',
            'parameters': {'slice_duration': 10.0},
            'model_files': {'classification_method': 'onnx'},
            'enabled': True,
            'is_system': True,
            'created_at': now,
        },
        {
            'config_id': 'anomaly-001',
            'config_name': 'Anomaly Detection',
            'analysis_method_id': 'anomaly_detection',
            'parameters': {'threshold': 0.8},
            'model_files': {'detection_method': 'isolation_forest'},
            'enabled': True,
            'is_system': False,
            'created_at': now,
        },
        {
            'config_id': 'speech-001',
            'config_name': 'Speech Recognition',
            'analysis_method_id': 'speech_recognition',
            'parameters': {'language': 'zh-TW'},
            'model_files': {'model_type': 'whisper'},
            'enabled': False,
            'is_system': False,
            'created_at': now,
        },
    ]


@pytest.fixture
def multiple_routing_rules() -> List[Dict[str, Any]]:
    """
    Multiple routing rules for testing priority and matching

    Returns rules with different conditions and priorities
    """
    now = datetime.now(timezone.utc)

    return [
        {
            'rule_id': 'rule-high-priority',
            'rule_name': 'High Priority Devices',
            'conditions': {'device_id': {'$regex': 'priority-.*'}},
            'target_config_id': 'audio-class-001',
            'priority': 1000,
            'enabled': True,
            'created_at': now,
        },
        {
            'rule_id': 'rule-anomaly',
            'rule_name': 'Anomaly Detection Route',
            'conditions': {'tags': {'$in': ['anomaly', 'monitor']}},
            'target_config_id': 'anomaly-001',
            'priority': 500,
            'enabled': True,
            'created_at': now,
        },
        {
            'rule_id': 'rule-default',
            'rule_name': 'Default Classification',
            'conditions': {},
            'target_config_id': 'audio-class-001',
            'priority': 100,
            'enabled': True,
            'created_at': now,
        },
        {
            'rule_id': 'rule-disabled',
            'rule_name': 'Disabled Rule',
            'conditions': {'device_id': 'special'},
            'target_config_id': 'speech-001',
            'priority': 200,
            'enabled': False,
            'created_at': now,
        },
    ]
