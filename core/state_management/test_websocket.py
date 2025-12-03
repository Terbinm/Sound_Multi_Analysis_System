"""
測試 WebSocket 事件推送
用於驗證節點事件是否正確推送到前端
"""
import time
from services.websocket_manager import websocket_manager

def test_node_events():
    """測試節點事件推送"""
    
    print("=" * 60)
    print("測試 WebSocket 節點事件推送")
    print("=" * 60)
    
    # 測試節點註冊事件
    print("\n1. 測試節點註冊事件...")
    websocket_manager.emit_node_registered({
        'node_id': 'test_node_001',
        'status': 'online',
        'capabilities': ['TEST_CAPABILITY'],
        'version': 'v1.0.0',
        'max_concurrent_tasks': 5,
        'tags': ['test']
    })
    print("✓ 節點註冊事件已推送")
    time.sleep(1)
    
    # 測試節點心跳事件
    print("\n2. 測試節點心跳事件...")
    websocket_manager.emit_node_heartbeat({
        'node_id': 'test_node_001',
        'status': 'online',
        'current_tasks': 2,
        'max_concurrent_tasks': 5,
        'load_ratio': 40.0,
        'timestamp': time.time(),
        'capability': 'TEST_CAPABILITY'
    })
    print("✓ 節點心跳事件已推送")
    time.sleep(1)
    
    # 測試節點離線事件
    print("\n3. 測試節點離線事件...")
    websocket_manager.emit_node_offline({
        'node_id': 'test_node_001',
        'status': 'offline',
        'timestamp': time.time(),
        'capability': 'TEST_CAPABILITY'
    })
    print("✓ 節點離線事件已推送")
    time.sleep(1)
    
    # 測試節點上線事件
    print("\n4. 測試節點上線事件...")
    websocket_manager.emit_node_online({
        'node_id': 'test_node_001',
        'status': 'online',
        'timestamp': time.time(),
        'current_tasks': 0,
        'capability': 'TEST_CAPABILITY'
    })
    print("✓ 節點上線事件已推送")
    time.sleep(1)
    
    # 測試統計更新事件
    print("\n5. 測試統計更新事件...")
    websocket_manager.emit_stats_updated({
        'total_nodes': 3,
        'online_nodes': 2,
        'offline_nodes': 1,
        'timestamp': time.time()
    })
    print("✓ 統計更新事件已推送")
    
    print("\n" + "=" * 60)
    print("所有測試事件已推送")
    print("請在瀏覽器開發者工具的控制台中檢查是否收到事件")
    print("=" * 60)

if __name__ == '__main__':
    from state_management_main import app, socketio
    
    with app.app_context():
        # 等待服務啟動
        print("等待 WebSocket 服務初始化...")
        time.sleep(2)
        
        # 執行測試
        test_node_events()
