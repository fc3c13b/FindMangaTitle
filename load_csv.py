"""
load_csv.py - CSVテストデータをDBにインポート
"""
import csv
import os
from database import initialize_database, insert_folder_title

def load_csv(csv_path: str = "test_data/sample_folders.csv"):
    """CSVファイルをDBにロード"""
    initialize_database()
    
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return
    
    count = 0
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            folder_name = row.get('folder_name', '').strip()
            expected_title = row.get('expected_title', '').strip()
            if folder_name and expected_title:
                insert_folder_title(
                    folder_name=folder_name,
                    correct_title=expected_title,
                    confidence=1.0,
                    source='manual'
                )
                count += 1
    
    print(f"Loaded {count} records from {csv_path}")

if __name__ == "__main__":
    load_csv()