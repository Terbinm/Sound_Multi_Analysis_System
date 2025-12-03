/**
 * WebSocket 客戶端管理器
 * 用於管理 Socket.IO 連接、自動重連和事件訂閱
 */
class WebSocketClient {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.eventHandlers = {};
        this.subscribedRooms = new Set();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // 初始重連延遲 1 秒
        this.statusIndicator = null;
    }

    /**
     * 初始化 WebSocket 連接
     */
    init() {
        console.log('[WebSocket] 初始化連接...');

        // 連接到 Socket.IO 服務器
        this.socket = io({
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: this.reconnectDelay,
            reconnectionDelayMax: 5000,
            timeout: 10000,
        });

        // 註冊核心事件處理器
        this._registerCoreHandlers();

        return this;
    }

    /**
     * 註冊核心事件處理器
     */
    _registerCoreHandlers() {
        // 連接成功
        this.socket.on('connect', () => {
            console.log('[WebSocket] 連接成功');
            this.connected = true;
            this.reconnectAttempts = 0;
            this._updateStatusIndicator('connected');

            // 重新訂閱所有房間
            this._resubscribeRooms();

            // 觸發自定義連接事件
            this._triggerEvent('ws:connected', {});
        });

        // 連接建立確認
        this.socket.on('connection_established', (data) => {
            console.log('[WebSocket] 連接已建立, Client ID:', data.client_id);
        });

        // 斷開連接
        this.socket.on('disconnect', (reason) => {
            console.warn('[WebSocket] 連接斷開:', reason);
            this.connected = false;
            this._updateStatusIndicator('disconnected');
            this._triggerEvent('ws:disconnected', { reason });
        });

        // 連接錯誤
        this.socket.on('connect_error', (error) => {
            console.error('[WebSocket] 連接錯誤:', error);
            this.reconnectAttempts++;
            this._updateStatusIndicator('error');
            this._triggerEvent('ws:error', { error });
        });

        // 重連嘗試
        this.socket.io.on('reconnect_attempt', () => {
            console.log(`[WebSocket] 嘗試重連 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            this._updateStatusIndicator('reconnecting');
        });

        // 重連成功
        this.socket.io.on('reconnect', (attemptNumber) => {
            console.log(`[WebSocket] 重連成功 (嘗試次數: ${attemptNumber})`);
            this._updateStatusIndicator('connected');
        });

        // 重連失敗
        this.socket.io.on('reconnect_failed', () => {
            console.error('[WebSocket] 重連失敗，已達最大嘗試次數');
            this._updateStatusIndicator('failed');
            this._triggerEvent('ws:reconnect_failed', {});
        });
    }

    /**
     * 訂閱房間
     * @param {string} room - 房間名稱
     */
    subscribe(room) {
        // 立即加入訂閱列表，無論是否已連接
        this.subscribedRooms.add(room);

        if (!this.socket || !this.connected) {
            console.warn(`[WebSocket] 尚未連接，房間 ${room} 將在連接建立後自動訂閱`);
            return;
        }

        console.log(`[WebSocket] 訂閱房間: ${room}`);
        this.socket.emit('subscribe', { room });

        // 監聽訂閱確認
        this.socket.once('subscribed', (data) => {
            console.log(`[WebSocket] 已訂閱房間: ${data.room}`);
        });
    }

    /**
     * 取消訂閱房間
     * @param {string} room - 房間名稱
     */
    unsubscribe(room) {
        if (!this.socket || !this.connected) {
            return;
        }

        console.log(`[WebSocket] 取消訂閱房間: ${room}`);
        this.socket.emit('unsubscribe', { room });
        this.subscribedRooms.delete(room);

        // 監聽取消訂閱確認
        this.socket.once('unsubscribed', (data) => {
            console.log(`[WebSocket] 已取消訂閱房間: ${data.room}`);
        });
    }

    /**
     * 重新訂閱所有房間（用於重連後）
     */
    _resubscribeRooms() {
        if (this.subscribedRooms.size === 0) {
            return;
        }

        console.log('[WebSocket] 重新訂閱房間...');
        this.subscribedRooms.forEach(room => {
            this.socket.emit('subscribe', { room });
        });
    }

    /**
     * 註冊事件處理器
     * @param {string} event - 事件名稱
     * @param {function} handler - 處理函數
     */
    on(event, handler) {
        if (!this.socket) {
            console.warn('[WebSocket] Socket 未初始化');
            return;
        }

        // 保存處理器引用
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);

        // 註冊到 socket.io
        this.socket.on(event, handler);
        console.log(`[WebSocket] 註冊事件處理器: ${event}`);
    }

    /**
     * 移除事件處理器
     * @param {string} event - 事件名稱
     * @param {function} handler - 處理函數（可選）
     */
    off(event, handler) {
        if (!this.socket) {
            return;
        }

        if (handler) {
            // 移除特定處理器
            this.socket.off(event, handler);
            if (this.eventHandlers[event]) {
                const index = this.eventHandlers[event].indexOf(handler);
                if (index > -1) {
                    this.eventHandlers[event].splice(index, 1);
                }
            }
        } else {
            // 移除所有處理器
            this.socket.off(event);
            delete this.eventHandlers[event];
        }

        console.log(`[WebSocket] 移除事件處理器: ${event}`);
    }

    /**
     * 觸發自定義事件
     * @param {string} event - 事件名稱
     * @param {object} data - 事件數據
     */
    _triggerEvent(event, data) {
        const customEvent = new CustomEvent(event, { detail: data });
        window.dispatchEvent(customEvent);
    }

    /**
     * 更新連接狀態指示器
     * @param {string} status - 狀態 (connected, disconnected, reconnecting, error, failed)
     */
    _updateStatusIndicator(status) {
        if (!this.statusIndicator) {
            this.statusIndicator = document.getElementById('ws-status-indicator');
        }

        if (this.statusIndicator) {
            // 移除所有狀態類
            this.statusIndicator.className = 'ws-status';

            // 添加當前狀態類
            this.statusIndicator.classList.add(`ws-status-${status}`);

            // 更新文字
            const statusText = {
                'connected': '已連接',
                'disconnected': '已斷開',
                'reconnecting': '重連中...',
                'error': '連接錯誤',
                'failed': '連接失敗'
            };
            this.statusIndicator.textContent = statusText[status] || status;
        }

        // 觸發狀態變更事件
        this._triggerEvent('ws:status_changed', { status });
    }

    /**
     * 設置狀態指示器元素
     * @param {HTMLElement} element - 狀態指示器元素
     */
    setStatusIndicator(element) {
        this.statusIndicator = element;
    }

    /**
     * 斷開連接
     */
    disconnect() {
        if (this.socket) {
            console.log('[WebSocket] 主動斷開連接');
            this.socket.disconnect();
            this.connected = false;
        }
    }

    /**
     * 獲取連接狀態
     * @returns {boolean}
     */
    isConnected() {
        return this.connected && this.socket && this.socket.connected;
    }
}

// 創建全局實例
const wsClient = new WebSocketClient();

// 自動初始化（當頁面加載完成後）
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        wsClient.init();
    });
} else {
    wsClient.init();
}
