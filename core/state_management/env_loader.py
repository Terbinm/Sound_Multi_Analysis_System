"""
在 core/state_management 內提供 env_loader 的代理
確保共用專案根目錄的 load_project_env 函數
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV_LOADER = PROJECT_ROOT / 'env_loader.py'
MODULE_NAME = '_project_root_env_loader'


def _load_root_env_module() -> ModuleType:
    """透過路徑載入專案根目錄的 env_loader 模組"""
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]

    spec = importlib.util.spec_from_file_location(MODULE_NAME, ROOT_ENV_LOADER)
    if spec is None or spec.loader is None:
        raise ImportError(f'無法載入 env_loader 模組: {ROOT_ENV_LOADER}')

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    sys.modules[MODULE_NAME] = module
    return module


_root_env_module = _load_root_env_module()

# 重新導出函式避免其他模組修改引用路徑
load_project_env = _root_env_module.load_project_env
