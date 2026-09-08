# DB保存ロジック修正の実装計画

## 背景（資料目的）

本プロジェクトは、マンガフォルダ名からタイトルを抽出するシステムです。
正規表現ルールとLLMの2つの方法でタイトルを抽出し、結果をSQLiteデータベース(`manga_titles.db`)に保存します。

### 関連作業との関係性
- 本実装計画は、README.mdへの5シナリオ追記・`database.py`への`export_to_csv()`追加（前工程）とは別の課題として発見された
- 前工程でDBデータをエクスポートした際、`folder_titles`テーブルにゴミデータが混入していることに気付き、本修正が発足
- 本計画の完了後、READMEに記載された利用シナリオ（CSVエクスポート等）が正しく動作する状態になる

## 発見された問題

DBの`folder_titles`テーブルにゴミデータが混入していることが発覚しました。

### ルート原因（2026/08/16確認）
- **folder_titles件数**: 67,398件
- **processing_log件数**: 67,445件
- **差異**: 47件のLLM失敗分 + 144件のゴミデータ（LLM応答がフォルダ名カラムに保存されたもの）

### バグの詳細
1. **実装ミス** (`extractor.py:97`): LLM結果をDBに保存する際、`insert_folder_title()`の第1引数が`folder_name`ではなく`llm_title`になっている
   ```python
   # バグ
   insert_folder_title(llm_title, llm_title, ...)
   # 正解
   insert_folder_title(folder_name, llm_title, ...)
   ```
2. **設計ミス**: `extract()`関数は正規表現ルールで成功した場合、`log_processing()`は呼ぶが`insert_folder_title()`を呼ばない（LLM成功時のみ保存する矛盾）

## ゴール

1. `extractor.py`のDB保存ロジックを修正し、全抽出結果が`folder_titles`に正しく保存されるようにする
2. 本番DB(`folder_titles`)を正しい状態に再構築する
3. LLMコストを最小化しながらデータを修復する（パターンマッチ成功分は再処理不要）

## 実装計画（①〜⑦の順で実行）

| Step | 内容 | 出力・修正ファイル | ステータス |
|------|------|-------------------|-----------|
| ① | processing_logから100件サンプリングCSV生成（テスト用） | `test_data/test_sample_100.csv` | ☑ |
| ② | テストスクリプト作成 | `test_db_save.py` | ☑ |
| ③ | ベースラインテスト実行（修正前・失敗確認） | 出力: terminal log | ☑ |
| ④ | extractor.py修正（2箇所：引数間違い＋未保存） | `extractor.py` | ☑ |
| ⑤ | テスト再実行（修正後・PASS確認） | `test_results/test_output.csv` | ☑ |
| ⑥ | folder_titles全削除＆processing_logからパターンマッチ分を移行 | DB更新 | ☑ |
| ⑦ | 残りLLM対象フォルダのみ再スキャン | DB更新（background_rescan.py使用） | ☑ |

## 追加修正（計画外に発見・対応）

| Step | 内容 | 修正ファイル | ステータス |
|------|------|-------------|-----------|
| ⑧ | `background_rescan.py` に連続429エラーで即停止するロジックを追加 | `background_rescan.py` | ☑ |
| ⑨ | 429エラー時に日付変更判定し、翌日にリトライするロジックを追加 | `background_rescan.py` | ☑ |

### ⑧の詳細
- バッチの最後のフォルダで429エラーが発生すると、そのバッチは`break`で終了しますが、次のバッチにそのまま進むという問題があった
- 連続429エラー回数をカウントし、3回連続で429が発生したら処理を終了（`return`）するように修正
- LLM成功すればカウンターをリセット（一時的な429には対応）

### ⑨の詳細
- 夜中に起動して翌朝に完了するケースに対応するため、日付変更判定を追加
- 429エラー発生時、現在の日付と`start_date`を比較し、日付が変わっていたらAPI枠リセットとみなしてカウンターをリセット
- 同じ日で3回連続429なら処理終了（チェックポイント保存済みなので次回実行で続きから再開可能）

## テスト出力形式（評価用CSV）

`test_results/test_output.csv`の列構成：
```
folder_name, expected_title, actual_extracted_title, db_folder_name, db_correct_title, method, confidence, db_save_status
```

- `db_save_status`: OK / MISSING / WRONG_FOLDER_NAME / WRONG_TITLE

## 進行ルール

1. ①→⑦の順序で進める（前のステップが完了するまで次に進まない）
2. 各ステップ完了時にこのファイルを更新（☐ → ☑）
3. task_progressパラメータでも並行して管理する
4. 計画と異なる作業をする場合は理由を明示する