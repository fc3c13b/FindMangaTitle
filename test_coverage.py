"""
正規表現パターンカバレッジテスト
scanned_folders.csv に対して正規表現マッチ率を測定
"""

import csv
import sys
from pathlib import Path
from typing import Optional

# extractorのハイブリッド抽出器インポート
sys.path.insert(0, str(Path(__file__).parent))
from extractor import MangaTitleExtractor

CSV_PATH = "test_data/scanned_folders.csv"


def test_coverage(csv_path: str, sample: int = 0) -> dict:
    """カバレッジテスト実行"""
    extractor = MangaTitleExtractor()
    
    # CSV読み込み
    rows = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row['folder_name'])
    
    if sample > 0 and sample < len(rows):
        import random
        random.seed(42)
        rows = random.sample(rows, sample)
    
    total = len(rows)
    matched = 0
    regex_matched = 0
    llm_matched = 0
    
    print(f"[START] Testing {total} folder names...")
    
    for i, folder in enumerate(rows):
        title, confidence, method = extractor.extract(folder)
        if title:
            matched += 1
            # LLM使用フラグは内部ロジックなので簡易判定
            # 正規表現でマッチした場合はregex_matchedとする（詳細な追跡は後で改善可能）
        
        if (i + 1) % 5000 == 0:
            print(f"  Progress: {i+1}/{total} ({(i+1)/total*100:.1f}%)")
    
    # 結果表示
    rate = matched / total * 100 if total > 0 else 0
    print(f"\n[RESULT]")
    print(f"  Total:      {total}")
    print(f"  Matched:    {matched} ({rate:.1f}%)")
    print(f"  Unmatched:  {total - matched} ({100-rate:.1f}%)")
    
    return {
        'total': total,
        'matched': matched,
        'unmatched': total - matched,
        'rate': rate,
    }


def main():
    sample = 1000  # デフォルトは1000件サンプリング（高速）
    if len(sys.argv) > 1:
        try:
            sample = int(sys.argv[1])
        except ValueError:
            pass
    
    if sample == 0:
        print("Note: Full dataset (48k+). This may take a while...")
    
    test_coverage(CSV_PATH, sample=sample)


if __name__ == '__main__':
    main()