from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QStyle,
    QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QMenu,
)

from .config import AppConfig
from .engine import TorrentEngine, TorrentFile
from .utils import format_bytes, format_rate


DARK_STYLESHEET = """
QWidget { background: #1f2329; color: #e6edf3; }
QLineEdit, QSpinBox, QComboBox, QTreeWidget, QTableWidget { background: #15191e; border: 1px solid #3a414a; padding: 4px; }
QPushButton { background: #2d333b; border: 1px solid #444c56; padding: 6px 10px; }
QPushButton:hover { background: #373e47; }
QHeaderView::section { background: #2d333b; color: #e6edf3; padding: 5px; border: 0; }
QProgressBar { border: 1px solid #444c56; text-align: center; }
QProgressBar::chunk { background: #3b82f6; }
QCheckBox::indicator, QTreeView::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #8b949e;
    border-radius: 3px;
    background: #0d1117;
}
QCheckBox::indicator:checked, QTreeView::indicator:checked {
    background: #3b82f6;
    border: 2px solid #bfdbfe;
}
QCheckBox::indicator:indeterminate, QTreeView::indicator:indeterminate {
    background: #64748b;
    border: 2px solid #cbd5e1;
}
"""


TEXT = {
    "en": {
        "select_files": "Select files - {title}",
        "select_hint": "Check only the files you want to download.",
        "select_all": "Select all",
        "clear_all": "Clear all",
        "file": "File",
        "size": "Size",
        "save_to": "Save to:",
        "browse": "Browse...",
        "download_folder": "Download folder",
        "no_files_title": "No files selected",
        "no_files": "Select at least one file.",
        "no_dest_title": "No destination",
        "no_dest": "Choose a download folder.",
        "loading_magnet": "Loading magnet metadata",
        "loading_magnet_msg": "Connecting to peers and loading the file list...",
        "cancel": "Cancel",
        "magnet_error": "Magnet error",
        "settings": "Settings",
        "default_download": "Default download folder",
        "download_limit": "Download limit",
        "max_peers": "Max peer connections",
        "enable_dht": "Enable DHT",
        "enable_pex": "Enable PEX",
        "enable_lsd": "Enable LSD",
        "enable_tcp": "Enable TCP peers",
        "enable_utp": "Enable uTP peers",
        "completion": "Completion",
        "delete_source": "Delete source .torrent after completion",
        "policy": "Policy",
        "seeding_disabled": "Seeding disabled",
        "upload_disabled": "Piece payload upload disabled",
        "remove_after": "Immediate session removal after completion",
        "startup": "Startup",
        "start_windows": "Start with Windows",
        "tray": "Tray",
        "minimize_tray": "Minimize to system tray",
        "notifications": "Notifications",
        "notify_complete": "Show completion notification",
        "theme": "Theme",
        "language": "Language",
        "toolbar_main": "Main",
        "add_torrent": "Add .torrent",
        "add_magnet": "Add magnet",
        "pause": "Pause",
        "resume": "Resume",
        "remove": "Remove",
        "name": "Name",
        "progress": "Progress",
        "down": "Down",
        "piece_upload": "Piece upload",
        "peers": "Peers",
        "state": "State",
        "save_path": "Save path",
        "open": "Open",
        "quit": "Quit",
        "open_torrent": "Open torrent",
        "torrent_files": "Torrent files (*.torrent)",
        "torrent_error": "Torrent error",
        "magnet_uri": "Magnet URI:",
        "invalid_magnet_title": "Invalid magnet",
        "invalid_magnet": "The text does not look like a magnet URI.",
        "download_stopped": "Download stopped",
        "download_complete": "Download complete",
    },
    "ko": {
        "select_files": "파일 선택 - {title}",
        "select_hint": "다운로드할 파일만 체크하세요.",
        "select_all": "전체 선택",
        "clear_all": "전체 해제",
        "file": "파일",
        "size": "크기",
        "save_to": "저장 위치:",
        "browse": "찾아보기...",
        "download_folder": "다운로드 폴더",
        "no_files_title": "파일이 선택되지 않음",
        "no_files": "최소 한 개 이상의 파일을 선택하세요.",
        "no_dest_title": "저장 위치 없음",
        "no_dest": "다운로드 폴더를 선택하세요.",
        "loading_magnet": "마그넷 메타데이터 불러오는 중",
        "loading_magnet_msg": "피어에 연결해 파일 목록을 불러오는 중입니다...",
        "cancel": "취소",
        "magnet_error": "마그넷 오류",
        "settings": "설정",
        "default_download": "기본 다운로드 폴더",
        "download_limit": "다운로드 속도 제한",
        "max_peers": "최대 피어 연결 수",
        "enable_dht": "DHT 사용",
        "enable_pex": "PEX 사용",
        "enable_lsd": "LSD 사용",
        "enable_tcp": "TCP 피어 사용",
        "enable_utp": "uTP 피어 사용",
        "completion": "완료 후",
        "delete_source": "완료 후 원본 .torrent 파일 삭제",
        "policy": "정책",
        "seeding_disabled": "시딩 사용 안 함",
        "upload_disabled": "파일 조각 업로드 사용 안 함",
        "remove_after": "완료 즉시 토렌트 세션에서 제거",
        "startup": "시작",
        "start_windows": "Windows 시작 시 실행",
        "tray": "트레이",
        "minimize_tray": "최소화 시 시스템 트레이로 이동",
        "notifications": "알림",
        "notify_complete": "다운로드 완료 알림 표시",
        "theme": "테마",
        "language": "언어",
        "toolbar_main": "메인",
        "add_torrent": ".torrent 추가",
        "add_magnet": "마그넷 추가",
        "pause": "일시정지",
        "resume": "재개",
        "remove": "제거",
        "name": "이름",
        "progress": "진행률",
        "down": "다운로드",
        "piece_upload": "조각 업로드",
        "peers": "피어",
        "state": "상태",
        "save_path": "저장 경로",
        "open": "열기",
        "quit": "종료",
        "open_torrent": "토렌트 열기",
        "torrent_files": "토렌트 파일 (*.torrent)",
        "torrent_error": "토렌트 오류",
        "magnet_uri": "마그넷 URI:",
        "invalid_magnet_title": "잘못된 마그넷",
        "invalid_magnet": "올바른 마그넷 URI 형식이 아닙니다.",
        "download_stopped": "다운로드 중단",
        "download_complete": "다운로드 완료",
    },
}


def tr(language: str, key: str, **kwargs) -> str:
    lang = language if language in TEXT else "en"
    text = TEXT[lang].get(key, TEXT["en"].get(key, key))
    return text.format(**kwargs)


def apply_theme(app: QApplication, theme: str) -> None:
    app.setStyleSheet(DARK_STYLESHEET if theme == "dark" else "")


class FileSelectionDialog(QDialog):
    def __init__(self, title: str, files: list[TorrentFile], default_dir: str, language: str, parent=None):
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(tr(language, "select_files", title=title))
        self.resize(760, 560)
        self.files = files
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(language, "select_hint")))

        row = QHBoxLayout()
        select_all = QPushButton(tr(language, "select_all"))
        clear_all = QPushButton(tr(language, "clear_all"))
        select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        clear_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        row.addWidget(select_all)
        row.addWidget(clear_all)
        row.addStretch()
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr(language, "file"), tr(language, "size")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        self._populate_tree()

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(default_dir)
        browse = QPushButton(tr(language, "browse"))
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel(tr(language, "save_to")))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept_checked)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _populate_tree(self) -> None:
        folders: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for file in self.files:
            parts = Path(file.path).parts
            parent = self.tree.invisibleRootItem()
            prefix: tuple[str, ...] = ()
            for part in parts[:-1]:
                prefix += (part,)
                item = folders.get(prefix)
                if item is None:
                    item = QTreeWidgetItem([part, ""])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                    item.setCheckState(0, Qt.CheckState.Checked)
                    parent.addChild(item)
                    folders[prefix] = item
                parent = item
            leaf = QTreeWidgetItem([parts[-1] if parts else file.path, format_bytes(file.size)])
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.CheckState.Checked)
            leaf.setData(0, Qt.ItemDataRole.UserRole, file.index)
            parent.addChild(leaf)
        self.tree.expandAll()

    def _set_all(self, state: Qt.CheckState) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(0, state)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr(self.language, "download_folder"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _accept_checked(self) -> None:
        if not self.selected_indices():
            QMessageBox.warning(self, tr(self.language, "no_files_title"), tr(self.language, "no_files"))
            return
        if not self.path_edit.text().strip():
            QMessageBox.warning(self, tr(self.language, "no_dest_title"), tr(self.language, "no_dest"))
            return
        self.accept()

    def selected_indices(self) -> list[int]:
        result: list[int] = []
        stack = [self.tree.invisibleRootItem()]
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                child = item.child(i)
                idx = child.data(0, Qt.ItemDataRole.UserRole)
                if idx is not None and child.checkState(0) == Qt.CheckState.Checked:
                    result.append(int(idx))
                stack.append(child)
        return sorted(result)

    @property
    def save_path(self) -> str:
        return self.path_edit.text().strip()


class MagnetMetadataDialog(QDialog):
    def __init__(self, engine: TorrentEngine, magnet_uri: str, save_path: str, language: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.language = language
        self.token = engine.prepare_magnet(magnet_uri, save_path)
        self.metadata: tuple[str, list[TorrentFile]] | None = None
        self.setWindowTitle(tr(language, "loading_magnet"))
        self.resize(420, 120)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(language, "loading_magnet_msg")))
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        cancel = QPushButton(tr(language, "cancel"))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _poll(self) -> None:
        try:
            metadata = self.engine.magnet_metadata(self.token)
            if metadata is not None:
                self.metadata = metadata
                self.timer.stop()
                self.accept()
        except Exception as exc:
            self.timer.stop()
            QMessageBox.critical(self, tr(self.language, "magnet_error"), str(exc))
            self.reject()

    def reject(self) -> None:
        self.timer.stop()
        self.engine.cancel_pending_magnet(self.token)
        super().reject()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        lang = config.language
        self.setWindowTitle(tr(lang, "settings"))
        self.resize(520, 560)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.download_dir = QLineEdit(config.download_dir)
        browse = QPushButton(tr(lang, "browse"))
        browse.clicked.connect(self._browse)
        path_layout.addWidget(self.download_dir, 1)
        path_layout.addWidget(browse)
        form.addRow(tr(lang, "default_download"), path_widget)

        self.download_limit = QSpinBox()
        self.download_limit.setRange(0, 10_000_000)
        self.download_limit.setSuffix(" KiB/s (0 = unlimited)")
        self.download_limit.setValue(config.download_limit_kib)
        form.addRow(tr(lang, "download_limit"), self.download_limit)

        self.max_connections = QSpinBox()
        self.max_connections.setRange(2, 5000)
        self.max_connections.setValue(config.max_connections)
        form.addRow(tr(lang, "max_peers"), self.max_connections)

        self.dht = QCheckBox(tr(lang, "enable_dht")); self.dht.setChecked(config.enable_dht)
        self.pex = QCheckBox(tr(lang, "enable_pex")); self.pex.setChecked(config.enable_pex)
        self.lsd = QCheckBox(tr(lang, "enable_lsd")); self.lsd.setChecked(config.enable_lsd)
        self.tcp = QCheckBox(tr(lang, "enable_tcp")); self.tcp.setChecked(config.enable_tcp)
        self.utp = QCheckBox(tr(lang, "enable_utp")); self.utp.setChecked(config.enable_utp)
        for label, widget in (("DHT", self.dht), ("PEX", self.pex), ("LSD", self.lsd), ("TCP", self.tcp), ("uTP", self.utp)):
            form.addRow(label, widget)

        self.delete_source = QCheckBox(tr(lang, "delete_source"))
        self.delete_source.setChecked(config.delete_torrent_source)
        form.addRow(tr(lang, "completion"), self.delete_source)

        for text in (tr(lang, "seeding_disabled"), tr(lang, "upload_disabled"), tr(lang, "remove_after")):
            fixed = QCheckBox(text)
            fixed.setChecked(True)
            fixed.setEnabled(False)
            form.addRow(tr(lang, "policy"), fixed)

        self.start_windows = QCheckBox(tr(lang, "start_windows")); self.start_windows.setChecked(config.start_with_windows)
        self.minimize_tray = QCheckBox(tr(lang, "minimize_tray")); self.minimize_tray.setChecked(config.minimize_to_tray)
        self.notify = QCheckBox(tr(lang, "notify_complete")); self.notify.setChecked(config.notify_on_complete)
        form.addRow(tr(lang, "startup"), self.start_windows)
        form.addRow(tr(lang, "tray"), self.minimize_tray)
        form.addRow(tr(lang, "notifications"), self.notify)

        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(config.theme)
        form.addRow(tr(lang, "theme"), self.theme)

        self.language = QComboBox()
        self.language.addItem("English", "en")
        self.language.addItem("한국어", "ko")
        index = self.language.findData(config.language)
        self.language.setCurrentIndex(index if index >= 0 else 0)
        form.addRow(tr(lang, "language"), self.language)

        layout.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr(self.config.language, "download_folder"), self.download_dir.text())
        if path:
            self.download_dir.setText(path)

    def apply(self) -> None:
        self.config.download_dir = self.download_dir.text().strip()
        self.config.download_limit_kib = self.download_limit.value()
        self.config.max_connections = self.max_connections.value()
        self.config.enable_dht = self.dht.isChecked()
        self.config.enable_pex = self.pex.isChecked()
        self.config.enable_lsd = self.lsd.isChecked()
        self.config.enable_tcp = self.tcp.isChecked()
        self.config.enable_utp = self.utp.isChecked()
        self.config.delete_torrent_source = self.delete_source.isChecked()
        self.config.start_with_windows = self.start_windows.isChecked()
        self.config.minimize_to_tray = self.minimize_tray.isChecked()
        self.config.notify_on_complete = self.notify.isChecked()
        self.config.theme = self.theme.currentText()
        self.config.language = str(self.language.currentData())
        self.config.save()


class MainWindow(QMainWindow):
    def __init__(self, engine: TorrentEngine, config: AppConfig):
        super().__init__()
        self.engine = engine
        self.config = config
        self.rows: dict[str, int] = {}
        self.actions: dict[str, QAction] = {}
        self.resize(1100, 620)
        self._build_toolbar()
        self._build_table()
        self._build_tray()
        self._retranslate()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _build_toolbar(self) -> None:
        self.toolbar = self.addToolBar("Main")
        self.toolbar.setMovable(False)
        for key, slot in (("add_torrent", self.add_torrent), ("add_magnet", self.add_magnet), ("pause", self.pause_selected), ("resume", self.resume_selected), ("remove", self.remove_selected), ("settings", self.open_settings)):
            action = QAction(self)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
            self.actions[key] = action

    def _build_table(self) -> None:
        self.table = QTableWidget(0, 7)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.setCentralWidget(self.table)

    def _build_tray(self) -> None:
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray_menu = QMenu()
        self.tray_open = self.tray_menu.addAction("", self._restore)
        self.tray_quit = self.tray_menu.addAction("", QApplication.instance().quit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda reason: self._restore() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _retranslate(self) -> None:
        lang = self.config.language
        self.setWindowTitle("Download Only Torrent")
        self.toolbar.setWindowTitle(tr(lang, "toolbar_main"))
        for key, action in self.actions.items():
            action.setText(tr(lang, key))
        self.table.setHorizontalHeaderLabels([
            tr(lang, "name"), tr(lang, "progress"), tr(lang, "down"),
            tr(lang, "piece_upload"), tr(lang, "peers"), tr(lang, "state"), tr(lang, "save_path")
        ])
        self.tray_open.setText(tr(lang, "open"))
        self.tray_quit.setText(tr(lang, "quit"))

    def add_torrent(self) -> None:
        lang = self.config.language
        path, _ = QFileDialog.getOpenFileName(self, tr(lang, "open_torrent"), "", tr(lang, "torrent_files"))
        if not path:
            return
        try:
            title, files = self.engine.preview_torrent(path)
            dialog = FileSelectionDialog(title, files, self.config.download_dir, lang, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.config.download_dir = dialog.save_path
                self.config.save()
                self.engine.add_torrent_file(path, dialog.save_path, dialog.selected_indices())
        except Exception as exc:
            QMessageBox.critical(self, tr(lang, "torrent_error"), str(exc))

    def add_magnet(self) -> None:
        lang = self.config.language
        uri, ok = QInputDialog.getMultiLineText(self, tr(lang, "add_magnet"), tr(lang, "magnet_uri"))
        uri = uri.strip()
        if not ok or not uri:
            return
        if not uri.lower().startswith("magnet:?"):
            QMessageBox.warning(self, tr(lang, "invalid_magnet_title"), tr(lang, "invalid_magnet"))
            return
        try:
            loader = MagnetMetadataDialog(self.engine, uri, self.config.download_dir, lang, self)
            if loader.exec() != QDialog.DialogCode.Accepted or loader.metadata is None:
                return
            title, files = loader.metadata
            dialog = FileSelectionDialog(title, files, self.config.download_dir, lang, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.config.download_dir = dialog.save_path
                self.config.save()
                self.engine.pending_magnets[loader.token].save_path = dialog.save_path
                self.engine.start_magnet(loader.token, dialog.selected_indices())
            else:
                self.engine.cancel_pending_magnet(loader.token)
        except Exception as exc:
            QMessageBox.critical(self, tr(lang, "magnet_error"), str(exc))

    def _poll(self) -> None:
        lang = self.config.language
        for snap in self.engine.poll():
            if snap.error:
                QMessageBox.critical(self, tr(lang, "download_stopped"), f"{snap.name}\n\n{snap.error}")
            if snap.completed and self.config.notify_on_complete:
                self.tray.showMessage(tr(lang, "download_complete"), snap.name, QSystemTrayIcon.MessageIcon.Information, 5000)
            if snap.removed:
                self._remove_row(snap.task_id)
                continue
            row = self._ensure_row(snap.task_id)
            self.table.setItem(row, 0, QTableWidgetItem(snap.name))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, snap.task_id)
            bar = self.table.cellWidget(row, 1)
            if not isinstance(bar, QProgressBar):
                bar = QProgressBar()
                bar.setRange(0, 1000)
                self.table.setCellWidget(row, 1, bar)
            bar.setValue(int(snap.progress * 1000))
            bar.setFormat(f"{snap.progress * 100:.1f}%")
            self.table.setItem(row, 2, QTableWidgetItem(format_rate(snap.download_rate)))
            self.table.setItem(row, 3, QTableWidgetItem(format_bytes(snap.payload_uploaded)))
            self.table.setItem(row, 4, QTableWidgetItem(str(snap.peers)))
            self.table.setItem(row, 5, QTableWidgetItem(snap.state))
            self.table.setItem(row, 6, QTableWidgetItem(snap.save_path))

    def _ensure_row(self, task_id: str) -> int:
        if task_id in self.rows:
            return self.rows[task_id]
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.rows[task_id] = row
        return row

    def _remove_row(self, task_id: str) -> None:
        row = self.rows.pop(task_id, None)
        if row is None:
            return
        self.table.removeRow(row)
        for key, current in list(self.rows.items()):
            if current > row:
                self.rows[key] = current - 1

    def _selected_task_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return str(value) if value else None

    def pause_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.engine.pause(task_id)

    def resume_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.engine.resume(task_id)

    def remove_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.engine.remove(task_id)
            self._remove_row(task_id)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply()
            self.engine.apply_config(self.config)
            apply_theme(QApplication.instance(), self.config.theme)
            self._retranslate()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and self.config.minimize_to_tray:
            QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.tray.hide()
        super().closeEvent(event)

    def _restore(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
