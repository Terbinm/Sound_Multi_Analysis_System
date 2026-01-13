"""
統一分析配置 Schema 定義

此模組定義了分析服務的完整配置結構，包含：
- Schema 版本號（確保分佈式節點一致性）
- 分類方法定義（含模型需求）
- 參數群組定義（含欄位類型、標題、說明、預設值）

前端透過 API 取得此 Schema 後，可動態生成配置表單。
"""

from typing import Dict, Any, List, Optional
import hashlib
import json

# ==================== Schema 版本 ====================
SCHEMA_VERSION = "1.0.0"


def _generate_schema_hash(schema_data: Dict[str, Any]) -> str:
    """
    根據 Schema 內容生成雜湊值，用於驗證配置一致性。
    """
    schema_str = json.dumps(schema_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(schema_str.encode('utf-8')).hexdigest()[:16]


# ==================== 模型檔案定義 ====================
MODEL_FILES_DEFINITION: Dict[str, Dict[str, Any]] = {
    'rf_model': {
        'key': 'rf_model',
        'label': 'RF 分類模型',
        'filename': 'mimii_fan_rf_classifier.pkl',
        'description': 'Random Forest 分類模型檔案',
        'extensions': ['.pkl'],
    },
    'rf_metadata': {
        'key': 'rf_metadata',
        'label': '模型元資料',
        'filename': 'model_metadata.json',
        'description': 'RF 模型的元資料（類別、特徵等資訊）',
        'extensions': ['.json'],
    },
    'cyclegan_checkpoint': {
        'key': 'cyclegan_checkpoint',
        'label': 'CycleGAN 檢查點',
        'filename': 'last.ckpt',
        'description': 'CycleGAN 模型檢查點檔案',
        'extensions': ['.ckpt', '.pth'],
    },
    'cyclegan_normalization': {
        'key': 'cyclegan_normalization',
        'label': 'CycleGAN 正規化參數',
        'filename': 'normalization_params.json',
        'description': 'CycleGAN 輸入正規化參數',
        'extensions': ['.json'],
    },
}


# ==================== 分類方法定義 ====================
CLASSIFICATION_METHODS: List[Dict[str, Any]] = [
    {
        'key': 'random',
        'label': '隨機分類',
        'description': '不使用模型的隨機分類，依機率分配結果',
        'version': '1.0.0',
        'required_models': [],
        'optional_models': [],
        'params': [
            {
                'name': 'normal_probability',
                'label': '正常機率',
                'type': 'number',
                'description': '分類為正常的機率 (0-1)',
                'default': 0.7,
                'min': 0,
                'max': 1,
                'step': 0.05,
            },
        ],
    },
    {
        'key': 'rf_model',
        'label': '隨機森林分類器',
        'description': '使用 LEAF 特徵的隨機森林模型進行分類',
        'version': '1.0.0',
        'required_models': ['rf_model'],
        'optional_models': ['rf_metadata'],
        'params': [
            {
                'name': 'threshold',
                'label': '決策閾值',
                'type': 'number',
                'description': '分類決策的機率閾值',
                'default': 0.5,
                'min': 0,
                'max': 1,
                'step': 0.05,
            },
            {
                'name': 'rf_aggregation',
                'label': '特徵聚合方式',
                'type': 'select',
                'description': '多片段特徵的聚合方法',
                'default': 'mean',
                'options': [
                    {'value': 'mean', 'label': '平均值'},
                    {'value': 'max', 'label': '最大值'},
                    {'value': 'median', 'label': '中位數'},
                    {'value': 'flatten', 'label': '展平 (串接)'},
                ],
            },
        ],
    },
    {
        'key': 'cyclegan_rf',
        'label': 'CycleGAN + 隨機森林',
        'description': '透過 CycleGAN 進行特徵轉換後使用隨機森林分類',
        'version': '1.0.0',
        'required_models': ['cyclegan_checkpoint', 'rf_model'],
        'optional_models': ['cyclegan_normalization', 'rf_metadata'],
        'params': [
            {
                'name': 'threshold',
                'label': '決策閾值',
                'type': 'number',
                'description': '分類決策的機率閾值',
                'default': 0.5,
                'min': 0,
                'max': 1,
                'step': 0.05,
            },
            {
                'name': 'cyclegan_direction',
                'label': 'CycleGAN 轉換方向',
                'type': 'select',
                'description': '特徵轉換方向',
                'default': 'AtoB',
                'options': [
                    {'value': 'AtoB', 'label': 'A 到 B (正常到異常)'},
                    {'value': 'BtoA', 'label': 'B 到 A (異常到正常)'},
                ],
            },
            {
                'name': 'apply_normalization',
                'label': '套用正規化',
                'type': 'boolean',
                'description': '是否在 CycleGAN 前套用正規化',
                'default': True,
            },
            {
                'name': 'rf_aggregation',
                'label': '特徵聚合方式',
                'type': 'select',
                'description': '多片段特徵的聚合方法',
                'default': 'mean',
                'options': [
                    {'value': 'mean', 'label': '平均值'},
                    {'value': 'max', 'label': '最大值'},
                    {'value': 'median', 'label': '中位數'},
                    {'value': 'flatten', 'label': '展平 (串接)'},
                ],
            },
        ],
    },
]


# ==================== 參數群組定義 ====================
PARAMETER_GROUPS: List[Dict[str, Any]] = [
    {
        'key': 'classification',
        'label': '分類設定',
        'description': '基本分類參數',
        'collapsed': False,
        'fields': [
            {
                'name': 'classes',
                'label': '分類類別',
                'type': 'tags',
                'description': '定義分類標籤（以逗號分隔）',
                'default': ['normal', 'abnormal'],
                'suggestions': ['normal', 'abnormal', 'unknown'],
            },
        ],
    },
    {
        'key': 'audio',
        'label': '音訊處理',
        'description': '音訊切片與取樣參數',
        'collapsed': True,
        'fields': [
            {
                'name': 'slice_duration',
                'label': '切片時長（秒）',
                'type': 'number',
                'description': '每個音訊切片的時長（秒）',
                'default': 0.16,
                'min': 0.01,
                'max': 10.0,
                'step': 0.01,
            },
            {
                'name': 'slice_interval',
                'label': '切片間隔（秒）',
                'type': 'number',
                'description': '切片起始點之間的間隔',
                'default': 0.20,
                'min': 0.01,
                'max': 10.0,
                'step': 0.01,
            },
            {
                'name': 'sample_rate',
                'label': '取樣率（Hz）',
                'type': 'select',
                'description': '音訊取樣率',
                'default': 16000,
                'options': [
                    {'value': 8000, 'label': '8000 Hz'},
                    {'value': 16000, 'label': '16000 Hz'},
                    {'value': 22050, 'label': '22050 Hz'},
                    {'value': 44100, 'label': '44100 Hz'},
                ],
            },
            {
                'name': 'channels',
                'label': '音訊聲道',
                'type': 'select',
                'description': '要處理的聲道',
                'default': [1],
                'options': [
                    {'value': [1], 'label': '聲道 1'},
                    {'value': [2], 'label': '聲道 2'},
                    {'value': [1, 2], 'label': '雙聲道'},
                ],
            },
            {
                'name': 'min_segment_duration',
                'label': '最小片段時長（秒）',
                'type': 'number',
                'description': '有效片段的最小時長',
                'default': 0.05,
                'min': 0.01,
                'max': 1.0,
                'step': 0.01,
            },
        ],
    },
    {
        'key': 'conversion',
        'label': '檔案轉換',
        'description': '輸入檔案轉換設定',
        'collapsed': True,
        'fields': [
            {
                'name': 'csv_normalize',
                'label': '正規化 CSV 數值',
                'type': 'boolean',
                'description': '自動正規化 CSV 中超出範圍的數值',
                'default': True,
            },
            {
                'name': 'csv_header',
                'label': 'CSV 標題列',
                'type': 'select',
                'description': 'CSV 檔案是否包含標題列',
                'default': None,
                'options': [
                    {'value': None, 'label': '無標題'},
                    {'value': 0, 'label': '第一列為標題'},
                ],
            },
        ],
    },
    {
        'key': 'leaf',
        'label': 'LEAF 特徵擷取',
        'description': 'LEAF 音訊前端參數',
        'collapsed': True,
        'fields': [
            {
                'name': 'n_filters',
                'label': '濾波器數量',
                'type': 'number',
                'description': '濾波器組聲道數',
                'default': 40,
                'min': 10,
                'max': 128,
                'step': 1,
            },
            {
                'name': 'window_len',
                'label': '視窗長度（毫秒）',
                'type': 'number',
                'description': '分析視窗長度（毫秒）',
                'default': 25.0,
                'min': 5.0,
                'max': 100.0,
                'step': 1.0,
            },
            {
                'name': 'window_stride',
                'label': '視窗步進（毫秒）',
                'type': 'number',
                'description': '視窗跳躍大小（毫秒）',
                'default': 10.0,
                'min': 1.0,
                'max': 50.0,
                'step': 1.0,
            },
            {
                'name': 'init_min_freq',
                'label': '最小頻率（Hz）',
                'type': 'number',
                'description': '濾波器組的最小頻率',
                'default': 60.0,
                'min': 0.0,
                'max': 1000.0,
                'step': 10.0,
            },
            {
                'name': 'init_max_freq',
                'label': '最大頻率（Hz）',
                'type': 'number',
                'description': '濾波器組的最大頻率',
                'default': 8000.0,
                'min': 1000.0,
                'max': 22050.0,
                'step': 100.0,
            },
            {
                'name': 'pcen_compression',
                'label': 'PCEN 壓縮',
                'type': 'boolean',
                'description': '啟用 Per-Channel Energy Normalization',
                'default': True,
            },
            {
                'name': 'batch_size',
                'label': '批次大小',
                'type': 'number',
                'description': '處理批次大小',
                'default': 32,
                'min': 1,
                'max': 256,
                'step': 1,
            },
        ],
    },
]


def get_analysis_config_schema() -> Dict[str, Any]:
    """
    取得完整的分析配置 Schema。

    Returns:
        包含版本、分類方法、參數群組的完整 Schema
    """
    schema = {
        'schema_version': SCHEMA_VERSION,
        'classification_methods': CLASSIFICATION_METHODS,
        'model_files': MODEL_FILES_DEFINITION,
        'parameter_groups': PARAMETER_GROUPS,
    }

    # 計算 Schema 雜湊值
    schema['schema_hash'] = _generate_schema_hash({
        'version': SCHEMA_VERSION,
        'methods': CLASSIFICATION_METHODS,
        'groups': PARAMETER_GROUPS,
    })

    return schema


def get_method_by_key(method_key: str) -> Optional[Dict[str, Any]]:
    """
    根據 key 取得分類方法定義。
    """
    for method in CLASSIFICATION_METHODS:
        if method['key'] == method_key:
            return method
    return None


def get_model_requirements(method_key: str) -> Dict[str, Any]:
    """
    取得指定分類方法的模型需求（相容舊版 MODEL_REQUIREMENTS 格式）。

    此函式提供向後相容性，返回與原 config.py 中 MODEL_REQUIREMENTS 相同的格式。
    """
    method = get_method_by_key(method_key)
    if not method:
        return {
            'description': 'Unknown method',
            'required_files': [],
            'optional_files': [],
        }

    required_files = []
    for model_key in method.get('required_models', []):
        if model_key in MODEL_FILES_DEFINITION:
            model_def = MODEL_FILES_DEFINITION[model_key].copy()
            required_files.append(model_def)

    optional_files = []
    for model_key in method.get('optional_models', []):
        if model_key in MODEL_FILES_DEFINITION:
            model_def = MODEL_FILES_DEFINITION[model_key].copy()
            optional_files.append(model_def)

    return {
        'description': method.get('label', method_key),
        'required_files': required_files,
        'optional_files': optional_files,
    }


def get_all_model_requirements() -> Dict[str, Dict[str, Any]]:
    """
    取得所有分類方法的模型需求（相容舊版格式）。
    """
    requirements = {}
    for method in CLASSIFICATION_METHODS:
        requirements[method['key']] = get_model_requirements(method['key'])
    return requirements


def get_default_parameters() -> Dict[str, Any]:
    """
    取得所有參數的預設值。

    Returns:
        按群組組織的預設參數字典
    """
    defaults = {}
    for group in PARAMETER_GROUPS:
        group_key = group['key']
        defaults[group_key] = {}
        for field in group.get('fields', []):
            defaults[group_key][field['name']] = field.get('default')
    return defaults


def get_method_default_params(method_key: str) -> Dict[str, Any]:
    """
    取得指定分類方法的預設參數。
    """
    method = get_method_by_key(method_key)
    if not method:
        return {}

    params = {}
    for param in method.get('params', []):
        params[param['name']] = param.get('default')
    return params


def validate_parameters(parameters: Dict[str, Any], method_key: str) -> List[str]:
    """
    驗證參數是否符合 Schema 定義。

    Returns:
        錯誤訊息列表，空列表表示驗證通過
    """
    errors = []
    method = get_method_by_key(method_key)

    # 驗證分類方法特定參數
    if method:
        for param_def in method.get('params', []):
            param_name = param_def['name']
            # 檢查方法特定參數（通常在 classification 群組下或直接在 parameters 中）
            # 這裡只做基本驗證，可根據需求擴展

    # 驗證參數群組
    for group in PARAMETER_GROUPS:
        group_key = group['key']
        group_params = parameters.get(group_key, {})

        for field in group.get('fields', []):
            field_name = field['name']
            field_type = field.get('type')
            value = group_params.get(field_name)

            if value is None:
                continue  # 允許使用預設值

            # 數值範圍驗證
            if field_type == 'number':
                if not isinstance(value, (int, float)):
                    errors.append(f"{group_key}.{field_name}: Expected number")
                    continue
                if 'min' in field and value < field['min']:
                    errors.append(f"{group_key}.{field_name}: Value {value} below minimum {field['min']}")
                if 'max' in field and value > field['max']:
                    errors.append(f"{group_key}.{field_name}: Value {value} above maximum {field['max']}")

            # 選項驗證
            elif field_type == 'select':
                valid_values = [opt['value'] for opt in field.get('options', [])]
                if value not in valid_values:
                    errors.append(f"{group_key}.{field_name}: Invalid option '{value}'")

            # 布林值驗證
            elif field_type == 'boolean':
                if not isinstance(value, bool):
                    errors.append(f"{group_key}.{field_name}: Expected boolean")

    return errors


# ==================== 向後相容：舊版 config_schema 函式 ====================

def get_config_schema() -> Dict[str, Any]:
    """
    回傳節點可用來生成表單的配置 schema（向後相容）。
    """
    schema = get_analysis_config_schema()

    # 轉換為舊版 sections 格式
    sections = []
    for group in PARAMETER_GROUPS:
        section = {
            'key': group['key'],
            'title': group['label'],
            'fields': []
        }
        for field in group.get('fields', []):
            section['fields'].append({
                'section': group['key'],
                'name': field['name'],
                'label': field.get('label', field['name']),
                'type': field.get('type', 'text'),
                'default': field.get('default'),
                'description': field.get('description', ''),
            })
        sections.append(section)

    return {
        'schema_version': schema['schema_version'],
        'schema_hash': schema['schema_hash'],
        'sections': sections,
    }


def build_node_config_metadata() -> Dict[str, Any]:
    """
    給節點註冊用的完整 metadata（向後相容）。
    """
    schema = get_analysis_config_schema()
    return {
        'schema_version': schema['schema_version'],
        'schema_hash': schema['schema_hash'],
        'config_schema': schema,
        'analysis_config_template': {
            'parameters': get_default_parameters(),
        }
    }
