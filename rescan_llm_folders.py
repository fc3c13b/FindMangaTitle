"""
rescan_llm_folders.py - LLM対象フォルダのみを再スキャン

processing_logからconfidence < thresholdの未処理分を抽出し、
修正後のextractor.pyで再スキャンする。
"""

import csv
import sqlite3
from dotenv import load_dotenv
from config import get_quality_threshold

DB_PATH = "manga_titles.db"
PENDING_CSV = "llm_pending_folders.csv"


def extract_pending_folders():
    """processing_logからLLM対象フォルダを抽出"""
    threshold = get_quality_threshold()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
        SELECT DISTINCT folder_name FROM processing_log
        WHERE confidence < ? OR extracted_title = ''
        ORDER BY folder_name
    """
    cursor.execute(query, (threshold,))
    rows = cursor.fetchall()
    conn.close()

    folders = [row[0] for row in rows]
    
    with open(PENDING_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['folder_name'])
        for fn in folders:
            writer.writerow([fn])

    print(f"LLM対象フォルダ抽出完了: {len(folders)}件 → {PENDING_CSV}")
    return folders


def main():
    load_dotenv()
    threshold = get_quality_threshold()
    print(f"品質閾値: {threshold}")
    
    # 1. 未処理フォルダをCSVに出力
    folders = extract_pending_folders()
    
    # 2. extractor.pyのbatch_extractで再スキャン
    from extractor import MangaTitleExtractor
    
    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    extractor = MangaTitleExtractor(use_llm=True, api_key=api_key)
    results = extractor.batch_extract(folders, save_to_db=True)
    
    print(f"\n再スキャン完了: {len(results)}件処理済み")


if __name__ == "__main__":
    main()