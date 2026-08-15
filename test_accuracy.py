"""
test_accuracy.py - 正規表現ルール・LLMの精度検証
"""
import csv
import os
from database import get_learning_data
from pattern_analyzer import load_and_apply_rules, get_active_rules
from extractor import MangaTitleExtractor

def test():
    rules = get_active_rules()
    
    # CSVから直接データを読み込む（DBキャッシュバイパス）
    csv_path = "test_data/sample_folders.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return
    
    data = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get('folder_name', '').strip()
            et = row.get('expected_title', '').strip()
            if fn and et:
                data.append((fn, et))
    
    if not data:
        print("No learning data in DB. Run python load_csv.py first.")
        return
    
    correct = 0
    total = len(data)
    mismatches = []
    
    for folder, expected in data:
        result = load_and_apply_rules(folder, rules)
        if result == expected:
            correct += 1
        else:
            mismatches.append((folder, expected, result))
    
    print("=" * 60)
    print("Accuracy: {}/{} ({:.1f}%)".format(correct, total, correct/total*100))
    print("=" * 60)
    print()
    print("=== Mismatches ({} cases) ===".format(len(mismatches)))
    
    for i, (folder, exp, got) in enumerate(mismatches):
        print("\n[{}]".format(i+1))
        print("  Folder:   {}".format(folder))
        print("  Expected: {}".format(exp))
        print("  Got:      {}".format(got))
    
    # Summary by pattern type
    print("\n\n=== Summary ===")
    print("Total tests: {}".format(total))
    print("Correct: {} ({:.1f}%)".format(correct, correct/total*100))
    print("Wrong:   {} ({:.1f}%)".format(len(mismatches), len(mismatches)/total*100))

def test_llm():
    """LLMを使用して精度を検証（品質閾値を下げてLLMを強制呼び出し）"""
    
    # DBを完全にクリア
    import sqlite3
    db_path = "manga_titles.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM folder_titles")
    conn.commit()
    conn.close()
    csv_path = "test_data/sample_folders.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return
    
    data = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get('folder_name', '').strip()
            et = row.get('expected_title', '').strip()
            if fn and et:
                data.append((fn, et))
    
    extractor = MangaTitleExtractor(use_llm=True)
    
    # DBをクリアしてテスト
    import sqlite3
    db_path = "manga_titles.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM folder_titles")
    conn.commit()
    conn.close()
    
    correct = 0
    total = len(data)
    mismatches = []
    
    for i, (folder, expected) in enumerate(data):
        result, confidence, method = extractor.extract(folder)
        if result == expected:
            correct += 1
        else:
            mismatches.append((folder, expected, result, method))
        if (i + 1) % 10 == 0:
            print(f"Processing... {i+1}/{total}")
    
    print("=" * 60)
    print("LLM Accuracy: {}/{} ({:.1f}%)".format(correct, total, correct/total*100))
    print("=" * 60)
    print()
    print("=== Mismatches ({} cases) ===".format(len(mismatches)))
    
    for i, (folder, exp, got, method) in enumerate(mismatches):
        print("\n[{}]".format(i+1))
        print("  Folder:   {}".format(folder))
        print("  Expected: {}".format(exp))
        print("  Got:      {} (method: {})".format(got, method))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="LLMを使用してテスト")
    args = parser.parse_args()
    
    if args.llm:
        test_llm()
    else:
        test()
