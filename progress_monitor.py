#!/usr/bin/env python3
"""
進捗モニタアプリケーション
- APIで調べたタイトル・返り値を表示
- 一時停止・再開機能
- 経過時間・残り時間を1分おきに更新表示

使い方:
    python progress_monitor.py [総フォルダ数] [--pause-file FILE]
    
    例) python progress_monitor.py 48347
"""

import sys
import time
import sqlite3
import threading
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QLabel, QPushButton, QTextEdit,
                                 QProgressBar, QTableWidget, QTableWidgetItem,
                                 QHeaderView, QGroupBox, QMessageBox)
    from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

# DBパス
DB_PATH = Path(__file__).parent / "manga_titles.db"

PAGE_SIZE = 100


class ApiSearchWorkerSignals(QObject):
    """非同期API検索用信号"""
    finished = pyqtSignal()


class ApiSearchWorker(QObject):
    """
    未完了項目をAPI(extractor)で検索する Qt Worker
    QThread で動かすよう設計
    """
    finished = pyqtSignal()

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path

    def do_work(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
        except Exception as e:
            print(f"[ApiSearchWorker] DB接続エラー: {e}")
            self.finished.emit()
            return

        try:
            # extractorを内部からインポート（同一プロジェクト）
            import importlib
            extractor_mod = importlib.import_module("extractor")
            MangaTitleExtractor = extractor_mod.MangaTitleExtractor

            ext = MangaTitleExtractor(use_llm=True, api_key="")

            cur = conn.cursor()
            # extracted_title が空白・NULL のフォルダ名を抽出
            cur.execute("""
                SELECT folder_name
                FROM processing_log
                WHERE extracted_title IS NULL
                   OR TRIM(extracted_title) = ''
                ORDER BY id DESC
                LIMIT 500
            """)
            rows = cur.fetchall()
            folders = [r[0].strip() for r in rows if r[0].strip()]

            if not folders:
                print("[ApiSearchWorker] 未完了項目が見つかりませんでした。")
                self.finished.emit()
                conn.close()
                return

            updated = 0
            skipped = 0
            for folder_name in folders:
                try:
                    title, conf, method = ext.extract(folder_name)
                    if title and title.strip():
                        cur.execute("""
                            UPDATE processing_log
                            SET extracted_title = ?
                            WHERE folder_name = ?
                              AND (extracted_title IS NULL OR TRIM(extracted_title) = '')
                            LIMIT 1
                        """, (title.strip(), folder_name))
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    print(f"[ApiSearchWorker] 処理エラー {folder_name}: {e}")
                    skipped += 1

            conn.commit()
            print(f"[ApiSearchWorker] 完了: 更新={updated}, スキップ={skipped}, 対象={len(folders)}件")
        except Exception as e:
            print(f"[ApiSearchWorker] 全体エラー: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

            self.finished.emit()


class ProgressMonitorWindow(QMainWindow):
    """進捗モニタウィンドウ"""

    def __init__(self, total_folders: int = 0, pause_file: str = ".paused"):
        super().__init__()
        self.processing = True          # 処理中フラグ
        self.paused = False             # 一時停止フラグ
        self.start_time = None          # 開始時間
        self.pause_start_time = None    # 一時停止開始時間
        self.total_pause_time = timedelta()  # 累計一時停止時間
        self.total_folders = total_folders
        self.pause_file_path = Path(pause_file)

        # ページング用
        self.current_page = 1
        self.total_pages = 1

        self.init_ui()
        self.start_monitoring()

    def init_ui(self):
        """UIを初期化"""
        self.setWindowTitle("漫画タイトル抽出 - 進捗モニタ")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # === ステータスグループ ===
        status_group = QGroupBox("処理ステータス")
        status_layout = QVBoxLayout(status_group)

        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        # ステータス情報
        info_layout = QHBoxLayout()

        self.label_elapsed = QLabel("経過時間: --")
        info_layout.addWidget(self.label_elapsed)

        self.label_remaining = QLabel("残り時間: --")
        info_layout.addWidget(self.label_remaining)

        self.label_progress = QLabel(f"進捗: 0/{self.total_folders} (0%)")
        info_layout.addWidget(self.label_progress)

        status_layout.addLayout(info_layout)
        main_layout.addWidget(status_group)

        # === 制御ボタン ===
        button_layout = QHBoxLayout()

        self.btn_pause = QPushButton("一時停止")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setMinimumWidth(120)
        button_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("終了")
        self.btn_stop.clicked.connect(self.stop_processing)
        self.btn_stop.setMinimumWidth(120)
        button_layout.addWidget(self.btn_stop)

        main_layout.addLayout(button_layout)

        # === 結果テーブル ===
        result_group = QGroupBox("処理結果一覧（全件ページング表示）")
        result_layout = QVBoxLayout(result_group)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["番号", "フォルダ名", "抽出タイトル", "方法"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(3, 80)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        result_layout.addWidget(self.table)

        # ページングとAPI検索用ボタン行（＋JUMP）
        page_layout = QHBoxLayout()

        self.btn_prev_page = QPushButton("◀ 前へ")
        self.btn_prev_page.clicked.connect(self.prev_page)
        self.btn_prev_page.setMinimumWidth(90)
        page_layout.addWidget(self.btn_prev_page)

        self.btn_next_page = QPushButton("次へ ▶")
        self.btn_next_page.clicked.connect(self.next_page)
        self.btn_next_page.setMinimumWidth(90)
        page_layout.addWidget(self.btn_next_page)

        btn_10_prev = QPushButton("10枚前")
        btn_10_prev.clicked.connect(lambda: self.jump_pages(-10))
        page_layout.addWidget(btn_10_prev)

        btn_10_next = QPushButton("10枚次")
        btn_10_next.clicked.connect(lambda: self.jump_pages(+10))
        page_layout.addWidget(btn_10_next)

        btn_100_prev = QPushButton("100枚前")
        btn_100_prev.clicked.connect(lambda: self.jump_pages(-100))
        page_layout.addWidget(btn_100_prev)

        btn_100_next = QPushButton("100枚次")
        btn_100_next.clicked.connect(lambda: self.jump_pages(+100))
        page_layout.addWidget(btn_100_next)

        btn_1000_prev = QPushButton("1000枚前")
        btn_1000_prev.clicked.connect(lambda: self.jump_pages(-1000))
        page_layout.addWidget(btn_1000_prev)

        btn_1000_next = QPushButton("1000枚次")
        btn_1000_next.clicked.connect(lambda: self.jump_pages(+1000))
        page_layout.addWidget(btn_1000_next)

        btn_first = QPushButton("先頭へ")
        btn_first.clicked.connect(self.go_first_page)
        page_layout.addWidget(btn_first)

        btn_last = QPushButton("末尾へ")
        btn_last.clicked.connect(self.go_last_page)
        page_layout.addWidget(btn_last)

        self.label_page = QLabel("ページ: 1/1")
        self.label_page.setAlignment(Qt.AlignCenter)
        page_layout.addWidget(self.label_page)

        page_layout.addStretch()

        self.btn_api_search = QPushButton("APIで未完了を検索")
        self.btn_api_search.setToolTip("タイトルが未設定のフォルダをAPI(extractor)で補完します")
        self.btn_api_search.clicked.connect(self.run_api_search)
        self.btn_api_search.setMinimumWidth(180)
        page_layout.addWidget(self.btn_api_search)

        result_layout.addLayout(page_layout)
        main_layout.addWidget(result_group)

    def start_monitoring(self):
        """モニタリング開始"""
        self.start_time = datetime.now()

        # 1秒ごとにUIを更新
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress)
        self.update_timer.start(1000)

        # 初回更新
        self.update_progress()

    def update_progress(self):
        """進捗情報をDBから取得して更新（ページング対応）"""
        if not DB_PATH.exists():
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # 処理済み件数（processing_logテーブル）
            cursor.execute("SELECT COUNT(*) FROM processing_log")
            processed = cursor.fetchone()[0]

            # ページ計算
            total_pages = max(1, (processed + PAGE_SIZE - 1) // PAGE_SIZE)
            self.total_pages = total_pages

            # 現在ページが範囲外なら1に戻す
            if self.current_page < 1:
                self.current_page = 1
            if self.current_page > total_pages:
                self.current_page = 1

            # 現在ページの結果を取得
            offset = (self.current_page - 1) * PAGE_SIZE
            cursor.execute("""
                SELECT folder_name, extracted_title, rule_applied
                FROM processing_log
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (PAGE_SIZE, offset))
            page_rows = cursor.fetchall()
            conn.close()

            # UI更新（進捗・時間関係は従来と同じ）
            total = self.total_folders if self.total_folders > 0 else max(processed, 1)
            progress_pct = (processed / total * 100) if total > 0 else 0
            self.progress_bar.setValue(min(int(progress_pct), 100))
            self.label_progress.setText(f"進捗: {processed}/{total} ({progress_pct:.1f}%)")

            # 時間計算
            if self.start_time and processed > 0:
                now = datetime.now()
                elapsed = now - self.start_time - self.total_pause_time
                self.label_elapsed.setText(f"経過時間: {self.format_timedelta(elapsed)}")

                # 残り時間の推定
                avg_time_per_item = elapsed / processed
                remaining_items = total - processed
                if remaining_items > 0:
                    remaining = avg_time_per_item * remaining_items
                    self.label_remaining.setText(f"残り時間: {self.format_timedelta(remaining)}")
                else:
                    self.label_remaining.setText("残り時間: 0秒（完了！）")

            # テーブル更新（現在のページ分）
            self.table.setRowCount(len(page_rows))
            for i, (folder_name, title, rule) in enumerate(page_rows):
                row = i
                # 番号: 全件中での位置（最新=1）
                seq = offset + 1 + i

                item_num = QTableWidgetItem(str(seq))
                self.table.setItem(row, 0, item_num)

                item_folder = QTableWidgetItem(folder_name or "")
                self.table.setItem(row, 1, item_folder)

                item_title = QTableWidgetItem(title or "(なし)")
                self.table.setItem(row, 2, item_title)

                item_status = QTableWidgetItem(rule or "-")
                if title:
                    item_status.setForeground(Qt.green)
                else:
                    item_status.setForeground(Qt.gray)
                self.table.setItem(row, 3, item_status)

            # ページ表示更新
            self.label_page.setText(f"ページ: {self.current_page}/{self.total_pages} (計{processed}件)")

            # 前/次 ボタンの有効・無効
            self.btn_prev_page.setEnabled(self.current_page > 1)
            self.btn_next_page.setEnabled(self.current_page < self.total_pages)

        except Exception as e:
            print(f"[ProgressMonitor] Error: {e}")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_progress()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_progress()


    def jump_pages(self, delta):
        target = self.current_page + delta
        target = max(1, min(self.total_pages, target))
        self.current_page = target
        self.load_page(self.current_page)

    def go_first_page(self):
        self.jump_pages(1 - self.current_page)

    def go_last_page(self):
        self.jump_pages(self.total_pages - self.current_page)

    def run_api_search(self):
        """
        「APIで未完了を検索」ボタンの処理
        - 既に検索中の場合は無視
        - ボタンを無効化 → 完了後に有効化・テーブル更新
        """
        if getattr(self, "api_search_running", False):
            return

        if not DB_PATH.exists():
            print("[ProgressMonitor] DBが見つかりません。")
            return

        self.api_search_running = True
        self.btn_api_search.setEnabled(False)
        self.btn_api_search.setText("API検索中...")

        try:
            # QThread を使うため、worker を別スレッドに移動する
            worker = ApiSearchWorker(str(DB_PATH))
            thread = QThread()

            # 完了後の処理（メインスレッドで実行）
            def on_api_search_finished():
                self.api_search_running = False
                self.btn_api_search.setEnabled(True)
                self.btn_api_search.setText("APIで未完了を検索")
                self.current_page = 1
                self.update_progress()
                # スレッドは一度きり利用のため、ここで終了＋クリーンアップ
                thread.quit()
                thread.wait()

            worker.moveToThread(thread)
            thread.started.connect(worker.do_work)
            worker.finished.connect(on_api_search_finished, Qt.QueuedConnection)

            thread.start()
        except Exception as e:
            self.api_search_running = False
            self.btn_api_search.setEnabled(True)
            self.btn_api_search.setText("APIで未完了を検索")
            print(f"[ProgressMonitor] API検索開始エラー: {e}")

    def toggle_pause(self):
        """一時停止・再開のトグル"""
        if self.paused:
            # 再開
            pause_end = datetime.now()
            self.total_pause_time += (pause_end - self.pause_start_time)
            self.paused = False
            self.pause_start_time = None
            self.btn_pause.setText("一時停止")
            self.processing = True

            # 一時停止ファイルを削除
            if self.pause_file_path.exists():
                self.pause_file_path.unlink()
            print("[ProgressMonitor] 処理を再開しました")
        else:
            # 一時停止
            self.paused = True
            self.pause_start_time = datetime.now()
            self.btn_pause.setText("再開")

            # 一時停止ファイルを作成（pipeline.pyが検知用）
            self.pause_file_path.write_text(f"paused_at:{datetime.now().isoformat()}")
            print("[ProgressMonitor] 処理を一時停止しました")

    def stop_processing(self):
        """処理終了"""
        reply = QMessageBox.question(
            self, "確認", "処理を終了しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.processing = False
            now = datetime.now()
            elapsed = now - self.start_time - self.total_pause_time
            QMessageBox.information(
                self, "終了",
                f"処理を終了しました。\n経過時間: {self.format_timedelta(elapsed)}"
            )
            # 一時停止ファイルを削除
            if self.pause_file_path.exists():
                self.pause_file_path.unlink()
            self.close()

    def format_timedelta(self, td):
        """timedeltaを文字列に変換"""
        total_seconds = int(td.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}時間{minutes}分{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"


def main():
    """メイン関数"""
    if not HAS_PYQT:
        print("PyQt5 がインストールされていません。pip install PyQt5 を実行してください。")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="漫画タイトル抽出 - 進捗モニタ")
    parser.add_argument("total", nargs="?", type=int, default=0, help="総フォルダ数（推定残り時間に使用）")
    parser.add_argument("--pause-file", default=".paused", help="一時停止ファイルパス")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = ProgressMonitorWindow(total_folders=args.total, pause_file=args.pause_file)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()