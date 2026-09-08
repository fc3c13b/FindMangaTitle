"""
extractor.py - 漫画タイトル抽出エンジン

2段階アプローチ:
1. 正規表現ルールでノイズ除去
2. LLMで最終的なタイトルを推定（ルールだけでは不十分な場合）
"""

import csv
import re
import time
import os
from datetime import date
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


# Gemini API 無料枠のレート制限設定
GEMINI_MAX_REQUESTS_PER_MINUTE = 12  # マージンを持って12回に制限

class LLMRateLimitError(Exception):
    """LLM API容量不足（429）を通知する例外"""
    pass


ERROR_LOG_PATH = "error.log"


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
            insert_folder_title(folder_name, extracted, confidence=quality, source="rule")
            return extracted, quality, "rule"

        # 3. LLMによる抽出（ルールだけでは不十分な場合）
        if self.use_llm and self.api_key:
            llm_title = self._extract_with_llm(folder_name)
            if llm_title:
                processing_time = (time.time() - start_time) * 1000
                log_processing(folder_name, llm_title, rule_applied="llm", confidence=0.9)

                # LLM結果をDBにキャッシュ
                insert_folder_title(folder_name, llm_title, confidence=0.9, source="llm")
                return llm_title, 0.9, "llm"

        # Fallback: ルール適用結果を使用（品質が低い場合は None を返す）
        processing_time = (time.time() - start_time) * 1000
        log_processing(folder_name, extracted if quality >= 0.3 else "", rule_applied="regex_fallback", confidence=quality)
        return extracted if quality >= 0.3 else "", quality, "rule"

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
        """LLMを使用してタイトルを抽出（Google Gemini）
        
        429エラー発生時は即座に LLMRateLimitError を raise し、
        リトライしない（API容量不足はリトライしても変わらないため）。
        """
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
"""

        try:
            response = client.models.generate_content(
                model=get_llm_model(),
                contents=prompt,
            )
            result = response.text.strip()
            return result if result else None

        except Exception as e:
            error_msg = str(e).lower()

            # 429 エラーは容量不足 → リトライせず例外で通知
            if "429" in error_msg or "resource_exhausted" in error_msg or "rate_limit" in error_msg:
                raise LLMRateLimitError(f"API容量不足 (429): {e}")

            # その他のエラー
            print(f"[LLM] 呼び出しエラー: {e}")
            return None

    def _append_to_error_log(self, message: str):
        """error.log に追記"""
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{date.today()} {message}\n")

    def batch_extract(
        self,
        folder_names: List[str],
        save_to_db: bool = True,
    ) -> List[Dict]:
        """
        バッチ処理で複数フォルダー名からタイトルを抽出

        429エラー発生時は即座にLLM呼び出しを停止し、残りはルールのみで高速処理。

        Returns:
            結果リスト [{folder_name, title, confidence, method}, ...]
        """
        results = []
        total = len(folder_names)

        llm_success_count = 0       # 今日AIで取得成功した件数
        llm_429_count = 0           # API容量不足で未処理の件数
        llm_pending_folders: List[str] = []   # 429で未処理のフォルダ名
        llm_exhausted = False       # 初めて429が発生したらTrue

        for i, folder_name in enumerate(folder_names):
            try:
                title, confidence, method = self.extract(folder_name)
            except LLMRateLimitError as e:
                # 初めての429 → フラグ立てて以降LLMを呼ばない
                if not llm_exhausted:
                    llm_exhausted = True
                    print(f"\n[警告] {e} - 以降のフォルダはLLMを使用しません")

                llm_429_count += 1
                llm_pending_folders.append(folder_name)
                title, confidence, method = "", 0.0, "llm_429"

            if method == "llm":
                llm_success_count += 1

            results.append({
                "folder_name": folder_name,
                "title": title,
                "confidence": confidence,
                "method": method,
            })

            if (i + 1) % 50 == 0 or (i + 1) == total:
                remaining = total - (i + 1)
                suffix = f" (LLM未処理: {llm_429_count}件)" if llm_exhausted else ""
                print(f"処理中... {i+1}/{total}件完了（残り{remaining}件{suffix}）")

        # 未処理フォルダをCSVに出力
        pending_csv = "llm_pending.csv"
        if llm_pending_folders:
            with open(pending_csv, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['folder_name'])
                for fn in llm_pending_folders:
                    writer.writerow([fn])

        # error.log に今日分の成功件数を追記
        if llm_success_count > 0 or llm_429_count > 0:
            self._append_to_error_log(
                f"llm_success:{llm_success_count} llm_429:{llm_429_count}"
            )

        # サマリー表示
        print(f"\n--- バッチ処理完了 ---")
        print(f"合計: {total}件")
        methods_summary = {}
        for r in results:
            m = r["method"]
            methods_summary[m] = methods_summary.get(m, 0) + 1
        labels = {"llm": "AIで取得成功", "rule": "正規表現ルール", "db_hit": "DBキャッシュ"}
        for method, count in methods_summary.items():
            label = labels.get(method, method)
            print(f"  {method} ({label}): {count}件")

        if llm_pending_folders:
            print(f"\n[未処理フォルダ] {pending_csv} に出力しました ({llm_429_count}件)")
            print(f'再処理コマンド: python extractor.py --batch "{pending_csv}"')
        if llm_success_count > 0 or llm_429_count > 0:
            print(f"\n今日AIで取得成功した件数: {llm_success_count}件 → error.log に記録しました")

        # DBへの保存
        if save_to_db:
            for item in results:
                if item["method"] not in ("db_hit", "llm_429"):
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


if __name__ == "__main__":
    main()