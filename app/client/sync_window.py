"""
Note review and import window.

Component Type: Client (UI / Initiation Volatility).
Shows notes downloaded from the Slate. User selects which to process through the
AI pipeline (parse → render → ingest → vault). Notes are downloaded from the device
and cleared as part of listing (protocol requirement: delete_oldest advances the pointer).
"""

from __future__ import annotations

import time
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
    NSProgressIndicator,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)

from app.utilities.models import NotePreview

_W    = 580
_H    = 420
_PAD  = 16
_SWITCH = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _label(text: str, x: float, y: float, w: float = 200, h: float = 18) -> NSTextField:
    f = NSTextField.labelWithString_(text)
    f.setFrame_(NSMakeRect(x, y, w, h))
    f.setFont_(NSFont.systemFontOfSize_(12))
    return f


def _button(title: str, x: float, y: float, w: float = 90, h: float = 24) -> NSButton:
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    return b


# ---------------------------------------------------------------------------
# Table data source
# ---------------------------------------------------------------------------

class _NoteTableSource(NSObject):

    def init(self):
        self = objc.super(_NoteTableSource, self).init()
        if self is None:
            return None
        self.m_rows: list[dict] = []
        return self

    def set_rows(self, rows: list[dict]) -> None:
        self.m_rows = [dict(r) for r in rows]

    def rows(self) -> list[dict]:
        return list(self.m_rows)

    def numberOfRowsInTableView_(self, _table):
        return len(self.m_rows)

    def tableView_objectValueForTableColumn_row_(self, _table, column, row):
        if row >= len(self.m_rows):
            return None
        col_id = str(column.identifier())
        val    = self.m_rows[row].get(col_id)
        if col_id == "import":
            return 1 if val else 0
        return str(val) if val is not None else ""

    def tableView_setObjectValue_forTableColumn_row_(self, _table, value, column, row):
        if row >= len(self.m_rows):
            return
        col_id = str(column.identifier())
        if col_id == "import":
            self.m_rows[row]["import"] = bool(int(value)) if value is not None else False


# ---------------------------------------------------------------------------
# Window controller
# ---------------------------------------------------------------------------

class SyncWindowController(NSObject):
    """
    Review window for notes fetched from the Bamboo Slate.

    Component Type: Client (UI / Initiation Volatility).
    Calls ISyncManager.list_notes() to download all notes into memory (the device
    is cleared as a side-effect of iteration). Lets the user select which notes to
    run through the ingest pipeline via ISyncManager.import_notes().
    """

    def init(self):
        self = objc.super(SyncWindowController, self).init()
        if self is None:
            return None
        self.m_sync_manager  = None
        self.m_bridge        = None
        self.m_window:         NSWindow    = None
        self.m_table:          NSTableView = None
        self.m_source          = _NoteTableSource.alloc().init()
        self.m_status_label:   NSTextField = None
        self.m_spinner         = None
        self.m_import_btn:     NSButton    = None
        self.m_select_all_btn: NSButton    = None
        self.m_desel_btn:      NSButton    = None
        self.m_previews:       list        = []
        return self

    def initWithSyncManager_bridge_(self, sync_manager, bridge):
        self = self.init()
        if self is None:
            return None
        self.m_sync_manager = sync_manager
        self.m_bridge       = bridge
        return self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        if self.m_window is None:
            self._build_window()
        self._reset_ui()
        self.m_window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        future = self.m_bridge.run(self.m_sync_manager.list_notes())
        future.add_done_callback(self._on_list_done)

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
        )
        self.m_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, _H), style, NSBackingStoreBuffered, False,
        )
        # Windows from alloc/init default to releasedWhenClosed=YES: the red
        # close button would free the window while self.m_window still points
        # at it, crashing the next show().
        self.m_window.setReleasedWhenClosed_(False)
        self.m_window.setTitle_("Sync Notes from Bamboo Slate")
        self.m_window.center()

        cv = self.m_window.contentView()

        # ── Top bar: spinner + status ─────────────────────────────────
        self.m_spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(_PAD, _H - 42, 20, 20)
        )
        self.m_spinner.setStyle_(1)  # NSProgressIndicatorStyleSpinning
        self.m_spinner.setDisplayedWhenStopped_(False)
        cv.addSubview_(self.m_spinner)

        self.m_status_label = _label("", _PAD + 28, _H - 40, _W - _PAD - 44, 18)
        cv.addSubview_(self.m_status_label)

        # ── Table ─────────────────────────────────────────────────────
        # Room below the table for the caption explaining the device is cleared.
        table_y = 70
        table_h = _H - 54 - table_y

        table = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, _W - 2 * _PAD, table_h))
        table.setUsesAlternatingRowBackgroundColors_(True)
        table.setRowHeight_(20)
        table.setAllowsMultipleSelection_(False)

        # Import checkbox column
        chk_col = NSTableColumn.alloc().initWithIdentifier_("import")
        chk_col.setWidth_(32)
        chk_col.headerCell().setStringValue_("✓")
        chk_col.setEditable_(True)
        cell = NSButtonCell.alloc().init()
        cell.setButtonType_(_SWITCH)
        cell.setTitle_("")
        chk_col.setDataCell_(cell)
        table.addTableColumn_(chk_col)

        for ident, title, width in [
            ("index",    "#",          40),
            ("filename", "Filename",  200),
            ("date",     "Date / Time", 160),
            ("size",     "Size",        80),
        ]:
            col = NSTableColumn.alloc().initWithIdentifier_(ident)
            col.setWidth_(width)
            col.headerCell().setStringValue_(title)
            col.setEditable_(False)
            table.addTableColumn_(col)

        table.setDataSource_(self.m_source)
        self.m_table = table

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(_PAD, table_y, _W - 2 * _PAD, table_h)
        )
        scroll.setDocumentView_(table)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(2)
        cv.addSubview_(scroll)

        # ── Caption ────────────────────────────────────────────────────
        # By the time this list is drawn the notes are already off the device:
        # delete_oldest is the only way to advance the file pointer. Say so, and
        # say where the raw data is, so an unimported note does not look lost.
        caption = _label(
            "These notes have been removed from the Slate. Anything you do not "
            "import is kept on this Mac, in spool/ inside the scratch folder.",
            _PAD, 48, _W - 2 * _PAD, 14,
        )
        caption.setFont_(NSFont.systemFontOfSize_(11))
        caption.setTextColor_(NSColor.secondaryLabelColor())
        cv.addSubview_(caption)

        # ── Bottom button row ──────────────────────────────────────────
        self.m_select_all_btn = _button("Select All",    _PAD,           16, 90)
        self.m_desel_btn      = _button("Deselect All",  _PAD + 98,      16, 100)
        cancel_btn            = _button("Cancel",        _W - _PAD - 198, 16, 88)
        self.m_import_btn     = _button("Import Selected", _W - _PAD - 138, 16, 128)

        self.m_select_all_btn.setTarget_(self)
        self.m_select_all_btn.setAction_("onSelectAll:")
        self.m_desel_btn.setTarget_(self)
        self.m_desel_btn.setAction_("onDeselectAll:")
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("onCancel:")
        self.m_import_btn.setTarget_(self)
        self.m_import_btn.setAction_("onImport:")

        cv.addSubview_(self.m_select_all_btn)
        cv.addSubview_(self.m_desel_btn)
        cv.addSubview_(cancel_btn)
        cv.addSubview_(self.m_import_btn)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _reset_ui(self) -> None:
        self.m_previews = []
        self.m_source.set_rows([])
        if self.m_table is not None:
            self.m_table.reloadData()
        self._set_busy(True, "Connecting to Bamboo Slate…")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if busy:
            self.m_spinner.startAnimation_(None)
            self.m_import_btn.setEnabled_(False)
            self.m_select_all_btn.setEnabled_(False)
            self.m_desel_btn.setEnabled_(False)
        else:
            self.m_spinner.stopAnimation_(None)
        if message:
            self.m_status_label.setStringValue_(message)

    # ------------------------------------------------------------------
    # Async callbacks (marshalled to main thread)
    # ------------------------------------------------------------------

    def _on_list_done(self, future) -> None:
        try:
            self._pending_previews = future.result()
            self._pending_error    = None
        except Exception as exc:
            self._pending_previews = []
            self._pending_error    = str(exc)
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyListResult:", None, False
        )

    def applyListResult_(self, _) -> None:
        previews = self._pending_previews
        error    = self._pending_error

        if error:
            self._set_busy(False, f"Error: {error}")
            return

        if not previews:
            self._set_busy(False, "No notes found on device.")
            return

        self.m_previews = previews
        rows = []
        for p in previews:
            label    = time.strftime("%Y%m%d_%H%M%S", time.gmtime(p.timestamp))
            date_str = time.strftime("%Y-%m-%d  %H:%M", time.gmtime(p.timestamp))
            size_str = f"{len(p.raw_bytes) / 1024:.1f} KB"
            rows.append({
                "import":   True,
                "index":    str(p.index + 1),
                "filename": label,
                "date":     date_str,
                "size":     size_str,
            })
        self.m_source.set_rows(rows)
        self.m_table.reloadData()

        self.m_import_btn.setEnabled_(True)
        self.m_select_all_btn.setEnabled_(True)
        self.m_desel_btn.setEnabled_(True)
        self._set_busy(False)
        self.m_status_label.setStringValue_(
            f"{len(previews)} note(s) fetched from device — select which to import."
        )

    def _on_import_done(self, future) -> None:
        try:
            result = future.result()
            msg    = f"Imported {result.synced_count} note(s)."
            if result.failed_count:
                msg += (
                    f"  {result.failed_count} failed — raw data kept in _scratch/spool/."
                )
            self._pending_import_msg = msg
            self._pending_import_ok  = result.failed_count == 0
        except Exception as exc:
            self._pending_import_msg = f"Import error: {exc}"
            self._pending_import_ok  = False
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyImportResult:", None, False
        )

    def applyImportResult_(self, _) -> None:
        msg = getattr(self, "_pending_import_msg", "Done.")
        self._set_busy(False, msg)
        # Only dismiss on a clean run — otherwise the message would never be read.
        if getattr(self, "_pending_import_ok", False):
            self.m_window.orderOut_(None)
        else:
            self.m_import_btn.setEnabled_(True)
            self.m_select_all_btn.setEnabled_(True)
            self.m_desel_btn.setEnabled_(True)

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def onSelectAll_(self, _) -> None:
        rows = self.m_source.rows()
        for r in rows:
            r["import"] = True
        self.m_source.set_rows(rows)
        self.m_table.reloadData()

    def onDeselectAll_(self, _) -> None:
        rows = self.m_source.rows()
        for r in rows:
            r["import"] = False
        self.m_source.set_rows(rows)
        self.m_table.reloadData()

    def onCancel_(self, _) -> None:
        self.m_window.orderOut_(None)

    def onImport_(self, _) -> None:
        rows     = self.m_source.rows()
        selected = [
            self.m_previews[i]
            for i, r in enumerate(rows)
            if r.get("import") and i < len(self.m_previews)
        ]
        if not selected:
            self.m_status_label.setStringValue_("No notes selected — check at least one row.")
            return
        self._set_busy(True, f"Importing {len(selected)} note(s)…")
        future = self.m_bridge.run(self.m_sync_manager.import_notes(selected))
        future.add_done_callback(self._on_import_done)
