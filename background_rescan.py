"""
background_rescan.py - バックグラウンドでLLM再スキャンを実行

チェックポイント機能付き。途中中断しても続きから再開可能。
DOS窓のコンソールとrescan.logに進行状況を出力。

使い方:
    python background_rescan.py
"""

import csv
import json
import sqlite3
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# ============================================================
# 設定
# ============================================================
DB_PATH = "manga_titles.db"
CHECKPOINT_FILE = "checkpoint.json"
LOG_FILE = "rescan.log"
PENDING_CSV = "llm_pending_folders.csv"

BATCH_SIZE = 50          # 1バッチあたりのフォルダ数
API_WAIT_SEC = 5         # API呼び出し間のウェイト（秒）
BATCH_WAIT_SEC = 30      # バッチ間の待機時間（秒）

# ============================================================
# ユーティリティ
# ============================================================
def log_message(msg):
    """コンソールとログファイルに出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_checkpoint():
    """チェックポイントを読み込み（なければ空）"""
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed": [], "total": 0}

def save_checkpoint(processed_list, total):
    """チェックポイントを保存"""
    data = {
        "processed": processed_list,
        "total": total,
        "timestamp": datetime.now().isoformat()
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============================================================
# メイン処理
# ============================================================
def main():
    load_dotenv()

    log_message("=" * 60)
    log_message("LLM再スキャン開始")
    log_message(f"バッチサイズ: {BATCH_SIZE}, APIウェイト: {API_WAIT_SEC}秒, バッチ間待機: {BATCH_WAIT_SEC}秒")

    # 1. チェックポイント読み込み
    checkpoint = load_checkpoint()
    processed_set = set(checkpoint.get("processed", []))
    log_message(f"チェックポイント読み込み: {len(processed_set)}件の処理済みデータを検出")

    # 2. 未処理フォルダをCSVから読み込み（既処理分は除外）
    if not PENDING_CSV or not __import__('os').path.exists(PENDING_CSV):
        log_message(f"エラー: {PENDING_CSV} が見つかりません")
        sys.exit(1)

    folders = []
    with open(PENDING_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("folder_name", "").strip()
            if fn and fn not in processed_set:
                folders.append(fn)

    total = len(folders)
    log_message(f"処理対象フォルダ: {total}件（チェックポイント既処理分は除外済み）")

    if total == 0:
        log_message("未処理フォルダがありません。完了しました。")
        return

    # 3. extractor.pyのMangaTitleExtractorを使用
    from extractor import MangaTitleExtractor, LLMRateLimitError

    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    extractor = MangaTitleExtractor(use_llm=True, api_key=api_key)

    # 4. バッチ処理ループ
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    processed_list = list(processed_set)  # 既処理分を継承
    llm_success_total = 0
    llm_429_total = 0
    consecutive_429_count = 0  # 連続429エラー回数
    MAX_CONSECUTIVE_429 = 3   # この回数連続で429なら処理終了
    start_date = datetime.now().strftime("%Y-%m-%d")  # 開始日（翌日判定用）

    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_folders = folders[start:end]
        
        batch_start_time = time.time()
        batch_llm_success = 0
        batch_rule = 0
        batch_429 = 0

        for folder_name in batch_folders:
            try:
                title, confidence, method = extractor.extract(folder_name)
                
                if method == "llm":
                    batch_llm_success += 1
                    llm_success_total += 1
                elif method == "rule":
                    batch_rule += 1
                    
                processed_list.append(folder_name)

            except LLMRateLimitError as e:
                # 429エラー → このフォルダと残りはスキップして次のバッチで再試行
                log_message(f"  ⚠ API容量不足 (429): {e}")
                batch_429 += 1
                llm_429_total += 1
                
                # 現在のフォルダをprocessed_listに追加しない（次回リトライ）
                # 残りのフォルダもprocessed_listに加えないが、バッチは続行
                consecutive_429_count += 1
                break

            # API間ウェイト
            time.sleep(API_WAIT_SEC)

        batch_elapsed = time.time() - batch_start_time
        current_total = start + len(batch_folders)
        progress_pct = (len(processed_list) / (total + len(checkpoint.get("processed", [])))) * 100 if total > 0 else 100
        
        log_message(
            f"[バッチ {batch_idx+1}/{num_batches}] "
            f"処理完了: {len(batch_folders)}件 "
            f"(LLM成功: {batch_llm_success}, ルール: {batch_rule}, 429: {batch_429}) | "
            f"累計: {len(processed_list)}/{total + len(checkpoint.get('processed', []))}件 "
            f"({progress_pct:.1f}%) | "
            f"所要時間: {batch_elapsed:.0f}秒"
        )

        # チェックポイント保存
        save_checkpoint(processed_list, total)

        # 連続429エラー判定＆翌日判定
        if batch_429 > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            if today != start_date:
                # 日付が変わった → API枠がリセットされたとみなしてカウンターをリセット
                log_message(f"🔄 日付が変更されました ({start_date} → {today})。API枠がリセットされたため継続します。")
                consecutive_429_count = 0
                start_date = today
            elif consecutive_429_count >= MAX_CONSECUTIVE_429:
                log_message(f"⚠ 連続{consecutive_429_count}回429エラーが発生しました。API枠が尽きたため処理を終了します。")
                log_message(f"既処理: {len(processed_list)}件 / 総数: {total}件（残り分は次回再実行で処理されます）")
                return
        else:
            consecutive_429_count = 0  # 429がなければカウンターをリセット

        # バッチ間待機
        if batch_idx < num_batches - 1 and batch_429 == 0:
            log_message(f"次バッチまで {BATCH_WAIT_SEC}秒待機...")
            time.sleep(BATCH_WAIT_SEC)

    # 5. 完了メッセージ
    log_message("=" * 60)
    log_message("全件処理完了!")
    log_message(f"LLM成功: {llm_success_total}件, ルール: ???件（累計）")
    log_message(f"チェックポイントファイル: {CHECKPOINT_FILE}")
    log_message(f"ログファイル: {LOG_FILE}")

if __name__ == "__main__":
    main()