"""
Mock MongoDB classes for testing

Provides comprehensive mocking of pymongo classes including:
- MongoClient
- Database
- Collection (with CRUD operations)
- Cursor
- GridFS / GridFSBucket
- ChangeStream
"""
import copy
import fnmatch
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Iterator, Callable, Union
from bson import ObjectId


class MockCursor:
    """Mock MongoDB Cursor for query results"""

    def __init__(self, documents: List[Dict[str, Any]], projection: Optional[Dict] = None):
        self._documents = documents
        self._projection = projection
        self._skip_count = 0
        self._limit_count = 0
        self._sort_key = None
        self._sort_direction = 1
        self._index = 0

    def skip(self, count: int) -> 'MockCursor':
        """Skip first n documents"""
        self._skip_count = count
        return self

    def limit(self, count: int) -> 'MockCursor':
        """Limit results to n documents"""
        self._limit_count = count
        return self

    def sort(self, key_or_list: Union[str, List], direction: int = 1) -> 'MockCursor':
        """Sort results"""
        if isinstance(key_or_list, str):
            self._sort_key = key_or_list
            self._sort_direction = direction
        elif isinstance(key_or_list, list) and len(key_or_list) > 0:
            self._sort_key = key_or_list[0][0]
            self._sort_direction = key_or_list[0][1]
        return self

    def _apply_projection(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Apply projection to document"""
        if not self._projection:
            return doc

        result = {}
        include_mode = any(v == 1 for v in self._projection.values() if v != 0)

        for key, value in doc.items():
            if key == '_id':
                if self._projection.get('_id', 1) != 0:
                    result[key] = value
            elif include_mode:
                if self._projection.get(key, 0) == 1:
                    result[key] = value
            else:
                if self._projection.get(key, 1) != 0:
                    result[key] = value

        return result

    def _get_processed_documents(self) -> List[Dict[str, Any]]:
        """Get documents after applying skip, limit, sort"""
        docs = self._documents[:]

        # Apply sort
        if self._sort_key:
            docs.sort(
                key=lambda x: x.get(self._sort_key, ''),
                reverse=(self._sort_direction == -1)
            )

        # Apply skip
        if self._skip_count:
            docs = docs[self._skip_count:]

        # Apply limit
        if self._limit_count:
            docs = docs[:self._limit_count]

        # Apply projection
        docs = [self._apply_projection(doc) for doc in docs]

        return docs

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        """Iterate over documents"""
        for doc in self._get_processed_documents():
            yield copy.deepcopy(doc)

    def __next__(self) -> Dict[str, Any]:
        """Get next document"""
        docs = self._get_processed_documents()
        if self._index >= len(docs):
            raise StopIteration
        doc = docs[self._index]
        self._index += 1
        return copy.deepcopy(doc)

    def count(self) -> int:
        """Count documents (deprecated but still used)"""
        return len(self._get_processed_documents())

    def count_documents(self) -> int:
        """Count documents"""
        return len(self._get_processed_documents())

    def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        """Convert cursor to list"""
        docs = self._get_processed_documents()
        if length:
            docs = docs[:length]
        return [copy.deepcopy(doc) for doc in docs]


class MockChangeStream:
    """Mock MongoDB Change Stream for watching collection changes"""

    def __init__(self, collection: 'MockCollection'):
        self._collection = collection
        self._changes: List[Dict[str, Any]] = []
        self._is_alive = True
        self._lock = threading.Lock()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return self

    def __next__(self) -> Dict[str, Any]:
        """Get next change event"""
        while self._is_alive:
            with self._lock:
                if self._changes:
                    return self._changes.pop(0)
            time.sleep(0.01)
        raise StopIteration

    def close(self) -> None:
        """Close the change stream"""
        self._is_alive = False

    def _push_change(self, operation_type: str, document: Dict[str, Any],
                     document_key: Optional[Dict] = None) -> None:
        """Push a change event (for testing)"""
        with self._lock:
            self._changes.append({
                'operationType': operation_type,
                'fullDocument': copy.deepcopy(document),
                'documentKey': document_key or {'_id': document.get('_id')},
                'clusterTime': datetime.now(timezone.utc),
            })

    @property
    def alive(self) -> bool:
        return self._is_alive


class MockInsertOneResult:
    """Mock result for insert_one operation"""
    def __init__(self, inserted_id: Any, acknowledged: bool = True):
        self.inserted_id = inserted_id
        self.acknowledged = acknowledged


class MockInsertManyResult:
    """Mock result for insert_many operation"""
    def __init__(self, inserted_ids: List[Any], acknowledged: bool = True):
        self.inserted_ids = inserted_ids
        self.acknowledged = acknowledged


class MockUpdateResult:
    """Mock result for update operations"""
    def __init__(self, matched_count: int, modified_count: int,
                 upserted_id: Optional[Any] = None, acknowledged: bool = True):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id
        self.acknowledged = acknowledged


class MockDeleteResult:
    """Mock result for delete operations"""
    def __init__(self, deleted_count: int, acknowledged: bool = True):
        self.deleted_count = deleted_count
        self.acknowledged = acknowledged


class MockCollection:
    """
    Mock MongoDB Collection with full CRUD support

    Supports:
    - find, find_one, find_one_and_update, find_one_and_delete
    - insert_one, insert_many
    - update_one, update_many
    - delete_one, delete_many
    - count_documents, estimated_document_count
    - create_index, drop_index
    - watch (change streams)
    - aggregate (basic support)
    """

    def __init__(self, name: str, database: 'MockDatabase'):
        self.name = name
        self.database = database
        self._documents: List[Dict[str, Any]] = []
        self._indexes: Dict[str, Dict] = {}
        self._change_streams: List[MockChangeStream] = []
        self._lock = threading.Lock()

    def _match_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if document matches query"""
        if not query:
            return True

        for key, condition in query.items():
            # Handle special operators
            if key.startswith('$'):
                if key == '$and':
                    if not all(self._match_query(doc, q) for q in condition):
                        return False
                elif key == '$or':
                    if not any(self._match_query(doc, q) for q in condition):
                        return False
                elif key == '$nor':
                    if any(self._match_query(doc, q) for q in condition):
                        return False
                continue

            # Get nested value
            value = self._get_nested_value(doc, key)

            # Handle condition types
            if isinstance(condition, dict):
                if not self._match_operators(value, condition):
                    return False
            else:
                # Direct equality or array containment
                if isinstance(value, list):
                    # If document field is an array, check if condition is in array
                    if condition not in value:
                        return False
                elif value != condition:
                    return False

        return True

    def _get_nested_value(self, doc: Dict[str, Any], key: str) -> Any:
        """Get nested value using dot notation"""
        keys = key.split('.')
        value = doc
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        return value

    def _match_operators(self, value: Any, operators: Dict[str, Any]) -> bool:
        """Match MongoDB query operators"""
        for op, op_value in operators.items():
            if op == '$eq':
                if value != op_value:
                    return False
            elif op == '$ne':
                if value == op_value:
                    return False
            elif op == '$gt':
                if value is None or value <= op_value:
                    return False
            elif op == '$gte':
                if value is None or value < op_value:
                    return False
            elif op == '$lt':
                if value is None or value >= op_value:
                    return False
            elif op == '$lte':
                if value is None or value > op_value:
                    return False
            elif op == '$in':
                if value not in op_value:
                    return False
            elif op == '$nin':
                if value in op_value:
                    return False
            elif op == '$exists':
                if (value is not None) != op_value:
                    return False
            elif op == '$regex':
                if value is None:
                    return False
                pattern = op_value
                flags = operators.get('$options', '')
                regex_flags = 0
                if 'i' in flags:
                    regex_flags |= re.IGNORECASE
                if not re.search(pattern, str(value), regex_flags):
                    return False
            elif op == '$type':
                # Simplified type matching
                pass
        return True

    def _apply_update(self, doc: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """Apply update operators to document"""
        updated = copy.deepcopy(doc)

        for op, fields in update.items():
            if op == '$set':
                for key, value in fields.items():
                    self._set_nested_value(updated, key, value)
            elif op == '$unset':
                for key in fields:
                    self._unset_nested_value(updated, key)
            elif op == '$inc':
                for key, value in fields.items():
                    current = self._get_nested_value(updated, key) or 0
                    self._set_nested_value(updated, key, current + value)
            elif op == '$push':
                for key, value in fields.items():
                    current = self._get_nested_value(updated, key) or []
                    if isinstance(value, dict) and '$each' in value:
                        current.extend(value['$each'])
                    else:
                        current.append(value)
                    self._set_nested_value(updated, key, current)
            elif op == '$pull':
                for key, value in fields.items():
                    current = self._get_nested_value(updated, key) or []
                    self._set_nested_value(updated, key, [x for x in current if x != value])
            elif op == '$addToSet':
                for key, value in fields.items():
                    current = self._get_nested_value(updated, key) or []
                    if value not in current:
                        current.append(value)
                    self._set_nested_value(updated, key, current)
            elif op == '$currentDate':
                for key, value in fields.items():
                    self._set_nested_value(updated, key, datetime.now(timezone.utc))
            elif not op.startswith('$'):
                # Direct field replacement (not recommended but supported)
                updated[op] = fields

        return updated

    def _set_nested_value(self, doc: Dict[str, Any], key: str, value: Any) -> None:
        """Set nested value using dot notation"""
        keys = key.split('.')
        current = doc
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def _unset_nested_value(self, doc: Dict[str, Any], key: str) -> None:
        """Remove nested value using dot notation"""
        keys = key.split('.')
        current = doc
        for k in keys[:-1]:
            if k not in current:
                return
            current = current[k]
        current.pop(keys[-1], None)

    def find(self, filter: Optional[Dict] = None, projection: Optional[Dict] = None,
             *args, **kwargs) -> MockCursor:
        """Find documents matching filter"""
        filter = filter or {}
        with self._lock:
            matched = [doc for doc in self._documents if self._match_query(doc, filter)]
        return MockCursor(matched, projection)

    def find_one(self, filter: Optional[Dict] = None, projection: Optional[Dict] = None,
                 sort: Optional[List] = None, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Find one document matching filter"""
        cursor = self.find(filter, projection)
        if sort:
            cursor.sort(sort)
        for doc in cursor:
            return doc
        return None

    def find_one_and_update(self, filter: Dict, update: Dict,
                            return_document: bool = False,
                            upsert: bool = False, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Find and update one document"""
        with self._lock:
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    if not return_document:
                        original = copy.deepcopy(doc)
                    self._documents[i] = self._apply_update(doc, update)
                    self._notify_change('update', self._documents[i])
                    return self._documents[i] if return_document else original

            if upsert:
                new_doc = {'_id': ObjectId()}
                new_doc.update(filter)
                new_doc = self._apply_update(new_doc, update)
                self._documents.append(new_doc)
                self._notify_change('insert', new_doc)
                return new_doc if return_document else None

        return None

    def find_one_and_delete(self, filter: Dict, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Find and delete one document"""
        with self._lock:
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    deleted = self._documents.pop(i)
                    self._notify_change('delete', deleted)
                    return deleted
        return None

    def insert_one(self, document: Dict[str, Any], *args, **kwargs) -> MockInsertOneResult:
        """Insert one document"""
        doc = copy.deepcopy(document)
        if '_id' not in doc:
            doc['_id'] = ObjectId()

        with self._lock:
            self._documents.append(doc)
            self._notify_change('insert', doc)

        return MockInsertOneResult(doc['_id'])

    def insert_many(self, documents: List[Dict[str, Any]], *args, **kwargs) -> MockInsertManyResult:
        """Insert multiple documents"""
        inserted_ids = []
        for document in documents:
            result = self.insert_one(document)
            inserted_ids.append(result.inserted_id)
        return MockInsertManyResult(inserted_ids)

    def update_one(self, filter: Dict, update: Dict, upsert: bool = False,
                   *args, **kwargs) -> MockUpdateResult:
        """Update one document"""
        with self._lock:
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    self._documents[i] = self._apply_update(doc, update)
                    self._notify_change('update', self._documents[i])
                    return MockUpdateResult(1, 1)

            if upsert:
                new_doc = {'_id': ObjectId()}
                new_doc.update(filter)
                new_doc = self._apply_update(new_doc, update)
                self._documents.append(new_doc)
                self._notify_change('insert', new_doc)
                return MockUpdateResult(0, 0, new_doc['_id'])

        return MockUpdateResult(0, 0)

    def update_many(self, filter: Dict, update: Dict, upsert: bool = False,
                    *args, **kwargs) -> MockUpdateResult:
        """Update multiple documents"""
        matched = 0
        modified = 0

        with self._lock:
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    matched += 1
                    old_doc = copy.deepcopy(doc)
                    self._documents[i] = self._apply_update(doc, update)
                    if self._documents[i] != old_doc:
                        modified += 1
                        self._notify_change('update', self._documents[i])

        return MockUpdateResult(matched, modified)

    def delete_one(self, filter: Dict, *args, **kwargs) -> MockDeleteResult:
        """Delete one document"""
        with self._lock:
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    deleted = self._documents.pop(i)
                    self._notify_change('delete', deleted)
                    return MockDeleteResult(1)
        return MockDeleteResult(0)

    def delete_many(self, filter: Dict, *args, **kwargs) -> MockDeleteResult:
        """Delete multiple documents"""
        deleted_count = 0
        with self._lock:
            to_delete = []
            for i, doc in enumerate(self._documents):
                if self._match_query(doc, filter):
                    to_delete.append(i)

            for i in reversed(to_delete):
                deleted = self._documents.pop(i)
                self._notify_change('delete', deleted)
                deleted_count += 1

        return MockDeleteResult(deleted_count)

    def count_documents(self, filter: Optional[Dict] = None, *args, **kwargs) -> int:
        """Count documents matching filter"""
        filter = filter or {}
        with self._lock:
            return sum(1 for doc in self._documents if self._match_query(doc, filter))

    def estimated_document_count(self) -> int:
        """Estimate document count"""
        return len(self._documents)

    def distinct(self, key: str, filter: Optional[Dict] = None, *args, **kwargs) -> List[Any]:
        """Get distinct values for a field"""
        filter = filter or {}
        values = set()
        with self._lock:
            for doc in self._documents:
                if self._match_query(doc, filter):
                    value = self._get_nested_value(doc, key)
                    if value is not None:
                        values.add(value)
        return list(values)

    def create_index(self, keys: Union[str, List], **kwargs) -> str:
        """Create an index"""
        if isinstance(keys, str):
            index_name = f"{keys}_1"
        else:
            index_name = '_'.join(f"{k}_{d}" for k, d in keys)

        self._indexes[index_name] = {
            'keys': keys,
            'options': kwargs,
        }
        return index_name

    def drop_index(self, index_name: str) -> None:
        """Drop an index"""
        self._indexes.pop(index_name, None)

    def list_indexes(self) -> List[Dict]:
        """List all indexes"""
        return [{'name': name, **info} for name, info in self._indexes.items()]

    def aggregate(self, pipeline: List[Dict], *args, **kwargs) -> MockCursor:
        """Basic aggregation support"""
        result = self._documents[:]

        for stage in pipeline:
            for op, value in stage.items():
                if op == '$match':
                    result = [doc for doc in result if self._match_query(doc, value)]
                elif op == '$project':
                    result = [self._project_doc(doc, value) for doc in result]
                elif op == '$limit':
                    result = result[:value]
                elif op == '$skip':
                    result = result[value:]
                elif op == '$sort':
                    for key, direction in reversed(list(value.items())):
                        result.sort(
                            key=lambda x: x.get(key, ''),
                            reverse=(direction == -1)
                        )

        return MockCursor(result)

    def _project_doc(self, doc: Dict, projection: Dict) -> Dict:
        """Apply projection in aggregation"""
        cursor = MockCursor([doc], projection)
        for d in cursor:
            return d
        return {}

    def watch(self, pipeline: Optional[List] = None, *args, **kwargs) -> MockChangeStream:
        """Watch collection for changes"""
        stream = MockChangeStream(self)
        self._change_streams.append(stream)
        return stream

    def _notify_change(self, operation_type: str, document: Dict[str, Any]) -> None:
        """Notify all change streams of a change"""
        for stream in self._change_streams:
            if stream.alive:
                stream._push_change(operation_type, document)

    def drop(self) -> None:
        """Drop the collection"""
        with self._lock:
            self._documents.clear()
            self._indexes.clear()


class MockDatabase:
    """Mock MongoDB Database"""

    def __init__(self, name: str, client: 'MockMongoClient'):
        self.name = name
        self.client = client
        self._collections: Dict[str, MockCollection] = {}
        self._lock = threading.Lock()

    def __getitem__(self, name: str) -> MockCollection:
        return self.get_collection(name)

    def __getattr__(self, name: str) -> MockCollection:
        if name.startswith('_'):
            raise AttributeError(name)
        return self.get_collection(name)

    def get_collection(self, name: str, *args, **kwargs) -> MockCollection:
        """Get or create a collection"""
        with self._lock:
            if name not in self._collections:
                self._collections[name] = MockCollection(name, self)
            return self._collections[name]

    def list_collection_names(self) -> List[str]:
        """List all collection names"""
        return list(self._collections.keys())

    def create_collection(self, name: str, *args, **kwargs) -> MockCollection:
        """Create a new collection"""
        return self.get_collection(name)

    def drop_collection(self, name: str) -> None:
        """Drop a collection"""
        with self._lock:
            if name in self._collections:
                self._collections[name].drop()
                del self._collections[name]

    def command(self, command: Union[str, Dict], *args, **kwargs) -> Dict:
        """Execute database command"""
        if isinstance(command, str):
            if command == 'ping':
                return {'ok': 1}
            elif command == 'serverStatus':
                return {'ok': 1, 'version': '4.4.0', 'uptime': 1000}
        elif isinstance(command, dict):
            if 'ping' in command:
                return {'ok': 1}
        return {'ok': 1}


class MockMongoClient:
    """Mock MongoDB Client"""

    def __init__(self, host: str = 'localhost', port: int = 27017, *args, **kwargs):
        self.host = host
        self.port = port
        self._databases: Dict[str, MockDatabase] = {}
        self._lock = threading.Lock()
        self._server_info = {
            'version': '4.4.0',
            'gitVersion': 'mock',
            'modules': [],
            'allocator': 'mock',
            'javascriptEngine': 'mock',
            'sysInfo': 'mock',
            'versionArray': [4, 4, 0, 0],
            'ok': 1,
        }

    def __getitem__(self, name: str) -> MockDatabase:
        return self.get_database(name)

    def __getattr__(self, name: str) -> MockDatabase:
        if name.startswith('_'):
            raise AttributeError(name)
        return self.get_database(name)

    def get_database(self, name: str, *args, **kwargs) -> MockDatabase:
        """Get or create a database"""
        with self._lock:
            if name not in self._databases:
                self._databases[name] = MockDatabase(name, self)
            return self._databases[name]

    def list_database_names(self) -> List[str]:
        """List all database names"""
        return list(self._databases.keys())

    def server_info(self) -> Dict:
        """Get server info"""
        return self._server_info

    def admin(self) -> MockDatabase:
        """Get admin database"""
        return self.get_database('admin')

    def close(self) -> None:
        """Close the client"""
        pass

    def drop_database(self, name: str) -> None:
        """Drop a database"""
        with self._lock:
            if name in self._databases:
                del self._databases[name]


class MockGridFSFile:
    """Mock GridFS file object"""

    def __init__(self, file_id: Any, filename: str, content: bytes, metadata: Optional[Dict] = None):
        self._id = file_id
        self.filename = filename
        self._content = content
        self.metadata = metadata or {}
        self.length = len(content)
        self.upload_date = datetime.now(timezone.utc)
        self.md5 = 'mock_md5_hash'
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        """Read file content"""
        if size < 0:
            data = self._content[self._position:]
            self._position = len(self._content)
        else:
            data = self._content[self._position:self._position + size]
            self._position += size
        return data

    def seek(self, position: int) -> None:
        """Seek to position"""
        self._position = position

    def tell(self) -> int:
        """Get current position"""
        return self._position

    def close(self) -> None:
        """Close file"""
        pass


class MockGridFS:
    """Mock GridFS for file storage"""

    def __init__(self, database: Optional[MockDatabase] = None, collection: str = 'fs'):
        self.database = database
        self.collection = collection
        self._files: Dict[Any, MockGridFSFile] = {}
        self._lock = threading.Lock()

    def put(self, data: bytes, filename: str = None, **kwargs) -> ObjectId:
        """Store file in GridFS"""
        file_id = ObjectId()
        gfs_file = MockGridFSFile(file_id, filename or str(file_id), data, kwargs.get('metadata'))
        with self._lock:
            self._files[file_id] = gfs_file
        return file_id

    def get(self, file_id: Any) -> MockGridFSFile:
        """Get file from GridFS"""
        with self._lock:
            if file_id in self._files:
                return self._files[file_id]
        raise Exception(f"No file found with id: {file_id}")

    def get_last_version(self, filename: str) -> MockGridFSFile:
        """Get last version of file by filename"""
        with self._lock:
            for gfs_file in reversed(list(self._files.values())):
                if gfs_file.filename == filename:
                    return gfs_file
        raise Exception(f"No file found with filename: {filename}")

    def delete(self, file_id: Any) -> None:
        """Delete file from GridFS"""
        with self._lock:
            self._files.pop(file_id, None)

    def exists(self, file_id: Any = None, filename: str = None) -> bool:
        """Check if file exists"""
        with self._lock:
            if file_id:
                return file_id in self._files
            if filename:
                return any(f.filename == filename for f in self._files.values())
        return False

    def list(self) -> List[str]:
        """List all filenames"""
        with self._lock:
            return [f.filename for f in self._files.values()]

    def find(self, filter: Optional[Dict] = None, *args, **kwargs) -> Iterator[MockGridFSFile]:
        """Find files matching filter"""
        filter = filter or {}
        with self._lock:
            for gfs_file in self._files.values():
                match = True
                for key, value in filter.items():
                    if key == 'filename' and gfs_file.filename != value:
                        match = False
                    elif key == '_id' and gfs_file._id != value:
                        match = False
                if match:
                    yield gfs_file


class MockGridFSBucket:
    """Mock GridFS Bucket (newer API)"""

    def __init__(self, database: MockDatabase, bucket_name: str = 'fs', *args, **kwargs):
        self.database = database
        self.bucket_name = bucket_name
        self._gridfs = MockGridFS(database, bucket_name)

    def upload_from_stream(self, filename: str, source: bytes, metadata: Optional[Dict] = None) -> ObjectId:
        """Upload file from stream"""
        return self._gridfs.put(source, filename=filename, metadata=metadata)

    def download_to_stream(self, file_id: Any, destination) -> None:
        """Download file to stream"""
        gfs_file = self._gridfs.get(file_id)
        destination.write(gfs_file.read())

    def open_download_stream(self, file_id: Any) -> MockGridFSFile:
        """Open download stream"""
        return self._gridfs.get(file_id)

    def delete(self, file_id: Any) -> None:
        """Delete file"""
        self._gridfs.delete(file_id)

    def find(self, filter: Optional[Dict] = None, *args, **kwargs) -> Iterator[MockGridFSFile]:
        """Find files"""
        return self._gridfs.find(filter, *args, **kwargs)
