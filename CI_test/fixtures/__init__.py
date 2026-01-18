"""
Shared Fixture Modules for CI Testing

This package contains reusable fixtures organized by category:
- mongodb_fixtures: MongoDB mock and connection fixtures
- rabbitmq_fixtures: RabbitMQ mock and connection fixtures
- websocket_fixtures: WebSocket/SocketIO mock fixtures
- config_fixtures: Configuration and settings fixtures
- env_fixtures: Environment variable fixtures
"""
from .mongodb_fixtures import (
    mock_mongodb_handler,
    mock_multi_mongodb_handler,
    sample_collection_data,
)
from .rabbitmq_fixtures import (
    mock_rabbitmq_publisher,
    mock_rabbitmq_consumer,
)
from .websocket_fixtures import (
    mock_socketio_server,
    mock_websocket_manager,
)
from .config_fixtures import (
    mock_config,
    mock_analysis_config,
)
from .env_fixtures import (
    production_env,
    development_env,
    testing_env,
)

__all__ = [
    # MongoDB fixtures
    'mock_mongodb_handler',
    'mock_multi_mongodb_handler',
    'sample_collection_data',
    # RabbitMQ fixtures
    'mock_rabbitmq_publisher',
    'mock_rabbitmq_consumer',
    # WebSocket fixtures
    'mock_socketio_server',
    'mock_websocket_manager',
    # Config fixtures
    'mock_config',
    'mock_analysis_config',
    # Environment fixtures
    'production_env',
    'development_env',
    'testing_env',
]
