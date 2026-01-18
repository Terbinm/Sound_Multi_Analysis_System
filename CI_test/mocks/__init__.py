"""
Shared Mock Classes for CI Testing
"""
from .mock_mongodb import (
    MockMongoClient,
    MockDatabase,
    MockCollection,
    MockCursor,
    MockGridFS,
    MockGridFSBucket,
    MockChangeStream,
)
from .mock_rabbitmq import (
    MockChannel,
    MockConnection,
    MockMessage,
    MockBasicProperties,
)

__all__ = [
    # MongoDB mocks
    'MockMongoClient',
    'MockDatabase',
    'MockCollection',
    'MockCursor',
    'MockGridFS',
    'MockGridFSBucket',
    'MockChangeStream',
    # RabbitMQ mocks
    'MockChannel',
    'MockConnection',
    'MockMessage',
    'MockBasicProperties',
]
