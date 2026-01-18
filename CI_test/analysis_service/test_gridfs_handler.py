"""
Tests for GridFS Handler in Analysis Service

Tests cover:
- File retrieval
- File storage
- Metadata handling
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestFileRetrieval:
    """Test file retrieval from GridFS"""

    @pytest.mark.unit
    def test_get_recording_file(self, mock_gridfs_handler, sample_wav_content):
        """Test getting recording file from GridFS"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='recording.wav')

        gfs_file = mock_gridfs_handler.get(file_id)
        content = gfs_file.read()

        assert content == sample_wav_content

    @pytest.mark.unit
    def test_get_file_by_id(self, mock_gridfs_handler, sample_wav_content):
        """Test getting file by file ID"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='test.wav')

        gfs_file = mock_gridfs_handler.get(file_id)
        assert gfs_file._id == file_id

    @pytest.mark.unit
    def test_get_file_content_streaming(self, mock_gridfs_handler, sample_wav_content):
        """Test streaming file content"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='stream.wav')

        gfs_file = mock_gridfs_handler.get(file_id)

        # Read in chunks
        chunk_size = 1024
        chunks = []
        while True:
            chunk = gfs_file.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)

        full_content = b''.join(chunks)
        assert full_content == sample_wav_content

    @pytest.mark.unit
    def test_get_model_file(self, mock_gridfs_handler):
        """Test getting model file from GridFS"""
        model_content = b'mock onnx model binary'
        file_id = mock_gridfs_handler.put(
            model_content,
            filename='model.onnx',
            metadata={'type': 'model'}
        )

        gfs_file = mock_gridfs_handler.get(file_id)
        assert gfs_file.read() == model_content


class TestFileStorage:
    """Test file storage to GridFS"""

    @pytest.mark.unit
    def test_store_analysis_result(self, mock_gridfs_handler):
        """Test storing analysis result file"""
        result_data = b'{"classification": "normal", "confidence": 0.95}'

        file_id = mock_gridfs_handler.put(
            result_data,
            filename='result_001.json',
            metadata={
                'type': 'analysis_result',
                'recording_id': 'rec-001',
            }
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_store_processed_audio(self, mock_gridfs_handler, sample_wav_content):
        """Test storing processed audio file"""
        file_id = mock_gridfs_handler.put(
            sample_wav_content,
            filename='processed_audio.wav',
            metadata={
                'type': 'processed_audio',
                'original_file': 'original.wav',
                'processing_step': 'step1_slicer',
            }
        )

        assert file_id is not None

    @pytest.mark.unit
    def test_store_feature_file(self, mock_gridfs_handler):
        """Test storing feature extraction output"""
        import struct
        # Mock numpy array as bytes
        feature_data = struct.pack('f' * 100, *[0.0] * 100)

        file_id = mock_gridfs_handler.put(
            feature_data,
            filename='features_001.npy',
            metadata={
                'type': 'features',
                'feature_type': 'leaf',
                'shape': [10, 10],
            }
        )

        assert file_id is not None


class TestMetadataHandling:
    """Test file metadata handling"""

    @pytest.mark.unit
    def test_store_with_metadata(self, mock_gridfs_handler, sample_wav_content):
        """Test storing file with metadata"""
        metadata = {
            'recording_uuid': 'uuid-001',
            'device_id': 'device-001',
            'sample_rate': 16000,
            'channels': 1,
            'duration': 10.0,
        }

        file_id = mock_gridfs_handler.put(
            sample_wav_content,
            filename='recording.wav',
            metadata=metadata
        )

        gfs_file = mock_gridfs_handler.get(file_id)
        assert gfs_file.metadata == metadata

    @pytest.mark.unit
    def test_file_length(self, mock_gridfs_handler, sample_wav_content):
        """Test file length attribute"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='test.wav')

        gfs_file = mock_gridfs_handler.get(file_id)
        assert gfs_file.length == len(sample_wav_content)

    @pytest.mark.unit
    def test_file_upload_date(self, mock_gridfs_handler, sample_wav_content):
        """Test file upload date"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='test.wav')

        gfs_file = mock_gridfs_handler.get(file_id)
        assert gfs_file.upload_date is not None


class TestFileOperations:
    """Test various file operations"""

    @pytest.mark.unit
    def test_delete_file(self, mock_gridfs_handler, sample_wav_content):
        """Test deleting file from GridFS"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='to_delete.wav')

        mock_gridfs_handler.delete(file_id)

        assert not mock_gridfs_handler.exists(file_id=file_id)

    @pytest.mark.unit
    def test_check_file_exists(self, mock_gridfs_handler, sample_wav_content):
        """Test checking if file exists"""
        file_id = mock_gridfs_handler.put(sample_wav_content, filename='exists.wav')

        assert mock_gridfs_handler.exists(file_id=file_id) is True
        assert mock_gridfs_handler.exists(filename='exists.wav') is True

    @pytest.mark.unit
    def test_list_files(self, mock_gridfs_handler, sample_wav_content):
        """Test listing files"""
        mock_gridfs_handler.put(sample_wav_content, filename='file1.wav')
        mock_gridfs_handler.put(sample_wav_content, filename='file2.wav')
        mock_gridfs_handler.put(sample_wav_content, filename='file3.wav')

        files = mock_gridfs_handler.list()
        assert len(files) >= 3

    @pytest.mark.unit
    def test_find_files_by_filter(self, mock_gridfs_handler, sample_wav_content):
        """Test finding files with filter"""
        mock_gridfs_handler.put(sample_wav_content, filename='audio.wav')
        mock_gridfs_handler.put(b'model', filename='model.onnx')

        audio_files = list(mock_gridfs_handler.find({'filename': 'audio.wav'}))
        assert len(audio_files) >= 1
