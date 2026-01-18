"""
Tests for Upload API

Tests cover:
- File upload handling
- GridFS integration
- Metadata extraction
- Upload validation
"""
import pytest
import io
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestFileUpload:
    """Test file upload functionality"""

    @pytest.mark.unit
    def test_upload_wav_file(self, mock_gridfs_handler, sample_wav_content):
        """Test uploading WAV file"""
        file_id = mock_gridfs_handler.put(
            sample_wav_content,
            filename='test_audio.wav',
            metadata={'device_id': 'device-001', 'type': 'recording'}
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_upload_with_metadata(self, mock_gridfs_handler, sample_wav_content):
        """Test upload with metadata"""
        metadata = {
            'device_id': 'device-001',
            'recording_uuid': 'uuid-001',
            'sample_rate': 16000,
            'channels': 1,
            'duration': 10.0,
        }

        file_id = mock_gridfs_handler.put(
            sample_wav_content,
            filename='recording.wav',
            metadata=metadata
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_upload_creates_recording_document(self, mock_get_db, sample_wav_content):
        """Test that upload creates recording document"""
        recordings_collection = mock_get_db['recordings']

        recording_doc = {
            'recording_uuid': 'uuid-001',
            'device_id': 'device-001',
            'filename': 'recording.wav',
            'file_size': len(sample_wav_content),
            'sample_rate': 16000,
            'channels': 1,
            'upload_status': 'completed',
            'analysis_status': 'pending',
            'created_at': datetime.now(timezone.utc),
        }

        result = recordings_collection.insert_one(recording_doc)
        assert result.inserted_id is not None

        recording = recordings_collection.find_one({'recording_uuid': 'uuid-001'})
        assert recording is not None
        assert recording['upload_status'] == 'completed'


class TestGridFSIntegration:
    """Test GridFS file storage integration"""

    @pytest.mark.unit
    def test_store_file_in_gridfs(self, mock_gridfs_handler, sample_wav_content):
        """Test storing file in GridFS"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='test.wav')
        assert file_id is not None

    @pytest.mark.unit
    def test_retrieve_file_from_gridfs(self, mock_gridfs_handler, sample_wav_content):
        """Test retrieving file from GridFS"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='test.wav')

        gfs_file = mock_gridfs_handler.get(file_id)
        content = gfs_file.read()

        assert content == sample_wav_content

    @pytest.mark.unit
    def test_delete_file_from_gridfs(self, mock_gridfs_handler, sample_wav_content):
        """Test deleting file from GridFS"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='to_delete.wav')

        mock_gridfs_handler.delete(file_id)

        assert not mock_gridfs_handler.exists(file_id=file_id)

    @pytest.mark.unit
    def test_file_exists_check(self, mock_gridfs_handler, sample_wav_content):
        """Test checking if file exists"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='exists.wav')

        assert mock_gridfs_handler.exists(file_id=file_id) is True
        assert mock_gridfs_handler.exists(filename='exists.wav') is True

    @pytest.mark.unit
    def test_get_file_by_filename(self, mock_gridfs_handler, sample_wav_content):
        """Test getting file by filename"""
        mock_gridfs_handler.put(sample_wav_content, filename='named_file.wav')

        gfs_file = mock_gridfs_handler.get_last_version('named_file.wav')
        assert gfs_file.filename == 'named_file.wav'


class TestModelFileUpload:
    """Test model file upload for analysis configs"""

    @pytest.mark.unit
    def test_upload_onnx_model(self, mock_gridfs_handler):
        """Test uploading ONNX model file"""
        model_content = b'mock onnx model binary content'

        file_id = mock_gridfs_handler.put(
            model_content,
            filename='classifier.onnx',
            metadata={
                'type': 'model',
                'format': 'onnx',
                'version': '1.0.0',
            }
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_upload_label_mapping(self, mock_gridfs_handler):
        """Test uploading label mapping file"""
        import json

        labels = {
            '0': 'normal',
            '1': 'anomaly',
            '2': 'unknown',
        }
        label_content = json.dumps(labels).encode('utf-8')

        file_id = mock_gridfs_handler.put(
            label_content,
            filename='labels.json',
            metadata={'type': 'label_mapping'}
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_update_config_with_model_file(self, mock_get_db, mock_gridfs_handler):
        """Test updating config with uploaded model file"""
        configs_collection = mock_get_db['analysis_configs']

        # Create config
        configs_collection.insert_one({
            'config_id': 'model-config',
            'config_name': 'Model Config',
            'model_files': {},
        })

        # Upload model
        model_content = b'model binary'
        file_id = mock_gridfs_handler.put(model_content, filename='model.onnx')

        # Update config
        configs_collection.update_one(
            {'config_id': 'model-config'},
            {
                '$set': {
                    'model_files.onnx_model': {
                        'file_id': str(file_id),
                        'filename': 'model.onnx',
                        'version': '1.0.0',
                    }
                }
            }
        )

        config = configs_collection.find_one({'config_id': 'model-config'})
        assert config['model_files']['onnx_model']['filename'] == 'model.onnx'


class TestUploadValidation:
    """Test upload validation"""

    @pytest.mark.unit
    def test_validate_wav_format(self, sample_wav_content):
        """Test validating WAV file format"""
        # Check WAV header
        is_valid_wav = sample_wav_content[:4] == b'RIFF' and sample_wav_content[8:12] == b'WAVE'
        assert is_valid_wav is True

    @pytest.mark.unit
    def test_validate_file_size(self, sample_wav_content):
        """Test file size validation"""
        max_size = 100 * 1024 * 1024  # 100MB limit
        file_size = len(sample_wav_content)

        is_valid_size = file_size <= max_size
        assert is_valid_size is True

    @pytest.mark.unit
    def test_reject_oversized_file(self):
        """Test rejecting oversized file"""
        max_size = 1024  # 1KB limit for test
        large_content = b'x' * 2048  # 2KB

        is_valid = len(large_content) <= max_size
        assert is_valid is False

    @pytest.mark.unit
    def test_validate_file_extension(self):
        """Test validating file extension"""
        allowed_extensions = {'wav', 'mp3', 'flac', 'ogg'}

        valid_filenames = ['audio.wav', 'audio.mp3', 'audio.flac']
        invalid_filenames = ['audio.txt', 'audio.exe', 'audio']

        for fname in valid_filenames:
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            assert ext in allowed_extensions

        for fname in invalid_filenames:
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            assert ext not in allowed_extensions or ext == ''


class TestUploadStatusTracking:
    """Test upload status tracking"""

    @pytest.mark.unit
    def test_track_upload_progress(self, mock_get_db):
        """Test tracking upload progress"""
        uploads_collection = mock_get_db['upload_progress']

        upload_status = {
            'upload_id': 'upload-001',
            'filename': 'large_file.wav',
            'total_size': 1000000,
            'uploaded_bytes': 0,
            'status': 'in_progress',
            'started_at': datetime.now(timezone.utc),
        }

        uploads_collection.insert_one(upload_status)

        # Simulate progress update
        uploads_collection.update_one(
            {'upload_id': 'upload-001'},
            {'$set': {'uploaded_bytes': 500000}}
        )

        status = uploads_collection.find_one({'upload_id': 'upload-001'})
        assert status['uploaded_bytes'] == 500000

    @pytest.mark.unit
    def test_complete_upload(self, mock_get_db):
        """Test completing upload"""
        uploads_collection = mock_get_db['upload_progress']

        uploads_collection.insert_one({
            'upload_id': 'upload-001',
            'status': 'in_progress',
        })

        uploads_collection.update_one(
            {'upload_id': 'upload-001'},
            {
                '$set': {
                    'status': 'completed',
                    'completed_at': datetime.now(timezone.utc),
                }
            }
        )

        status = uploads_collection.find_one({'upload_id': 'upload-001'})
        assert status['status'] == 'completed'

    @pytest.mark.unit
    def test_failed_upload(self, mock_get_db):
        """Test failed upload handling"""
        uploads_collection = mock_get_db['upload_progress']

        uploads_collection.insert_one({
            'upload_id': 'upload-fail',
            'status': 'in_progress',
        })

        uploads_collection.update_one(
            {'upload_id': 'upload-fail'},
            {
                '$set': {
                    'status': 'failed',
                    'error_message': 'Connection lost',
                    'failed_at': datetime.now(timezone.utc),
                }
            }
        )

        status = uploads_collection.find_one({'upload_id': 'upload-fail'})
        assert status['status'] == 'failed'
        assert status['error_message'] == 'Connection lost'
