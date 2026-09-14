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
"""


def apply_theme(app: QApplication, theme: str) -> None:
    app.setStyleSheet(DARK_STYLESHEET if theme == "dark" else "")


class FileSelectionDialog(QDialog):
    def __init__(self, title: str, files: list[TorrentFile], default_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Select files - {title}")
        self.resize(760, 560)
        self.files = files
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Check only the files you want to download."))

        row = QHBoxLayout()
        select_all = QPushButton("Select all")
        clear_all = QPushButton("Clear all")
        select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        clear_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        row.addWidget(select_all)
        row.addWidget(clear_all)
        row.addStretch()
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Size"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        self._populate_tree()

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(default_dir)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Save to:"))
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
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _accept_checked(self) -> None:
        if not self.selected_indices():
            QMessageBox.warning(self, "No files selected", "Select at least one file.")
            return
        if not self.path_edit.text().strip():
            QMessageBox.warning(self, "No destination", "Choose a download folder.")
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
    def __init__(self, engine: TorrentEngine, magnet_uri: str, save_path: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.token = engine.prepare_magnet(magnet_uri, save_path)
        self.metadata: tuple[str, list[TorrentFile]] | None = None
        self.setWindowTitle("Loading magnet metadata")
        self.resize(420, 120)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Connecting to peers and loading the file list..."))
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        cancel = QPushButton("Cancel")
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
            QMessageBox.critical(self, "Magnet error", str(exc))
            self.reject()

    def reject(self) -> None:
        self.timer.stop()
        self.engine.cancel_pending_magnet(self.token)
        super().reject()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.resize(520, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.download_dir = QLineEdit(config.download_dir)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(self.download_dir, 1)
        path_layout.addWidget(browse)
        form.addRow("Default download folder", path_widget)

        self.download_limit = QSpinBox()
        self.download_limit.setRange(0, 10_000_000)
        self.download_limit.setSuffix(" KiB/s (0 = unlimited)")
        self.download_limit.setValue(config.download_limit_kib)
        form.addRow("Download limit", self.download_limit)

        self.max_connections = QSpinBox()
        self.max_connections.setRange(2, 5000)
        self.max_connections.setValue(config.max_connections)
        form.addRow("Max peer connections", self.max_connections)

        self.dht = QCheckBox("Enable DHT"); self.dht.setChecked(config.enable_dht)
        self.pex = QCheckBox("Enable PEX"); self.pex.setChecked(config.enable_pex)
        self.lsd = QCheckBox("Enable LSD"); self.lsd.setChecked(config.enable_lsd)
        self.tcp = QCheckBox("Enable TCP peers"); self.tcp.setChecked(config.enable_tcp)
        self.utp = QCheckBox("Enable uTP peers"); self.utp.setChecked(config.enable_utp)
        for label, widget in (("DHT", self.dht), ("PEX", self.pex), ("LSD", self.lsd), ("TCP", self.tcp), ("uTP", self.utp)):
            form.addRow(label, widget)

        self.delete_source = QCheckBox("Delete source .torrent after completion")
        self.delete_source.setChecked(config.delete_torrent_source)
        form.addRow("Completion", self.delete_source)

        for text in ("Seeding disabled", "Piece payload upload disabled", "Immediate session removal after completion"):
            fixed = QCheckBox(text)
            fixed.setChecked(True)
            fixed.setEnabled(False)
            form.addRow("Policy", fixed)

        self.start_windows = QCheckBox("Start with Windows"); self.start_windows.setChecked(config.start_with_windows)
        self.minimize_tray = QCheckBox("Minimize to system tray"); self.minimize_tray.setChecked(config.minimize_to_tray)
        self.notify = QCheckBox("Show completion notification"); self.notify.setChecked(config.notify_on_complete)
        form.addRow("Startup", self.start_windows)
        form.addRow("Tray", self.minimize_tray)
        form.addRow("Notifications", self.notify)

        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(config.theme)
        form.addRow("Theme", self.theme)
        layout.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.download_dir.text())
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
        self.config.save()


class MainWindow(QMainWindow):
    def __init__(self, engine: TorrentEngine, config: AppConfig):
        super().__init__()
        self.engine = engine
        self.config = config
        self.rows: dict[str, int] = {}
        self.setWindowTitle("Download Only Torrent")
        self.resize(1100, 620)
        self._build_toolbar()
        self._build_table()
        self._build_tray()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        for text, slot in (("Add .torrent", self.add_torrent), ("Add magnet", self.add_magnet), ("Pause", self.pause_selected), ("Resume", self.resume_selected), ("Remove", self.remove_selected), ("Settings", self.open_settings)):
            action = QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)

    def _build_table(self) -> None:
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Name", "Progress", "Down", "Piece upload", "Peers", "State", "Save path"])
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
        menu = QMenu()
        menu.addAction("Open", self._restore)
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._restore() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def add_torrent(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open torrent", "", "Torrent files (*.torrent)")
        if not path:
            return
        try:
            title, files = self.engine.preview_torrent(path)
            dialog = FileSelectionDialog(title, files, self.config.download_dir, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.config.download_dir = dialog.save_path
                self.config.save()
                self.engine.add_torrent_file(path, dialog.save_path, dialog.selected_indices())
        except Exception as exc:
            QMessageBox.critical(self, "Torrent error", str(exc))

    def add_magnet(self) -> None:
        uri, ok = QInputDialog.getMultiLineText(self, "Add magnet", "Magnet URI:")
        uri = uri.strip()
        if not ok or not uri:
            return
        if not uri.lower().startswith("magnet:?"):
            QMessageBox.warning(self, "Invalid magnet", "The text does not look like a magnet URI.")
            return
        try:
            loader = MagnetMetadataDialog(self.engine, uri, self.config.download_dir, self)
            if loader.exec() != QDialog.DialogCode.Accepted or loader.metadata is None:
                return
            title, files = loader.metadata
            dialog = FileSelectionDialog(title, files, self.config.download_dir, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.config.download_dir = dialog.save_path
                self.config.save()
                self.engine.pending_magnets[loader.token].save_path = dialog.save_path
                self.engine.start_magnet(loader.token, dialog.selected_indices())
            else:
                self.engine.cancel_pending_magnet(loader.token)
        except Exception as exc:
            QMessageBox.critical(self, "Magnet error", str(exc))

    def _poll(self) -> None:
        for snap in self.engine.poll():
            if snap.error:
                QMessageBox.critical(self, "Download stopped", f"{snap.name}\n\n{snap.error}")
            if snap.completed and self.config.notify_on_complete:
                self.tray.showMessage("Download complete", snap.name, QSystemTrayIcon.MessageIcon.Information, 5000)
            if snap.removed:
                self._remove_row(snap.task_id)
                continue
            row = self._ensure_row(snap.task_id)
            self.table.setItem(row, 0, QTableWidgetItem(snap.name))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, snap.task_id)
            bar = self.table.cellWidget(row, 1)
            if not isinstance(bar, QProgressBar):
                bar = QProgressBar(); bar.setRange(0, 1000); self.table.setCellWidget(row, 1, bar)
            bar.setValue(int(snap.progress * 1000)); bar.setFormat(f"{snap.progress * 100:.1f}%")
            self.table.setItem(row, 2, QTableWidgetItem(format_rate(snap.download_rate)))
            self.table.setItem(row, 3, QTableWidgetItem(format_bytes(snap.payload_uploaded)))
            self.table.setItem(row, 4, QTableWidgetItem(str(snap.peers)))
            self.table.setItem(row, 5, QTableWidgetItem(snap.state))
            self.table.setItem(row, 6, QTableWidgetItem(snap.save_path))

    def _ensure_row(self, task_id: str) -> int:
        if task_id in self.rows:
            return self.rows[task_id]
        row = self.table.rowCount(); self.table.insertRow(row); self.rows[task_id] = row
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
        if task_id: self.engine.pause(task_id)

    def resume_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id: self.engine.resume(task_id)

    def remove_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.engine.remove(task_id); self._remove_row(task_id)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply(); self.engine.apply_config(self.config); apply_theme(QApplication.instance(), self.config.theme)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and self.config.minimize_to_tray:
            QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.tray.hide()
        super().closeEvent(event)

    def _restore(self) -> None:
        self.showNormal(); self.show(); self.raise_(); self.activateWindow()
