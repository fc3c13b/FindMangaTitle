"""
labeler.py - ラベリングツール

フォルダー名と正しい漫画タイトールのペアを手動で入力・管理するCLIツール
約1000件をラベル付けして学習データとして使用
"""

import os
import sys
from typing import List, Tuple, Optional

from database import (
    initialize_database,
    insert_folder_title,
    get_all_titles,
    get_learning_data,
)


def print_menu():
    """メニュー表示"""
    print("\n" + "=" * 50)
    print("   漫画タイトル ラベリングツール")
    print("=" * 50)
    print("  [1] 新しいラベルを入力")
    print("  [2]既存ラベルを表示")
    print("  [3] CSVエクスポート")
    print("  [4] バッチCSVインポート")
    print("  [Q] 終了")
    print("=" * 50)


def add_label():
    """新しいフォルダー名→タイトルペアを追加"""
    print("\n--- 新しいラベル入力 ---")
    folder_name = input("フォルダー名: ").strip()
    if not folder_name:
        print("キャンセルしました")
        return False

    correct_title = input("正しい漫画タイトル: ").strip()
    if not correct_title:
        print("キャンセルしました")
        return False

    insert_folder_title(folder_name, correct_title, confidence=1.0, source="manual")
    print(f"保存完了: [{folder_name}] → {correct_title}")
    return True


def show_labels():
    """既存ラベルを表示"""
    data = get_learning_data()
    if not data:
        print("\nラベルデータがありません")
        return

    stats = __import__('database').get_statistics()
    print(f"\n--- ラベルデータ (合計 {len(data)} 件) ---")
    print(f"統計: {stats}")

    # ページネーション表示
    page_size = 10
    for i in range(0, len(data), page_size):
        print(f"\n[{i+1}-{min(i+page_size, len(data))}]:")
        for folder_name, correct_title in data[i:i + page_size]:
            print(f"  フォルダー: {folder_name}")
            print(f"  タイトル:   {correct_title}")
            print()

        if i + page_size < len(data):
            key = input("  >> さらに表示するには Enter (qで終了) >> ")
            if key.lower() == 'q':
                break


def export_csv(output_path: str = "learning_data.csv"):
    """ラベルデータをCSVにエクスポート"""
    import csv

    data = get_learning_data()
    if not data:
        print("\nエクスポートするデータがありません")
        return

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['folder_name', 'correct_title'])
        writer.writerows(data)

    print(f"\nCSVエクスポート完了: {output_path} ({len(data)}件)")


def import_csv(input_path: str):
    """CSVからバッチインポート"""
    import csv

    if not os.path.exists(input_path):
        print(f"ファイルが見つかりません: {input_path}")
        return

    count = 0
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            folder_name = row.get('folder_name', '').strip()
            correct_title = row.get('correct_title', '').strip()
            if folder_name and correct_title:
                insert_folder_title(folder_name, correct_title, confidence=1.0, source="manual")
                count += 1

    print(f"\nCSVインポート完了: {count}件追加")


def main():
    """メインループ"""
    initialize_database()

    while True:
        print_menu()
        choice = input("選択 >> ").strip().lower()

        if choice == 'q':
            print("終了します")
            break
        elif choice == '1':
            add_label()
        elif choice == '2':
            show_labels()
        elif choice == '3':
            output_path = input("出力ファイル名 (default: learning_data.csv): ").strip()
            if not output_path:
                output_path = "learning_data.csv"
            export_csv(output_path)
        elif choice == '4':
            input_path = input("インポートするCSVファイルパス: ").strip()
            if input_path:
                import_csv(input_path)
        else:
            print("無効な選択です")


if __name__ == "__main__":
    main()