"""
実データフォルダー名のスキャンツール
指定されたパス配下の1階層フォルダ名を収集し、CSVに出力。
"""

import os
import csv
import sys
from pathlib import Path
from datetime import datetime

# スキャン対象パス
SCAN_PATHS = [
    r"M:\MangaS\Manga\Manga 2nd",
    r"M:\MangaS\Manga\Manga 3rd",
    r"M:\MangaS\Manga\Manga 4th",
    r"M:\MangaS\Manga\Manga 5th",
    r"M:\MangaS\Manga\Manga 完\Manga 完 1st",
    r"M:\MangaS\Manga\Manga 完\Manga 完 2nd",
    r"M:\MangaS\Manga\Manga 完\Manga 完 3rd",
    r"M:\MangaS\Manga\Manga 完\Manga 完 4th",
    r"M:\MangaS\Manga\Manga 完\Manga 完 5th",
    r"E:\MangaDL\hentaizap.com\doujinshi",
    r"E:\MangaDL\hitomi.jp\hitomi.jp.net\doujinshi",
    r"E:\MangaDL\hitomi.jp.net\doujinshi",
    r"E:\MangaDL\nyahentai.one\doujinshi",
    r"F:\MangaDL\wnacg\wnacg.com\同人誌",
]

OUTPUT_CSV = "test_data/scanned_folders.csv"


def scan_directory(path: str) -> list[tuple[str, str]]:
    """指定パス配下の1階層フォルダ名を収集"""
    results = []
    p = Path(path)
    
    if not p.exists():
        print(f"  [WARN] パスが存在しません: {path}")
        return results
    
    if not p.is_dir():
        print(f"  [WARN] ディレクトリではありません: {path}")
        return results
    
    for entry in sorted(p.iterdir()):
        if entry.is_dir() and not entry.name.startswith('.'):
            results.append((entry.name, str(path)))
    
    return results


def main():
    print(f"={len(SCAN_PATHS)}")
    all_entries = []
    
    for scan_path in SCAN_PATHS:
        print(f"[SCANNING] {scan_path}")
        entries = scan_directory(scan_path)
        print(f"  -> {len(entries)} folders found")
        all_entries.extend(entries)
    
    # CSV出力
    output_path = Path(OUTPUT_CSV)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['folder_name', 'source_path'])
        for folder_name, source_path in all_entries:
            writer.writerow([folder_name, source_path])
    
    print(f"\n[COMPLETE] {len(all_entries)} folders exported to {output_path}")
    return len(all_entries)


if __name__ == '__main__':
    main()