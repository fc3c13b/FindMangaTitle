"""
database.py - SQLite DB 操作モジュール

漫画タイトル抽出用のデータベース管理
- フォルダー名と正解タイトールのマッピング
- 抽出ルール/パターンの保存
- 処理履歴の記録
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple


DB_PATH = os.path.join(os.path.dirname(__file__), "manga_titles.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """データベース接続を取得"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")  # 並列読み書き最適化
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def initialize_database(db_path: str = DB_PATH):
    """データベースとテーブルを作成"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # フォルダー名 → タイトールマッピングテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folder_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            correct_title TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'manual',  -- manual, llm, rule
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 抽出ルールテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extraction_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            replacement TEXT DEFAULT '',
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 処理履歴テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL,
            extracted_title TEXT,
            rule_applied TEXT,
            confidence REAL,
            processing_time_ms REAL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # インデックス作成
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_folder_name
        ON folder_titles(folder_name)
    """)

    conn.commit()
    conn.close()
    print(f"データベース初期化完了: {db_path}")


def insert_folder_title(
    folder_name: str,
    correct_title: str,
    confidence: float = 1.0,
    source: str = "manual",
    db_path: str = DB_PATH
):
    """フォルダー名とタイトールのペアを挿入"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 既存レコードの更新または新規挿入
    cursor.execute("""
        INSERT INTO folder_titles (folder_name, correct_title, confidence, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(folder_name) DO UPDATE SET
            correct_title=excluded.correct_title,
            confidence=excluded.confidence,
            source=excluded.source,
            updated_at=CURRENT_TIMESTAMP
    """, (folder_name, correct_title, confidence, source))

    conn.commit()
    conn.close()


def insert_batch_titles(
    titles: List[Tuple[str, str, float, str]],
    db_path: str = DB_PATH
):
    """バッチ挿入 (folder_name, correct_title, confidence, source)"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    for folder_name, correct_title, confidence, source in titles:
        cursor.execute("""
            INSERT INTO folder_titles (folder_name, correct_title, confidence, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(folder_name) DO UPDATE SET
                correct_title=excluded.correct_title,
                confidence=excluded.confidence,
                source=excluded.source,
                updated_at=CURRENT_TIMESTAMP
        """, (folder_name, correct_title, confidence, source))

    conn.commit()
    conn.close()


def get_title_by_folder(folder_name: str, db_path: str = DB_PATH) -> Optional[str]:
    """フォルダー名からタイトルを取得"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT correct_title, confidence FROM folder_titles
        WHERE folder_name = ?
    """, (folder_name,))

    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    return None


def get_all_titles(db_path: str = DB_PATH) -> List[Tuple[str, str]]:
    """すべてのタイトルデータを取得"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT folder_name, correct_title FROM folder_titles
        ORDER BY id
    """)

    results = cursor.fetchall()
    conn.close()
    return results


def get_learning_data(db_path: str = DB_PATH) -> List[Tuple[str, str]]:
    """学習用データを取得（手動ラベル付きのみ）"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT folder_name, correct_title FROM folder_titles
        WHERE source = 'manual'
        ORDER BY id
    """)

    results = cursor.fetchall()
    conn.close()
    return results


def insert_extraction_rule(
    rule_name: str,
    pattern: str,
    replacement: str = "",
    description: str = "",
    priority: int = 0,
    db_path: str = DB_PATH
):
    """抽出ルールを挿入"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO extraction_rules
        (rule_name, pattern, replacement, description, priority)
        VALUES (?, ?, ?, ?, ?)
    """, (rule_name, pattern, replacement, description, priority))

    conn.commit()
    conn.close()


def get_active_rules(db_path: str = DB_PATH) -> List[Tuple[str, str, str, int]]:
    """有効な抽出ルールを取得（優先度順）"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT rule_name, pattern, replacement, priority
        FROM extraction_rules
        WHERE is_active = 1
        ORDER BY priority DESC
    """)

    results = cursor.fetchall()
    conn.close()
    return results


def log_processing(
    folder_name: str,
    extracted_title: str,
    rule_applied: str = "",
    confidence: float = 0.0,
    processing_time_ms: float = 0.0,
    db_path: str = DB_PATH
):
    """処理履歴をログ"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO processing_log
        (folder_name, extracted_title, rule_applied, confidence, processing_time_ms)
        VALUES (?, ?, ?, ?, ?)
    """, (folder_name, extracted_title, rule_applied, confidence, processing_time_ms))

    conn.commit()
    conn.close()


def get_statistics(db_path: str = DB_PATH) -> dict:
    """統計情報を取得"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM folder_titles")
    total_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT source, COUNT(*), AVG(confidence)
        FROM folder_titles
        GROUP BY source
    """)
    source_stats = cursor.fetchall()

    conn.close()

    return {
        "total_entries": total_count,
        "source_breakdown": {row[0]: {"count": row[1], "avg_confidence": row[2]}
                             for row in source_stats}
    }


if __name__ == "__main__":
    initialize_database()
    print("データベース初期化完了")