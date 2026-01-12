"""
提供可配置欄位的結構化描述，讓節點註冊時可把可填寫項目與 Markdown 說明寫進 nodes_status。
"""
from textwrap import dedent
from typing import Dict, Any, List

from config import (
    AUDIO_CONFIG,
    CONVERSION_CONFIG,
    LEAF_CONFIG,
    CLASSIFICATION_CONFIG,
)


def _section_fields(defaults: Dict[str, Any], field_order: List[str], section_key: str) -> List[Dict[str, Any]]:
    """
    按指定順序輸出欄位描述，保留型別資訊以便表單渲染。
    """
    fields = []
    for key in field_order:
        if key not in defaults:
            continue
        value = defaults[key]
        field_type = "list" if isinstance(value, list) else "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "text"
        fields.append({
            "section": section_key,
            "name": key,
            "label": key,
            "type": field_type,
            "default": value,
            "description": ""
        })
    return fields


def get_config_schema() -> Dict[str, Any]:
    """
    回傳節點可用來生成表單的配置 schema 與 Markdown。
    """
    markdown = dedent(f"""
    # 可配置參數快速參考

    ## AUDIO_CONFIG
    - slice_duration: {AUDIO_CONFIG['slice_duration']}
    - slice_interval: {AUDIO_CONFIG['slice_interval']}
    - channels: {AUDIO_CONFIG['channels']}
    - sample_rate: {AUDIO_CONFIG['sample_rate']}
    - min_segment_duration: {AUDIO_CONFIG['min_segment_duration']}

    ## CONVERSION_CONFIG
    - supported_input_formats: {CONVERSION_CONFIG['supported_input_formats']}
    - csv_header: {CONVERSION_CONFIG['csv_header']}
    - csv_normalize: {CONVERSION_CONFIG['csv_normalize']}
    - output_format: {CONVERSION_CONFIG['output_format']}
    - output_sample_rate: {CONVERSION_CONFIG['output_sample_rate']}

    ## LEAF_CONFIG
    - n_filters: {LEAF_CONFIG['n_filters']}
    - sample_rate: {LEAF_CONFIG['sample_rate']}
    - window_len: {LEAF_CONFIG['window_len']}
    - window_stride: {LEAF_CONFIG['window_stride']}
    - pcen_compression: {LEAF_CONFIG['pcen_compression']}
    - init_min_freq: {LEAF_CONFIG['init_min_freq']}
    - init_max_freq: {LEAF_CONFIG['init_max_freq']}
    - batch_size: {LEAF_CONFIG['batch_size']}
    - device: {LEAF_CONFIG['device']}

    ## CLASSIFICATION_CONFIG
    - default_method: {CLASSIFICATION_CONFIG['default_method']} (支援: {CLASSIFICATION_CONFIG.get('support_list', [])})
    - use_model: {CLASSIFICATION_CONFIG.get('use_model', False)}
    - classes: {CLASSIFICATION_CONFIG['classes']}
    - normal_probability: {CLASSIFICATION_CONFIG['normal_probability']}
    - model_path: {CLASSIFICATION_CONFIG['model_path']}
    - threshold: {CLASSIFICATION_CONFIG['threshold']}
    """).strip()

    sections = [
        {
            "key": "audio",
            "title": "AUDIO_CONFIG",
            "fields": _section_fields(
                AUDIO_CONFIG,
                ["slice_duration", "slice_interval", "channels", "sample_rate", "min_segment_duration"],
                "audio"
            )
        },
        {
            "key": "conversion",
            "title": "CONVERSION_CONFIG",
            "fields": _section_fields(
                CONVERSION_CONFIG,
                ["supported_input_formats", "csv_header", "csv_normalize", "output_format", "output_sample_rate"],
                "conversion"
            )
        },
        {
            "key": "leaf",
            "title": "LEAF_CONFIG",
            "fields": _section_fields(
                LEAF_CONFIG,
                ["n_filters", "sample_rate", "window_len", "window_stride", "pcen_compression",
                 "init_min_freq", "init_max_freq", "batch_size", "device"],
                "leaf"
            )
        },
        {
            "key": "classification",
            "title": "CLASSIFICATION_CONFIG",
            "fields": _section_fields(
                CLASSIFICATION_CONFIG,
                ["default_method", "support_list", "use_model", "classes", "normal_probability", "model_path", "threshold"],
                "classification"
            )
        }
    ]

    return {
        "markdown": markdown,
        "sections": sections
    }


def build_node_config_metadata() -> Dict[str, Any]:
    """
    給節點註冊用的完整 metadata，直接寫入 nodes_status.info。
    """
    schema = get_config_schema()
    return {
        "config_markdown": schema["markdown"],
        "config_schema": schema["sections"],
        "analysis_config_template": {
            "parameters": {
                "audio": AUDIO_CONFIG,
                "conversion": CONVERSION_CONFIG,
                "leaf": LEAF_CONFIG,
                "classification": CLASSIFICATION_CONFIG
            }
        }
    }
