"""
scan_all.py - 全データソースパスを一括スキャン
READMEに記載された25パスを順に処理し、DBに蓄積する。
"""
import subprocess
import sys
import csv
import argparse
from pathlib import Path

# README.md に記載された全データソースパス
DATA_SOURCES = [
    # 同人誌系
    r"F:\MangaDL\wnacg\wnacg.com\同人誌",
    r"F:\MangaDL\hitomi.la\Doujinshi",
    r"E:\MangaDL\asmhentai.com",
    r"E:\MangaDL\e-hentai.org\doujinshi",
    r"E:\MangaDL\hentaizap.com\doujinshi",
    r"E:\MangaDL\hitomi.jp.net\doujinshi",
    r"E:\MangaDL\nhentai.net",
    r"E:\MangaDL\nyahentai.one\doujinshi",
    r"E:\MangaDL\rokuhentai.com\doujinshi",
    # 漫画系
    r"M:\MangaS\Manga\Manga 1st",
    r"M:\MangaS\Manga\Manga 2nd",
    r"M:\MangaS\Manga\Manga 3rd",
    r"M:\MangaS\Manga\Manga 4th",
    r"M:\MangaS\Manga\Manga 5th",
    r"M:\MangaS\Manga\Manga 完\Manga 完 1st",
    r"M:\MangaS\Manga\Manga 完\Manga 完 2nd",
    r"M:\MangaS\Manga\Manga 完\Manga 完 3rd",
    r"M:\MangaS\Manga\Manga 完\Manga 完 4th",
    r"M:\MangaS\Manga\Manga 完\Manga 完 5th",
    # その他
    r"O:\NEW",
    r"O:\NEW2",
    r"O:\NEW3",
    r"O:\NEWA",
    r"O:\NEWB",
]


def main():
    parser = argparse.ArgumentParser(description="全データソースを一括スキャン")
    parser.add_argument("--rescan", action="store_true", help="DBにあるフォルダも再処理")
    parser.add_argument("--no-llm", action="store_true", help="LLM不使用（高速）")
    parser.add_argument("--limit", type=int, default=0, help="各パスの処理上限数（0=無制限）")
    parser.add_argument("--start", type=int, default=0, help="開始インデックス（継続用）")
    args = parser.parse_args()

    total = len(DATA_SOURCES)
    success_count = 0
    skip_count = 0
    fail_count = 0

    print(f"全 {total} データソースをスキャンします。")
    print("=" * 60)

    all_llm_needed = set()  # 全パスのLLM必要フォルダを収集

    for i, source in enumerate(DATA_SOURCES):
        if i < args.start:
            print(f"[SKIP] ({i+1}/{total}) {source}")
            skip_count += 1
            continue

        path = Path(source)
        if not path.exists():
            print(f"[SKIP] ({i+1}/{total}) {source} -> パスが存在しません")
            skip_count += 1
            continue

        cmd = [sys.executable, "pipeline.py", "--root", source]
        if args.rescan:
            cmd.append("--rescan")
        if args.no_llm:
            cmd.append("--no-llm")
        if args.limit > 0:
            cmd.extend(["--limit", str(args.limit)])

        print(f"[{i+1}/{total}] {source}")
        try:
            result = subprocess.run(cmd, check=True)
            success_count += 1
            print(f"[OK] ({i+1}/{total}) {source}")

            # LLM必要フォルダを収集
            if args.no_llm:
                llm_csv = Path("results_llm_needed.csv")
                if llm_csv.exists():
                    with open(llm_csv, 'r', encoding='utf-8-sig') as f:
                        reader = csv.reader(f)
                        next(reader, None)  # ヘッダーをスキップ
                        for row in reader:
                            if row:
                                all_llm_needed.add(row[0])
        except subprocess.CalledProcessError as e:
            fail_count += 1
            print(f"[FAIL] ({i+1}/{total}) {source} -> {e}")

    # 累計LLM必要フォルダを出力
    if args.no_llm and all_llm_needed:
        output_file = "all_llm_needed.csv"
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['folder_name'])
            for fn in sorted(all_llm_needed):
                writer.writerow([fn])
        print(f"\n[累計] LLM必要フォルダ合計: {len(all_llm_needed)}件")
        print(f"  -> {output_file} に出力しました")
        print(f"  再処理コマンド: python extractor.py --batch \"{output_file}\"")

    print("=" * 60)
    print(f"完了: OK={success_count}, SKIP={skip_count}, FAIL={fail_count}")


if __name__ == "__main__":
    main()