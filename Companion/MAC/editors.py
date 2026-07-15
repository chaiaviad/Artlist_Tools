"""
Editor windows for the Companion (dark mode, normal pop-ups — they do NOT
follow the mouse, and the companion hides while one is open).

* GalleryEditor — characters / locations / media. Add via + or by dragging
  files in; delete selected; **drag thumbnails to re-order** (the order drives
  what the menu shows). Newest added go to the front. No filenames in the UI.
* SauceEditor  — edit each sauce's saved text prompt.
"""

import os

from PySide6 import QtCore, QtGui, QtWidgets

import store


def dark_qss(ui=1.0):
    def s(px):
        return int(round(px * ui))
    return f"""
QWidget {{ background:#1e1f24; color:#e7e9ee;
           font-family:'Segoe UI', sans-serif; font-size:{s(13)}px; }}
QLabel#title {{ font-size:{s(19)}px; font-weight:600; color:#f3f5f9; }}
QLabel#hint  {{ color:#8b909b; font-size:{s(12)}px; }}
QPushButton {{ background:#2c2f37; border:1px solid #3a3e48;
               border-radius:{s(9)}px; padding:{s(8)}px {s(16)}px; color:#e7e9ee; }}
QPushButton:hover {{ background:#383c46; }}
QPushButton:pressed {{ background:#43485a; }}
QPushButton#primary {{ background:#3b5bdb; border-color:#4c6ef5; }}
QPushButton#primary:hover {{ background:#4c6ef5; }}
QPushButton#danger:hover {{ background:#5a2730; border-color:#7a3340; }}
QListWidget {{ background:#15161a; border:1px solid #2a2d35;
               border-radius:{s(12)}px; padding:{s(8)}px; outline:none; }}
QListWidget::item {{ color:#c8cdd6; padding:{s(6)}px; border-radius:{s(10)}px; }}
QListWidget::item:selected {{ background:#243049;
               border:1px solid #4c6ef5; color:#ffffff; }}
QLineEdit, QTextEdit {{ background:#15161a; border:1px solid #2a2d35;
               border-radius:{s(8)}px; padding:{s(6)}px; color:#e7e9ee;
               selection-background-color:#3b5bdb; }}
QScrollBar:vertical {{ background:transparent; width:{s(10)}px; margin:{s(4)}px; }}
QScrollBar::handle:vertical {{ background:#3a3e48; border-radius:{s(5)}px;
               min-height:{s(30)}px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
"""


def _ui_scale():
    scr = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
    if scr is None:
        scr = QtGui.QGuiApplication.primaryScreen()
    if scr is None:
        return 1.0
    return max(1.0, scr.logicalDotsPerInch() / 96.0)


class _Window(QtWidgets.QWidget):
    """Shared dark-window chrome."""

    closed = QtCore.Signal()

    def __init__(self, title, subtitle, size=(760, 560)):
        super().__init__()
        self.ui = _ui_scale()
        self.setWindowTitle(f"Companion — {title}")
        self.setStyleSheet(dark_qss(self.ui))
        self.resize(int(size[0] * self.ui), int(size[1] * self.ui))
        self.setMinimumSize(int(460 * self.ui), int(360 * self.ui))

        m = int(16 * self.ui)
        self.root = QtWidgets.QVBoxLayout(self)
        self.root.setContentsMargins(m + 2, m, m + 2, m)
        self.root.setSpacing(int(12 * self.ui))

        header = QtWidgets.QVBoxLayout()
        header.setSpacing(2)
        lbl = QtWidgets.QLabel(title)
        lbl.setObjectName("title")
        sub = QtWidgets.QLabel(subtitle)
        sub.setObjectName("hint")
        header.addWidget(lbl)
        header.addWidget(sub)
        self.root.addLayout(header)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def open_centered(self):
        screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2,
                  geo.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()


class AssetList(QtWidgets.QListWidget):
    """Icon grid. Re-order by dragging a thumbnail with the mouse (done fully
    manually — Qt's IconMode drag-drop is unreliable). Still accepts dropped
    files from Explorer/Chrome to add (DropOnly)."""

    filesDropped = QtCore.Signal(list)
    reordered = QtCore.Signal()
    deleteRequested = QtCore.Signal()

    def __init__(self, thumb):
        super().__init__()
        self.setViewMode(QtWidgets.QListWidget.IconMode)
        self.setIconSize(QtCore.QSize(thumb, thumb))
        self.setGridSize(QtCore.QSize(thumb + 22, thumb + 22))
        self.setResizeMode(QtWidgets.QListWidget.Adjust)
        self.setMovement(QtWidgets.QListWidget.Static)
        self.setFlow(QtWidgets.QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setSpacing(int(thumb * 0.08))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # We do reordering ourselves with the mouse, so Qt's own item drag is
        # OFF. DropOnly still lets us catch external file drops to add.
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self._press_row = -1
        self._moved = False

    @staticmethod
    def _pt(event):
        try:
            return event.position().toPoint()
        except AttributeError:
            return event.pos()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Delete and self.selectedItems():
            self.deleteRequested.emit()
            return
        super().keyPressEvent(event)

    # ----- manual mouse reorder ------------------------------------------- #
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press_row = self.indexAt(self._pt(event)).row()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & QtCore.Qt.LeftButton) and self._press_row >= 0:
            idx = self.indexAt(self._pt(event))
            target = idx.row()
            if target >= 0 and target != self._press_row:
                it = self.takeItem(self._press_row)
                self.insertItem(target, it)
                self.setCurrentItem(it)
                it.setSelected(True)
                self._press_row = target
                self._moved = True
            return                      # don't let the base view rubber-band
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        moved = self._moved
        self._press_row = -1
        self._moved = False
        super().mouseReleaseEvent(event)
        if moved:
            self.reordered.emit()

    # ----- external file drops (add) -------------------------------------- #
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()
                     if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
                event.acceptProposedAction()


class GalleryEditor(_Window):
    THUMB = 132

    def __init__(self, kind, title, allow_video=False):
        sub = ("Drag files in / press +  ·  drag thumbnails to re-order  ·  "
               "newest first" + ("  ·  images & videos" if allow_video else ""))
        super().__init__(title, sub)
        self.kind = kind
        self.allow_video = allow_video
        self.thumb = int(self.THUMB * self.ui)
        self.setAcceptDrops(True)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(int(8 * self.ui))
        add_btn = QtWidgets.QPushButton("  +  Add")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.add_dialog)
        del_btn = QtWidgets.QPushButton("Delete selected")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_selected)
        self.count_lbl = QtWidgets.QLabel("")
        self.count_lbl.setObjectName("hint")
        bar.addWidget(add_btn)
        bar.addWidget(del_btn)
        bar.addStretch(1)
        bar.addWidget(self.count_lbl)
        self.root.addLayout(bar)

        self.list = AssetList(self.thumb)
        self.list.filesDropped.connect(self._add_paths)
        self.list.reordered.connect(self._persist_order)
        self.list.deleteRequested.connect(self.delete_selected)
        self.root.addWidget(self.list, 1)

        self._empty = QtWidgets.QLabel(
            "Nothing here yet.\nDrag files in, or press “+ Add”.")
        self._empty.setAlignment(QtCore.Qt.AlignCenter)
        self._empty.setObjectName("hint")
        self.root.addWidget(self._empty)

        self.refresh()

    # ----- data ----------------------------------------------------------- #
    def refresh(self):
        self.list.clear()
        paths = store.list_items(self.kind)
        for path in paths:
            item = QtWidgets.QListWidgetItem("")        # no filename in the UI
            item.setIcon(QtGui.QIcon(self._thumb(path)))
            item.setData(QtCore.Qt.UserRole, path)
            item.setToolTip(os.path.basename(path))
            item.setSizeHint(QtCore.QSize(self.thumb + 16, self.thumb + 16))
            self.list.addItem(item)
        self.count_lbl.setText(f"{len(paths)} item(s)")
        self._empty.setVisible(not paths)
        self.list.setVisible(bool(paths))

    def _thumb(self, path):
        d = self.thumb
        canvas = QtGui.QPixmap(d, d)
        canvas.fill(QtGui.QColor(20, 21, 26))
        src = store.load_pixmap(path)
        if not src.isNull():
            scaled = src.scaled(d, d, QtCore.Qt.KeepAspectRatio,
                                QtCore.Qt.SmoothTransformation)
            p = QtGui.QPainter(canvas)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.drawPixmap(int((d - scaled.width()) / 2),
                         int((d - scaled.height()) / 2), scaled)
            if store.is_video(path):
                p.setBrush(QtGui.QColor(0, 0, 0, 120))
                p.setPen(QtCore.Qt.NoPen)
                p.drawEllipse(QtCore.QPointF(d / 2, d / 2), d * 0.16, d * 0.16)
                p.setBrush(QtGui.QColor(255, 255, 255, 230))
                r = d * 0.08
                p.drawPolygon(QtGui.QPolygonF([
                    QtCore.QPointF(d / 2 - r * 0.5, d / 2 - r),
                    QtCore.QPointF(d / 2 - r * 0.5, d / 2 + r),
                    QtCore.QPointF(d / 2 + r, d / 2)]))
            p.end()
        return canvas

    # ----- actions -------------------------------------------------------- #
    def add_dialog(self):
        if self.kind == "media":
            filt = "All files (*)"          # Drag & Dropper holds any file
        else:
            filt = "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add files", "", filt)
        self._add_paths(paths)

    def _add_paths(self, paths):
        if paths:
            store.add_files(self.kind, paths)
            self.refresh()

    def delete_selected(self):
        paths = [it.data(QtCore.Qt.UserRole) for it in self.list.selectedItems()]
        if paths:
            store.delete(paths)
            self.refresh()

    def _persist_order(self):
        order = [self.list.item(i).data(QtCore.Qt.UserRole)
                 for i in range(self.list.count())]
        store.set_order(self.kind, order)

    # ----- window-level drop (covers the empty state) --------------------- #
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        self._add_paths(paths)
        if paths:
            event.acceptProposedAction()


class SauceEditor(_Window):
    """Edit sauces' prompts and order. Drag names to re-order (that's the menu
    order too — first 6 show in the circle). No Save button — it always saves;
    just close the window to go back to the companion."""

    def __init__(self):
        super().__init__("Sauce Editor",
                         "Drag to re-order · first 6 show in the menu · "
                         "edits save automatically",
                         size=(820, 560))
        self._loading = False

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(int(12 * self.ui))
        self.root.addLayout(body, 1)

        # left: re-orderable sauce names + add/delete
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(int(8 * self.ui))
        self.list = QtWidgets.QListWidget()
        self.list.setFixedWidth(int(240 * self.ui))
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.list.currentRowChanged.connect(self._on_row)
        self.list.model().rowsMoved.connect(self._persist)
        self.list.installEventFilter(self)       # Delete key removes a sauce
        left.addWidget(self.list, 1)
        lb = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("+ Add")
        add.setObjectName("primary")
        add.clicked.connect(self._add)
        rem = QtWidgets.QPushButton("Delete")
        rem.setObjectName("danger")
        rem.clicked.connect(self._delete)
        lb.addWidget(add)
        lb.addWidget(rem)
        left.addLayout(lb)
        body.addLayout(left)

        # right: name + prompt (live-editing, no save button)
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(int(8 * self.ui))
        right.addWidget(self._hint("Name"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.textChanged.connect(self._on_name_changed)
        right.addWidget(self.name_edit)
        right.addWidget(self._hint("Prompt"))
        self.prompt_edit = QtWidgets.QTextEdit()
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        right.addWidget(self.prompt_edit, 1)
        body.addLayout(right, 1)

        for s in store.load_sauces():
            self.list.addItem(self._make_item(dict(s)))
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if (obj is self.list and event.type() == QtCore.QEvent.KeyPress
                and event.key() == QtCore.Qt.Key_Delete
                and self.list.currentRow() >= 0):
            self._delete()
            return True
        return super().eventFilter(obj, event)

    def _hint(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("hint")
        return lbl

    def _make_item(self, d):
        it = QtWidgets.QListWidgetItem("🧪  " + d["name"])
        it.setData(QtCore.Qt.UserRole, d)
        return it

    def _on_row(self, row):
        it = self.list.item(row) if row >= 0 else None
        d = it.data(QtCore.Qt.UserRole) if it else None
        self._loading = True
        self.name_edit.setText(d["name"] if d else "")
        self.prompt_edit.setPlainText(d["prompt"] if d else "")
        self._loading = False

    def _on_name_changed(self, text):
        if self._loading:
            return
        it = self.list.currentItem()
        if it:
            d = dict(it.data(QtCore.Qt.UserRole))   # data() returns a copy
            d["name"] = text or "Untitled"
            it.setData(QtCore.Qt.UserRole, d)        # ...so store it back
            it.setText("🧪  " + d["name"])

    def _on_prompt_changed(self):
        if self._loading:
            return
        it = self.list.currentItem()
        if it:
            d = dict(it.data(QtCore.Qt.UserRole))
            d["prompt"] = self.prompt_edit.toPlainText()
            it.setData(QtCore.Qt.UserRole, d)

    def _add(self):
        self.list.insertItem(0, self._make_item({"name": "New sauce", "prompt": ""}))
        self.list.setCurrentRow(0)
        self.name_edit.setFocus()
        self._persist()

    def _delete(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self._persist()

    def _persist(self, *args):
        sauces = [self.list.item(i).data(QtCore.Qt.UserRole)
                  for i in range(self.list.count())]
        store.save_sauces(sauces)

    def closeEvent(self, event):
        self._persist()
        super().closeEvent(event)
