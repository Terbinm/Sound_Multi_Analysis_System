"""
Environment Variable Fixtures for Testing

Provides fixtures for:
- Production environment simulation
- Development environment simulation
- Testing environment configuration
"""
import os
import pytest
from typing import Dict, Generator
from unittest.mock import patch


@pytest.fixture
def base_environment() -> Dict[str, str]:
    """
    Base environment variables common to all environments
    """
    return {
        'LOG_LEVEL': 'INFO',
        'TZ': 'Asia/Taipei',
        'PYTHONUNBUFFERED': '1',
    }


@pytest.fixture
def production_env(base_environment: Dict[str, str]) -> Dict[str, str]:
    """
    Production environment variables

    Simulates production deployment settings
    """
    env = base_environment.copy()
    env.update({
        # Flask
        'FLASK_ENV': 'production',
        'FLASK_DEBUG': '0',
        'SECRET_KEY': 'production-secret-key-change-in-deployment',

        # Web Server
        'WEB_HOST': '0.0.0.0',
        'WEB_PORT': '55103',
        'WORKERS': '4',
        'WORKER_CLASS': 'gevent',

        # MongoDB
        'MONGODB_HOST': 'mongodb',
        'MONGODB_PORT': '27017',
        'MONGODB_DATABASE': 'sound_analysis',
        'MONGODB_USERNAME': 'sound_user',
        'MONGODB_PASSWORD': 'sound_password',
        'MONGODB_AUTH_SOURCE': 'admin',

        # RabbitMQ
        'RABBITMQ_HOST': 'rabbitmq',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USERNAME': 'sound_user',
        'RABBITMQ_PASSWORD': 'sound_password',
        'RABBITMQ_VHOST': 'sound_analysis',
        'RABBITMQ_QUEUE_NAME': 'analysis_queue',
        'RABBITMQ_EXCHANGE_NAME': 'analysis_exchange',

        # Analysis Service
        'ANALYSIS_NODE_ID': '',  # Auto-generated
        'MAX_WORKERS': '4',
        'MODEL_CACHE_DIR': '/app/models',

        # Paths
        'UPLOAD_FOLDER': '/app/uploads',
        'LOG_DIR': '/app/logs',
    })
    return env


@pytest.fixture
def development_env(base_environment: Dict[str, str]) -> Dict[str, str]:
    """
    Development environment variables

    Simulates local development settings
    """
    env = base_environment.copy()
    env.update({
        # Flask
        'FLASK_ENV': 'development',
        'FLASK_DEBUG': '1',
        'SECRET_KEY': 'dev-secret-key',

        # Web Server
        'WEB_HOST': 'localhost',
        'WEB_PORT': '55103',

        # MongoDB (local)
        'MONGODB_HOST': 'localhost',
        'MONGODB_PORT': '27017',
        'MONGODB_DATABASE': 'sound_analysis_dev',
        'MONGODB_USERNAME': '',
        'MONGODB_PASSWORD': '',
        'MONGODB_AUTH_SOURCE': '',

        # RabbitMQ (local)
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USERNAME': 'guest',
        'RABBITMQ_PASSWORD': 'guest',
        'RABBITMQ_VHOST': '/',
        'RABBITMQ_QUEUE_NAME': 'dev_analysis_queue',
        'RABBITMQ_EXCHANGE_NAME': 'dev_analysis_exchange',

        # Analysis Service
        'ANALYSIS_NODE_ID': 'dev-node-001',
        'MAX_WORKERS': '2',
        'MODEL_CACHE_DIR': 'models',

        # Paths
        'UPLOAD_FOLDER': 'uploads',
        'LOG_DIR': 'logs',
        'LOG_LEVEL': 'DEBUG',
    })
    return env


@pytest.fixture
def testing_env(base_environment: Dict[str, str]) -> Dict[str, str]:
    """
    Testing environment variables

    Optimized for CI/test execution
    """
    env = base_environment.copy()
    env.update({
        # Flask
        'FLASK_ENV': 'testing',
        'FLASK_DEBUG': '0',
        'TESTING': '1',
        'SECRET_KEY': 'test-secret-key-for-ci',
        'WTF_CSRF_ENABLED': '0',

        # Web Server
        'WEB_HOST': 'localhost',
        'WEB_PORT': '55199',

        # MongoDB (test instance)
        'MONGODB_HOST': 'localhost',
        'MONGODB_PORT': '27017',
        'MONGODB_DATABASE': 'test_sound_analysis',
        'MONGODB_USERNAME': 'test_user',
        'MONGODB_PASSWORD': 'test_password',
        'MONGODB_AUTH_SOURCE': 'admin',

        # RabbitMQ (test instance)
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USERNAME': 'test_user',
        'RABBITMQ_PASSWORD': 'test_password',
        'RABBITMQ_VHOST': 'test_vhost',
        'RABBITMQ_QUEUE_NAME': 'test_queue',
        'RABBITMQ_EXCHANGE_NAME': 'test_exchange',

        # Analysis Service
        'ANALYSIS_NODE_ID': 'test-node-001',
        'MAX_WORKERS': '1',
        'MODEL_CACHE_DIR': 'test_models',

        # Paths (use temp directories in tests)
        'UPLOAD_FOLDER': 'test_uploads',
        'LOG_DIR': 'test_logs',
        'LOG_LEVEL': 'WARNING',

        # Test-specific
        'DISABLE_EXTERNAL_CONNECTIONS': '1',
        'USE_MOCK_SERVICES': '1',
    })
    return env


@pytest.fixture
def edge_client_env() -> Dict[str, str]:
    """
    Environment variables for edge client testing
    """
    return {
        'EDGE_DEVICE_ID': 'test-edge-001',
        'EDGE_DEVICE_NAME': 'Test_Edge_Client',
        'SERVER_URL': 'http://localhost:55103',
        'HEARTBEAT_INTERVAL': '30',
        'RECONNECT_DELAY': '5',
        'MAX_RECONNECT_DELAY': '60',
        'LOG_LEVEL': 'DEBUG',
        'TEMP_WAV_DIR': 'temp_wav',
        'LOG_DIR': 'logs',
    }


@pytest.fixture
def analysis_service_env() -> Dict[str, str]:
    """
    Environment variables for analysis service testing
    """
    return {
        'ANALYSIS_NODE_ID': 'test-analysis-node',
        'CAPABILITIES': 'audio_classification,anomaly_detection',
        'MAX_CONCURRENT_TASKS': '2',
        'HEARTBEAT_INTERVAL': '10',
        'MODEL_CACHE_DIR': 'models',
        'LOG_LEVEL': 'DEBUG',

        # MongoDB
        'MONGODB_HOST': 'localhost',
        'MONGODB_PORT': '27017',
        'MONGODB_DATABASE': 'test_analysis',

        # RabbitMQ
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_QUEUE_NAME': 'test_analysis_queue',
    }


@pytest.fixture
def patched_production_env(production_env: Dict[str, str]) -> Generator[Dict[str, str], None, None]:
    """
    Patch environment with production settings

    Usage:
        def test_production_behavior(patched_production_env):
            # os.environ now has production values
            assert os.getenv('FLASK_ENV') == 'production'
    """
    with patch.dict(os.environ, production_env, clear=False):
        yield production_env


@pytest.fixture
def patched_development_env(development_env: Dict[str, str]) -> Generator[Dict[str, str], None, None]:
    """
    Patch environment with development settings

    Usage:
        def test_dev_behavior(patched_development_env):
            assert os.getenv('FLASK_DEBUG') == '1'
    """
    with patch.dict(os.environ, development_env, clear=False):
        yield development_env


@pytest.fixture
def patched_testing_env(testing_env: Dict[str, str]) -> Generator[Dict[str, str], None, None]:
    """
    Patch environment with testing settings

    Usage:
        def test_in_test_env(patched_testing_env):
            assert os.getenv('TESTING') == '1'
    """
    with patch.dict(os.environ, testing_env, clear=False):
        yield testing_env


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """
    Provide a clean environment without project-specific variables

    Useful for testing default value handling
    """
    keys_to_remove = [
        'FLASK_ENV', 'FLASK_DEBUG', 'SECRET_KEY',
        'MONGODB_HOST', 'MONGODB_PORT', 'MONGODB_DATABASE',
        'RABBITMQ_HOST', 'RABBITMQ_PORT',
        'ANALYSIS_NODE_ID', 'TESTING',
    ]

    original_values = {}
    for key in keys_to_remove:
        if key in os.environ:
            original_values[key] = os.environ.pop(key)

    yield

    # Restore original values
    for key, value in original_values.items():
        os.environ[key] = value


@pytest.fixture
def docker_env(production_env: Dict[str, str]) -> Dict[str, str]:
    """
    Environment variables for Docker deployment testing

    Extends production env with Docker-specific settings
    """
    env = production_env.copy()
    env.update({
        'DOCKER_CONTAINER': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONUNBUFFERED': '1',

        # Docker networking
        'MONGODB_HOST': 'mongodb',
        'RABBITMQ_HOST': 'rabbitmq',

        # Volume paths
        'UPLOAD_FOLDER': '/app/uploads',
        'MODEL_CACHE_DIR': '/app/models',
        'LOG_DIR': '/app/logs',

        # Health check
        'HEALTH_CHECK_PORT': '8080',
    })
    return env
