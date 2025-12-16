# 檔案上傳與路由選擇功能

## 功能概述

此功能允許用戶通過 Web 介面上傳音訊檔案並選擇多個路由規則進行分析。

## 新增檔案

### API 層
- `api/upload_api.py` - 上傳 API，提供三個端點：
  - `POST /api/uploads/submit` - 提交檔案上傳
  - `GET /api/uploads/recent` - 獲取最近上傳記錄
  - `GET /api/uploads/config` - 獲取上傳配置

### 視圖層
- `views/upload_views.py` - 上傳視圖，提供三個路由：
  - `/uploads` - 上傳記錄列表
  - `/uploads/create` - 檔案上傳頁面
  - `/uploads/<analyze_uuid>` - 重導向至資料詳情頁

### 前端模板
- `templates/uploads/create.html` - 四步驟上傳嚮導頁面
- `templates/uploads/list.html` - 上傳記錄列表頁面

### 修改的檔案
- `state_management_main.py` - 註冊上傳 API Blueprint
- `templates/partials/sidebar_nav.html` - 新增導航選單項目

## 使用方式

### 1. 上傳檔案

訪問 `/uploads/create` 頁面，按照四個步驟操作：

**步驟 1：上傳音訊檔案**
- 支援拖放上傳或點擊瀏覽
- 支援格式：WAV, MP3, M4A, FLAC, OGG, AAC
- 檔案大小限制：可通過環境變數 `MAX_CONTENT_LENGTH` 設定

**步驟 2：選擇分析路由**
- 從可用路由規則中選擇（多選）
- 選擇執行模式：串行或並行

**步驟 3：填寫檔案資訊**
- 表單模式：填寫預設欄位（dataset_UUID、device_id、label 等）
- JSON 模式：直接編輯 JSON

**步驟 4：確認與提交**
- 檢視所有資訊
- 提交上傳
- 獲得 AnalyzeUUID 和任務數量

### 2. 查看上傳記錄

訪問 `/uploads` 頁面查看所有上傳記錄：
- 顯示檔案名稱、上傳者、上傳時間
- 顯示已指派的路由規則
- 點擊「查看」進入資料詳情頁

### 3. API 使用

**提交上傳（需要登入）：**
```bash
curl -X POST http://localhost:5000/api/uploads/submit \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio.wav" \
  -F "router_ids=router_id_1" \
  -F "router_ids=router_id_2" \
  -F 'info_features={"dataset_UUID":"test","label":"normal"}' \
  -F "sequential=true"
```

**獲取最近上傳：**
```bash
curl http://localhost:5000/api/uploads/recent?limit=10&user_only=false
```

**獲取上傳配置：**
```bash
curl http://localhost:5000/api/uploads/config
```

## 資料流程

1. **前端上傳** → 檔案通過 FormData 提交至 `/api/uploads/submit`
2. **檔案驗證** → 檢查格式、大小、路由規則有效性
3. **GridFS 儲存** → 檔案上傳至 MongoDB GridFS
4. **創建記錄** → 在 `recordings` 集合建立文檔
5. **任務派送** → 調用 `TaskDispatcher.dispatch_by_router_ids()`
6. **RabbitMQ 發布** → 任務訊息發送至分析服務
7. **即時通知** → WebSocket 推送狀態更新（待實作）

## 權限控制

- 所有上傳功能需要登入（`@login_required`）
- 未來可擴展為角色權限控制（`@role_required`）

## 資料結構

### MongoDB 記錄
```json
{
  "AnalyzeUUID": "uuid",
  "files": {
    "raw": {
      "fileId": "GridFS ObjectId",
      "filename": "audio.wav",
      "type": "wav"
    }
  },
  "info_features": {
    "uploaded_by": "username",
    "uploaded_at": "2025-12-16T10:30:00",
    "upload_source": "web_ui",
    "dataset_UUID": "custom_value",
    "device_id": "custom_value",
    "label": "normal"
  },
  "analyze_features": {},
  "assigned_router_ids": ["router_id_1", "router_id_2"],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## 未來擴展建議

1. **批次上傳** - 支援一次上傳多個檔案
2. **進度條** - 顯示上傳進度（大檔案）
3. **WebSocket 整合** - 即時推送分析進度
4. **配額管理** - 限制用戶上傳次數/大小
5. **歷史記錄** - 查看個人上傳歷史與統計
6. **檔案預覽** - 音訊波形預覽
7. **下載結果** - 直接下載分析報告

## 測試建議

1. 上傳不同格式的音訊檔案
2. 選擇多個路由規則測試串行/並行執行
3. 測試檔案大小限制
4. 測試無效路由規則處理
5. 測試 JSON 編輯模式
6. 查看上傳記錄列表
7. 驗證任務是否正確派送到 RabbitMQ
