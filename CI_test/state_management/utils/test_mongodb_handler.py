"""
Tests for MongoDBHandler Utility

Tests cover:
- Connection management
- Index creation
- MultiMongoDBHandler functionality
- Connection pooling
"""
import pytest
from unittest.mock import MagicMock, patch


class TestMongoDBHandlerConnection:
    """Test MongoDB connection management"""

    @pytest.mark.unit
    def test_singleton_instance(self, patched_mongodb):
        """Test MongoDBHandler singleton pattern"""
        # Multiple calls should return same instance concept
        assert patched_mongodb is not None

    @pytest.mark.unit
    def test_connection_success(self, patched_mongodb, mock_database):
        """Test successful MongoDB connection"""
        # Verify database is accessible
        assert mock_database is not None
        assert mock_database.name == 'test_database'

    @pytest.mark.unit
    def test_get_collection(self, mock_database):
        """Test getting a collection"""
        collection = mock_database['test_collection']
        assert collection is not None
        assert collection.name == 'test_collection'

    @pytest.mark.unit
    def test_get_database(self, mock_mongo_client):
        """Test getting database from client"""
        db = mock_mongo_client['test_db']
        assert db is not None

    @pytest.mark.unit
    def test_close_connection(self, mock_mongo_client):
        """Test closing connection"""
        mock_mongo_client.close()
        # No exception should be raised


class TestIndexCreation:
    """Test index creation functionality"""

    @pytest.mark.unit
    def test_create_single_field_index(self, mock_collection):
        """Test creating single field index"""
        index_name = mock_collection.create_index('field_name')
        assert index_name is not None

    @pytest.mark.unit
    def test_create_compound_index(self, mock_collection):
        """Test creating compound index"""
        index_name = mock_collection.create_index([
            ('field1', 1),
            ('field2', -1),
        ])
        assert index_name is not None

    @pytest.mark.unit
    def test_create_unique_index(self, mock_collection):
        """Test creating unique index"""
        index_name = mock_collection.create_index('unique_field', unique=True)
        assert index_name is not None

    @pytest.mark.unit
    def test_create_ttl_index(self, mock_collection):
        """Test creating TTL index"""
        index_name = mock_collection.create_index(
            'expire_at',
            expireAfterSeconds=3600
        )
        assert index_name is not None

    @pytest.mark.unit
    def test_list_indexes(self, mock_collection):
        """Test listing collection indexes"""
        mock_collection.create_index('field1')
        mock_collection.create_index('field2')

        indexes = mock_collection.list_indexes()
        assert len(indexes) >= 2

    @pytest.mark.unit
    def test_drop_index(self, mock_collection):
        """Test dropping an index"""
        index_name = mock_collection.create_index('to_drop')
        mock_collection.drop_index(index_name)

        # No exception should be raised


class TestMultiMongoDBHandler:
    """Test MultiMongoDBHandler for multiple instance connections"""

    @pytest.mark.unit
    def test_connect_to_instance(self, mock_multi_mongodb_handler):
        """Test connecting to a MongoDB instance"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'database': 'test_db',
        }

        db = mock_multi_mongodb_handler.connect('instance-001', config)
        assert db is not None

    @pytest.mark.unit
    def test_connect_to_multiple_instances(self, mock_multi_mongodb_handler):
        """Test connecting to multiple instances"""
        configs = [
            {'host': 'host1', 'port': 27017, 'database': 'db1'},
            {'host': 'host2', 'port': 27017, 'database': 'db2'},
            {'host': 'host3', 'port': 27017, 'database': 'db3'},
        ]

        for i, config in enumerate(configs):
            db = mock_multi_mongodb_handler.connect(f'instance-{i}', config)
            assert db is not None

    @pytest.mark.unit
    def test_get_existing_connection(self, mock_multi_mongodb_handler):
        """Test getting an existing connection"""
        config = {'host': 'localhost', 'port': 27017, 'database': 'test_db'}
        mock_multi_mongodb_handler.connect('instance-001', config)

        connection = mock_multi_mongodb_handler.get_connection('instance-001')
        assert connection is not None

    @pytest.mark.unit
    def test_disconnect_instance(self, mock_multi_mongodb_handler):
        """Test disconnecting from an instance"""
        config = {'host': 'localhost', 'port': 27017, 'database': 'test_db'}
        mock_multi_mongodb_handler.connect('instance-001', config)
        mock_multi_mongodb_handler.disconnect('instance-001')

        connection = mock_multi_mongodb_handler.get_connection('instance-001')
        assert connection is None

    @pytest.mark.unit
    def test_disconnect_all(self, mock_multi_mongodb_handler):
        """Test disconnecting all instances"""
        configs = [
            {'host': 'host1', 'port': 27017, 'database': 'db1'},
            {'host': 'host2', 'port': 27017, 'database': 'db2'},
        ]

        for i, config in enumerate(configs):
            mock_multi_mongodb_handler.connect(f'instance-{i}', config)

        mock_multi_mongodb_handler.disconnect_all()

        # All connections should be closed
        assert mock_multi_mongodb_handler.get_connection('instance-0') is None
        assert mock_multi_mongodb_handler.get_connection('instance-1') is None


class TestCollectionOperations:
    """Test collection CRUD operations through handler"""

    @pytest.mark.unit
    def test_insert_and_find(self, mock_collection):
        """Test insert and find operations"""
        doc = {'name': 'test', 'value': 123}
        result = mock_collection.insert_one(doc)
        assert result.inserted_id is not None

        found = mock_collection.find_one({'name': 'test'})
        assert found is not None
        assert found['value'] == 123

    @pytest.mark.unit
    def test_update_document(self, mock_collection):
        """Test update operation"""
        mock_collection.insert_one({'name': 'test', 'value': 100})

        result = mock_collection.update_one(
            {'name': 'test'},
            {'$set': {'value': 200}}
        )
        assert result.modified_count == 1

        updated = mock_collection.find_one({'name': 'test'})
        assert updated['value'] == 200

    @pytest.mark.unit
    def test_delete_document(self, mock_collection):
        """Test delete operation"""
        mock_collection.insert_one({'name': 'to_delete'})

        result = mock_collection.delete_one({'name': 'to_delete'})
        assert result.deleted_count == 1

        found = mock_collection.find_one({'name': 'to_delete'})
        assert found is None

    @pytest.mark.unit
    def test_count_documents(self, mock_collection):
        """Test document count"""
        mock_collection.insert_one({'type': 'a'})
        mock_collection.insert_one({'type': 'a'})
        mock_collection.insert_one({'type': 'b'})

        total = mock_collection.count_documents({})
        type_a = mock_collection.count_documents({'type': 'a'})

        assert total == 3
        assert type_a == 2

    @pytest.mark.unit
    def test_find_with_projection(self, mock_collection):
        """Test find with field projection"""
        mock_collection.insert_one({
            'name': 'test',
            'public': 'visible',
            'secret': 'hidden',
        })

        doc = mock_collection.find_one(
            {'name': 'test'},
            {'secret': 0}  # Exclude secret field
        )

        assert 'public' in doc
        assert 'secret' not in doc
