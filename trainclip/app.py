"""PySide6 desktop UI for the Version 0.1 workflow."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from .worker import BatchWorker, Options


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrainClip — 列車自動検出・動画切り出し")
        self.resize(1380, 820)
        self.settings = QSettings("TrainClip", "TrainClip")
        self.worker: BatchWorker | None = None
        self.rows: dict[str, int] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("TrainClip")
        title.setObjectName("title")
        subtitle = QLabel("動画を解析して、列車が映る区間を自動で保存します。")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("ファイル一覧"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ファイル", "長さ", "検出数", "状態"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 270)
        self.table.setColumnWidth(1, 75)
        self.table.setColumnWidth(2, 65)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.addWidget(QLabel("処理状況"))
        self.current_name = QLabel("待機中")
        self.current_name.setObjectName("currentName")
        middle_layout.addWidget(self.current_name)
        self.current_bar = QProgressBar()
        middle_layout.addWidget(self.current_bar)
        self.current_time = QLabel("00:00:00 / 00:00:00")
        middle_layout.addWidget(self.current_time)
        middle_layout.addSpacing(15)
        middle_layout.addWidget(QLabel("処理ログ"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        middle_layout.addWidget(self.log, 1)
        splitter.addWidget(middle)

        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(10)
        paths = QGroupBox("フォルダ")
        paths_layout = QGridLayout(paths)
        self.input_path = QLineEdit()
        self.output_path = QLineEdit()
        input_button = QPushButton("参照")
        output_button = QPushButton("参照")
        input_button.clicked.connect(lambda: self._browse(self.input_path))
        output_button.clicked.connect(lambda: self._browse(self.output_path))
        paths_layout.addWidget(QLabel("入力"), 0, 0)
        paths_layout.addWidget(self.input_path, 0, 1)
        paths_layout.addWidget(input_button, 0, 2)
        paths_layout.addWidget(QLabel("出力"), 1, 0)
        paths_layout.addWidget(self.output_path, 1, 1)
        paths_layout.addWidget(output_button, 1, 2)
        self.recursive = QCheckBox("サブフォルダも検索")
        self.recursive.setChecked(True)
        paths_layout.addWidget(self.recursive, 2, 1, 1, 2)
        settings_layout.addWidget(paths)

        clip_group = QGroupBox("区間の設定")
        clip_layout = QFormLayout(clip_group)
        self.before = self._double(0, 120, 10, " 秒")
        self.after = self._double(0, 120, 10, " 秒")
        self.minimum_duration = self._double(0, 600, 20, " 秒")
        self.consecutive = QSpinBox()
        self.consecutive.setRange(1, 100)
        self.consecutive.setValue(2)
        self.merge_gap = self._double(0, 120, 10, " 秒")
        clip_layout.addRow("検出前", self.before)
        clip_layout.addRow("検出後", self.after)
        clip_layout.addRow("最低動画時間", self.minimum_duration)
        clip_layout.addRow("最低連続検出", self.consecutive)
        clip_layout.addRow("イベント統合", self.merge_gap)
        settings_layout.addWidget(clip_group)

        ai_group = QGroupBox("ローカル AI")
        ai_layout = QFormLayout(ai_group)
        self.model = QLineEdit("COCO_V1")
        self.analysis_fps = self._double(0.5, 10, 2, " fps")
        self.confidence = self._double(0.1, 0.95, 0.5, "")
        self.confidence.setSingleStep(0.05)
        self.min_area = self._double(0, 100, 0, " %")
        self.device = QComboBox()
        self.device.addItems(["自動", "GPU", "CPU"])
        self.force = QCheckBox("保存済み解析結果を使わず再解析")
        ai_layout.addRow("モデル", self.model)
        ai_layout.addRow("解析速度", self.analysis_fps)
        ai_layout.addRow("信頼度", self.confidence)
        ai_layout.addRow("最低検出面積", self.min_area)
        ai_layout.addRow("処理デバイス", self.device)
        ai_layout.addRow(self.force)
        settings_layout.addWidget(ai_group)

        export_group = QGroupBox("出力")
        export_layout = QFormLayout(export_group)
        self.mode = QComboBox()
        self.mode.addItems(["正確（再エンコード）", "高速（キーフレーム依存）"])
        export_layout.addRow("切り出し方式", self.mode)
        settings_layout.addWidget(export_group)
        settings_layout.addStretch()
        splitter.addWidget(settings_panel)
        splitter.setSizes([450, 420, 430])

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.start_button = QPushButton("解析開始")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("中断")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.overall_label = QLabel("全体: 0 / 0 ファイル")
        self.overall_bar = QProgressBar()
        self.overall_bar.setFixedWidth(260)
        footer_layout.addWidget(self.start_button)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addStretch()
        footer_layout.addWidget(self.overall_label)
        footer_layout.addWidget(self.overall_bar)
        layout.addWidget(footer)

        self._load_settings()
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f6f8fb; color: #172033; font-size: 13px; }
            QLabel#title { font-size: 27px; font-weight: 750; color: #122240; }
            QLabel#subtitle { color: #5e6c83; margin-bottom: 8px; }
            QLabel#currentName { font-size: 17px; font-weight: 650; margin-top: 12px; }
            QGroupBox { border: 1px solid #dce3ed; border-radius: 8px;
                        margin-top: 8px; padding: 13px 9px 8px; font-weight: 650; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget, QTextEdit {
                background: white; border: 1px solid #d7dfea; border-radius: 5px; padding: 4px;
            }
            QPushButton { background: white; border: 1px solid #cad4e2; border-radius: 6px;
                          padding: 8px 14px; }
            QPushButton:hover { background: #e9f0fa; }
            QPushButton#primary { background: #2459d2; border-color: #2459d2; color: white;
                                  font-weight: 650; min-width: 96px; }
            QPushButton#primary:hover { background: #1747b7; }
            QProgressBar { background: #e1e7f0; border: 0; border-radius: 5px;
                           text-align: center; min-height: 13px; }
            QProgressBar::chunk { background: #3470e5; border-radius: 5px; }
        """)

    @staticmethod
    def _double(minimum: float, maximum: float, value: float, suffix: str) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(2)
        control.setSingleStep(0.5)
        control.setValue(value)
        control.setSuffix(suffix)
        return control

    def _browse(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択", target.text())
        if folder:
            target.setText(folder)

    def _load_settings(self) -> None:
        for name, control in (("source", self.input_path), ("output", self.output_path),
                              ("model", self.model)):
            value = self.settings.value(name)
            if value:
                control.setText(str(value))
        for name, control in (("before", self.before), ("after", self.after),
                              ("minimum_duration", self.minimum_duration),
                              ("analysis_fps", self.analysis_fps),
                              ("confidence", self.confidence), ("merge_gap", self.merge_gap),
                              ("min_area", self.min_area)):
            value = self.settings.value(name)
            if value is not None:
                control.setValue(float(value))
        value = self.settings.value("consecutive")
        if value is not None:
            self.consecutive.setValue(int(value))
        for name, control in (("recursive", self.recursive), ("force", self.force)):
            value = self.settings.value(name)
            if value is not None:
                control.setChecked(str(value).lower() in ("true", "1"))
        self.device.setCurrentIndex(int(self.settings.value("device", 0)))
        self.mode.setCurrentIndex(int(self.settings.value("mode", 0)))

    def _save_settings(self) -> None:
        for name, control in (("source", self.input_path), ("output", self.output_path),
                              ("model", self.model)):
            self.settings.setValue(name, control.text())
        for name, control in (("before", self.before), ("after", self.after),
                              ("minimum_duration", self.minimum_duration),
                              ("analysis_fps", self.analysis_fps), ("confidence", self.confidence),
                              ("merge_gap", self.merge_gap), ("min_area", self.min_area),
                              ("consecutive", self.consecutive)):
            self.settings.setValue(name, control.value())
        self.settings.setValue("recursive", self.recursive.isChecked())
        self.settings.setValue("force", self.force.isChecked())
        self.settings.setValue("device", self.device.currentIndex())
        self.settings.setValue("mode", self.mode.currentIndex())

    def _start(self) -> None:
        source = Path(self.input_path.text().strip()).expanduser().resolve()
        output_text = self.output_path.text().strip()
        if not self.input_path.text().strip() or not source.is_dir():
            QMessageBox.warning(self, "入力フォルダ", "存在する入力フォルダを選択してください。")
            return
        if not output_text:
            QMessageBox.warning(self, "出力フォルダ", "出力フォルダを選択してください。")
            return
        output = Path(output_text).expanduser().resolve()
        if output == source or source.is_relative_to(output):
            QMessageBox.warning(self, "出力フォルダ", "入力フォルダと別の出力先を選択してください。")
            return
        model = self.model.text().strip()
        if not model:
            QMessageBox.warning(self, "AI モデル", "モデル名またはモデルファイルを指定してください。")
            return
        self._save_settings()
        options = Options(
            source=source, output=output, recursive=self.recursive.isChecked(),
            force_analysis=self.force.isChecked(), before=self.before.value(),
            after=self.after.value(), minimum_duration=self.minimum_duration.value(),
            analysis_fps=self.analysis_fps.value(), confidence=self.confidence.value(),
            consecutive=self.consecutive.value(), merge_gap=self.merge_gap.value(),
            min_area_percent=self.min_area.value(), model=model,
            device=["auto", "cuda", "cpu"][self.device.currentIndex()],
            exact=self.mode.currentIndex() == 0,
        )
        self.rows.clear()
        self.table.setRowCount(0)
        self.log.clear()
        self.current_bar.setValue(0)
        self.overall_bar.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker = BatchWorker(options)
        self.worker.found.connect(self._found)
        self.worker.state.connect(self._state)
        self.worker.overall.connect(self._overall)
        self.worker.current.connect(self._current)
        self.worker.message.connect(self.log.append)
        self.worker.finished_summary.connect(self._finished)
        self.worker.finished.connect(self._worker_stopped)
        self.worker.start()

    def _found(self, path: str, label: str) -> None:
        row = self.table.rowCount()
        self.rows[path] = row
        self.table.insertRow(row)
        for column, value in enumerate((label, "-", "-", "待機中")):
            self.table.setItem(row, column, QTableWidgetItem(value))

    def _state(self, path: str, duration: str, count: str, status: str) -> None:
        row = self.rows.get(path)
        if row is None:
            return
        for column, value in ((1, duration), (2, count), (3, status)):
            self.table.item(row, column).setText(value)
        self.table.scrollToItem(self.table.item(row, 0))

    def _overall(self, done: int, total: int) -> None:
        self.overall_label.setText(f"全体: {done} / {total} ファイル")
        self.overall_bar.setValue(int(done * 100 / total) if total else 0)

    def _current(self, label: str, progress: int, time_text: str) -> None:
        self.current_name.setText(label)
        self.current_bar.setValue(progress)
        self.current_time.setText(time_text)

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.log.append("中断を要求しました。現在の処理を停止します。")

    def _finished(self, processed: int, errors: int, cancelled: bool) -> None:
        result = "中断" if cancelled else "完了"
        self.log.append(f"{result}: 処理済み {processed} 件、エラー {errors} 件")
        self.current_name.setText(result)

    def _worker_stopped(self) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.worker = None

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(
                self, "処理中", "処理を中断して終了しますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait()
        self._save_settings()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

