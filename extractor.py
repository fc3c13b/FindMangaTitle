"""
extractor.py - 漫画タイトル抽出エンジン

2段階アプローチ:
1. 正規表現ルールでノイズ除去
2. LLMで最終的なタイトルを推定（ルールだけでは不十分な場合）
"""

import re
import time
import os
from typing import List, Tuple, Optional, Dict
from dotenv import load_dotenv

load_dotenv()

from config import get_quality_threshold, get_llm_model
from database import (
    get_active_rules,
    get_title_by_folder,
    insert_folder_title,
    log_processing,
)
from pattern_analyzer import load_and_apply_rules


class MangaTitleExtractor:
    """漫画タイトル抽出エンジン"""

    def __init__(self, use_llm: bool = True, api_key: str = ""):
        self.use_llm = use_llm
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        self.rules = None  # 初回アクセス時に読み込み

    def _load_rules(self):
        """ルールをDBから読み込む"""
        if self.rules is None:
            self.rules = get_active_rules()

    def extract(self, folder_name: str) -> Tuple[str, float, str]:
        """
        フォルダー名からタイトルを抽出

        Returns:
            (extracted_title, confidence, method)
            method: 'db_hit', 'rule', 'llm'
        """
        self._load_rules()

        # 1. DB ヒットチェック
        cached = get_title_by_folder(folder_name)
        if cached:
            log_processing(folder_name, cached, rule_applied="cache_hit", confidence=1.0)
            return cached, 1.0, "db_hit"

        start_time = time.time()

        # 2. 正規表現ルール適用（複数回適用してネストされた括弧も除去）
        extracted = folder_name.strip()
        for _ in range(3):
            new_extracted = load_and_apply_rules(extracted, self.rules)
            if new_extracted == extracted:
                break
            extracted = new_extracted

        # ルール適用後の品質判定
        quality = self._estimate_quality(folder_name, extracted)

        threshold = get_quality_threshold()
        if quality >= threshold:
            # 信頼性十分な場合、LLM不使用で完了
            processing_time = (time.time() - start_time) * 1000
            log_processing(folder_name, extracted, rule_applied="regex_rules", confidence=quality)
            return extracted, quality, "rule"

        # 3. LLMによる抽出（ルールだけでは不十分な場合）
        if self.use_llm and self.api_key:
            llm_title = self._extract_with_llm(folder_name)
            if llm_title:
                processing_time = (time.time() - start_time) * 1000
                log_processing(folder_name, llm_title, rule_applied="llm", confidence=0.9)

                # LLM結果をDBにキャッシュ
                insert_folder_title(llm_title, llm_title, confidence=0.9, source="llm")
                return llm_title, 0.9, "llm"

        # Fallback: ルール適用結果を使用
        processing_time = (time.time() - start_time) * 1000
        log_processing(folder_name, extracted, rule_applied="regex_fallback", confidence=quality)
        return extracted, quality, "rule"

    def _estimate_quality(self, original: str, extracted: str) -> float:
        """
        抽出結果の品質を推定

        - 空白文字のみになった → 0.0
        - タイトル長が極端に短い/長い → 低め
        - ブラケット・括弧が残っている → ペナルティ
        - 元のテキストと同一（何も除去されていない）→ 非常に低い品質
        - 著者名が含まれている可能性がある → ペナルティ
        """
        if not extracted.strip():
            return 0.0

        # タイトル長が極端な場合は品質を落とす
        title_len = len(extracted)
        if title_len < 2:
            return 0.1
        if title_len > 50:
            return 0.3

        # 元のテキストと同一（何も処理されていない）→ LLMに任せる
        if extracted.strip() == original.strip():
            return 0.2

        quality = 0.35  # ベースをさらに下げる

        # ブラケット [xxx] が残っているかチェック
        remaining_brackets = re.findall(r'\[[^\]]+\]', extracted)
        bracket_penalty = len(remaining_brackets) * 0.15

        # 括弧 (xxx) が含まれているかチェック（位置に関係なくペナルティ）
        has_parens = bool(re.search(r'\([^)]*\)', extracted))
        paren_penalty = 0.25 if has_parens else 0.0

        # 著者名が含まれる可能性（日本語が先頭に存在してその後にスペース+タイトルが続くパターン）
        leading_author = bool(re.match(r'^[\w\u3000-\u9FFF]{1,8}\s+', extracted))
        author_penalty = 0.3 if leading_author else 0.0

        # "巻" や "号" などの番号関連語が含まれる場合
        volume_words = re.search(r'[巻号]', extracted)
        volume_penalty = 0.15 if volume_words else 0.0

        # 数字のみの単語が含まれる（巻数・章番号など）
        has_numbers = bool(re.search(r'\b\d+\b', extracted))
        number_penalty = 0.1 if has_numbers else 0.0

        # 日本語と英語が混在している場合（著者名 + タイトルのパターン）
        mixed_lang = bool(re.search(r'[\u3000-\u9FFF].*[\wA-Za-z]', extracted))
        mix_penalty = 0.15 if mixed_lang else 0.0

        # "EXPLORER" や "[Purple]" などの不要な副題が残っている場合
        subtitle_patterns = re.search(r'\b(EXPLORER|ONLY|Special|Bonus)\b', extracted, re.IGNORECASE)
        subtitle_penalty = 0.15 if subtitle_patterns else 0.0

        # フォルダー名と抽出結果が非常によく似ている（変更が少ない）→ LLMに任せるべき
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, original, extracted).ratio()
        if similarity > 0.85 and extracted != original:
            quality -= 0.2

        quality = max(0.0, min(1.0, quality - bracket_penalty - paren_penalty - author_penalty - volume_penalty - number_penalty - mix_penalty - subtitle_penalty))
        return quality

    def _extract_with_llm(self, folder_name: str) -> Optional[str]:
        """LLMを使用してタイトルを抽出（Google Gemini）"""
        try:
            from google import genai
        except ImportError:
            print("google-genaiがインストールされていません")
            return None

        client = genai.Client(api_key=self.api_key)

        prompt = f"""以下の漫画フォルダー名から、漫画の正しいタイトルだけを抽出してください。

重要なルール:
1. フォルダー名の先頭にある日本語人名（著者名）は必ず除去してください
2. 巻数・チャプター番号・ファイルサイズ・解像度などの不要な情報は除去してください
3. 「EXPLORER」「ONLY」「Special」「Bonus」などの副題は除去してください
4. 「[Purple]」などのカラー版を示すタグは除去してください
5. タイトルのみを返してください
        try:
            response = client.models.generate_content(
                model=get_llm_model(),
                contents=prompt,
            )
            result = response.text.strip()
            return result if result else None
        except Exception as e:
            print(f"LLM呼び出しエラー: {e}")
            return None

    def batch_extract(
        self,
        folder_names: List[str],
        save_to_db: bool = True,
    ) -> List[Dict]:
        """
        バッチ処理で複数フォルダー名からタイトルを抽出

        Returns:
            結果リスト [{folder_name, title, confidence, method}, ...]
        """
        results = []
        total = len(folder_names)

        for i, folder_name in enumerate(folder_names):
            title, confidence, method = self.extract(folder_name)
            results.append({
                "folder_name": folder_name,
                "title": title,
                "confidence": confidence,
                "method": method,
            })

            if (i + 1) % 50 == 0 or (i + 1) == total:
                print(f"処理中... {i+1}/{total}件完了")

        # DBへの保存
        if save_to_db:
            for item in results:
                if item["method"] != "db_hit":
                    insert_folder_title(
                        folder_name=item["folder_name"],
                        correct_title=item["title"],
                        confidence=item["confidence"],
                        source="rule" if item["method"] == "rule" else "llm",
                    )

        return results


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description="漫画タイトル抽出エンジン")
    parser.add_argument("--folder", type=str, help="単一フォルダー名のテスト")
    parser.add_argument("--batch", type=str, help="バッチ処理用CSVファイルパス")
    parser.add_argument("--no-llm", action="store_true", help="LLMを使用しない")
    parser.add_argument("--api-key", type=str, help="Gemini APIキー")

    args = parser.parse_args()

    extractor = MangaTitleExtractor(
        use_llm=not args.no_llm,
        api_key=args.api_key or "",
    )

    if args.folder:
        title, confidence, method = extractor.extract(args.folder)
        print(f"\n入力: {args.folder}")
        print(f"結果: {title} (信頼度: {confidence:.2f}, 方法: {method})")

    elif args.batch:
        import csv

        if not os.path.exists(args.batch):
            print(f"ファイルが見つかりません: {args.batch}")
            return

        folder_names = []
        with open(args.batch, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                fn = row.get('folder_name', '').strip()
                if fn:
                    folder_names.append(fn)

        print(f"\nバッチ処理開始 ({len(folder_names)}件)")
        results = extractor.batch_extract(folder_names)

        # 統計表示
        methods = {}
        for r in results:
            methods[r["method"]] = methods.get(r["method"], 0) + 1

        print(f"\n--- バッチ処理完了 ---")
        print(f"合計: {len(results)}件")
        for method, count in methods.items():
            print(f"  {method}: {count}件")


if __name__ == "__main__":
    main()