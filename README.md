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

## 使用方法

### 1. セットアップ

```bash
pip install -r requirements.txt
set OPENAI_API_KEY=sk-xxxxxxxxxxxxx   # Windowsの場合
export OPENAI_API_KEY=sk-xxxxxxxxxxxxx # Linux/Macの場合
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

## ライセンス

MIT License