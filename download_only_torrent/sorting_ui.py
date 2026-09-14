from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtWidgets import QTableWidgetItem, QTreeWidgetItem

from .ui import FileSelectionDialog
from .utils import format_bytes


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
    return sum(_folder_total_size(item.child(i), sizes) for i in range(item.childCount()))


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

    children.sort(key=key, reverse=order == Qt.SortOrder.DescendingOrder)
    parent.addChildren(children)
    for child in children:
        _sort_tree_children(child, column, order, sizes)


def _install_file_selection_sorting() -> None:
    if getattr(FileSelectionDialog, "_sorting_extended", False):
        return

    original_init = FileSelectionDialog.__init__

    def extended_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._sort_sizes = {int(file.index): int(file.size) for file in self.files}

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
        descending = str(settings.value("ui/file_sort_desc", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
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
                        if self._file_sort_order == Qt.SortOrder.AscendingOrder
                        else Qt.SortOrder.AscendingOrder
                    )
                else:
                    self._file_sort_column = 1 if sort_column == 1 else 0
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
                # reset expanded state while doing so. The original file picker
                # opened every folder by default, so preserve that behavior both
                # on first show and after every header sort.
                self.tree.expandAll()
            finally:
                self.tree.setUpdatesEnabled(True)

            header.setSortIndicator(self._file_sort_column, self._file_sort_order)
            settings.setValue("ui/file_sort_column", self._file_sort_column)
            settings.setValue(
                "ui/file_sort_desc",
                self._file_sort_order == Qt.SortOrder.DescendingOrder,
            )

        header.sectionClicked.connect(apply_sort)
        apply_sort()

    FileSelectionDialog.__init__ = extended_init
    FileSelectionDialog._sorting_extended = True


def _task_ids_for_selected_rows(window) -> list[str]:
    model = window.table.selectionModel()
    if model is None:
        return []
    result: list[str] = []
    for index in model.selectedRows():
        item = window.table.item(index.row(), 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        if value:
            result.append(str(value))
    return result


def _rebuild_row_map(window) -> None:
    rows: dict[str, int] = {}
    for row in range(window.table.rowCount()):
        item = window.table.item(row, 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        if value:
            rows[str(value)] = row
    window.rows = rows


def _decorate_main_rows(window) -> None:
    table = window.table
    for row in range(table.rowCount()):
        name_item = table.item(row, 0)
        task_id = (
            str(name_item.data(Qt.ItemDataRole.UserRole))
            if name_item and name_item.data(Qt.ItemDataRole.UserRole)
            else ""
        )
        task = window.engine.tasks.get(task_id)
        try:
            status = task.handle.status() if task is not None else None
        except Exception:
            status = None

        name = name_item.text() if name_item else ""
        item = SortableTableItem(name, name.casefold())
        if task_id:
            item.setData(Qt.ItemDataRole.UserRole, task_id)
        table.setItem(row, 0, item)

        progress_widget = table.cellWidget(row, 1)
        progress = (
            float(progress_widget.value()) / 1000.0
            if progress_widget is not None and hasattr(progress_widget, "value")
            else 0.0
        )
        table.setItem(row, 1, SortableTableItem("", progress))

        rate = int(getattr(status, "download_payload_rate", 0)) if status else 0
        text = table.item(row, 2).text() if table.item(row, 2) else ""
        table.setItem(row, 2, SortableTableItem(text, rate))

        if task is not None and status is not None:
            total_upload = int(getattr(status, "total_payload_upload", 0))
            payload_upload = max(0, total_upload - int(task.initial_payload_upload))
        else:
            payload_upload = 0
        text = table.item(row, 3).text() if table.item(row, 3) else ""
        table.setItem(row, 3, SortableTableItem(text, payload_upload))

        peers = int(getattr(status, "num_peers", 0)) if status else 0
        text = table.item(row, 4).text() if table.item(row, 4) else "0"
        table.setItem(row, 4, SortableTableItem(text, peers))

        state = table.item(row, 5).text() if table.item(row, 5) else ""
        table.setItem(row, 5, SortableTableItem(state, state.casefold()))

        save_path = table.item(row, 6).text() if table.item(row, 6) else ""
        table.setItem(row, 6, SortableTableItem(save_path, save_path.casefold()))


def _restore_selection(window, task_ids: list[str]) -> None:
    selection = window.table.selectionModel()
    if selection is None:
        return
    window.table.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    first_row: int | None = None
    for task_id in task_ids:
        row = window.rows.get(task_id)
        if row is None:
            continue
        selection.select(window.table.model().index(row, 0), flags)
        if first_row is None:
            first_row = row
    if first_row is not None:
        window.table.setCurrentCell(first_row, 0)


def _install_main_table_sorting(window) -> None:
    table = window.table
    settings = QSettings()
    try:
        sort_column = int(settings.value("ui/main_sort_column", 0))
    except (TypeError, ValueError):
        sort_column = 0
    sort_column = max(0, min(table.columnCount() - 1, sort_column))
    descending = str(settings.value("ui/main_sort_desc", "false")).lower() in {
        "1",
        "true",
        "yes",
    }
    sort_order = (
        Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
    )

    original_poll = window._poll
    try:
        window.timer.timeout.disconnect(original_poll)
    except Exception:
        try:
            window.timer.timeout.disconnect()
        except Exception:
            pass

    table.setSortingEnabled(False)

    def sorted_poll() -> None:
        selected_ids = _task_ids_for_selected_rows(window)
        table.setSortingEnabled(False)
        _rebuild_row_map(window)
        original_poll()
        _decorate_main_rows(window)
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        table.sortItems(header.sortIndicatorSection(), header.sortIndicatorOrder())
        _rebuild_row_map(window)
        _restore_selection(window, selected_ids)

    window.timer.timeout.connect(sorted_poll)

    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    header.setSortIndicator(sort_column, sort_order)
    table.setSortingEnabled(True)
    table.sortItems(sort_column, sort_order)
    _rebuild_row_map(window)

    def save_sort(column: int, order: Qt.SortOrder) -> None:
        settings.setValue("ui/main_sort_column", int(column))
        settings.setValue("ui/main_sort_desc", order == Qt.SortOrder.DescendingOrder)

    header.sortIndicatorChanged.connect(save_sort)


def install_sorting_ui(window) -> None:
    """Enable persistent numeric-aware sorting in file and main download lists."""

    _install_file_selection_sorting()
    _install_main_table_sorting(window)
