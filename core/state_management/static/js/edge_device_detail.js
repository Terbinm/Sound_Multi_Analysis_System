/**
 * Edge Device Detail Page JavaScript
 * 設備詳情頁面的主要邏輯
 */

// ==================== Modal 管理器 ====================
const ModalManager = {
    /**
     * 開啟 Modal
     * @param {string} modalId - Modal 的 ID
     * @param {Function|null} onOpen - 開啟後的回調函數
     */
    open(modalId, onOpen = null) {
        const modal = document.getElementById(modalId);
        if (!modal) {
            console.warn(`Modal "${modalId}" not found`);
            return;
        }

        modal.classList.remove('hidden');
        requestAnimationFrame(() => {
            modal.style.display = 'flex';
            if (onOpen) onOpen();
        });
    },

    /**
     * 關閉 Modal
     * @param {string} modalId - Modal 的 ID
     * @param {Function|null} onClose - 關閉後的回調函數
     */
    close(modalId, onClose = null) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        modal.style.display = 'none';
        modal.classList.add('hidden');
        if (onClose) onClose();
    },

    /**
     * 關閉所有 Modal
     */
    closeAll() {
        const modals = document.querySelectorAll('[id$="-modal"]');
        modals.forEach(modal => {
            modal.style.display = 'none';
            modal.classList.add('hidden');
        });
    }
};

// ==================== Edge Device Detail Controller ====================
class EdgeDeviceDetail {
    constructor(deviceId, initialManagerIds = []) {
        this.deviceId = deviceId;
        this.currentManagerIds = initialManagerIds;
        this.socket = null;

        this.offlineReasonDisplay = {
            'never_connected': '從未連線',
            'heartbeat_timeout': '心跳超時',
            'connection_lost': '連線中斷'
        };

        this.init();
    }

    init() {
        this.initSocket();
        this.initEventListeners();

        // 頁面載入時載入管理人員顯示
        if (this.currentManagerIds.length > 0) {
            this.loadManagersDisplay();
        }
    }

    // ==================== Socket.IO ====================
    initSocket() {
        this.socket = io();

        // 修復 3：改善訂閱時機 - 確保無論連接狀態都能訂閱
        const subscribeToRoom = () => {
            this.socket.emit('subscribe', {room: 'edge_devices'});
        };

        // 如果 Socket 已連接，立即訂閱
        if (this.socket.connected) {
            subscribeToRoom();
        }

        // 監聽連接事件（重新連接時也會觸發）
        this.socket.on('connect', subscribeToRoom);

        // 狀態更新
        this.socket.on('edge_device.status_changed', (data) => {
            if (data.device_id === this.deviceId) {
                this.updateStatusDisplay(data.status, data.offline_reason, data.offline_reason_display);
            }
        });

        // 設備離線
        this.socket.on('edge_device.offline', (data) => {
            if (data.device_id === this.deviceId) {
                this.updateStatusDisplay('offline', data.offline_reason, data.offline_reason_display);
            }
        });

        // 錄音開始
        // 修復 2：錄音開始時同時更新狀態 badge
        this.socket.on('edge_device.recording_started', (data) => {
            if (data.device_id === this.deviceId) {
                this.showRecordingProgress();
                this.updateStatusDisplay('RECORDING');  // 新增：更新狀態為錄音中
            }
        });

        // 錄音進度
        this.socket.on('edge_device.recording_progress', (data) => {
            if (data.device_id === this.deviceId) {
                this.updateRecordingProgress(data.progress_percent);
            }
        });

        // 錄音完成
        // 修復 1：錄音完成時同時更新狀態 badge
        this.socket.on('edge_device.recording_completed', (data) => {
            if (data.device_id === this.deviceId) {
                this.hideRecordingProgress();
                this.updateStatusDisplay('IDLE');  // 新增：更新狀態為在線
            }
        });

        // 錄音上傳完成
        this.socket.on('edge_device.recording_uploaded', (data) => {
            if (data.device_id === this.deviceId) {
                this.addNewRecordingRow(data);
            }
        });
    }

    initEventListeners() {
        document.addEventListener('DOMContentLoaded', () => {
            if (this.currentManagerIds.length > 0) {
                this.loadManagersDisplay();
            }
        });
    }

    // ==================== 狀態更新 ====================
    updateStatusDisplay(status, offlineReason, offlineReasonText) {
        const indicator = document.getElementById('status-indicator');
        const badge = document.getElementById('status-badge');
        const recordBtn = document.getElementById('record-btn');
        const deleteBtn = document.getElementById('delete-btn');

        indicator.className = 'absolute -top-1 -right-1 h-5 w-5 rounded-full border-2 border-white shadow-sm';
        badge.className = 'tech-badge text-sm px-4 py-2';

        const isOnline = (status === 'IDLE');

        if (isOnline) {
            indicator.classList.add('bg-green-500');
            badge.classList.add('bg-green-100', 'text-green-700', 'border-green-200');
            badge.textContent = '在線';
            recordBtn.disabled = false;
            deleteBtn.disabled = true;
        } else if (status === 'RECORDING') {
            indicator.classList.add('bg-red-500', 'animate-pulse');
            badge.classList.add('bg-red-100', 'text-red-700', 'border-red-200');
            badge.textContent = '錄音中';
            recordBtn.disabled = true;
            deleteBtn.disabled = true;
        } else {
            indicator.classList.add('bg-gray-400');
            badge.classList.add('bg-gray-100', 'text-gray-600', 'border-gray-200');
            badge.textContent = '離線';
            recordBtn.disabled = true;
            deleteBtn.disabled = false;
        }

        // 更新離線原因
        let reasonSpan = document.getElementById('offline-reason');
        if (status === 'OFFLINE' && offlineReason) {
            const reasonText = offlineReasonText || this.offlineReasonDisplay[offlineReason] || '未知原因';
            if (!reasonSpan) {
                reasonSpan = document.createElement('span');
                reasonSpan.id = 'offline-reason';
                reasonSpan.className = 'text-xs text-gray-500';
                reasonSpan.title = '離線原因';
                const badgeContainer = badge.parentElement;
                if (badgeContainer) {
                    badgeContainer.appendChild(reasonSpan);
                }
            }
            reasonSpan.innerHTML = `<i class="fas fa-info-circle mr-1"></i>${reasonText}`;
            reasonSpan.style.display = '';
        } else if (reasonSpan) {
            reasonSpan.style.display = 'none';
        }
    }

    // ==================== 錄音功能 ====================
    triggerRecording() {
        const durationInput = document.getElementById('record-duration');
        const duration = parseInt(durationInput.value);
        const recordBtn = document.getElementById('record-btn');

        if (isNaN(duration) || duration < 1 || duration > 3600) {
            this.showToast('請輸入有效的錄音時長（1-3600 秒）', 'error');
            return;
        }

        recordBtn.disabled = true;
        recordBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 發送中...';

        fetch(`/api/edge-devices/${this.deviceId}/record`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({duration: duration})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                this.showToast('錄音已開始', 'success');
            } else {
                this.showToast('錯誤: ' + (data.message || '未知錯誤'), 'error');
                recordBtn.disabled = false;
                recordBtn.innerHTML = '<i class="fas fa-circle mr-1"></i> 錄音';
            }
        })
        .catch(err => {
            this.showToast('請求失敗: ' + err.message, 'error');
            recordBtn.disabled = false;
            recordBtn.innerHTML = '<i class="fas fa-circle mr-1"></i> 錄音';
        });
    }

    // ==================== Toast 通知 ====================
    showToast(message, type = 'info') {
        const existingToast = document.getElementById('toast-notification');
        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.createElement('div');
        toast.id = 'toast-notification';
        toast.className = `fixed top-4 right-4 z-50 px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full`;

        if (type === 'success') {
            toast.classList.add('bg-green-500', 'text-white');
            toast.innerHTML = `<i class="fas fa-check-circle mr-2"></i>${message}`;
        } else if (type === 'error') {
            toast.classList.add('bg-red-500', 'text-white');
            toast.innerHTML = `<i class="fas fa-exclamation-circle mr-2"></i>${message}`;
        } else {
            toast.classList.add('bg-blue-500', 'text-white');
            toast.innerHTML = `<i class="fas fa-info-circle mr-2"></i>${message}`;
        }

        document.body.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.remove('translate-x-full');
            toast.classList.add('translate-x-0');
        });

        setTimeout(() => {
            toast.classList.remove('translate-x-0');
            toast.classList.add('translate-x-full');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ==================== 音訊設備查詢 ====================
    queryAudioDevices() {
        fetch(`/api/edge-devices/${this.deviceId}/audio-devices`)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                this.showToast('已發送音訊設備查詢請求，請重新整理頁面查看更新的設備', 'success');
            } else {
                this.showToast('錯誤: ' + (data.message || '未知錯誤'), 'error');
            }
        });
    }

    queryAudioDevicesInModal() {
        const icon = document.getElementById('unified-query-icon');
        const hint = document.getElementById('unified-audio-device-hint');
        const select = document.getElementById('unified-audio-device-index');

        icon.classList.add('fa-spin');
        hint.textContent = '正在查詢音訊設備...';
        hint.classList.remove('text-green-600', 'text-red-600');
        hint.classList.add('text-blue-600');

        fetch(`/api/edge-devices/${this.deviceId}/audio-devices`)
        .then(r => r.json())
        .then(data => {
            icon.classList.remove('fa-spin');

            if (data.success) {
                hint.textContent = '已發送查詢請求，正在等待設備回應...';

                let pollCount = 0;
                const maxPolls = 10;
                const pollInterval = setInterval(() => {
                    pollCount++;
                    fetch(`/api/edge-devices/${this.deviceId}`)
                    .then(r => r.json())
                    .then(deviceData => {
                        if (deviceData.success && deviceData.device) {
                            const audioConfig = deviceData.device.audio_config || {};
                            const devices = audioConfig.available_devices || [];

                            if (devices.length > 0) {
                                clearInterval(pollInterval);

                                const currentValue = select.value;
                                select.innerHTML = '';
                                devices.forEach(dev => {
                                    const option = document.createElement('option');
                                    option.value = dev.index;
                                    option.textContent = `${dev.index}: ${dev.name}`;
                                    if (dev.index == currentValue || dev.index == audioConfig.default_device_index) {
                                        option.selected = true;
                                    }
                                    select.appendChild(option);
                                });

                                hint.textContent = `已更新，找到 ${devices.length} 個音訊設備`;
                                hint.classList.remove('text-blue-600');
                                hint.classList.add('text-green-600');
                            } else if (pollCount >= maxPolls) {
                                clearInterval(pollInterval);
                                hint.textContent = '查詢逾時，請稍後再試';
                                hint.classList.remove('text-blue-600');
                                hint.classList.add('text-red-600');
                            }
                        }
                    });
                }, 1500);
            } else {
                hint.textContent = '錯誤: ' + (data.message || '未知錯誤');
                hint.classList.remove('text-blue-600');
                hint.classList.add('text-red-600');
            }
        })
        .catch(err => {
            icon.classList.remove('fa-spin');
            hint.textContent = '查詢失敗: ' + err.message;
            hint.classList.remove('text-blue-600');
            hint.classList.add('text-red-600');
        });
    }

    // ==================== 排程功能 ====================
    toggleSchedule(enabled) {
        const action = enabled ? 'enable' : 'disable';
        fetch(`/api/edge-devices/${this.deviceId}/schedule/${action}`, {method: 'POST'})
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                this.showToast('錯誤: ' + (data.message || '未知錯誤'), 'error');
            }
        });
    }

    // ==================== 設備配置摺疊功能 ====================
    toggleConfigSection(event) {
        const content = document.getElementById('config-section-content');
        const icon = document.getElementById('config-collapse-icon');

        if (content.classList.contains('hidden')) {
            content.classList.remove('hidden');
            icon.classList.add('rotate-90');
        } else {
            content.classList.add('hidden');
            icon.classList.remove('rotate-90');
        }
    }

    // ==================== 統一編輯配置功能 ====================
    openUnifiedConfigModal(intervalSeconds) {
        // 防護：確保 intervalSeconds 是有效數字，預設為 3600 秒（1 小時）
        intervalSeconds = Number(intervalSeconds) || 3600;

        let displayValue, unitValue;

        if (intervalSeconds >= 86400 && intervalSeconds % 86400 === 0) {
            displayValue = intervalSeconds / 86400;
            unitValue = '86400';
        } else if (intervalSeconds >= 3600 && intervalSeconds % 3600 === 0) {
            displayValue = intervalSeconds / 3600;
            unitValue = '3600';
        } else if (intervalSeconds >= 60 && intervalSeconds % 60 === 0) {
            displayValue = intervalSeconds / 60;
            unitValue = '60';
        } else {
            displayValue = intervalSeconds;
            unitValue = '1';
        }

        document.getElementById('unified-schedule-interval').value = displayValue;
        document.getElementById('unified-schedule-interval-unit').value = unitValue;

        this.loadUnifiedManagersList();
        ModalManager.open('unified-config-modal');
    }

    loadUnifiedManagersList() {
        const container = document.getElementById('unified-managers-list');

        fetch('/api/edge-devices/users/list')
        .then(r => r.json())
        .then(data => {
            if (data.users && data.users.length > 0) {
                let html = '';
                data.users.forEach(user => {
                    const userId = user.id || user.user_id;
                    const isChecked = this.currentManagerIds.includes(userId) ? 'checked' : '';
                    const isAdmin = user.role === 'admin';
                    const roleText = isAdmin ? ' (管理員)' : '';
                    html += `
                        <label class="flex items-center p-2 rounded-lg border border-gray-200 hover:border-emerald-300 cursor-pointer transition-colors">
                            <input type="checkbox" name="unified_manager_ids" value="${userId}"
                                   class="unified-manager-checkbox h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500" ${isChecked}>
                            <span class="ml-2 text-sm text-gray-700">${user.username}${roleText}</span>
                        </label>
                    `;
                });
                container.innerHTML = html;
            } else {
                container.innerHTML = `
                    <div class="text-center py-4">
                        <i class="fas fa-users-slash text-2xl text-gray-300 mb-2"></i>
                        <p class="text-xs text-gray-500">沒有可用的用戶</p>
                    </div>
                `;
            }
        })
        .catch(err => {
            console.error('載入用戶列表失敗:', err);
            container.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-exclamation-circle text-2xl text-red-400 mb-2"></i>
                    <p class="text-xs text-red-500">載入失敗</p>
                </div>
            `;
        });
    }

    closeUnifiedConfigModal() {
        ModalManager.close('unified-config-modal', () => {
            document.getElementById('unified-photo-input').value = '';
        });
    }

    previewUnifiedPhoto(input) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const preview = document.getElementById('unified-photo-preview');
                preview.innerHTML = `<img src="${e.target.result}" alt="預覽" class="h-full w-full object-cover">`;
            };
            reader.readAsDataURL(input.files[0]);
        }
    }

    async uploadUnifiedPhoto() {
        const input = document.getElementById('unified-photo-input');
        if (!input.files || !input.files[0]) {
            return true;
        }

        const formData = new FormData();
        formData.append('photo', input.files[0]);

        try {
            const res = await fetch(`/api/edge-devices/${this.deviceId}/photo`, {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            if (!result.success) {
                this.showToast('照片上傳失敗: ' + (result.message || '未知錯誤'), 'error');
                return false;
            }
            return true;
        } catch (err) {
            this.showToast('照片上傳失敗: ' + err.message, 'error');
            return false;
        }
    }

    async saveUnifiedConfig() {
        // 收集設備資訊
        const deviceName = document.getElementById('unified-device-name').value.trim();
        const locationData = {
            name: document.getElementById('unified-location-name').value.trim(),
            building: document.getElementById('unified-location-building').value.trim(),
            floor: document.getElementById('unified-location-floor').value.trim(),
            room: document.getElementById('unified-location-room').value.trim()
        };
        const selectedManagerIds = Array.from(document.querySelectorAll('.unified-manager-checkbox:checked'))
            .map(cb => cb.value);

        // 收集音訊配置資料
        const audioData = {
            default_device_index: parseInt(document.getElementById('unified-audio-device-index').value),
            sample_rate: parseInt(document.getElementById('unified-audio-sample-rate').value),
            channels: parseInt(document.getElementById('unified-audio-channels').value),
            bit_depth: parseInt(document.getElementById('unified-audio-bit-depth').value)
        };

        const intervalValue = parseFloat(document.getElementById('unified-schedule-interval').value);
        const intervalUnit = parseInt(document.getElementById('unified-schedule-interval-unit').value);
        const intervalSeconds = intervalValue * intervalUnit;
        const durationSeconds = parseInt(document.getElementById('unified-schedule-duration').value);
        const scheduleEnabled = document.getElementById('unified-schedule-enabled').checked;

        // 前端驗證
        if (intervalSeconds <= 0) {
            this.showToast('間隔時間必須大於 0', 'error');
            return;
        }

        if (intervalSeconds < durationSeconds) {
            this.showToast('間隔時間不可小於錄音時長（' + durationSeconds + ' 秒）', 'error');
            return;
        }

        const scheduleData = {
            interval_seconds: intervalSeconds,
            duration_seconds: durationSeconds
        };

        const selectedRouterIds = Array.from(document.querySelectorAll('.unified-router-checkbox:checked'))
            .map(cb => cb.value);

        let hasError = false;

        // 上傳照片（如果有選擇）
        const photoUploaded = await this.uploadUnifiedPhoto();
        if (!photoUploaded) {
            hasError = true;
        }

        // 儲存設備名稱
        try {
            const nameRes = await fetch(`/api/edge-devices/${this.deviceId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_name: deviceName})
            });
            const nameResult = await nameRes.json();
            if (!nameResult.success) {
                this.showToast('設備名稱儲存失敗: ' + (nameResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('設備名稱儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 儲存位置資訊
        try {
            const locationRes = await fetch(`/api/edge-devices/${this.deviceId}/location`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(locationData)
            });
            const locationResult = await locationRes.json();
            if (!locationResult.success) {
                this.showToast('位置資訊儲存失敗: ' + (locationResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('位置資訊儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 儲存管理人員
        try {
            const managersRes = await fetch(`/api/edge-devices/${this.deviceId}/managers`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({manager_ids: selectedManagerIds})
            });
            const managersResult = await managersRes.json();
            if (!managersResult.success) {
                this.showToast('管理人員儲存失敗: ' + (managersResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('管理人員儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 儲存音訊配置
        try {
            const audioRes = await fetch(`/api/edge-devices/${this.deviceId}/audio-config`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(audioData)
            });
            const audioResult = await audioRes.json();
            if (!audioResult.success) {
                this.showToast('音訊配置儲存失敗: ' + (audioResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('音訊配置儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 儲存排程配置
        try {
            const scheduleRes = await fetch(`/api/edge-devices/${this.deviceId}/schedule`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(scheduleData)
            });
            const scheduleResult = await scheduleRes.json();
            if (!scheduleResult.success) {
                this.showToast('排程配置儲存失敗: ' + (scheduleResult.error || scheduleResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('排程配置儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 啟用/停用排程
        try {
            const action = scheduleEnabled ? 'enable' : 'disable';
            const toggleRes = await fetch(`/api/edge-devices/${this.deviceId}/schedule/${action}`, {method: 'POST'});
            const toggleResult = await toggleRes.json();
            if (!toggleResult.success) {
                this.showToast('排程狀態更新失敗: ' + (toggleResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('排程狀態更新失敗: ' + err.message, 'error');
            hasError = true;
        }

        // 儲存路由配置
        try {
            const routerRes = await fetch(`/api/edge-devices/${this.deviceId}/routers`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({router_ids: selectedRouterIds})
            });
            const routerResult = await routerRes.json();
            if (!routerResult.success) {
                this.showToast('路由配置儲存失敗: ' + (routerResult.message || '未知錯誤'), 'error');
                hasError = true;
            }
        } catch (err) {
            this.showToast('路由配置儲存失敗: ' + err.message, 'error');
            hasError = true;
        }

        if (!hasError) {
            this.showToast('所有設定已儲存成功', 'success');
            setTimeout(() => location.reload(), 500);
        }
    }

    // ==================== 刪除設備功能 ====================
    deleteDevice() {
        const deleteBtn = document.getElementById('delete-btn');
        if (deleteBtn && deleteBtn.disabled) {
            this.showToast('無法刪除在線或錄音中的設備。請等待設備離線後再試', 'error');
            return;
        }

        const statusBadge = document.getElementById('status-badge');
        const statusText = statusBadge ? statusBadge.textContent.replace(/\s+/g, '') : '';
        if (!statusText.includes('離線')) {
            this.showToast('無法刪除在線或錄音中的設備。請等待設備離線後再試', 'error');
            return;
        }

        this.openDeleteConfirmModal();
    }

    openDeleteConfirmModal() {
        ModalManager.open('delete-confirm-modal', () => {
            const content = document.getElementById('delete-confirm-content');
            content.classList.remove('scale-95', 'opacity-0');
            content.classList.add('scale-100', 'opacity-100');
        });
    }

    closeDeleteConfirmModal() {
        const content = document.getElementById('delete-confirm-content');
        content.classList.remove('scale-100', 'opacity-100');
        content.classList.add('scale-95', 'opacity-0');
        setTimeout(() => {
            ModalManager.close('delete-confirm-modal');
        }, 300);
    }

    confirmDeleteDevice(listUrl) {
        const checkbox = document.getElementById('delete-recordings-checkbox');
        const deleteRecordings = checkbox ? checkbox.checked : false;

        this.closeDeleteConfirmModal();

        const params = new URLSearchParams();
        if (deleteRecordings) {
            params.append('delete_recordings', 'true');
        }

        const url = `/api/edge-devices/${this.deviceId}` + (params.toString() ? `?${params}` : '');

        fetch(url, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const msg = deleteRecordings
                    ? `設備已刪除，同時刪除了 ${data.deleted_recordings || 0} 筆錄音資料`
                    : '設備已刪除';
                this.showToast(msg, 'success');
                setTimeout(() => {
                    window.location.href = listUrl;
                }, 1500);
            } else {
                this.showToast('刪除失敗: ' + (data.error || '未知錯誤'), 'error');
            }
        })
        .catch(err => {
            this.showToast('刪除失敗: ' + err.message, 'error');
        });
    }

    // ==================== 錄音進度條控制 ====================
    showRecordingProgress() {
        const container = document.getElementById('recording-progress-container');
        if (container) {
            container.classList.remove('hidden');
            this.updateRecordingProgress(0);
        }
    }

    updateRecordingProgress(percent) {
        const bar = document.getElementById('recording-progress-bar');
        const text = document.getElementById('recording-progress-text');
        if (bar && text) {
            bar.style.width = percent + '%';
            text.textContent = Math.round(percent) + '%';
        }
    }

    hideRecordingProgress() {
        const container = document.getElementById('recording-progress-container');
        if (container) {
            container.classList.add('hidden');
        }
        const recordBtn = document.getElementById('record-btn');
        if (recordBtn) {
            recordBtn.disabled = false;
            recordBtn.innerHTML = '<i class="fas fa-circle mr-1"></i> 錄音';
        }
    }

    // ==================== 近期錄音表格即時更新 ====================
    addNewRecordingRow(data) {
        const placeholder = document.getElementById('no-recordings-placeholder');

        if (placeholder) {
            this.createRecordingsTable();
        }

        const newRow = this.createRecordingRow(data, 1);

        const currentTbody = document.getElementById('recent-recordings-tbody');
        if (currentTbody) {
            currentTbody.insertBefore(newRow, currentTbody.firstChild);
            this.renumberRecordingRows();

            while (currentTbody.children.length > 10) {
                currentTbody.removeChild(currentTbody.lastChild);
            }
        }

        this.showToast('新錄音已上傳', 'success');
    }

    createRecordingRow(data, index) {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50';

        const timestamp = new Date().toLocaleString('zh-TW', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false
        }).replace(/\//g, '-');

        const routerCount = data.assigned_router_ids ? data.assigned_router_ids.length : 0;
        const routerBadge = routerCount > 0
            ? `<span class="tech-badge text-xs bg-emerald-100 text-emerald-700">${routerCount} 個路由</span>`
            : `<span class="tech-badge text-xs bg-gray-100 text-gray-600">無</span>`;

        const uuid = data.recording_uuid || data.analyze_uuid || '';
        const displayUuid = uuid.length > 16 ? uuid.substring(0, 16) + '...' : uuid;

        tr.innerHTML = `
            <td class="row-number px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-400">${index}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-600">
                <a href="/data/${uuid}" class="text-emerald-600 hover:text-emerald-700 hover:underline">
                    ${displayUuid}
                </a>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">${data.filename || '-'}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">${data.duration != null ? parseFloat(data.duration).toFixed(1) : '-'}s</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">${routerBadge}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${timestamp}</td>
        `;

        return tr;
    }

    renumberRecordingRows() {
        const tbody = document.getElementById('recent-recordings-tbody');
        if (tbody) {
            const rows = tbody.querySelectorAll('tr');
            rows.forEach((row, index) => {
                const numberCell = row.querySelector('.row-number');
                if (numberCell) {
                    numberCell.textContent = index + 1;
                }
            });
        }
    }

    createRecordingsTable() {
        const placeholder = document.getElementById('no-recordings-placeholder');
        if (placeholder) {
            placeholder.remove();
        }

        const container = document.getElementById('recent-recordings-container');
        if (container) {
            container.innerHTML = `
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12">#</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">分析 UUID</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">檔案名稱</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">時長</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">分析路由</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">建立時間</th>
                        </tr>
                    </thead>
                    <tbody id="recent-recordings-tbody" class="bg-white divide-y divide-gray-200">
                    </tbody>
                </table>
            `;
        }
    }

    // ==================== 管理人員顯示功能 ====================
    loadManagersDisplay() {
        const container = document.getElementById('managers-avatar-container');

        if (this.currentManagerIds.length === 0) {
            container.innerHTML = `<span class="text-sm text-gray-400">尚未指派管理人員</span>`;
            return;
        }

        fetch(`/api/edge-devices/${this.deviceId}/managers`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.managers) {
                const maxAvatars = 5;
                const managers = data.managers;
                const displayCount = Math.min(managers.length, maxAvatars);
                const remainingCount = managers.length - maxAvatars;

                let avatarsHtml = '';
                for (let i = 0; i < displayCount; i++) {
                    const manager = managers[i];
                    const initial = manager.username.charAt(0).toUpperCase();
                    const isAdmin = manager.role === 'admin';
                    const bgClass = isAdmin
                        ? 'from-purple-500 to-indigo-600'
                        : 'from-blue-500 to-indigo-600';
                    avatarsHtml += `
                        <div class="h-9 w-9 rounded-full bg-gradient-to-br ${bgClass} flex items-center justify-center text-white text-sm font-semibold border-2 border-white shadow-sm"
                             title="${manager.username}${isAdmin ? ' (管理員)' : ''}">
                            ${initial}
                        </div>
                    `;
                }

                let remainingHtml = '';
                if (remainingCount > 0) {
                    remainingHtml = `
                        <div class="h-9 w-9 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 text-xs font-semibold border-2 border-white shadow-sm">
                            +${remainingCount}
                        </div>
                    `;
                }

                const nameList = managers.map(m => m.username + (m.role === 'admin' ? ' (管理員)' : '')).join('、');

                const maxDisplayNames = 3;
                let displayNameText = '';
                if (managers.length <= maxDisplayNames) {
                    displayNameText = managers.map(m => m.username).join('、');
                } else {
                    const displayedNames = managers.slice(0, maxDisplayNames).map(m => m.username).join('、');
                    const remainingNameCount = managers.length - maxDisplayNames;
                    displayNameText = `${displayedNames} 等 ${remainingNameCount} 人`;
                }

                container.innerHTML = `
                    <div class="flex items-center">
                        <div class="flex -space-x-2" title="${nameList}">
                            ${avatarsHtml}
                            ${remainingHtml}
                        </div>
                        <span class="ml-3 text-sm text-gray-600">${displayNameText}</span>
                    </div>
                `;
            }
        })
        .catch(err => {
            console.error('載入管理人員失敗:', err);
            container.innerHTML = `<span class="text-sm text-red-400">載入失敗</span>`;
        });
    }
}

// 導出供全域使用
window.ModalManager = ModalManager;
window.EdgeDeviceDetail = EdgeDeviceDetail;
