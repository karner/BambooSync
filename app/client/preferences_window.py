"""
Preferences window.

Component Type: Client (UI / Initiation Volatility).
Five-tab NSWindow built with PyObjC AppKit. Reads/writes via Settings utility.
On save, rebuilds the live HandlerRegistry so handler changes take effect
immediately without restarting.
"""

from __future__ import annotations

import objc
from Foundation import NSObject, NSMakeRect
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSButtonCell,
    NSColor,
    NSFont,
    NSOpenPanel,
    NSSavePanel,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)

from app.utilities.handler_registry import HandlerRegistry, OllamaHandler
from app.utilities.settings         import Settings

_W   = 600
_H   = 460
_PAD = 16
_TAB_CONTENT_W = 560
_TAB_CONTENT_H = 330

# NSButtonTypeSwitch integer value — checkbox cell style.
_SWITCH = 3


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _label(text: str, x: float, y: float, w: float = 160, h: float = 18) -> NSTextField:
    f = NSTextField.labelWithString_(text)
    f.setFrame_(NSMakeRect(x, y, w, h))
    f.setFont_(NSFont.systemFontOfSize_(12))
    return f


def _field(x: float, y: float, w: float = 320, h: float = 22, placeholder: str = "") -> NSTextField:
    f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    f.setPlaceholderString_(placeholder)
    return f


def _button(title: str, x: float, y: float, w: float = 90, h: float = 24) -> NSButton:
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    return b


def _checkbox(title: str, x: float, y: float, w: float = 340) -> NSButton:
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 18))
    b.setButtonType_(_SWITCH)
    b.setTitle_(title)
    b.setFont_(NSFont.systemFontOfSize_(13))
    return b


def _scroll_with_table(x: float, y: float, w: float, h: float) -> tuple[NSScrollView, NSTableView]:
    table  = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    table.setUsesAlternatingRowBackgroundColors_(True)
    table.setRowHeight_(20)
    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    scroll.setDocumentView_(table)
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(False)
    scroll.setBorderType_(2)  # NSBezelBorder
    return scroll, table


def _add_column(
    table:    NSTableView,
    ident:    str,
    title:    str,
    width:    float,
    editable: bool  = True,
    checkbox: bool  = False,
) -> NSTableColumn:
    col = NSTableColumn.alloc().initWithIdentifier_(ident)
    col.setWidth_(width)
    col.headerCell().setStringValue_(title)
    col.setEditable_(editable)
    if checkbox:
        cell = NSButtonCell.alloc().init()
        cell.setButtonType_(_SWITCH)
        cell.setTitle_("")
        col.setDataCell_(cell)
    table.addTableColumn_(col)
    return col


# ---------------------------------------------------------------------------
# Table data sources
# ---------------------------------------------------------------------------

class _TableDataSource(NSObject):
    """
    Generic editable NSTableView data source.

    Component Type: Client helper (UI Volatility).
    Stores a list of dicts. Checkbox columns store booleans as 0/1 for ObjC.
    """

    def init(self):
        self = objc.super(_TableDataSource, self).init()
        if self is None:
            return None
        self.m_rows: list[dict]    = []
        self.m_bool_cols: set[str] = set()
        return self

    def set_rows(self, rows: list[dict]) -> None:
        self.m_rows = [dict(r) for r in rows]

    def rows(self) -> list[dict]:
        return list(self.m_rows)

    def mark_bool_column(self, ident: str) -> None:
        self.m_bool_cols.add(ident)

    def add_row(self, row: dict) -> None:
        self.m_rows.append(dict(row))

    def remove_row(self, index: int) -> None:
        if 0 <= index < len(self.m_rows):
            self.m_rows.pop(index)

    # NSTableViewDataSource protocol

    def numberOfRowsInTableView_(self, _table):
        return len(self.m_rows)

    def tableView_objectValueForTableColumn_row_(self, _table, column, row):
        if row >= len(self.m_rows):
            return None
        col_id = str(column.identifier())
        val    = self.m_rows[row].get(col_id, "")
        if col_id in self.m_bool_cols:
            return 1 if val else 0
        return str(val) if val is not None else ""

    def tableView_setObjectValue_forTableColumn_row_(self, _table, value, column, row):
        if row >= len(self.m_rows):
            return
        col_id = str(column.identifier())
        if col_id in self.m_bool_cols:
            self.m_rows[row][col_id] = bool(int(value)) if value is not None else False
        else:
            self.m_rows[row][col_id] = str(value) if value is not None else ""


# ---------------------------------------------------------------------------
# Main controller
# ---------------------------------------------------------------------------

class PreferencesWindowController(NSObject):
    """
    Controls the five-tab preferences window.

    Component Type: Client (UI / Initiation Volatility).
    Reads initial values from Settings on show(). Writes back on Save.
    Rebuilds HandlerRegistry from handler settings so changes are live.
    """

    def init(self):
        self = objc.super(PreferencesWindowController, self).init()
        if self is None:
            return None
        self.m_settings: Settings          = None
        self.m_registry: HandlerRegistry   = None
        self.m_window:   NSWindow          = None

        # Vault tab
        self.m_vault_source  = _TableDataSource.alloc().init()
        self.m_vault_table:  NSTableView   = None

        # Handlers tab
        self.m_handler_source = _TableDataSource.alloc().init()
        self.m_handler_source.mark_bool_column("enabled")
        self.m_handler_table: NSTableView   = None
        self.m_default_popup: object        = None

        # Device tab
        self.m_addr_field:    NSTextField   = None
        self.m_timeout_field: NSTextField   = None

        # Sync tab
        self.m_auto_sync_check:        NSButton = None
        self.m_unrouted_quarantine:    NSButton = None
        self.m_unrouted_notify:        NSButton = None
        self.m_scratch_field:          NSTextField = None

        # Notifications tab
        self.m_notify_check: NSButton = None
        self.m_count_check:  NSButton = None
        return self

    def initWithSettings_registry_(self, settings: Settings, registry: HandlerRegistry):
        self = self.init()
        if self is None:
            return None
        self.m_settings = settings
        self.m_registry  = registry
        return self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        if self.m_window is None:
            self._build_window()
        self._load_values()
        self.m_window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        style = (NSWindowStyleMaskTitled
                 | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskMiniaturizable)
        self.m_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, _H), style, NSBackingStoreBuffered, False,
        )
        self.m_window.setTitle_("Preferences")
        self.m_window.center()

        cv = self.m_window.contentView()
        cv.addSubview_(self._build_tab_view())

        save_btn   = _button("Save",   _W - _PAD - 90, 12)
        cancel_btn = _button("Cancel", _W - _PAD - 188, 12)
        save_btn.setTarget_(self)
        save_btn.setAction_("onSave:")
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("onCancel:")
        cv.addSubview_(save_btn)
        cv.addSubview_(cancel_btn)

    def _build_tab_view(self) -> NSTabView:
        tv = NSTabView.alloc().initWithFrame_(
            NSMakeRect(0, 44, _W, _H - 44)
        )
        for title, builder in [
            ("Vaults",        self._build_vaults_tab),
            ("Device",        self._build_device_tab),
            ("AI Handlers",   self._build_handlers_tab),
            ("Sync",          self._build_sync_tab),
            ("Notifications", self._build_notifications_tab),
        ]:
            item = NSTabViewItem.alloc().init()
            item.setLabel_(title)
            item.setView_(builder())
            tv.addTabViewItem_(item)
        return tv

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_vaults_tab(self) -> NSTextField:
        view = NSTextField.labelWithString_("")  # blank container reuse
        view = _blank_view()

        scroll, table = _scroll_with_table(_PAD, 44, _TAB_CONTENT_W - 2 * _PAD, _TAB_CONTENT_H - 20)
        _add_column(table, "name", "Name",  130)
        _add_column(table, "path", "Path",  390)
        table.setDataSource_(self.m_vault_source)
        self.m_vault_table = table
        view.addSubview_(scroll)

        add_btn = _button("+ Add",          _PAD,           12, 76)
        rem_btn = _button("− Remove",       _PAD + 84,      12, 80)
        exp_btn = _button("Export env file…", _PAD + 172,   12, 130)
        add_btn.setTarget_(self); add_btn.setAction_("onAddVault:")
        rem_btn.setTarget_(self); rem_btn.setAction_("onRemoveVault:")
        exp_btn.setTarget_(self); exp_btn.setAction_("onExportEnv:")
        view.addSubview_(add_btn)
        view.addSubview_(rem_btn)
        view.addSubview_(exp_btn)

        hint = _label("Names become VAULT_<NAME>_PATH environment variables.", _PAD, _TAB_CONTENT_H + 4, 440)
        hint.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(hint)
        return view

    def _build_device_tab(self) -> object:
        view = _blank_view()
        y    = _TAB_CONTENT_H - 10

        view.addSubview_(_label("BLE Address", _PAD, y))
        self.m_addr_field = _field(_PAD + 110, y, 380, placeholder="e.g. 4D0C6741-2678-...")
        view.addSubview_(self.m_addr_field)

        y -= 36
        view.addSubview_(_label("Scan timeout", _PAD, y))
        self.m_timeout_field = _field(_PAD + 110, y, 60, placeholder="30")
        view.addSubview_(self.m_timeout_field)
        view.addSubview_(_label("seconds", _PAD + 178, y, 60))
        return view

    def _build_handlers_tab(self) -> object:
        view = _blank_view()

        scroll, table = _scroll_with_table(_PAD, 62, _TAB_CONTENT_W - 2 * _PAD, _TAB_CONTENT_H - 40)
        _add_column(table, "name",    "Name",    110)
        _add_column(table, "url",     "URL",     190)
        _add_column(table, "model",   "Model",   130)
        _add_column(table, "enabled", "On",       50, checkbox=True)
        table.setDataSource_(self.m_handler_source)
        self.m_handler_table = table
        view.addSubview_(scroll)

        add_btn = _button("+ Add",     _PAD,      36, 76)
        rem_btn = _button("− Remove",  _PAD + 84, 36, 80)
        add_btn.setTarget_(self); add_btn.setAction_("onAddHandler:")
        rem_btn.setTarget_(self); rem_btn.setAction_("onRemoveHandler:")
        view.addSubview_(add_btn)
        view.addSubview_(rem_btn)

        view.addSubview_(_label("Default handler", _PAD, 10))
        from AppKit import NSPopUpButton
        self.m_default_popup = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(_PAD + 120, 8, 200, 22)
        )
        view.addSubview_(self.m_default_popup)
        return view

    def _build_sync_tab(self) -> object:
        view = _blank_view()
        y    = _TAB_CONTENT_H - 10

        self.m_auto_sync_check = _checkbox("Auto-sync when Slate is detected", _PAD, y)
        view.addSubview_(self.m_auto_sync_check)

        y -= 36
        view.addSubview_(_label("Unrouted notes", _PAD, y + 2))
        self.m_unrouted_quarantine = _checkbox("Quarantine silently", _PAD + 110, y, 170)
        self.m_unrouted_notify     = _checkbox("Show notification",   _PAD + 288, y, 160)
        # Simulate radio group: toggling one unchecks the other.
        self.m_unrouted_quarantine.setTarget_(self)
        self.m_unrouted_quarantine.setAction_("onUnroutedChanged:")
        self.m_unrouted_notify.setTarget_(self)
        self.m_unrouted_notify.setAction_("onUnroutedChanged:")
        view.addSubview_(self.m_unrouted_quarantine)
        view.addSubview_(self.m_unrouted_notify)

        y -= 36
        view.addSubview_(_label("Scratch directory", _PAD, y + 2))
        self.m_scratch_field = _field(_PAD + 110, y, 300, placeholder="default (project _scratch/)")
        browse_btn = _button("Browse…", _PAD + 418, y, 72)
        browse_btn.setTarget_(self)
        browse_btn.setAction_("onBrowseScratch:")
        view.addSubview_(self.m_scratch_field)
        view.addSubview_(browse_btn)
        return view

    def _build_notifications_tab(self) -> object:
        view = _blank_view()
        y    = _TAB_CONTENT_H - 10

        self.m_notify_check = _checkbox("Notify when sync completes", _PAD, y)
        view.addSubview_(self.m_notify_check)

        y -= 28
        self.m_count_check = _checkbox("Show synced note count in menu bar title", _PAD, y)
        view.addSubview_(self.m_count_check)
        return view

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        s = self.m_settings

        self.m_vault_source.set_rows(s.get_vaults())
        self.m_vault_table.reloadData()

        self.m_addr_field.setStringValue_(s.get_device_address())
        self.m_timeout_field.setStringValue_(str(int(s.get_device_scan_timeout())))

        handlers = s.get_handlers()
        self.m_handler_source.set_rows(handlers)
        self.m_handler_table.reloadData()
        self._rebuild_default_popup(handlers, s.get_default_handler())

        self.m_auto_sync_check.setState_(1 if s.get_auto_sync() else 0)
        is_quarantine = s.get_unrouted_action() == "quarantine"
        self.m_unrouted_quarantine.setState_(1 if is_quarantine else 0)
        self.m_unrouted_notify.setState_(0 if is_quarantine else 1)
        self.m_scratch_field.setStringValue_(s.get_scratch_dir())

        self.m_notify_check.setState_(1 if s.get_notify_sync_complete() else 0)
        self.m_count_check.setState_(1 if s.get_show_count_in_menu() else 0)

    def _save_values(self) -> None:
        s = self.m_settings

        s.set_vaults(self.m_vault_source.rows())
        s.set_device_address(str(self.m_addr_field.stringValue()))
        try:
            s.set_device_scan_timeout(float(self.m_timeout_field.stringValue()))
        except ValueError:
            pass

        handlers = self.m_handler_source.rows()
        s.set_handlers(handlers)
        s.set_default_handler(str(self.m_default_popup.titleOfSelectedItem() or ""))

        s.set_auto_sync(self.m_auto_sync_check.state() == 1)
        action = "quarantine" if self.m_unrouted_quarantine.state() == 1 else "notify"
        s.set_unrouted_action(action)
        s.set_scratch_dir(str(self.m_scratch_field.stringValue()))

        s.set_notify_sync_complete(self.m_notify_check.state() == 1)
        s.set_show_count_in_menu(self.m_count_check.state() == 1)

        self._apply_handlers_to_registry(handlers)

    def _apply_handlers_to_registry(self, handlers: list[dict]) -> None:
        """Rebuilds live HandlerRegistry from saved handler rows."""
        for h in handlers:
            if not h.get("enabled"):
                continue
            name  = h.get("name", "").strip()
            url   = h.get("url", "http://localhost:11434").strip()
            model = h.get("model", "").strip()
            if name and model:
                self.m_registry.register(name, OllamaHandler(model=model, base_url=url))

    def _rebuild_default_popup(self, handlers: list[dict], current: str) -> None:
        self.m_default_popup.removeAllItems()
        names = [h.get("name", "") for h in handlers if h.get("name")]
        self.m_default_popup.addItemsWithTitles_(names)
        if current in names:
            self.m_default_popup.selectItemWithTitle_(current)

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def onSave_(self, _sender) -> None:
        self._save_values()
        self.m_window.orderOut_(None)

    def onCancel_(self, _sender) -> None:
        self.m_window.orderOut_(None)

    def onAddVault_(self, _sender) -> None:
        self.m_vault_source.add_row({"name": "", "path": ""})
        self.m_vault_table.reloadData()

    def onRemoveVault_(self, _sender) -> None:
        row = self.m_vault_table.selectedRow()
        if row >= 0:
            self.m_vault_source.remove_row(row)
            self.m_vault_table.reloadData()

    def onExportEnv_(self, _sender) -> None:
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_("bamboo-slate-env.sh")
        if panel.runModal():
            path = panel.URL().path()
            self.m_settings.export_env_file(path)

    def onAddHandler_(self, _sender) -> None:
        self.m_handler_source.add_row(
            {"name": "", "url": "http://localhost:11434", "model": "", "enabled": True}
        )
        self.m_handler_table.reloadData()
        self._rebuild_default_popup(
            self.m_handler_source.rows(), self.m_settings.get_default_handler()
        )

    def onRemoveHandler_(self, _sender) -> None:
        row = self.m_handler_table.selectedRow()
        if row >= 0:
            self.m_handler_source.remove_row(row)
            self.m_handler_table.reloadData()
            self._rebuild_default_popup(
                self.m_handler_source.rows(), self.m_settings.get_default_handler()
            )

    def onBrowseScratch_(self, _sender) -> None:
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal():
            self.m_scratch_field.setStringValue_(str(panel.URL().path()))

    def onUnroutedChanged_(self, sender) -> None:
        # Simulate radio group: ensure only one is selected.
        if sender is self.m_unrouted_quarantine:
            self.m_unrouted_notify.setState_(0)
        else:
            self.m_unrouted_quarantine.setState_(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_view() -> NSTextField:
    """Returns a plain NSView sized to the tab content area."""
    from AppKit import NSView
    return NSView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _TAB_CONTENT_W, _TAB_CONTENT_H + 30)
    )
