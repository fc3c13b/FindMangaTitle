"""
pattern_analyzer.py - パターン分析・ルール生成スクリプト

学習データ（1000件のラベル）を分析し、
フォルダー名 → タイトル変換の正規表現ルールを自動生成
"""

import re
import json
import os
from typing import List, Tuple, Dict
from collections import Counter

from database import (
    get_learning_data,
    insert_extraction_rule,
    get_active_rules,
)


# 既知の除去パターン（初期ルール）— 日本語対応版
DEFAULT_RULES = [
    # 同人誌系パターン
    {
        "name": "circum_event_code",
        "pattern": r"\(C\d{2,3}\)\s*",
        "description": "コミックマーケットイベントコード (C86, C105)",
        "priority": 100,
    },
    {
        "name": "circle_author_bracket",
        "pattern": r"\[[^\]]*\]\s*",
        "description": "[サークル名 (作者)] ブロック",
        "priority": 95,
    },
    {
        "name": "series_parenthesis",
        "pattern": r"\([^)]*(?:Project|プロジェクト|ブルーアーカイブ|艦これ|東方|ゼンレス)\)",
        "description": "(シリーズ名) 括弧内系列表記",
        "priority": 90,
    },
    {
        "name": "trailing_parenthesis_block",
        "pattern": r'\s+\([^)]*(?:#|Fate|東方|シリーズ|リマスター|完全版|全巻|Vol|vol)\)',
        "description": "タイトル後の括弧内サブタイトル/シリーズ名 (#01, Fate~, リマスターなど)",
        "priority": 87,
    },
    {
        "name": "trailing_parenthesis_general",
        "pattern": r'\s+\([^)]*\)',
        "description": "タイトル後の括弧ブロック（一般）- タイトル後の余分な注釈を除去（複数回適用）",
        "priority": 15,
    },
    {
        "name": "title_parenthesis_subtitle",
        "pattern": r'\s+\([^)]*(?:シリーズ|リマスター|完全版|全巻|Fate|#)\)',
        "description": "タイトル途中の括弧サブタイトル（系列名など）",
        "priority": 85,
    },
    {
        "name": "dl_version_tag",
        "pattern": r"\[DL版\]",
        "description": "[DL版] タグ",
        "priority": 85,
    },
    # 漫画系パターン
    {
        "name": "volume_range_space",
        "pattern": r"\s+\d+-\d+",
        "description": "巻数範囲表記 (1-40, 1-30) スペース区切り",
        "priority": 80,
    },
    {
        "name": "volume_range_hyphen",
        "pattern": r"\s*-\d+-\d+",
        "description": "巻数範囲表記 (-1-40, -1-30) ハイフン直結",
        "priority": 80,
    },
    {
        "name": "color_version",
        "pattern": r" カラー版",
        "description": "カラー版表記",
        "priority": 75,
    },
    {
        "name": "monochrome_version",
        "pattern": r" モノクロ版",
        "description": "モノクロ版表記",
        "priority": 75,
    },
    # 既存パターン（日本語以外）
    {
        "name": "volume_number_bracket",
        "pattern": r"\[?v(?:ol)?\.?\s*\d+\]?",
        "description": "ボリューム番号 (Vol.1, v2)",
        "priority": 70,
    },
    {
        "name": "chapter_number",
        "pattern": r"\[?c(?:hap)?\.?\s*\d+\]?",
        "description": "チャプター番号 (ch01, Chap.5)",
        "priority": 65,
    },
    {
        "name": "volume_kanji",
        "pattern": r"\d+巻",
        "description": "巻数表記 (3巻, 12巻)",
        "priority": 60,
    },
    {
        "name": "size_info_mb",
        "pattern": r"\[\d+(?:\.\d+)?(?:MB|GB)\]",
        "description": "ファイルサイズ情報 ([400MB])",
        "priority": 55,
    },
    {
        "name": "resolution_info",
        "pattern": r"\[\d+p\]",
        "description": "解像度情報 ([720p], [1080p])",
        "priority": 50,
    },
    {
        "name": "year_in_bracket",
        "pattern": r"\[(?:19|20)\d{2}\]",
        "description": "年号 ([2023], [1995])",
        "priority": 45,
    },
]


def analyze_patterns(learning_data: List[Tuple[str, str]]) -> Dict:
    """
    学習データを分析してパターンを抽出

    フォルダー名とタイトルの差分から、除去すべきノイズパターンを特定
    """
    print(f"データ分析中... ({len(learning_data)}件)")

    # 各ペアの差分を収集
    noise_patterns = []

    for folder_name, title in learning_data:
        # フォルダー名にあるがタイトルにない部分 = ノイズ
        folder_tokens = set(re.findall(r'\S+', folder_name))
        title_tokens = set(re.findall(r'\S+', title))
        noise = folder_tokens - title_tokens
        noise_patterns.extend(noise)

    # 頻出ノイズパターンを分析
    noise_counter = Counter(noise_patterns)
    print(f"\n検出されたノイズパターン (Top20):")
    for pattern, count in noise_counter.most_common(20):
        print(f"  [{count}回] {pattern}")

    return {
        "noise_patterns": dict(noise_counter.most_common(50)),
        "analyzed_count": len(learning_data),
    }


def generate_rules_from_llm(learning_data: List[Tuple[str, str]], api_key: str = "") -> List[Dict]:
    """
    LLM にルール生成を依頼（Google Gemini）

    学習データの一部をFew-shotとして提供し、
    追加の正規表現ルールを生成させる
    """
    try:
        from google import genai
    except ImportError:
        print("google-genaiパッケージが必要です: pip install google-genai")
        return []

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY環境変数が必要です")
        return []

    client = genai.Client(api_key=api_key)

    # Few-shotサンプル（最大20件）
    samples = learning_data[:20]
    examples_text = "\n".join(
        f"  Folder: {fn}\n  Title:  {ct}"
        for fn, ct in samples
    )

    prompt = (
        f"以下の漫画フォルダー名からタイトルを抽出する正規表現ルールを生成してください。"
        f"\n\nこれらの例を確認して、フォルダー名にあるがタイトルにない「ノイズパターン」を検出・除去するルールを考えてください："
        f"\n\nExamples:\n{examples_text}"
        '\n\n以下のJSON形式で追加ルールを返してください（デフォルト以外のみ）：'
        '{"rules": [{"name": "...", "pattern": "...", "description": "..."}]}'
    )

    from config import Config
    model_name = Config.get_llm_model()

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        result_text = response.text.strip()

        # JSONパース
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("rules", [])
    except json.JSONDecodeError:
        print(f"JSONパース失敗: {result_text[:200]}")

    return []


def save_rules(rules: List[Dict]):
    """ルールをDBに保存"""
    for rule in rules:
        insert_extraction_rule(
            rule_name=rule["name"],
            pattern=rule["pattern"],
            replacement="",
            description=rule.get("description", ""),
            priority=rule.get("priority", 50),
        )

    print(f"ルール保存完了: {len(rules)}件")


def load_and_apply_rules(text: str, rules: List[Tuple[str, str, str, int]] = None) -> str:
    """
    ルールを適用してテキストからノイズを除去

    Args:
        text: 処理するフォルダー名
        rules: (name, pattern, replacement, priority) のリスト
    """
    if rules is None:
        from database import get_active_rules
        rules = get_active_rules()

    result = text.strip()

    for name, pattern, replacement, priority in rules:
        new_result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        if new_result != result:
            result = new_result

    # 不要な区切り文字のクリーンアップ
    result = re.sub(r'[\s_\-]+$', '', result).strip()
    result = re.sub(r'^[\s_\-]+', '', result).strip()
    result = re.sub(r'[-_\s]+', ' ', result).strip()

    return result


def initialize_default_rules():
    """デフォルトルールをDBに投入"""
    existing = get_active_rules()
    existing_names = {name for name, _, _, _ in existing}

    added = 0
    for rule in DEFAULT_RULES:
        if rule["name"] not in existing_names:
            insert_extraction_rule(
                rule_name=rule["name"],
                pattern=rule["pattern"],
                replacement="",
                description=rule.get("description", ""),
                priority=rule["priority"],
            )
            added += 1

    print(f"デフォルトルール追加完了: {added}件新規")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description="パターン分析・ルール生成")
    parser.add_argument("--init", action="store_true", help="デフォルトルールを初期化")
    parser.add_argument("--analyze", action="store_true", help="学習データを分析")
    parser.add_argument("--llm-rules", action="store_true", help="LLMで追加ルール生成")
    parser.add_argument("--test", type=str, help="テスト文字列でルール適用を確認")
    parser.add_argument("--list", action="store_true", help="現在のルールを表示")

    args = parser.parse_args()

    if not any([args.init, args.analyze, args.llm_rules, args.test, args.list]):
        # デフォルト: 全処理実行
        args.init = True
        args.analyze = True

    if args.init:
        initialize_default_rules()

    if args.list:
        rules = get_active_rules()
        print("\n--- 有効な抽出ルール ---")
        for name, pattern, replacement, priority in rules:
            print(f"  [{priority:>3}] {name}: {pattern}")

    if args.analyze:
        learning_data = get_learning_data()
        if not learning_data:
            print("学習データがありません。ラベリングツールでデータを入力してください")
        else:
            analyze_patterns(learning_data)

    if args.llm_rules:
        learning_data = get_learning_data()
        if len(learning_data) < 5:
            print("LLM分析には最低5件の学習データが必要です")
        else:
            new_rules = generate_rules_from_llm(learning_data)
            if new_rules:
                save_rules(new_rules)

    if args.test:
        rules = get_active_rules()
        result = load_and_apply_rules(args.test, rules)
        print(f"\n入力: {args.test}")
        print(f"結果: {result}")


if __name__ == "__main__":
    main()