"""
Preferences window.

Component Type: Client (UI / Initiation Volatility).
Five-tab NSWindow built with PyObjC AppKit. Reads/writes via Settings utility.
On save, rebuilds the live HandlerRegistry so handler changes take effect
immediately without restarting.
"""

from __future__ import annotations

import objc
import queue as _queue
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
        self.m_settings:     Settings        = None
        self.m_registry:     HandlerRegistry = None
        self.m_slate_access: object         = None   # ISlateAccess
        self.m_bridge:       object         = None   # AsyncBridge
        self.m_window:       NSWindow       = None

        # Vault tab
        self.m_vault_source  = _TableDataSource.alloc().init()
        self.m_vault_table:  NSTableView   = None

        # Handlers tab
        self.m_handler_source = _TableDataSource.alloc().init()
        self.m_handler_source.mark_bool_column("enabled")
        self.m_handler_table: NSTableView   = None
        self.m_default_popup: object        = None

        # Device tab — configured device display
        self.m_device_name_label:  NSTextField            = None
        self.m_device_addr_label:  NSTextField            = None
        self.m_rescan_btn:         NSButton               = None
        self.m_pair_btn:           NSButton               = None
        self.m_scan_status_label:  NSTextField            = None
        self.m_scan_results_source = _TableDataSource.alloc().init()
        self.m_scan_results_table: NSTableView            = None
        self.m_timeout_field:      NSTextField            = None
        self.m_device_queue:       _queue.SimpleQueue     = None
        self.m_pair_addr:          str                    = ""
        self.m_pair_name:          str                    = ""
        self.m_pair_status:        str                    = ""
        self.m_pair_error:         str                    = ""
        self.m_scan_seen_addrs:    set                    = set()

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
        self.m_registry = registry
        return self

    def setSlateAccess_bridge_(self, slate_access, bridge) -> None:
        self.m_slate_access = slate_access
        self.m_bridge       = bridge

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
        # Windows from alloc/init default to releasedWhenClosed=YES: the red
        # close button would free the window while self.m_window still points
        # at it, crashing the next show().
        self.m_window.setReleasedWhenClosed_(False)
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

        # ── Configured Device ────────────────────────────────────────
        sect1 = _label("Configured Device", _PAD, 296, 200)
        sect1.setFont_(NSFont.boldSystemFontOfSize_(12))
        view.addSubview_(sect1)

        view.addSubview_(_label("Name", _PAD, 270))
        self.m_device_name_label = _label("None configured", _PAD + 90, 270, 400)
        self.m_device_name_label.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(self.m_device_name_label)

        view.addSubview_(_label("Address", _PAD, 246))
        self.m_device_addr_label = _label("—", _PAD + 90, 246, 400)
        self.m_device_addr_label.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(self.m_device_addr_label)

        forget_btn = _button("Forget",  _PAD,       214, 72)
        self.m_rescan_btn = _button("Rescan", _PAD + 80, 214, 76)
        forget_btn.setTarget_(self);       forget_btn.setAction_("onForget:")
        self.m_rescan_btn.setTarget_(self); self.m_rescan_btn.setAction_("onRescan:")
        view.addSubview_(forget_btn)
        view.addSubview_(self.m_rescan_btn)

        self.m_scan_status_label = _label("", _PAD + 164, 218, 260)
        self.m_scan_status_label.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(self.m_scan_status_label)

        # ── Nearby Devices ───────────────────────────────────────────
        sect2 = _label("Nearby Devices", _PAD, 186, 200)
        sect2.setFont_(NSFont.boldSystemFontOfSize_(12))
        view.addSubview_(sect2)

        scroll, table = _scroll_with_table(_PAD, 54, _TAB_CONTENT_W - 2 * _PAD, 128)
        _add_column(table, "name",    "Name",    200, editable=False)
        _add_column(table, "address", "Address", 300, editable=False)
        table.setDataSource_(self.m_scan_results_source)
        self.m_scan_results_table = table
        view.addSubview_(scroll)

        select_btn = _button("Select", _PAD, 24, 72)
        select_btn.setTarget_(self)
        select_btn.setAction_("onSelectDevice:")
        view.addSubview_(select_btn)

        # Pairing replaces the old register.py script: hold the Slate button
        # until it flashes, click Pair, then press the button once when asked.
        self.m_pair_btn = _button("Pair", _PAD + 80, 24, 72)
        self.m_pair_btn.setTarget_(self)
        self.m_pair_btn.setAction_("onPair:")
        view.addSubview_(self.m_pair_btn)

        view.addSubview_(_label("Scan timeout", _PAD + 164, 28, 100))
        self.m_timeout_field = _field(_PAD + 272, 24, 50, placeholder="10")
        view.addSubview_(self.m_timeout_field)
        view.addSubview_(_label("seconds", _PAD + 330, 28, 60))
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

        name = s.get_device_name()
        addr = s.get_device_address()
        self.m_device_name_label.setStringValue_(name if name else "None configured")
        self.m_device_addr_label.setStringValue_(addr if addr else "—")
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
        # Address/name are saved immediately on Select/Forget; only timeout is deferred.
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

    def onForget_(self, _sender) -> None:
        self.m_settings.set_device_name("")
        self.m_settings.set_device_address("")
        self.m_device_name_label.setStringValue_("None configured")
        self.m_device_addr_label.setStringValue_("—")

    def onRescan_(self, _sender) -> None:
        if self.m_slate_access is None or self.m_bridge is None:
            self.m_scan_status_label.setStringValue_("Scanner not available.")
            return
        self.m_rescan_btn.setEnabled_(False)
        self.m_scan_results_source.set_rows([])
        self.m_scan_results_table.reloadData()
        self.m_scan_seen_addrs = set()
        self.m_device_queue    = _queue.SimpleQueue()
        timeout = self._scan_timeout()
        self.m_scan_status_label.setStringValue_(f"Scanning ({int(timeout)}s)…")

        device_queue = self.m_device_queue

        def _on_device_found(device) -> None:
            device_queue.put({"name": device.name or "(unknown)", "address": str(device.address)})
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "drainDeviceQueue:", None, False
            )

        future = self.m_bridge.run(
            self.m_slate_access.scan_for_devices(timeout, on_device_found=_on_device_found)
        )
        future.add_done_callback(self._on_scan_future_done)

    def _scan_timeout(self) -> float:
        try:
            return float(self.m_timeout_field.stringValue())
        except (ValueError, AttributeError):
            return 10.0

    def _pair_target(self) -> tuple[str, str]:
        """
        The device to pair with: the highlighted scan result, else the already
        configured device (so a Slate that lost its registration can be re-paired
        without scanning first). Returns (address, name).
        """
        row  = self.m_scan_results_table.selectedRow()
        rows = self.m_scan_results_source.rows()
        if 0 <= row < len(rows):
            return rows[row].get("address", ""), rows[row].get("name", "")
        return self.m_settings.get_device_address(), self.m_settings.get_device_name()

    def onPair_(self, _sender) -> None:
        if self.m_slate_access is None or self.m_bridge is None:
            self.m_scan_status_label.setStringValue_("Bluetooth not available.")
            return

        address, name = self._pair_target()
        if not address:
            self.m_scan_status_label.setStringValue_(
                "Select a nearby device first, or configure one."
            )
            return

        self.m_pair_btn.setEnabled_(False)
        self.m_scan_status_label.setStringValue_(
            "Hold the Slate button until it flashes…"
        )

        slate           = self.m_slate_access
        timeout         = self._scan_timeout()
        self.m_pair_addr = address
        self.m_pair_name = name

        def _awaiting_button() -> None:
            # Fired from the asyncio thread — hop to the main thread to draw.
            self.m_pair_status = "Press the button on the Slate now…"
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "applyPairStatus:", None, False
            )

        async def _do_pair() -> None:
            device = await slate.find_device(address, timeout)
            if device is None:
                raise RuntimeError(
                    f"{address} not found — hold the button until it flashes, then pair."
                )
            await slate.register(device, on_awaiting_button=_awaiting_button)

        future = self.m_bridge.run(_do_pair())
        future.add_done_callback(self._on_pair_future_done)

    def applyPairStatus_(self, _) -> None:
        self.m_scan_status_label.setStringValue_(getattr(self, "m_pair_status", ""))

    def _on_pair_future_done(self, future) -> None:
        exc = future.exception()
        self.m_pair_error = str(exc) if exc else ""
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyPairResult:", None, False
        )

    def applyPairResult_(self, _) -> None:
        self.m_pair_btn.setEnabled_(True)
        error = getattr(self, "m_pair_error", "")
        if error:
            self.m_scan_status_label.setStringValue_(error)
            return

        # A paired device is the device to sync with.
        name = self.m_pair_name or "(unknown)"
        self.m_settings.set_device_address(self.m_pair_addr)
        self.m_settings.set_device_name(self.m_pair_name)
        self.m_device_name_label.setStringValue_(name)
        self.m_device_addr_label.setStringValue_(self.m_pair_addr)
        self.m_scan_status_label.setStringValue_(f"Paired with {name}.")

    def onSelectDevice_(self, _sender) -> None:
        row = self.m_scan_results_table.selectedRow()
        if row < 0:
            return
        rows = self.m_scan_results_source.rows()
        if row >= len(rows):
            return
        device = rows[row]
        name   = device.get("name", "")
        addr   = device.get("address", "")
        self.m_settings.set_device_name(name)
        self.m_settings.set_device_address(addr)
        self.m_device_name_label.setStringValue_(name or "(unknown)")
        self.m_device_addr_label.setStringValue_(addr)

    def drainDeviceQueue_(self, _) -> None:
        """Called on main thread — flushes new devices from queue into the sorted table."""
        if self.m_device_queue is None:
            return
        changed = False
        while True:
            try:
                row = self.m_device_queue.get_nowait()
            except _queue.Empty:
                break
            addr = row.get("address", "")
            if addr not in self.m_scan_seen_addrs:
                self.m_scan_seen_addrs.add(addr)
                self.m_scan_results_source.add_row(row)
                changed = True
        if changed:
            self._sort_scan_results()
            self.m_scan_results_table.reloadData()
            count = len(self.m_scan_results_source.rows())
            self.m_scan_status_label.setStringValue_(f"Found {count} device(s)…")

    def _sort_scan_results(self) -> None:
        rows = self.m_scan_results_source.rows()
        rows.sort(key=lambda r: (0 if "bamboo" in r["name"].lower() else 1, r["name"].lower()))
        self.m_scan_results_source.set_rows(rows)

    def _on_scan_future_done(self, future) -> None:
        """Called from asyncio thread — drains any remaining devices, then signals completion."""
        try:
            future.result()
        except Exception:
            pass
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "refreshScanResults:", None, False
        )

    def refreshScanResults_(self, _) -> None:
        """Called on main thread when scan completes — final drain, re-enable button."""
        self.drainDeviceQueue_(None)
        count = len(self.m_scan_results_source.rows())
        self.m_rescan_btn.setEnabled_(True)
        self.m_scan_status_label.setStringValue_(
            f"Found {count} device(s)." if count else "No devices found."
        )

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
