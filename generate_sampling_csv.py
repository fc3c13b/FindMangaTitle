"""processing_logから100件サンプリングしてCSVを生成"""
import sqlite3
import csv

conn = sqlite3.connect('manga_titles.db')
cursor = conn.cursor()
cursor.execute(
    'SELECT folder_name, extracted_title, rule_applied, confidence '
    'FROM processing_log ORDER BY RANDOM() LIMIT 100'
)
rows = cursor.fetchall()
conn.close()

with open('test_data/test_sample_100.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['folder_name', 'expected_title', 'rule_applied', 'confidence'])
    for row in rows:
        writer.writerow(row)

print(f'Sampled {len(rows)} rows to test_data/test_sample_100.csv')