"""
config.py - 設定ファイル読み込みモジュール
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# デフォルト値
DEFAULTS = {
    "quality_threshold": 0.7,
    "llm_model": "gemini-1.5-flash",
    "max_batch_size": 500,
    "db_path": "manga_titles.db",
}


def load_config() -> dict:
    """設定ファイルを読み込む（存在しない場合はデフォルト値）"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        DEFAULTS.update(user_config)
    return dict(DEFAULTS)


def get_db_path() -> str:
    """DBファイルのフルパスを返す"""
    config = load_config()
    db_path = config["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(__file__), db_path)
    return db_path


def get_quality_threshold() -> float:
    """品質閾値を返す"""
    return load_config()["quality_threshold"]


def get_llm_model() -> str:
    """LLMモデル名を返す"""
    return load_config()["llm_model"]