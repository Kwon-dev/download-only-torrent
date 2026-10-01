from __future__ import annotations

import libtorrent as lt

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
)

from .debug_ui import PropertiesDialog


TEXT = {
    "en": {
        "pause": "Pause",
        "resume": "Resume",
        "remove": "Remove",
        "properties": "Properties",
        "row_height": "Row height...",
        "remove_title": "Remove torrent",
        "remove_text": "Remove '{name}' from the download list?",
        "remove_many_text": "Remove {count} selected torrents from the download list?",
        "remove_info": (
            "By default only the torrent task is removed. Downloaded data and "
            "the original .torrent file are kept."
        ),
        "delete_data": "Also delete downloaded data",
        "delete_warning": "Downloaded data will be permanently deleted.",
        "delete_failed": "Could not remove torrent data",
        "row_height_title": "Row height",
        "row_height_label": "Height in pixels:",
    },
    "ko": {
        "pause": "일시정지",
        "resume": "재개",
        "remove": "제거",
        "properties": "속성",
        "row_height": "행 높이...",
        "remove_title": "토렌트 제거",
        "remove_text": "'{name}' 항목을 다운로드 목록에서 제거할까요?",
        "remove_many_text": "선택한 {count}개의 토렌트를 다운로드 목록에서 제거할까요?",
        "remove_info": (
            "기본적으로 토렌트 작업만 목록/세션에서 제거됩니다. "
            "다운로드된 데이터와 원본 .torrent 파일은 그대로 유지됩니다."
        ),
        "delete_data": "다운로드된 데이터도 함께 삭제",
        "delete_warning": "다운로드된 데이터는 복구할 수 없게 삭제됩니다.",
        "delete_failed": "토렌트 데이터 삭제 실패",
        "row_height_title": "행 높이",
        "row_height_label": "높이(px):",
    },
}


def _t(lang: str, key: str, **kwargs) -> str:
    table = TEXT.get(lang, TEXT["en"])
    value = table.get(key, TEXT["en"].get(key, key))
    return value.format(**kwargs)


def _delete_flag_candidates() -> list[object]:
    result: list[object] = []
    for owner_name in ("remove_flags_t", "options_t"):
        owner = getattr(lt, owner_name, None)
        value = getattr(owner, "delete_files", None) if owner is not None else None
        if value is not None:
            result.append(value)

    session_type = getattr(lt, "session", None)
    value = getattr(session_type, "delete_files", None) if session_type is not None else None
    if value is not None:
        result.append(value)

    # Older Python bindings accepted the integer bit flag directly.
    result.append(1)
    return result


def _remove_task(window, task_id: str, delete_data: bool) -> tuple[bool, str | None]:
    engine = window.engine
    task = engine.tasks.get(task_id)
    if task is None:
        return False, None

    was_paused = bool(task.paused)
    try:
        task.handle.pause()
        task.handle.clear_peers()
    except Exception:
        pass

    try:
        if delete_data:
            last_type_error: Exception | None = None
            removed = False
            for flag in _delete_flag_candidates():
                try:
                    engine.session.remove_torrent(task.handle, flag)
                    removed = True
                    break
                except TypeError as exc:
                    last_type_error = exc
            if not removed:
                raise RuntimeError(str(last_type_error or "delete_files flag unavailable"))
        else:
            engine.session.remove_torrent(task.handle)
    except Exception as exc:
        if not was_paused:
            try:
                task.handle.resume()
                engine._kick_discovery(task.handle)
            except Exception:
                pass
        return False, f"{task.name}: {exc}"

    engine.tasks.pop(task_id, None)
    engine.discard_saved_state(task.key)
    window._remove_row(task_id)
    return True, None


def _selected_task_ids(window) -> list[str]:
    selection = window.table.selectionModel()
    if selection is None:
        return []

    ids: list[str] = []
    for index in sorted(selection.selectedRows(), key=lambda idx: idx.row()):
        task_id = window._task_id_at_row(index.row())
        if task_id and task_id not in ids:
            ids.append(task_id)
    return ids


def _confirm_remove(window, task_ids: list[str]) -> None:
    task_ids = [task_id for task_id in task_ids if task_id in window.engine.tasks]
    if not task_ids:
        return

    lang = window.config.language
    box = QMessageBox(window)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(_t(lang, "remove_title"))

    if len(task_ids) == 1:
        task = window.engine.tasks[task_ids[0]]
        box.setText(_t(lang, "remove_text", name=task.name))
    else:
        box.setText(_t(lang, "remove_many_text", count=len(task_ids)))

    box.setInformativeText(_t(lang, "remove_info"))
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)

    delete_data = QCheckBox(_t(lang, "delete_data"), box)
    box.setCheckBox(delete_data)

    def update_warning(checked: bool) -> None:
        box.setInformativeText(
            _t(lang, "delete_warning") if checked else _t(lang, "remove_info")
        )

    delete_data.toggled.connect(update_warning)
    if box.exec() != QMessageBox.StandardButton.Yes:
        return

    errors: list[str] = []
    for task_id in list(task_ids):
        _, error = _remove_task(window, task_id, delete_data.isChecked())
        if error:
            errors.append(error)

    try:
        window.engine._persist_tasks()
    except Exception:
        pass

    if errors:
        QMessageBox.critical(
            window,
            _t(lang, "delete_failed"),
            "\n".join(errors),
        )


def _set_global_row_height(window, height: int) -> None:
    height = max(20, min(96, int(height)))
    settings = QSettings()
    settings.setValue("ui/row_height", height)
    settings.sync()

    header = window.table.verticalHeader()
    header.setDefaultSectionSize(height)
    for row in range(window.table.rowCount()):
        window.table.setRowHeight(row, height)


def _ask_row_height(window) -> None:
    settings = QSettings()
    current = int(settings.value("ui/row_height", 30))
    value, ok = QInputDialog.getInt(
        window,
        _t(window.config.language, "row_height_title"),
        _t(window.config.language, "row_height_label"),
        current,
        20,
        96,
        1,
    )
    if ok:
        _set_global_row_height(window, value)


def _configure_stable_table(window) -> None:
    table = window.table
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    vertical = table.verticalHeader()
    vertical.setMinimumSectionSize(20)
    vertical.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    row_height = int(QSettings().value("ui/row_height", 30))
    _set_global_row_height(window, row_height)

    # These columns previously used ResizeToContents, which caused visible
    # left/right layout movement whenever rates, peer counts or state text changed.
    horizontal = table.horizontalHeader()
    defaults = {1: 110, 2: 105, 3: 115, 4: 70, 5: 150}
    settings = QSettings()
    for column, default_width in defaults.items():
        horizontal.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        width = int(settings.value(f"ui/column_width_{column}", default_width))
        table.setColumnWidth(column, max(50, width))

    def save_column_width(index: int, _old: int, new: int) -> None:
        if index in defaults and new >= 50:
            settings.setValue(f"ui/column_width_{index}", new)

    horizontal.sectionResized.connect(save_column_width)

    def save_row_height(_index: int, _old: int, new: int) -> None:
        if 20 <= new <= 96:
            settings.setValue("ui/row_height", new)
            vertical.setDefaultSectionSize(new)

    vertical.sectionResized.connect(save_row_height)


def _install_shortcut(window, sequence: str, callback) -> QShortcut:
    shortcut = QShortcut(QKeySequence(sequence), window)
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.activated.connect(callback)
    return shortcut


def install_controls_ui(window) -> None:
    """Install batch controls, shortcuts, and stable user-resizable table sizing."""

    _configure_stable_table(window)

    try:
        window.table.customContextMenuRequested.disconnect()
    except Exception:
        pass

    def selected_task_ids() -> list[str]:
        return _selected_task_ids(window)

    def toggle_pause() -> None:
        task_ids = selected_task_ids()
        if not task_ids:
            return

        # If any selected task is running, Space pauses all selected tasks.
        # If all selected tasks are paused, Space resumes them all.
        any_running = any(
            not window.engine.is_paused(task_id) for task_id in task_ids
        )
        for task_id in task_ids:
            if any_running:
                if not window.engine.is_paused(task_id):
                    window.engine.pause(task_id)
            else:
                if window.engine.is_paused(task_id):
                    window.engine.resume(task_id)

    def pause_selected() -> None:
        for task_id in selected_task_ids():
            if not window.engine.is_paused(task_id):
                window.engine.pause(task_id)

    def resume_selected() -> None:
        for task_id in selected_task_ids():
            if window.engine.is_paused(task_id):
                window.engine.resume(task_id)

    def remove_selected() -> None:
        _confirm_remove(window, selected_task_ids())

    def show_properties() -> None:
        task_ids = selected_task_ids()
        if task_ids:
            PropertiesDialog(window, task_ids[0]).exec()

    def change_row_height(delta: int) -> None:
        current = int(QSettings().value("ui/row_height", 30))
        _set_global_row_height(window, current + delta)

    def select_all_rows() -> None:
        window.table.selectAll()

    shortcuts = [
        _install_shortcut(window, "Delete", remove_selected),
        _install_shortcut(window, "Space", toggle_pause),
        _install_shortcut(window, "Ctrl+O", window.add_torrent),
        _install_shortcut(window, "Ctrl+M", window.add_magnet),
        _install_shortcut(window, "Ctrl+,", window.open_settings),
        _install_shortcut(window, "Alt+Return", show_properties),
        _install_shortcut(window, "Ctrl++", lambda: change_row_height(2)),
        _install_shortcut(window, "Ctrl+-", lambda: change_row_height(-2)),
        _install_shortcut(window, "Ctrl+A", select_all_rows),
    ]
    # Keep Python references alive for the lifetime of the window.
    window._torrent_shortcuts = shortcuts

    def show_menu(pos) -> None:
        row = window.table.indexAt(pos).row()
        clicked_task_id = window._task_id_at_row(row)
        if not clicked_task_id:
            return

        selection = window.table.selectionModel()
        selected_rows = {index.row() for index in selection.selectedRows()} if selection else set()

        # Right-clicking an already-selected row keeps the whole multi-selection.
        # Right-clicking outside the selection selects just that row.
        if row not in selected_rows:
            window.table.clearSelection()
            window.table.selectRow(row)
            window.table.setCurrentCell(row, 0)

        task_ids = selected_task_ids()
        lang = window.config.language
        menu = QMenu(window)
        menu.setStyleSheet(
            "QMenu { padding: 3px; }"
            "QMenu::item { padding: 6px 16px 6px 10px; margin: 0px; }"
            "QMenu::separator { height: 1px; margin: 3px 6px; }"
            "QMenu::indicator { width: 0px; height: 0px; }"
        )

        pause_action = menu.addAction(_t(lang, "pause"))
        pause_action.setShortcut(QKeySequence("Space"))
        resume_action = menu.addAction(_t(lang, "resume"))
        resume_action.setShortcut(QKeySequence("Space"))
        remove_action = menu.addAction(_t(lang, "remove"))
        remove_action.setShortcut(QKeySequence("Delete"))
        menu.addSeparator()
        properties_action = menu.addAction(_t(lang, "properties"))
        properties_action.setShortcut(QKeySequence("Alt+Return"))
        row_height_action = menu.addAction(_t(lang, "row_height"))

        pause_action.setEnabled(
            any(not window.engine.is_paused(task_id) for task_id in task_ids)
        )
        resume_action.setEnabled(
            any(window.engine.is_paused(task_id) for task_id in task_ids)
        )
        properties_action.setEnabled(bool(task_ids))

        chosen = menu.exec(window.table.viewport().mapToGlobal(pos))
        if chosen is pause_action:
            pause_selected()
        elif chosen is resume_action:
            resume_selected()
        elif chosen is remove_action:
            _confirm_remove(window, task_ids)
        elif chosen is properties_action:
            # Properties is intentionally for the row that was right-clicked.
            PropertiesDialog(window, clicked_task_id).exec()
        elif chosen is row_height_action:
            _ask_row_height(window)

    window.table.customContextMenuRequested.connect(show_menu)
