"""
pipeline.py - フルパイプライン実行スクリプト

フォルダ走査 → バッチ抽出 → 結果エクスポート の一連処理を自動化
20万件規模のDB構築用
"""

import os
import sys
import time
import csv
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from database import initialize_database, get_statistics
from extractor import MangaTitleExtractor, LLMRateLimitError


def scan_folders(root_path: str, max_depth: int = 3) -> List[str]:
    """
    再帰的にフォルダー名を収集

    Args:
        root_path: スキャン開始ディレクトリ
        max_depth: 探索する最大深さ

    Returns:
        フォルダー名リスト（重複除去済み）
    """
    folder_names = set()

    for dirpath, dirnames, filenames in os.walk(root_path):
        # 深さ制限
        depth = len(dirpath.split(os.sep)) - len(root_path.split(os.sep))
        if max_depth and depth >= max_depth:
            dirnames.clear()
            continue

        # 隠しフォルダ・システムフォルダを除外
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith('.') and d not in {'__pycache__', 'node_modules', '.git'}
        ]

        for d in dirnames:
            folder_names.add(d)

    return sorted(folder_names)


def run_pipeline(
    root_path: str,
    output_csv: str = "results.csv",
    max_depth: int = 3,
    use_llm: bool = True,
    api_key: str = "",
    limit: int = 0,
    rescan: bool = False,
):
    """
    パイプライン実行

    Args:
        root_path: スキャン対象ディレクトリ
        output_csv: 結果出力CSVパス
        max_depth: フォルダ探索深さ
        use_llm: LLM使用フラグ
        api_key: Gemini APIキー
        limit: 処理件数制限（0=無制限）
    """
    # 1. DB初期化
    print("=" * 60)
    print("  漫画タイトル抽出パイプライン")
    print("=" * 60)

    initialize_database()
    print("\n[1/4] データベース初期化完了")

    # 2. フォルダ走査
    print("\n[2/4] フォルダー名をスキャン中...")
    folder_names = scan_folders(root_path, max_depth)
    print(f"  発見: {len(folder_names)}件のフォルダー")

    if limit:
        folder_names = folder_names[:limit]
        print(f"  制限適用: {limit}件に削減")

    # 3. タイトル抽出
    print("\n[3/4] タイトル抽出処理中...")
    extractor = MangaTitleExtractor(use_llm=use_llm, api_key=api_key)

    # 一時停止ファイルパス
    pause_file = Path(".paused")

    results = []
    failed_folders = []  # 失敗したフォルダー名を保持
    llm_needed_folders = []  # LLMが必要なフォルダー名を追跡（--no-llmモード用）
    total = len(folder_names)
    for i, folder_name in enumerate(folder_names):
        # 一時停止チェック
        while pause_file.exists():
            print(f"\n[一時停止中] {i+1}/{total} - 再開を待機...")
            time.sleep(2)

        try:
            title, confidence, method = extractor.extract(folder_name)
        except LLMRateLimitError as e:
            # API容量不足 → 即座に処理中止
            print(f"\n[停止] {e}")
            print("LLMを使用できないため処理を中断します。")
            print('llm_pending.csv に未処理フォルダが出力されました。')
            break

        result = {
            'folder_name': folder_name,
            'title': title,
            'confidence': confidence,
            'method': method
        }
        results.append(result)

        # 空タイトルまたは低品質の場合は追跡
        if not title or confidence < 0.3:
            failed_folders.append(folder_name)

        # LLM不使用モードで品質が低い場合、LLMが必要と判定
        if not use_llm and (not title or confidence < 0.5):
            llm_needed_folders.append(folder_name)

        # DBにログを記録（進捗モニタ用）
        from database import log_processing
        log_processing(folder_name, title, method, confidence, 0.0)

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{total}件処理済み ({(i+1)/total*100:.1f}%), 失敗: {len(failed_folders)}件")

    # 4. 結果エクスポート
    print(f"\n[4/4] 結果をCSVにエクスポート中... ({output_csv})")
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['folder_name', 'title', 'confidence', 'method'])
        writer.writeheader()
        writer.writerows(results)

    # 失敗フォルダーの報告
    if failed_folders:
        print(f"\n[警告] タイトル抽出に失敗または低品質のフォルダー: {len(failed_folders)}件")
        failed_csv = output_csv.replace('.csv', '_failed.csv')
        with open(failed_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['folder_name'])
            for fn in failed_folders:
                writer.writerow([fn])
        print(f"  -> {failed_csv} に出力しました")

    # --rescan が指定されている場合、失敗フォルダーをLLMで再処理
    if rescan and failed_folders:
        print(f"\n[Rescan] {len(failed_folders)}件の失敗フォルダーをLLMで再処理中...")
        extractor.use_llm = True  # LLMを確実に使用する
        for folder_name in failed_folders:
            title, confidence, method = extractor.extract(folder_name)
            if title and confidence >= 0.3:
                print(f"  [OK] {folder_name} -> {title}")

    # 統計表示
    stats = get_statistics()
    methods_summary = {}
    for r in results:
        m = r['method']
        methods_summary[m] = methods_summary.get(m, 0) + 1

    print("\n" + "=" * 60)
    print("  処理完了!")
    print("=" * 60)
    print(f"\nDB統計:")
    print(f"  総レコード数: {stats['total_entries']}")
    for source, data in stats['source_breakdown'].items():
        print(f"    {source}: {data['count']}件 (平均信頼度: {data['avg_confidence']:.2f})")

    print(f"\n処理方法別内訳:")
    for method, count in methods_summary.items():
        print(f"  {method}: {count}件")

    # LLM不使用モードの場合、LLM必要な件数を報告・エクスポート
    if not use_llm and llm_needed_folders:
        print(f"\n[LLM推計] 正規表現ルールのみでは不十分なフォルダー: {len(llm_needed_folders)}件")
        llm_csv = output_csv.replace('.csv', '_llm_needed.csv')
        with open(llm_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['folder_name'])
            for fn in llm_needed_folders:
                writer.writerow([fn])
        print(f"  -> {llm_csv} に出力しました")
        print(f"\nこれらの{len(llm_needed_folders)}件についてはLLMで再処理が必要です。")
        print(f"日次API枠500件の範囲内で、以下のコマンドで再処理:")
        print(f'  python extractor.py --batch "{llm_csv}"')

    print(f"\n出力ファイル: {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="漫画タイトル抽出パイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # カレントディレクトリをスキャン（LLM使用）
  python pipeline.py --root .

  # LLM不使用で高速処理
  python pipeline.py --root ./manga --no-llm

  # 最初の100件のみテスト実行
  python pipeline.py --root ./manga --limit 100

  # カスタム出力ファイル
  python pipeline.py --root ./manga -o my_results.csv
        """,
    )

    parser.add_argument("--root", "-r", type=str, default=".", help="スキャン対象ディレクトリ (default: .)")
    parser.add_argument("--output", "-o", type=str, default="results.csv", help="出力CSVファイルパス")
    parser.add_argument("--max-depth", type=int, default=3, help="フォルダ探索深さ (default: 3)")
    parser.add_argument("--no-llm", action="store_true", help="LLMを使用しない（高速だが精度はやや低い）")
    parser.add_argument("--api-key", type=str, help="Gemini APIキー（環境変数GEMINI_API_KEY也可）")
    parser.add_argument("--limit", type=int, default=0, help="処理件数制限 (0=無制限)")
    parser.add_argument("--rescan", action="store_true", help="低品質結果をLLMで再処理")

    args = parser.parse_args()

    run_pipeline(
        root_path=args.root,
        output_csv=args.output,
        max_depth=args.max_depth,
        use_llm=not args.no_llm,
        api_key=args.api_key or "",
        limit=args.limit,
        rescan=args.rescan,
    )


if __name__ == "__main__":
    main()