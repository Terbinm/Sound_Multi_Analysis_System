# Edge Device System Guide

## Overview

Edge Device System is a distributed audio recording system that allows remote edge clients to connect to a central state management server, receive recording commands, execute recordings, and upload audio files for analysis.

### Architecture

```
+-------------------+          WebSocket          +----------------------+
|   Edge Client     | <-------------------------> |   State Management   |
|  (edge_client.py) |                             |       Server         |
+-------------------+          HTTP POST          +----------------------+
         |          +-------------------------->           |
         |          (File Upload)                          |
         v                                                 v
+-------------------+                             +----------------------+
|  Audio Hardware   |                             |      MongoDB         |
|  (sounddevice)    |                             |  (GridFS for files)  |
+-------------------+                             +----------------------+
```

### Core Components

| Component | File | Description |
|-----------|------|-------------|
| Edge Client | `sub_system/edge_client/edge_client.py` | Main client application handling WebSocket communication |
| Config Manager | `sub_system/edge_client/config_manager.py` | Configuration loading, validation, and persistence |
| Audio Manager | `sub_system/edge_client/audio_manager.py` | Audio device management and recording |
| Device Manager | `core/state_management/services/edge_device_manager.py` | Server-side WebSocket event handling |
| Device API | `core/state_management/api/edge_device_api.py` | REST API endpoints |
| Device Model | `core/state_management/models/edge_device.py` | MongoDB data model |

---

## Communication Protocol

### WebSocket Events

#### Client to Server Events

| Event | Purpose | Data Format |
|-------|---------|-------------|
| `edge.register` | Device registration on connect | `{device_id?, device_name, platform, audio_config: {default_device_index, channels, sample_rate, bit_depth, available_devices[]}}` |
| `edge.heartbeat` | Periodic heartbeat (every 30s) | `{device_id, status, current_recording?, timestamp}` |
| `edge.recording_started` | Notify recording started | `{device_id, recording_uuid}` |
| `edge.recording_progress` | Report recording progress | `{device_id, recording_uuid, progress_percent}` |
| `edge.recording_completed` | Notify recording completed | `{device_id, recording_uuid, filename, file_size, file_hash, actual_duration}` |
| `edge.recording_failed` | Report recording failure | `{device_id, recording_uuid, error}` |
| `edge.audio_devices_response` | Response to device query | `{device_id, request_id, devices[]}` |
| `edge.status_changed` | Status change notification | `{device_id, status}` |

#### Server to Client Events

| Event | Purpose | Data Format |
|-------|---------|-------------|
| `edge.registered` | Registration confirmation | `{device_id, is_new}` |
| `edge.record` | Start recording command | `{recording_uuid, duration, channels, sample_rate, device_index, bit_depth}` |
| `edge.stop` | Stop recording command | `{recording_uuid}` |
| `edge.query_audio_devices` | Request audio device list | `{request_id}` |
| `edge.update_config` | Push config update | `{device_name?, audio_config?}` |
| `edge.error` | Error notification | `{error, message}` |

#### Server Broadcast Events (to Web UI)

| Event | Room | Description |
|-------|------|-------------|
| `edge_device.registered` | edge_devices | New device registered |
| `edge_device.offline` | edge_devices | Device went offline |
| `edge_device.online` | edge_devices | Device came online |
| `edge_device.status_changed` | edge_devices | Device status changed |
| `edge_device.heartbeat` | edge_devices | Heartbeat received |
| `edge_device.recording_started` | edge_devices | Recording started |
| `edge_device.recording_progress` | edge_devices | Recording progress update |
| `edge_device.recording_completed` | edge_devices | Recording completed |
| `edge_device.recording_failed` | edge_devices | Recording failed |
| `edge_device.recording_uploaded` | edge_devices | Recording file uploaded |
| `edge_device.stats_updated` | edge_devices | Statistics updated |

---

## REST API Endpoints

Base URL: `/api/edge-devices`

### Device Management

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/` | List all devices | Query: `status?` | `{success, data:[], count}` |
| GET | `/<device_id>` | Get device details | - | `{success, data:{...}}` |
| PUT | `/<device_id>` | Update device | `{device_name?}` | `{success, data:{...}}` |
| DELETE | `/<device_id>` | Delete device | Query: `force?` | `{success, message}` |
| GET | `/stats` | Get device statistics | - | `{success, data:{total_devices, online_devices, ...}}` |

### Recording Control

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| POST | `/<device_id>/record` | Send record command | `{duration, channels?, sample_rate?, device_index?, bit_depth?}` | `{success, data:{recording_uuid, parameters}}` |
| POST | `/<device_id>/stop` | Stop recording | - | `{success, message}` |
| GET | `/<device_id>/audio-devices` | Query audio devices | - | `{success, data:{available_devices[]}}` |

### Audio Configuration

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| PUT | `/<device_id>/audio-config` | Update audio config | `{default_device_index?, channels?, sample_rate?, bit_depth?}` | `{success, data:{...}}` |

### Schedule Management

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/<device_id>/schedule` | Get schedule config | - | `{success, data:{...}}` |
| PUT | `/<device_id>/schedule` | Update schedule | `{enabled?, interval_seconds?, duration_seconds?, start_time?, end_time?}` | `{success, data:{...}}` |
| POST | `/<device_id>/schedule/enable` | Enable schedule | - | `{success, message}` |
| POST | `/<device_id>/schedule/disable` | Disable schedule | - | `{success, message}` |

### Recording History

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/<device_id>/recordings` | Get recording history | Query: `limit?, skip?` | `{success, data:[], count, total}` |
| GET | `/recordings/<recording_uuid>` | Get recording details | - | `{success, data:{...}}` |
| GET | `/<device_id>/recordings/stats` | Get recording statistics | - | `{success, data:{total_recordings, success_count, ...}}` |

### Router Configuration

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/<device_id>/routers` | Get assigned routers | - | `{success, data:{assigned_router_ids, routers[]}}` |
| PUT | `/<device_id>/routers` | Update router assignment | `{router_ids[]}` | `{success, data:{assigned_router_ids}}` |

### File Upload

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| POST | `/upload_recording` | Upload recording file | Multipart: `file, device_id, recording_uuid, duration, file_size?, file_hash?` | `{success, file_id, analyze_uuid}` |

---

## Configuration

### Client Configuration (device_config.json)

```json
{
  "device_id": "uuid-string-or-null",
  "device_name": "Device_xxxxxx",
  "server_url": "http://localhost:55103",
  "audio_config": {
    "default_device_index": 0,
    "channels": 1,
    "sample_rate": 16000,
    "bit_depth": 16
  },
  "heartbeat_interval": 30,
  "reconnect_delay": 5,
  "max_reconnect_delay": 60,
  "temp_wav_dir": "temp_wav"
}
```

#### Parameter Description

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `device_id` | string/null | null | Unique device identifier (auto-generated if null) |
| `device_name` | string | auto | Human-readable device name |
| `server_url` | string | required | State management server URL |
| `heartbeat_interval` | int | 30 | Heartbeat interval in seconds |
| `reconnect_delay` | int | 5 | Initial reconnection delay in seconds |
| `max_reconnect_delay` | int | 60 | Maximum reconnection delay (exponential backoff cap) |
| `temp_wav_dir` | string | temp_wav | Temporary directory for recordings |

#### Audio Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `default_device_index` | int | 0 | Default audio input device index |
| `channels` | int | 1 | Number of audio channels (1=mono, 2=stereo) |
| `sample_rate` | int | 16000 | Audio sample rate in Hz |
| `bit_depth` | int | 16 | Audio bit depth (16 or 32) |

### Environment Variable Override

The following environment variables can override config file values:

| Variable | Overrides |
|----------|-----------|
| `EDGE_SERVER_URL` | server_url |
| `EDGE_DEVICE_NAME` | device_name |
| `EDGE_HEARTBEAT_INTERVAL` | heartbeat_interval |
| `EDGE_RECONNECT_DELAY` | reconnect_delay |
| `EDGE_MAX_RECONNECT_DELAY` | max_reconnect_delay |

### Server WebSocket Configuration

The server uses strict WebSocket timeout settings:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `WEBSOCKET_PING_INTERVAL` | 2 seconds | Server sends ping every 2 seconds |
| `WEBSOCKET_PING_TIMEOUT` | 6 seconds | Client must respond within 6 seconds |

**Important**: These settings are intentionally strict. The client must ensure it can respond to ping messages within the timeout period.

---

## Device Lifecycle

### Registration Flow

```
1. Client connects via WebSocket
2. Client sends 'edge.register' with device info
3. Server processes registration:
   - New device (no device_id): Generate new UUID
   - Existing device: Update connection info
   - Device ID exists but not in DB: Create new record with provided ID
4. Server responds with 'edge.registered' containing device_id
5. Client starts heartbeat thread
```

### Status States

| Status | Description |
|--------|-------------|
| `IDLE` | Device connected and idle |
| `RECORDING` | Device is currently recording |
| `OFFLINE` | Device disconnected or heartbeat timeout |

### Heartbeat Mechanism

- Client sends heartbeat every `heartbeat_interval` seconds (default: 30s)
- Server updates `last_heartbeat` timestamp on each heartbeat
- Device is considered offline if no heartbeat for 90 seconds (`EDGE_HEARTBEAT_TIMEOUT`)

---

## Recording Workflow

### Complete Recording Flow

```
1. Server sends 'edge.record' command
   {recording_uuid, duration, channels, sample_rate, device_index, bit_depth}

2. Client validates parameters and device state
   - Rejects if already recording

3. Client starts recording
   - Sends 'edge.recording_started' {device_id, recording_uuid}

4. Client reports progress periodically
   - Sends 'edge.recording_progress' {device_id, recording_uuid, progress_percent}

5. Recording completes
   - Success: Sends 'edge.recording_completed' with file info
   - Failure: Sends 'edge.recording_failed' with error

6. Client uploads file via HTTP POST to /upload_recording

7. Server stores file in GridFS and creates analysis record
```

### Recording Parameters

| Parameter | Type | Default | Constraints |
|-----------|------|---------|-------------|
| `duration` | int | required | >= 1 second |
| `channels` | int | 1 | 1 or 2 |
| `sample_rate` | int | 16000 | 8000, 16000, 22050, 44100, 48000 |
| `device_index` | int | 0 | Must be valid device index |
| `bit_depth` | int | 16 | 16 or 32 |

---

## Data Model

### MongoDB Document Structure

Collection: `edge_devices`

```json
{
  "_id": "device_id (UUID)",
  "device_name": "string",
  "status": "IDLE|OFFLINE|RECORDING",
  "platform": "linux|win32|darwin",
  "audio_config": {
    "default_device_index": 0,
    "channels": 1,
    "sample_rate": 16000,
    "bit_depth": 16,
    "available_devices": [
      {"index": 0, "name": "device_name", "max_input_channels": 2, ...}
    ]
  },
  "schedule_config": {
    "enabled": false,
    "interval_seconds": 3600,
    "duration_seconds": 60,
    "start_time": "HH:MM",
    "end_time": "HH:MM"
  },
  "connection_info": {
    "socket_id": "string",
    "ip_address": "string",
    "connected_at": "datetime",
    "last_heartbeat": "datetime",
    "current_recording": "uuid"
  },
  "statistics": {
    "total_recordings": 0,
    "success_count": 0,
    "error_count": 0,
    "last_recording_at": "datetime"
  },
  "assigned_router_ids": ["router_id_1", "router_id_2"],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## Troubleshooting Guide

### Common Issues

#### 1. Connection Drops After Some Time

**Symptoms**:
- Client shows connected but heartbeat stops being sent
- No disconnect event logged
- Server shows device as offline

**Possible Causes**:
- WebSocket ping/pong timeout (server sends ping every 2s, expects pong within 6s)
- Network instability
- Client event loop blocked

**Solutions**:
- Check `sio.connected` status in heartbeat loop
- Ensure client can respond to ping within 6 seconds
- Monitor for exceptions in heartbeat thread

#### 2. Device Not Registering

**Symptoms**:
- Client connects but doesn't appear in device list
- No `edge.registered` response received

**Possible Causes**:
- Server not processing `edge.register` event
- Database connection issue
- Invalid registration data

**Solutions**:
- Check server logs for registration errors
- Verify MongoDB connection
- Ensure all required fields are sent in registration

#### 3. Recording Upload Fails

**Symptoms**:
- Recording completes but file not uploaded
- HTTP timeout errors in client log

**Possible Causes**:
- Server unreachable via HTTP
- File too large
- Network timeout

**Solutions**:
- Verify server URL is accessible
- Check file size limits
- Increase upload timeout if needed

#### 4. Audio Device Not Found

**Symptoms**:
- Recording fails with device not found error
- Empty audio device list

**Possible Causes**:
- No audio input devices connected
- Device index changed
- Permission issues

**Solutions**:
- Run `python -m sounddevice` to list devices
- Update `default_device_index` in config
- Check audio device permissions

### Log Interpretation

#### Normal Connection Log

```
INFO - Edge client initialized: device_id=xxx, name=xxx
INFO - Attempting connection to server: http://localhost:55103
INFO - Connected to server
INFO - Sent device registration request
DEBUG - Heartbeat thread started
INFO - Device registration successful
DEBUG - Heartbeat sent: status=IDLE
```

#### Connection Lost Log

```
WARNING - SocketIO connection lost, stopping heartbeat thread
WARNING - Detected SocketIO disconnected
INFO - Disconnected from server, preparing to reconnect...
INFO - Attempting connection to server...
```

#### Recording Log

```
INFO - Received recording command: {duration: 60, ...}
INFO - Starting recording: duration=60s, channels=1, sample_rate=16000
DEBUG - Recording progress: 10%
DEBUG - Recording progress: 50%
DEBUG - Recording progress: 100%
INFO - Recording completed: filename.wav
INFO - Starting file upload: filename.wav
INFO - Upload completed, server verification passed
```

### Debug Mode

Enable debug logging by setting log level:

```python
logging.basicConfig(level=logging.DEBUG)
```

Or via environment variable:
```bash
set LOG_LEVEL=DEBUG
```

---

## Security Considerations

1. **Network Security**: Use HTTPS/WSS in production
2. **Authentication**: Consider adding device authentication tokens
3. **File Validation**: Server validates file hash and size on upload
4. **Input Validation**: All API inputs are validated before processing

---

## Performance Tuning

### Recommended Settings for Production

| Setting | Development | Production |
|---------|-------------|------------|
| `heartbeat_interval` | 30s | 30s |
| `reconnect_delay` | 5s | 5s |
| `max_reconnect_delay` | 60s | 120s |
| Log Level | DEBUG | INFO |

### Resource Considerations

- Each connected device maintains one WebSocket connection
- Recording files are stored temporarily on client before upload
- MongoDB GridFS stores all uploaded recordings
