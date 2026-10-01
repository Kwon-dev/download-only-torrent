from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .debug_ui import (
    _PEER_LEGEND,
    _format_endpoint,
    _peer_client,
    _peer_flag,
    _peer_flags,
    _peer_sources,
    _peer_summary,
)
from .utils import format_bytes, format_rate


TEXT = {
    "en": {
        "peers_tab": "Peers",
        "columns": [
            "Address",
            "Client",
            "Status",
            "Flags",
            "Have",
            "Down speed",
            "Received",
            "Source",
        ],
        "no_selection": "Select a download to see its peers.",
        "summary": (
            "{connected} connected (+{handshaking} connecting) | "
            "seeds {seeds}, {seeds_choking} choking us | "
            "{sending} sending now"
        ),
        "connecting": "Connecting",
        "choking": "Choking us",
        "receiving": "Receiving",
        "snubbed": "Unchoked, not sending",
        "waiting": "Unchoked, idle",
    },
    "ko": {
        "peers_tab": "피어",
        "columns": [
            "주소",
            "클라이언트",
            "상태",
            "플래그",
            "보유",
            "받는 속도",
            "받은 양",
            "출처",
        ],
        "no_selection": "다운로드를 선택하면 피어 목록이 표시됩니다.",
        "summary": (
            "연결 {connected} (+연결 시도 {handshaking}) | "
            "시더 {seeds}, 그중 막는 시더 {seeds_choking} | "
            "지금 보내는 피어 {sending}"
        ),
        "connecting": "연결 중",
        "choking": "막힘",
        "receiving": "받는 중",
        "snubbed": "열림, 전송 없음",
        "waiting": "열림, 대기",
    },
}

_SPLITTER_KEY = "ui/peer_panel_splitter"
_SORT_KEY = "ui/peer_panel_sort"
_REFRESH_MS = 1000


def _t(lang: str, key: str):
    return TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"][key])


class _SortItem(QTableWidgetItem):
    """Table item that sorts by a separate key (numbers sort numerically)."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):
        key = getattr(other, "_key", None)
        if key is None:
            return super().__lt__(other)
        try:
            return self._key < key
        except TypeError:
            return str(self._key) < str(key)


def peer_status(lang: str, peer) -> str:
    if _peer_flag(peer, "connecting") or _peer_flag(peer, "handshake"):
        return _t(lang, "connecting")
    if _peer_flag(peer, "remote_choked"):
        return _t(lang, "choking")
    if int(getattr(peer, "payload_down_speed", 0)) > 0:
        return _t(lang, "receiving")
    if _peer_flag(peer, "snubbed"):
        return _t(lang, "snubbed")
    return _t(lang, "waiting")


def peer_row(lang: str, peer) -> list[tuple[str, object]]:
    """(display text, sort key) for each column."""

    progress = float(getattr(peer, "progress", 0.0))
    rate = int(getattr(peer, "payload_down_speed", 0))
    received = int(getattr(peer, "total_download", 0))
    address = _format_endpoint(getattr(peer, "ip", "?"))
    client = _peer_client(peer)
    status = peer_status(lang, peer)
    flags = _peer_flags(peer)
    source = _peer_sources(peer)
    return [
        (address, address),
        (client, client.casefold()),
        (status, status),
        (flags, flags),
        (f"{progress * 100:.1f}%", progress),
        (format_rate(rate), rate),
        (format_bytes(received), received),
        (source, source),
    ]


class PeerPanel(QWidget):
    """µTorrent-style detail pane below the download list."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        lang = window.config.language

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 4, 4, 4)
        self.summary = QLabel(_t(lang, "no_selection"))
        page_layout.addWidget(self.summary)

        columns = _t(lang, "columns")
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((210, 160, 110, 80, 60, 95, 85, 70)):
            self.table.setColumnWidth(column, width)
        flags_item = self.table.horizontalHeaderItem(3)
        if flags_item is not None:
            flags_item.setToolTip(_PEER_LEGEND)
        self.table.setSortingEnabled(True)
        self._restore_sort()
        header.sortIndicatorChanged.connect(self._save_sort)
        page_layout.addWidget(self.table, 1)
        self.tabs.addTab(page, _t(lang, "peers_tab"))

        self.timer = QTimer(self)
        self.timer.setInterval(_REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _restore_sort(self) -> None:
        raw = str(QSettings().value(_SORT_KEY, "5:1"))
        try:
            column, order = (int(part) for part in raw.split(":"))
        except ValueError:
            column, order = 5, 1
        self.table.sortItems(column, Qt.SortOrder(order))

    def _save_sort(self, column: int, order) -> None:
        QSettings().setValue(_SORT_KEY, f"{column}:{int(order.value)}")

    def selected_task_id(self) -> str | None:
        return self.window._task_id_at_row(self.window.table.currentRow())

    def refresh(self) -> None:
        if not self.isVisible():
            return
        lang = self.window.config.language
        task = self.window.engine.tasks.get(self.selected_task_id() or "")
        if task is None:
            self.summary.setText(_t(lang, "no_selection"))
            self.table.setRowCount(0)
            return
        try:
            peers = list(task.handle.get_peer_info())
        except Exception:
            peers = []

        summary = _peer_summary(peers)
        self.summary.setText(
            _t(lang, "summary").format(
                connected=summary["connected"],
                handshaking=summary["handshaking"],
                seeds=summary["seeds"],
                seeds_choking=summary["seeds_choking"],
                sending=summary["sending"],
            )
        )

        # Rebuild the rows, keeping the selected peer and scroll position.
        selected = None
        current = self.table.currentRow()
        if current >= 0 and self.table.item(current, 0) is not None:
            selected = self.table.item(current, 0).text()
        scroll = self.table.verticalScrollBar().value()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(peers))
        for row, peer in enumerate(peers):
            for column, (text, key) in enumerate(peer_row(lang, peer)):
                self.table.setItem(row, column, _SortItem(text, key))
        self.table.setSortingEnabled(True)

        if selected is not None:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None and item.text() == selected:
                    self.table.selectRow(row)
                    break
        self.table.verticalScrollBar().setValue(scroll)


def install_peer_panel(window) -> PeerPanel:
    """Put a resizable peer pane under the download list."""

    table = window.takeCentralWidget()
    splitter = QSplitter(Qt.Orientation.Vertical, window)
    splitter.addWidget(table)
    panel = PeerPanel(window)
    splitter.addWidget(panel)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 2)
    splitter.setChildrenCollapsible(True)
    window.setCentralWidget(splitter)

    state = QSettings().value(_SPLITTER_KEY)
    if state is not None:
        splitter.restoreState(state)
    splitter.splitterMoved.connect(
        lambda *_: QSettings().setValue(_SPLITTER_KEY, splitter.saveState())
    )

    window.table.itemSelectionChanged.connect(panel.refresh)
    window._peer_panel = panel
    window._peer_splitter = splitter
    return panel
