"""
Data API
Provides audio streaming, download, and data deletion functionality
"""
import logging
from flask import Blueprint, request, jsonify, Response, abort
from flask_login import login_required
from bson import ObjectId
from werkzeug.exceptions import HTTPException
import gridfs

from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)

data_api_bp = Blueprint('data_api', __name__)


def _get_recording_and_file(analyze_uuid: str):
    """
    Get recording document and GridFS file info

    Returns:
        tuple: (record, file_id, fs) or raises 404
    """
    config = get_config()
    db = get_db()

    # Find the recording
    record = db[config.COLLECTIONS['recordings']].find_one({'AnalyzeUUID': analyze_uuid})
    if not record:
        abort(404, description='Recording not found')

    # Get file ID
    files = record.get('files', {})
    raw_file = files.get('raw', {})
    file_id = raw_file.get('fileId')

    if not file_id:
        abort(404, description='Audio file not found')

    # Convert string to ObjectId if needed
    if isinstance(file_id, str):
        file_id = ObjectId(file_id)

    fs = gridfs.GridFS(db)

    # Check if file exists in GridFS
    if not fs.exists(file_id):
        abort(404, description='Audio file not found in storage')

    return record, file_id, fs


@data_api_bp.route('/<analyze_uuid>/audio/stream', methods=['GET'])
@login_required
def stream_audio(analyze_uuid: str):
    """
    Stream audio file with HTTP Range support for seeking

    Supports partial content (206) for audio seeking in browser
    """
    try:
        record, file_id, fs = _get_recording_and_file(analyze_uuid)

        # Get the GridFS file
        grid_file = fs.get(file_id)
        file_size = grid_file.length
        content_type = grid_file.content_type or 'audio/wav'

        # Parse Range header
        range_header = request.headers.get('Range')

        if range_header:
            # Parse "bytes=start-end" format
            try:
                ranges = range_header.replace('bytes=', '').split('-')
                start = int(ranges[0]) if ranges[0] else 0
                end = int(ranges[1]) if ranges[1] else file_size - 1
            except (ValueError, IndexError):
                start = 0
                end = file_size - 1

            # Ensure valid range
            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))

            # Calculate content length
            content_length = end - start + 1

            # Seek to start position and read the range
            grid_file.seek(start)
            data = grid_file.read(content_length)

            # Build 206 Partial Content response
            response = Response(
                data,
                status=206,
                mimetype=content_type,
                direct_passthrough=True
            )
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response.headers['Accept-Ranges'] = 'bytes'
            response.headers['Content-Length'] = content_length
            # 允許 Web Audio API 存取
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Range, Accept-Ranges, Content-Length'

            return response

        else:
            # No Range header - return full file
            def generate():
                chunk_size = 1024 * 1024  # 1MB chunks
                while True:
                    chunk = grid_file.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

            response = Response(
                generate(),
                status=200,
                mimetype=content_type,
                direct_passthrough=True
            )
            response.headers['Accept-Ranges'] = 'bytes'
            response.headers['Content-Length'] = file_size
            # 允許 Web Audio API 存取
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Expose-Headers'] = 'Accept-Ranges, Content-Length'

            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio streaming failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@data_api_bp.route('/<analyze_uuid>/audio/download', methods=['GET'])
@login_required
def download_audio(analyze_uuid: str):
    """
    Download audio file as attachment
    """
    try:
        record, file_id, fs = _get_recording_and_file(analyze_uuid)

        # Get file info
        raw_file = record.get('files', {}).get('raw', {})
        filename = raw_file.get('filename', f'{analyze_uuid}.wav')

        # Get the GridFS file
        grid_file = fs.get(file_id)
        content_type = grid_file.content_type or 'audio/wav'

        def generate():
            chunk_size = 1024 * 1024  # 1MB chunks
            while True:
                chunk = grid_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        response = Response(
            generate(),
            status=200,
            mimetype=content_type,
            direct_passthrough=True
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = grid_file.length

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio download failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@data_api_bp.route('/<analyze_uuid>', methods=['DELETE'])
@login_required
def delete_recording(analyze_uuid: str):
    """
    Delete recording and associated GridFS files
    """
    try:
        config = get_config()
        db = get_db()
        fs = gridfs.GridFS(db)

        # Find the recording
        record = db[config.COLLECTIONS['recordings']].find_one({'AnalyzeUUID': analyze_uuid})
        if not record:
            return jsonify({'success': False, 'error': 'Recording not found'}), 404

        deleted_files = []
        errors = []

        # Delete GridFS files
        files = record.get('files', {})
        for file_type, file_info in files.items():
            if isinstance(file_info, dict) and 'fileId' in file_info:
                file_id = file_info['fileId']
                if isinstance(file_id, str):
                    file_id = ObjectId(file_id)

                try:
                    if fs.exists(file_id):
                        fs.delete(file_id)
                        deleted_files.append(file_type)
                        logger.info(f"Deleted GridFS file: {file_id} ({file_type})")
                except Exception as e:
                    errors.append(f"Failed to delete {file_type}: {str(e)}")
                    logger.error(f"Failed to delete GridFS file {file_id}: {e}")

        # Delete the recording document
        result = db[config.COLLECTIONS['recordings']].delete_one({'AnalyzeUUID': analyze_uuid})

        if result.deleted_count == 0:
            return jsonify({
                'success': False,
                'error': 'Failed to delete recording document'
            }), 500

        # Delete associated task execution logs
        logs_result = db[config.COLLECTIONS['task_execution_logs']].delete_many({
            'analyze_uuid': analyze_uuid
        })

        logger.info(
            f"Deleted recording: {analyze_uuid}, "
            f"files: {deleted_files}, logs: {logs_result.deleted_count}"
        )

        return jsonify({
            'success': True,
            'message': 'Recording deleted successfully',
            'deleted_files': deleted_files,
            'deleted_logs': logs_result.deleted_count,
            'errors': errors if errors else None
        })

    except Exception as e:
        logger.error(f"Delete recording failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@data_api_bp.route('/<analyze_uuid>/info', methods=['GET'])
@login_required
def get_recording_info(analyze_uuid: str):
    """
    Get recording information including audio metadata
    """
    try:
        config = get_config()
        db = get_db()

        record = db[config.COLLECTIONS['recordings']].find_one({'AnalyzeUUID': analyze_uuid})
        if not record:
            return jsonify({'success': False, 'error': 'Recording not found'}), 404

        # Get file info from GridFS
        files = record.get('files', {})
        raw_file = files.get('raw', {})
        file_id = raw_file.get('fileId')

        file_info = None
        if file_id:
            if isinstance(file_id, str):
                file_id = ObjectId(file_id)

            fs = gridfs.GridFS(db)
            if fs.exists(file_id):
                grid_file = fs.get(file_id)
                file_info = {
                    'filename': raw_file.get('filename'),
                    'file_size': grid_file.length,
                    'content_type': grid_file.content_type,
                    'upload_date': grid_file.upload_date.isoformat() if grid_file.upload_date else None,
                    'metadata': grid_file.metadata
                }

        # Extract info_features
        info_features = record.get('info_features', {})

        # Build response
        return jsonify({
            'success': True,
            'data': {
                'analyze_uuid': analyze_uuid,
                'file_info': file_info,
                'info_features': info_features,
                'created_at': record.get('created_at').isoformat() if record.get('created_at') else None,
                'updated_at': record.get('updated_at').isoformat() if record.get('updated_at') else None,
                'assigned_router_ids': record.get('assigned_router_ids', [])
            }
        })

    except Exception as e:
        logger.error(f"Get recording info failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
