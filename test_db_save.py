"""
test_db_save.py - DB保存ロジックのテストスクリプト

processing_logのサンプリングデータを使って、extract()の結果と
folder_titlesテーブルの内容を比較し、DB保存状態を検証する。

出力: test_results/test_output.csv
列構成:
  folder_name, expected_title, actual_extracted_title,
  db_folder_name, db_correct_title, method, confidence, db_save_status
"""

import csv
import os
from typing import Dict, List, Optional, Tuple

# extractor.py と同じモジュールパスを設定
from database import get_title_by_folder, get_connection

DB_PATH = os.path.join(os.path.dirname(__file__), "manga_titles.db")


def check_db_save_status(
    folder_name: str,
    expected_title: str,
    actual_extracted_title: str,
    method: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    DBに正しく保存されているかチェック。

    Returns:
        (db_save_status, db_folder_name, db_correct_title)
        - OK: 正しく保存されている
        - MISSING: DBに存在しない
        - WRONG_FOLDER_NAME: folder_nameカラムが間違っている
        - WRONG_TITLE: correct_titleカラムが間違っている
    """
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    # folder_titles从这个フォルダ名で検索
    cursor.execute(
        "SELECT folder_name, correct_title FROM folder_titles WHERE folder_name = ?",
        (folder_name,),
    )
    exact_match = cursor.fetchone()

    # 万が一、extracted_titleがfolder_nameとして保存されている場合もチェック
    if exact_match is None and method == "llm":
        cursor.execute(
            "SELECT folder_name, correct_title FROM folder_titles WHERE folder_name = ?",
            (actual_extracted_title,),
        )
        wrong_folder_match = cursor.fetchone()
        conn.close()

        if wrong_folder_match:
            return (
                "WRONG_FOLDER_NAME",
                wrong_folder_match[0],
                wrong_folder_match[1],
            )

    conn.close()

    if exact_match is None:
        return ("MISSING", None, None)

    # folder_nameは合っているがcorrect_titleが違う場合
    if exact_match[1] != expected_title and actual_extracted_title == expected_title:
        return ("WRONG_TITLE", exact_match[0], exact_match[1])

    # 完全に一致
    return ("OK", exact_match[0], exact_match[1])


def run_test(sample_csv: str = "test_data/test_sample_100.csv") -> List[Dict]:
    """テストを実行し、結果をCSVに出力"""

    from extractor import MangaTitleExtractor

    # LLMを使用しないモードでテスト（再現性のため）
    extractor = MangaTitleExtractor(use_llm=False, api_key="")

    # サンプルデータ読み込み
    samples = []
    with open(sample_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append({
                "folder_name": row["folder_name"].strip(),
                "expected_title": row["expected_title"].strip(),
                "rule_applied": row.get("rule_applied", "").strip(),
                "confidence": float(row.get("confidence", 0)),
            })

    results = []

    for sample in samples:
        folder_name = sample["folder_name"]
        expected_title = sample["expected_title"]

        # extract() を呼び出す（LLM不使用）
        actual_title, confidence, method = extractor.extract(folder_name)

        # DB保存状態をチェック
        db_status, db_folder, db_correct = check_db_save_status(
            folder_name, expected_title, actual_title, method
        )

        results.append({
            "folder_name": folder_name,
            "expected_title": expected_title,
            "actual_extracted_title": actual_title,
            "db_folder_name": db_folder or "",
            "db_correct_title": db_correct or "",
            "method": method,
            "confidence": confidence,
            "db_save_status": db_status,
        })

    # 結果をCSVに出力
    os.makedirs("test_results", exist_ok=True)
    output_path = "test_results/test_output.csv"
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    # サマリー表示
    status_counts = {}
    for r in results:
        s = r["db_save_status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    print(f"\n--- テスト結果 ({len(results)}件) ---")
    print(f"出力: {output_path}")
    print("\nDB保存ステータス集計:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}件")

    # 失敗がある場合はFAIL、全てOKならPASS
    failed = sum(v for k, v in status_counts.items() if k != "OK")
    overall = "FAIL" if failed > 0 else "PASS"
    print(f"\n総合判定: [{overall}] ({failed}件失敗)")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DB保存ロジックテスト")
    parser.add_argument("--sample", type=str, default="test_data/test_sample_100.csv", help="サンプルCSVパス")
    args = parser.parse_args()

    run_test(args.sample)


if __name__ == "__main__":
    main()