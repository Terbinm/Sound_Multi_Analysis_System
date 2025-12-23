# env_loader.py
import os
from pathlib import Path
from dotenv import load_dotenv

# 專案根目錄 = env_loader.py 所在的位置
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

def load_project_env():
    """強制全域載入 .env"""
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)
    return ENV_PATH
