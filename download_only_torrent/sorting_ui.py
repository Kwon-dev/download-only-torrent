from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QMessageBox,
    QProgressBar,
    QSystemTrayIcon,
    QTableWidgetItem,
    QTreeWidgetItem,
)

from .ui import FileSelectionDialog, state_label, tr
from .utils import format_bytes, format_rate


SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 37


class SortableTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a raw value instead of display text."""

    def __init__(self, text: str, sort_value):
        super().__init__(text)
        self.setData(SORT_ROLE, sort_value)

    def __lt__(self, other) -> bool:
        try:
            left = self.data(SORT_ROLE)
            right = other.data(SORT_ROLE)
            if left is not None and right is not None:
                return left < right
        except Exception:
            pass
        return self.text().casefold() < other.text().casefold()


def _folder_total_size(item: QTreeWidgetItem, sizes: dict[int, int]) -> int:
    idx = item.data(0, Qt.ItemDataRole.UserRole)
    if idx is not None:
        return int(sizes.get(int(idx), 0))
    return sum(
        _folder_total_size(item.child(i), sizes)
        for i in range(item.childCount())
    )


def _sort_tree_children(
    parent: QTreeWidgetItem,
    column: int,
    order: Qt.SortOrder,
    sizes: dict[int, int],
) -> None:
    children = [parent.takeChild(0) for _ in range(parent.childCount())]

    def key(item: QTreeWidgetItem):
        if column == 1:
            primary = _folder_total_size(item, sizes)
        else:
            primary = item.text(0).casefold()
        return primary, item.text(0).casefold()

    children.sort(
        key=key,
        reverse=order == Qt.SortOrder.DescendingOrder,
    )
    parent.addChildren(children)
    for child in children:
        _sort_tree_children(child, column, order, sizes)


def _install_file_selection_sorting() -> None:
    if getattr(FileSelectionDialog, "_sorting_extended", False):
        return

    original_init = FileSelectionDialog.__init__

    def extended_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._sort_sizes = {
            int(file.index): int(file.size) for file in self.files
        }

        # Show aggregate folder sizes as well, which makes size sorting useful
        # for multi-file torrents with nested folders.
        def populate_folder_sizes(item: QTreeWidgetItem) -> int:
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None:
                return int(self._sort_sizes.get(int(idx), 0))
            total = 0
            for i in range(item.childCount()):
                total += populate_folder_sizes(item.child(i))
            if item is not self.tree.invisibleRootItem():
                item.setText(1, format_bytes(total))
            return total

        populate_folder_sizes(self.tree.invisibleRootItem())

        settings = QSettings()
        try:
            column = int(settings.value("ui/file_sort_column", 0))
        except (TypeError, ValueError):
            column = 0
        column = 1 if column == 1 else 0
        descending = str(
            settings.value("ui/file_sort_desc", "false")
        ).lower() in {"1", "true", "yes"}
        order = (
            Qt.SortOrder.DescendingOrder
            if descending
            else Qt.SortOrder.AscendingOrder
        )
        self._file_sort_column = column
        self._file_sort_order = order

        header = self.tree.header()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(column, order)

        def apply_sort(sort_column: int | None = None) -> None:
            if sort_column is not None:
                if sort_column == self._file_sort_column:
                    self._file_sort_order = (
                        Qt.SortOrder.DescendingOrder
                        if self._file_sort_order
                        == Qt.SortOrder.AscendingOrder
                        else Qt.SortOrder.AscendingOrder
                    )
                else:
                    self._file_sort_column = (
                        1 if sort_column == 1 else 0
                    )
                    self._file_sort_order = Qt.SortOrder.AscendingOrder

            self.tree.setUpdatesEnabled(False)
            try:
                _sort_tree_children(
                    self.tree.invisibleRootItem(),
                    self._file_sort_column,
                    self._file_sort_order,
                    self._sort_sizes,
                )
                # Sorting reparents the QTreeWidgetItem hierarchy, and Qt may
                # reset expanded state while doing so. Preserve the original
                # file picker's fully-expanded behavior.
                self.tree.expandAll()
            finally:
                self.tree.setUpdatesEnabled(True)

            header.setSortIndicator(
                self._file_sort_column,
                self._file_sort_order,
            )
            settings.setValue(
                "ui/file_sort_column",
                self._file_sort_column,
            )
            settings.setValue(
                "ui/file_sort_desc",
                self._file_sort_order
                == Qt.SortOrder.DescendingOrder,
            )

        header.sectionClicked.connect(apply_sort)
        apply_sort()

    FileSelectionDialog.__init__ = extended_init
    FileSelectionDialog._sorting_extended = True


def _rebuild_row_map(window) -> None:
    rows: dict[str, int] = {}
    for row in range(window.table.rowCount()):
        item = window.table.item(row, 0)
        value = (
            item.data(Qt.ItemDataRole.UserRole)
            if item is not None
            else None
        )
        if value:
            rows[str(value)] = row
    window.rows = rows


def _update_sortable_item(
    table,
    row: int,
    column: int,
    text: str,
    sort_value,
    *,
    task_id: str | None = None,
) -> SortableTableItem:
    """Update a cell without replacing its item on every timer tick.

    QTableWidget selection is tied to the item/model indexes. Replacing every
    item every 500 ms caused Ctrl/Shift multi-row selections to disappear as
    download progress changed. Once a SortableTableItem exists, mutate it in
    place so the selection remains attached to the same objects.
    """

    item = table.item(row, column)
    if not isinstance(item, SortableTableItem):
        item = SortableTableItem(text, sort_value)
        table.setItem(row, column, item)
    else:
        if item.text() != text:
            item.setText(text)
        item.setData(SORT_ROLE, sort_value)

    if task_id is not None:
        item.setData(Qt.ItemDataRole.UserRole, task_id)
    return item


def _install_main_table_sorting(window) -> None:
    table = window.table
    settings = QSettings()
    try:
        sort_column = int(settings.value("ui/main_sort_column", 0))
    except (TypeError, ValueError):
        sort_column = 0
    sort_column = max(
        0,
        min(table.columnCount() - 1, sort_column),
    )
    descending = str(
        settings.value("ui/main_sort_desc", "false")
    ).lower() in {"1", "true", "yes"}
    sort_order = (
        Qt.SortOrder.DescendingOrder
        if descending
        else Qt.SortOrder.AscendingOrder
    )

    # Disconnect the original poll because it recreates every QTableWidgetItem
    # on every update. That object replacement is what cleared multi-selection.
    original_poll = window._poll
    try:
        window.timer.timeout.disconnect(original_poll)
    except Exception:
        try:
            window.timer.timeout.disconnect()
        except Exception:
            pass

    # Keep Qt's automatic sorting disabled. We sort explicitly after each data
    # update so item updates cannot move rows halfway through a poll cycle.
    table.setSortingEnabled(False)

    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    header.setSortIndicator(sort_column, sort_order)

    state = {
        "column": sort_column,
        "order": sort_order,
    }

    def save_sort() -> None:
        settings.setValue(
            "ui/main_sort_column",
            int(state["column"]),
        )
        settings.setValue(
            "ui/main_sort_desc",
            state["order"] == Qt.SortOrder.DescendingOrder,
        )

    def sort_now() -> None:
        table.sortItems(state["column"], state["order"])
        _rebuild_row_map(window)

    def header_clicked(column: int) -> None:
        if column == state["column"]:
            state["order"] = (
                Qt.SortOrder.DescendingOrder
                if state["order"] == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            state["column"] = int(column)
            state["order"] = Qt.SortOrder.AscendingOrder
        header.setSortIndicator(state["column"], state["order"])
        save_sort()
        sort_now()

    header.sectionClicked.connect(header_clicked)

    def stable_poll() -> None:
        lang = window.config.language

        # window.rows always describes the order produced by the previous sort.
        # The only time it changes during this loop is when a torrent completes
        # and _remove_row() intentionally removes that task.
        for snap in window.engine.poll():
            if snap.error:
                QMessageBox.critical(
                    window,
                    tr(lang, "download_stopped"),
                    f"{snap.name}\n\n{snap.error}",
                )
            if snap.completed and window.config.notify_on_complete:
                window.tray.showMessage(
                    tr(lang, "download_complete"),
                    snap.name,
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
            if snap.removed:
                window._remove_row(snap.task_id)
                continue

            row = window._ensure_row(snap.task_id)
            _update_sortable_item(
                table,
                row,
                0,
                snap.name,
                snap.name.casefold(),
                task_id=snap.task_id,
            )

            bar = table.cellWidget(row, 1)
            if not isinstance(bar, QProgressBar):
                bar = QProgressBar()
                bar.setRange(0, 1000)
                table.setCellWidget(row, 1, bar)
            bar.setValue(int(snap.progress * 1000))
            bar.setFormat(f"{snap.progress * 100:.1f}%")
            _update_sortable_item(
                table,
                row,
                1,
                "",
                float(snap.progress),
            )

            _update_sortable_item(
                table,
                row,
                2,
                format_rate(snap.download_rate),
                int(snap.download_rate),
            )
            _update_sortable_item(
                table,
                row,
                3,
                format_bytes(snap.payload_uploaded),
                int(snap.payload_uploaded),
            )
            _update_sortable_item(
                table,
                row,
                4,
                str(snap.peers),
                int(snap.peers),
            )
            state_text = state_label(lang, snap.state)
            _update_sortable_item(
                table,
                row,
                5,
                state_text,
                state_text.casefold(),
            )
            _update_sortable_item(
                table,
                row,
                6,
                snap.save_path,
                snap.save_path.casefold(),
            )

        # Sorting persistent items moves the selected items instead of deleting
        # and recreating them, so Ctrl/Shift/drag selections survive progress,
        # speed and peer-count updates.
        sort_now()

    window.timer.timeout.connect(stable_poll)
    sort_now()


def install_sorting_ui(window) -> None:
    """Enable persistent numeric-aware sorting in file and main download lists."""

    _install_file_selection_sorting()
    _install_main_table_sorting(window)
