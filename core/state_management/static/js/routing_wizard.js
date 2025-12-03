/**
 * 路由規則建立嚮導
 * 使用 Alpine.js 管理多步驟表單狀態
 */

function routingWizard() {
    return {
        // 當前步驟
        currentStep: 1,

        // 表單資料
        formData: {
            rule_name: '',
            description: '',
            priority: '60',
            analysis_method_id: '',
            config_id: '',
            mongodb_instance: 'default',
            conditions: '',
            backfill_enabled: false,
        },

        // 可用的分析方法列表
        availableMethods: [],

        // 可用的配置列表
        availableConfigs: [],

        // 預覽資料
        previewData: {
            total: 0,
            records: [],
            sample: []
        },

        // JSON 驗證
        jsonValid: false,
        jsonError: '',

        // 建立狀態
        creating: false,
        created: false,
        createdRuleId: '',
        createdRouterId: '',

        // 防抖計時器
        previewTimer: null,

        /**
         * 初始化
         */
        init() {
            console.log('路由規則建立嚮導已初始化');
            this.loadMethods();
        },

        /**
         * 載入分析方法列表
         */
        async loadMethods() {
            try {
                const response = await fetch('/api/configs/methods');
                const data = await response.json();

                if (data.success) {
                    this.availableMethods = data.data;
                    console.log(`已載入 ${this.availableMethods.length} 個分析方法`);
                } else {
                    console.error('載入分析方法失敗:', data.error);
                }
            } catch (error) {
                console.error('載入分析方法失敗:', error);
            }
        },

        /**
         * 載入配置列表（根據分析方法 ID）
         */
        async loadConfigs() {
            // 清空配置列表
            this.availableConfigs = [];
            this.formData.config_id = '';

            if (!this.formData.analysis_method_id) {
                return;
            }

            try {
                const response = await fetch(`/api/configs/method/${this.formData.analysis_method_id}`);
                const data = await response.json();

                if (data.success) {
                    this.availableConfigs = data.data;
                    console.log(`已載入 ${this.availableConfigs.length} 個配置`);

                    // 如果只有一個配置，自動選擇
                    if (this.availableConfigs.length === 1) {
                        this.formData.config_id = this.availableConfigs[0].config_id;
                    }
                } else {
                    console.error('載入配置失敗:', data.error);
                }
            } catch (error) {
                console.error('載入配置失敗:', error);
            }
        },

        /**
         * 驗證 JSON
         */
        validateJson() {
            try {
                if (!this.formData.conditions) {
                    this.jsonValid = false;
                    this.jsonError = '請輸入篩選條件';
                    return false;
                }

                JSON.parse(this.formData.conditions);
                this.jsonValid = true;
                this.jsonError = '';
                return true;
            } catch (e) {
                this.jsonValid = false;
                this.jsonError = `JSON 格式錯誤: ${e.message}`;
                return false;
            }
        },

        /**
         * 防抖預覽
         */
        debouncePreview() {
            clearTimeout(this.previewTimer);
            this.previewTimer = setTimeout(() => {
                if (this.validateJson()) {
                    this.loadPreview();
                }
            }, 1000);
        },

        /**
         * 載入預覽資料
         */
        async loadPreview() {
            try {
                const conditions = JSON.parse(this.formData.conditions);

                const response = await fetch('/api/routing/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        conditions: conditions,
                        limit: 100
                    })
                });

                const data = await response.json();

                if (data.success) {
                    this.previewData = data.data;
                } else {
                    console.error('預覽失敗:', data.error);
                    this.previewData = { total: 0, records: [], sample: [] };
                }
            } catch (error) {
                console.error('載入預覽失敗:', error);
                this.previewData = { total: 0, records: [], sample: [] };
            }
        },

        /**
         * 檢查步驟 1 是否可以繼續
         */
        canProceedStep1() {
            return this.formData.rule_name &&
                   this.formData.analysis_method_id &&
                   this.formData.config_id &&
                   this.validateJson();
        },

        /**
         * 下一步
         */
        nextStep() {
            // 驗證當前步驟
            if (this.currentStep === 1) {
                if (!this.canProceedStep1()) {
                    alert('請填寫所有必填欄位並確保 JSON 格式正確');
                    return;
                }

                // 如果沒有啟用追溯，直接跳到步驟 3
                if (!this.formData.backfill_enabled) {
                    this.currentStep = 3;
                } else {
                    this.currentStep = 2;
                }
            } else if (this.currentStep === 2) {
                this.currentStep = 3;
            }
        },

        /**
         * 上一步
         */
        previousStep() {
            if (this.currentStep === 3 && this.formData.backfill_enabled) {
                this.currentStep = 2;
            } else if (this.currentStep === 3 && !this.formData.backfill_enabled) {
                this.currentStep = 1;
            } else if (this.currentStep === 2) {
                this.currentStep = 1;
            }
        },

        /**
         * 建立規則
         */
        async createRule() {
            this.creating = true;

            try {
                // 解析 conditions
                const conditions = JSON.parse(this.formData.conditions);

                // 構建 actions
                const actions = [
                    {
                        analysis_method_id: this.formData.analysis_method_id,
                        config_id: this.formData.config_id,
                        mongodb_instance: this.formData.mongodb_instance
                    }
                ];

                // 構建規則資料
                const ruleData = {
                    rule_name: this.formData.rule_name,
                    description: this.formData.description,
                    priority: parseInt(this.formData.priority),
                    conditions: conditions,
                    actions: actions,
                    enabled: true,
                    backfill_enabled: this.formData.backfill_enabled
                };

                // 建立規則
                const response = await fetch('/api/routing', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(ruleData)
                });

                const data = await response.json();

                if (data.success) {
                    this.createdRuleId = data.data.rule_id;
                    this.createdRouterId = data.data.router_ids[0]; // 取第一個 router_id

                    // 如果啟用追溯，執行追溯
                    if (this.formData.backfill_enabled) {
                        await this.executeBackfill(this.createdRouterId);
                    }

                    this.created = true;
                    this.creating = false;
                } else {
                    throw new Error(data.error || '建立規則失敗');
                }
            } catch (error) {
                console.error('建立規則失敗:', error);
                alert(`建立規則失敗: ${error.message}`);
                this.creating = false;
            }
        },

        /**
         * 執行追溯
         */
        async executeBackfill(routerId) {
            try {
                const response = await fetch(`/api/routing/${routerId}/backfill`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        limit: null // 不限制，處理所有符合條件的資料
                    })
                });

                const data = await response.json();

                if (data.success) {
                    console.log(`追溯成功: 創建 ${data.data.tasks_created} 個任務`);
                } else {
                    console.error('追溯失敗:', data.error);
                    alert(`警告：規則已建立，但追溯歷史資料失敗: ${data.error}`);
                }
            } catch (error) {
                console.error('執行追溯失敗:', error);
                alert(`警告：規則已建立，但追溯歷史資料失敗: ${error.message}`);
            }
        }
    };
}
