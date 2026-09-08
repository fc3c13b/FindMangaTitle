"""
migrate_db.py - folder_titlesを再構築するスクリプト

1. folder_titles全削除
2. processing_logからrule_success分（confidence >= threshold）を移行
3. 残りのLLM対象フォルダは次のステップで再スキャン
"""

import sqlite3
from config import get_quality_threshold

DB_PATH = "manga_titles.db"


def rebuild_folder_titles():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    threshold = get_quality_threshold()
    print(f"品質閾値: {threshold}")

    # 1. folder_titles全削除
    cursor.execute("DELETE FROM folder_titles")
    deleted = cursor.rowcount
    print(f"folder_titles全削除: {deleted}件")

    # 2. processing_logからrule_success分を移行
    # rule_appliedが'cache_hit'以外でconfidence >= thresholdのものを移行
    query = """
        INSERT OR REPLACE INTO folder_titles (folder_name, correct_title, confidence, source)
        SELECT folder_name, extracted_title, confidence, 'rule'
        FROM processing_log
        WHERE confidence >= ?
          AND rule_applied != 'cache_hit'
          AND extracted_title != ''
    """
    cursor.execute(query, (threshold,))
    migrated = cursor.rowcount
    print(f"processing_logから移行: {migrated}件")

    # 3. 残りLLM対象フォルダ数をカウント
    query_remaining = """
        SELECT COUNT(*) FROM processing_log
        WHERE confidence < ?
           OR extracted_title = ''
    """
    cursor.execute(query_remaining, (threshold,))
    remaining = cursor.fetchone()[0]
    print(f"LLM再スキャン対象: {remaining}件")

    conn.commit()
    conn.close()

    # 最終確認
    conn2 = sqlite3.connect(DB_PATH)
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT COUNT(*) FROM folder_titles")
    final_count = cursor2.fetchone()[0]
    conn2.close()
    print(f"\n再構築完了: folder_titles {final_count}件")


if __name__ == "__main__":
    rebuild_folder_titles()