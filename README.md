# FindMangaTitle - 漫画フォルダー名からタイトルを抽出するツール

## アーキテクチャ

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ フォルダ走査 │ --→│ タイトル抽出  │ --→│   SQLite DB  │ --→│  CSVエクスポート│
│ (pipeline)  │     │(extractor)   │     │(database)    │     │               │
└─────────────┘     └──────┬───────┘     └──────────────┘     └──────────────┘
                           │
                     ┌──────┴───────┐
                     │  2段階アプローチ│
                     ├──────────────┤
                     │ 1. 正規表現   │ ← ルールでノイズ除去（高速）
                     │ 2. LLM       │ ← 複雑な場合はGPT-4o-miniに依頼
                     └──────────────┘
```

## ファイル構成

| ファイル | 説明 |
|---------|------|
| `database.py` | SQLite DB管理（スキーマ作成・CRUD） |
| `labeler.py` | ラベリングツール（1000件手入力用GUI） |
| `pattern_analyzer.py` | パターン分析・ルール自動生成 |
| `extractor.py` | タイトル抽出エンジン（2段階アプローチ） |
| `pipeline.py` | フルパイプライン実行スクリプト |
| `progress_monitor.py` | 進捗モニタGUI（API結果表示・一時停止・時間表示） |

## データソース

本ツールは以下のフォルダパスをデータソースとして使用します：

### 同人誌系
```
F:\MangaDL\wnacg\wnacg.com\同人誌
F:\MangaDL\hitomi.la\Doujinshi
E:\MangaDL\asmhentai.com
E:\MangaDL\e-hentai.org\doujinshi
E:\MangaDL\hentaizap.com\doujinshi
E:\MangaDL\hitomi.jp.net\doujinshi
E:\MangaDL\nhentai.net
E:\MangaDL\nyahentai.one\doujinshi
E:\MangaDL\rokuhentai.com\doujinshi
```

### 漫画系
```
M:\MangaS\Manga\Manga 1st
M:\MangaS\Manga\Manga 2nd
M:\MangaS\Manga\Manga 3rd
M:\MangaS\Manga\Manga 4th
M:\MangaS\Manga\Manga 5th
M:\MangaS\Manga\Manga 完\Manga 完 1st
M:\MangaS\Manga\Manga 完\Manga 完 2nd
M:\MangaS\Manga\Manga 完\Manga 完 3rd
M:\MangaS\Manga\Manga 完\Manga 完 4th
M:\MangaS\Manga\Manga 完\Manga 完 5th
```

### その他
```
O:\NEW
O:\NEW2
O:\NEW3
O:\NEWA
O:\NEWB
```

## 使用方法

### 1. セットアップ

```bash
pip install -r requirements.txt
set GEMINI_API_KEY=AIzaxxxxxxxxxxxxx   # Windowsの場合
export GEMINI_API_KEY=AIzaxxxxxxxxxxxxx # Linux/Mac場合
```

.envファイルにAPIキーを記載することもできます：
```
GEMINI_API_KEY=your_api_key_here
MEDIA_ARTS_DB_URL=https://mediaarts-db.artmuseums.go.jp
```

### 2. ラベリング（学習データ作成）

```bash
python labeler.py
# GUIで1000件程度を手入力
```

### 3. ルール生成・分析

```bash
# デフォルトルールの初期化
python pattern_analyzer.py --init

# 学習データからパターンを分析
python pattern_analyzer.py --analyze

# LLMで追加ルールを自動生成（LLM APIが必要）
python pattern_analyzer.py --llm-rules

# ルール確認
python pattern_analyzer.py --list

# テスト
python pattern_analyzer.py --test "One Piece Vol.1 [HQ] [Crunchyroll]"
```

### 4. タイトル抽出（単一）

```bash
python extractor.py --folder "Naruto ch045 [Colored] [720p]"
```

### 5. バッチ処理・パイプライン

```bash
# フォルダ走査 + 全件抽出 + CSV出力
python pipeline.py --root ./manga_folder -o results.csv

# LLM不使用（高速）
python pipeline.py --root ./manga_folder --no-llm

# テスト実行（100件のみ）
python pipeline.py --root ./manga_folder --limit 100

# 再スキャン（DBにあるフォルダも再処理）
python pipeline.py --root ./manga_folder --rescan
```

### 6. 進捗モニタGUI

```bash
python progress_monitor.py
```

進捗モニタGUIでは以下の機能を利用できます：
- **API結果表示**: APIで調べたタイトル・返り値をリスト表示
- **一時停止/再開**: 処理を途中で一時停止し、再開可能
- **経過時間/残り時間**: 1分おきに更新される時間を表示

### 7. 複数データソースの処理

**方法A: 一括処理スクリプト（全25パスを自動実行）**

```bash
# 全データソースを一括処理（DBに蓄積）
python scan_all.py --rescan

# 進捗モニタを別ウィンドウで起動して確認しながら処理
start python progress_monitor.py
python scan_all.py --rescan
```

**方法B: 個別パス指定**

```bash
python pipeline.py --root "F:\MangaDL\wnacg\wnacg.com\同人誌" -o results_wnacg.csv
python pipeline.py --root "F:\MangaDL\hitomi.la\Doujinshi" -o results_hitomi.csv
python pipeline.py --root "E:\MangaDL\asmhentai.com" -o results_asmhentai.csv

# 進捗モニタを別ウィンドウで起動して確認しながら処理
start python progress_monitor.py
python pipeline.py --root "M:\MangaS\Manga\Manga 1st" -o results_manga1st.csv
```

## 高度な使い方

### 1. APIとしての使い方

FastAPIベースのREST APIとして起動できます：

```bash
python api_server.py
# または
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

APIは以下のエンドポイントを公開します：

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/health` | ヘルスチェック |
| POST | `/extract` | 単一フォルダ名からタイトルを抽出 |
| POST | `/extract/batch` | 複数フォルダ名からバッチ抽出 |

**リクエスト例（単一）:**
```bash
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"folder_name": "Naruto ch045 [Colored]"}'
```

**リクエスト例（バッチ）:**
```bash
curl -X POST http://localhost:8000/extract/batch \
  -H "Content-Type: application/json" \
  -d '{"folder_names": ["One Piece Vol.1", "Bleach ch100"]}'
```

**レスポンス例:**
```json
{
  "original": "Naruto ch045 [Colored]",
  "title": "Naruto",
  "confidence": 0.95,
  "method": "regex"
}
```

APIドキュメントは `http://localhost:8000/docs` で確認できます（Swagger UI）。

### 2. DB全データの見方

SQLite DBに蓄積されたすべてのタイトルデータをCSVにエクスポート：

```bash
# Pythonから直接エクスポート
python -c "from database import export_to_csv; export_to_csv('all_results.csv')"
```

SQLiteコマンドラインツールで直接確認：

```bash
sqlite3 manga_titles.db "SELECT COUNT(*) FROM folder_titles;"
sqlite3 manga_titles.db ".mode csv" ".output titles.csv" "SELECT * FROM folder_titles;"
```

### 3. 未処理分の見方（LLM再処理が必要なフォルダ）

パイプライン実行時、正規表現では抽出できなかったフォルダは `results_llm_needed.csv` に出力されます：

```bash
# LLM不使用モードでスキャン → 未処理分を特定
python pipeline.py --root ./manga_folder --no-llm

# 生成された results_llm_needed.csv を確認
cat results_llm_needed.csv

# 未処理分にLLM再処理を適用
python extractor.py --batch "results_llm_needed.csv"
```

これにより、正規表現で処理可能なものは高速に処理し、複雑なものだけLLMにエスカレーションする2段階アプローチが実現できます。

### 4. フォルダー単位での追加

単一のフォルダー名からタイトルを抽出：

```bash
python extractor.py --folder "Naruto ch045 [Colored] [720p]"
```

DBに新しいマッピングを追加（手動ラベル）：

```bash
python labeler.py
# GUIで フォルダー名 → タイトル ペアを入力
```

### 5. 重複排除データの見方

DBは `folder_name` をUNIQUE制約としており、同じフォルダー名の登録は既存レコードを更新します。重複処理の詳細を確認：

```bash
# DBの重複レコード状況を確認
python -c "from database import get_statistics; import json; print(json.dumps(get_statistics(), indent=2))"
```

処理履歴（`processing_log` テーブル）から、いつどのルールで処理されたか追跡できます：

```bash
sqlite3 manga_titles.db "SELECT COUNT(*), folder_name FROM processing_log GROUP BY folder_name HAVING COUNT(*) > 1;"
```

## パイプラインフロー

1. **ラベリング**: 手動で約1000件の フォルダー名 → タイトル ペアを作成
2. **パターン分析**: 学習データからノイズパターンを特定し、LLMに追加ルール生成を依頼
3. **バッチ抽出**: 正規表現で処理できるものは高速処理、複雑なものはLLMにエスカレーション
4. **DB蓄積**: 結果をSQLite DBに保存し、次回以降の処理が高速化

## コスト最適化

- 20万件の場合、正規表現で80%以上処理可能 → LLMは数万件のみ使用
- 推定コスト: 5万回 × $0.1/1K tokens ≈ $5 (GPT-4o-mini)
- LLM不使用モード: `--no-llm` でAPIコストゼロ

## トラブルシューティング

### Pythonファイルが破損する（SyntaxError）

**現象:** `import argparsehttps://...` のように、行末尾にURLや不要なテキストが付加されSyntaxErrorになる。

**原因:**
- ファイル編集ツールがSEARCH/REPLACE処理中に改行コードを正しく扱えず、次の行と連結してしまう
- クリップボードにコピーしたURL等が混入する
- 複数のプロセスが同時に同じファイルを書き込む

**確認方法:**
```bash
python -m py_compile pipeline.py
# SyntaxErrorがあれば破損している
```

**復旧方法:**
```bash
# gitで最新コミットの状態に戻す
git checkout HEAD -- pipeline.py
```

**防止策:**

1. __Pre-commit Hooksを設定する__（推奨）

   ```bash
   pip install pre-commit
   ```

   `.pre-commit-config.yaml` を作成：
   ```yaml
   repos:
     - repo: local
       hooks:
         - id: py-compile
           name: Python Compile Check
           entry: python -m py_compile
           language: system
           types: [python]
           # 各.pyファイルをコンパイルチェック
           verbose: true
         - id: flake8
           name: Flake8 Lint
           entry: flake8
           language: system
           types: [python]
           additional_dependencies: [flake8]
   ```

   適用：
   ```bash
   pre-commit install
   ```

2. __CI/CDにコンパイルチェックを追加する__

   `.github/workflows/docker-publish.yml` に以下を挿入：
   ```yaml
   - name: Compile Check
     run: |
       python -m py_compile pipeline.py
       python -m py_compile extractor.py
       python -m py_compile database.py
   ```

3. __編集後の手動チェック__

   ファイル編集直後に以下を実行：
   ```bash
   for f in *.py; do python -m py_compile "$f" || echo "FAILED: $f"; done
   ```

## ライセンス

MIT License