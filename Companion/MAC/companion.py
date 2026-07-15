"""
Companion — a fun Win11 desktop "flying thing" that follows your mouse.

Controls
--------
  Alt , Alt   (double-tap quickly)        -> wake / sleep the companion
  Left-click + HOLD on the companion      -> open the radial menu (full circle)
        * quick flick to an option + RELEASE -> picks that section's DEFAULT
          (first) item  (e.g. Sauce -> "Image sauce", Character -> 1st char)
        * or PAUSE on an option -> its submenu replaces the ring (full circle);
          glide to a choice and RELEASE to pick it. Pull back to the centre to
          go back a level.
  1 / 2 / 3 / 4  (while the menu is open)  -> pick that section's default item
  Right-click the companion               -> it "dies" and goes to sleep
  Right-click a carried image             -> drop / dismiss it
  Ctrl+Alt+Q                              -> quit

Only one instance runs at a time (single-instance mutex).
"""

import os
import re
import sys
import math
import time
import base64
import random
import ctypes
import threading
from urllib.parse import urlsplit, unquote_to_bytes

IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"

if IS_WINDOWS:
    import winreg
    from ctypes import wintypes
    # Run in pure physical pixels so a multi-monitor overlay shares ONE
    # contiguous coordinate space. Fractional per-monitor DPI scaling would
    # give Qt a gapped logical space and misalign the companion on some
    # monitors. Must happen before QApplication is created.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtNetwork
except Exception:
    QtNetwork = None

import store
import editors
import muse
import sfx as sfx_mod

try:
    from pynput import keyboard as pynput_keyboard
except Exception:  # pragma: no cover
    pynput_keyboard = None


# --------------------------------------------------------------------------- #
#  Tunables
# --------------------------------------------------------------------------- #
FPS = 120
REST_GAP = 96.0
HIT_RADIUS = 60.0
CLICK_FREEZE_RADIUS = 64.0
APPROACH_RADIUS = 240.0
FAST_SPEED = 1500.0
SPRING_K = 90.0
SPRING_D = 15.0
DOUBLE_TAP_SECONDS = 0.40

BODY_R = 23.0

# radial menu (everything is a full circle around the companion)
MENU_RADIUS = 120.0          # primary ring
SUB_RADIUS = 162.0           # submenu ring (bigger, roomier petals)
MENU_DEADZONE = 36.0
DWELL_OPEN = 0.22            # pause on a primary this long to open its submenu
SUB_MAX_ASSETS = 5           # newest N assets shown (+ editor = 6 petals max)
SUB_MAX_SAUCES = 6           # first 6 sauces show in the circle (+ editor)

# mood
IDLE_SPEED = 14.0             # px/s below this counts as "not moving"
SAD_DELAY = 5.0              # seconds idle & untouched before it droops
SAD_RAMP = 2.5
IDLE_SLEEP_SECONDS = 300.0   # no engagement this long -> fade away (like Alt-Alt)

# death
DEATH_DURATION = 0.95
GRAVITY = 1700.0

# carried item
CARRY_SIZE = 92.0

# drag-a-file-onto-the-companion
DRAG_DWELL = 0.32            # hold a dragged file over it this long -> menu opens

# middle-click "surprise me" idea generator + jiggle-think animation
THINK_MIN_DUR = 0.8         # short jiggle, then the (local) idea drops instantly
THINK_MAX_WAIT = 3.0        # safety cap if even local generation stalls
JIGGLE_AMP = 5.0            # design px of think-wobble

# "shake it" easter egg — deliberately hard so it never fires by accident
SHAKE_VY = 420.0            # design px/s vertical speed counting as a shake
SHAKE_FLIPS = 12           # up/down reversals (~6 full up-down-up-down) within...
SHAKE_WINDOW = 1.6        # ...this window
SHAKE_COOLDOWN = 3.0
SURPRISE_DUR = 1.1
POOP_GRAVITY = 900.0
POOP_LIFE = 1.7

# --------------------------------------------------------------------------- #
#  Colour palettes  (chosen from the tray / hidden-icons menu, persisted)
#
#  Each palette: glow, body_hi, body_lo, wing, accent. The COL_* names below are
#  the *active* colours; set_palette() rebinds them and every painter reads them
#  live, so switching is instant. PALETTE_ORDER controls the menu order.
# --------------------------------------------------------------------------- #
# Palettes are colour schemes drawn from famous paintings — each pairs a body
# colour family with a contrasting accent ("pop", used for wings/glow and the
# menu highlight), like the blue+pink default.
PALETTES = {
    # the original — blue body + pink pop
    "Default":       {"glow": (120, 220, 255), "body_hi": (190, 245, 255),
                      "body_lo": (70, 150, 235), "wing": (190, 235, 255),
                      "accent": (255, 150, 230)},
    # aurora night — deep navy body + neon green wings/glow/pop
    "Starry Night":  {"glow": (120, 235, 150), "body_hi": (104, 122, 168),
                      "body_lo": (30, 40, 70),  "wing": (96, 240, 112),
                      "accent": (110, 245, 132)},
    # Hokusai, "The Great Wave" — Prussian teal + warm sand sky
    "Great Wave":    {"glow": (214, 236, 236), "body_hi": (176, 222, 228),
                      "body_lo": (22, 92, 120),  "wing": (120, 190, 200),
                      "accent": (224, 196, 138)},
    # Monet, "Water Lilies" — soft teal water + rose blooms
    "Water Lilies":  {"glow": (255, 190, 205), "body_hi": (200, 232, 222),
                      "body_lo": (66, 146, 142), "wing": (150, 198, 188),
                      "accent": (255, 124, 168)},
    # Klimt, "The Kiss" — gold leaf + emerald
    "Klimt Gold":    {"glow": (255, 216, 130), "body_hi": (250, 230, 172),
                      "body_lo": (188, 144, 42), "wing": (226, 190, 112),
                      "accent": (44, 160, 134)},
    # Rothko — deep crimson field + burnt orange
    "Rothko":        {"glow": (255, 150, 90),  "body_hi": (242, 156, 116),
                      "body_lo": (162, 42, 46),  "wing": (214, 104, 74),
                      "accent": (255, 162, 52)},
}
PALETTE_ORDER = ["Default", "Starry Night", "Great Wave",
                 "Water Lilies", "Klimt Gold", "Rothko"]

# active colours (filled in by set_palette below)
COL_GLOW = COL_BODY_HI = COL_BODY_LO = COL_WING = COL_ACCENT = COL_BODY_EDGE = None
COL_FACE = COL_BROW = None
ACTIVE_PALETTE = "Default"


def _luma(c):
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def set_palette(name):
    """Rebind the active COL_* colours to a named palette (default if unknown)."""
    global COL_GLOW, COL_BODY_HI, COL_BODY_LO, COL_WING, COL_ACCENT, COL_BODY_EDGE
    global COL_FACE, COL_BROW, ACTIVE_PALETTE
    if name not in PALETTES:
        name = "Default"
    pal = PALETTES[name]
    COL_GLOW = QtGui.QColor(*pal["glow"])
    COL_BODY_HI = QtGui.QColor(*pal["body_hi"])
    COL_BODY_LO = QtGui.QColor(*pal["body_lo"])
    COL_WING = QtGui.QColor(*pal["wing"])
    COL_ACCENT = QtGui.QColor(*pal["accent"])
    # the orb's outer rim — a darker shade of its own body colour (was a fixed
    # blue, which muddied non-blue palettes). Optional "edge" key overrides it.
    COL_BODY_EDGE = (QtGui.QColor(*pal["edge"]) if "edge" in pal
                     else COL_BODY_LO.darker(160))
    # face ink (mouth + eyebrows): keep the dark blue on light bodies, but flip
    # to a light tint on dark ones so the features stay visible. Judge by the
    # colour roughly *behind* the face (a blend toward body_lo from body_hi).
    face_bg = QtGui.QColor(
        int(COL_BODY_HI.red() + (COL_BODY_LO.red() - COL_BODY_HI.red()) * 0.6),
        int(COL_BODY_HI.green() + (COL_BODY_LO.green() - COL_BODY_HI.green()) * 0.6),
        int(COL_BODY_HI.blue() + (COL_BODY_LO.blue() - COL_BODY_HI.blue()) * 0.6))
    if _luma(face_bg) < 110:
        COL_FACE = QtGui.QColor(228, 236, 250)
        COL_BROW = QtGui.QColor(198, 212, 242)
    else:
        COL_FACE = QtGui.QColor(35, 60, 110)
        COL_BROW = QtGui.QColor(60, 90, 150)
    ACTIVE_PALETTE = name


set_palette("Default")

PRIMARY = [
    ("sauce", "Sauce", "1"),
    ("character", "Character", "2"),
    ("location", "Location", "3"),
    ("media", "Drag & Dropper", "4"),
]
KIND_OF = {"character": "characters", "location": "locations", "media": "media"}
EDITOR_LABEL = {
    "sauce": "Sauce editor",
    "character": "Character editor",
    "location": "Location editor",
    "media": "Media editor",
}


# --------------------------------------------------------------------------- #
#  Platform-specific: click-through, idle time, caret detection, paste
# --------------------------------------------------------------------------- #
if IS_WINDOWS:
    GWL_EXSTYLE       = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED     = 0x00080000
    WS_EX_TOOLWINDOW  = 0x00000080
    WS_EX_NOACTIVATE  = 0x08000000

    _user32   = ctypes.windll.user32
    _LONG_PTR = ctypes.c_ssize_t
    if hasattr(_user32, "GetWindowLongPtrW"):
        _get_style = _user32.GetWindowLongPtrW
        _set_style = _user32.SetWindowLongPtrW
    else:
        _get_style = _user32.GetWindowLongW
        _set_style = _user32.SetWindowLongW
    _get_style.restype  = _LONG_PTR
    _get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_style.restype  = _LONG_PTR
    _set_style.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]

    def _apply_base_ex_styles(hwnd):
        s = _get_style(hwnd, GWL_EXSTYLE)
        s |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
        _set_style(hwnd, GWL_EXSTYLE, s)

    def _set_click_through(hwnd, on):
        s = _get_style(hwnd, GWL_EXSTYLE)
        s = (s | WS_EX_TRANSPARENT) if on else (s & ~WS_EX_TRANSPARENT)
        _set_style(hwnd, GWL_EXSTYLE, s)

    # screensaver-style idle
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    _user32.GetLastInputInfo.restype  = wintypes.BOOL
    _kernel32 = ctypes.windll.kernel32
    _kernel32.GetTickCount.restype = wintypes.DWORD

    def _system_idle_seconds():
        """Seconds since the last system-wide keyboard or mouse input."""
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not _user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        tick = _kernel32.GetTickCount()
        return ((tick - lii.dwTime) & 0xFFFFFFFF) / 1000.0

    # caret detection + paste
    class _RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class _GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                    ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                    ("rcCaret", _RECT)]

    GUI_CARETBLINKING = 0x00000001
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetGUIThreadInfo.argtypes   = [wintypes.DWORD,
                                           ctypes.POINTER(_GUITHREADINFO)]
    _user32.GetGUIThreadInfo.restype    = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    _user32.GetWindowThreadProcessId.restype  = wintypes.DWORD

    def _has_text_caret():
        try:
            fg = _user32.GetForegroundWindow()
            if not fg:
                return False
            tid = _user32.GetWindowThreadProcessId(fg, None)
            gui = _GUITHREADINFO()
            gui.cbSize = ctypes.sizeof(_GUITHREADINFO)
            if not _user32.GetGUIThreadInfo(tid, ctypes.byref(gui)):
                return False
            if gui.hwndCaret:
                return True
            return bool(gui.flags & GUI_CARETBLINKING)
        except Exception:
            return False

    def _uia_editable():
        try:
            import uiautomation as auto
        except Exception:
            return None
        try:
            ctrl = auto.GetFocusedControl()
        except Exception:
            return None
        if not ctrl:
            return False
        try:
            ct = ctrl.ControlTypeName
        except Exception:
            return False
        try:
            if ct in ("EditControl", "ComboBoxControl"):
                return True
            if ct == "DocumentControl":
                try:
                    vp = ctrl.GetValuePattern()
                    if vp is not None:
                        return not bool(vp.IsReadOnly)
                except Exception:
                    pass
                return False
        except Exception:
            return False
        return False

    def _has_paste_target():
        if _has_text_caret():
            return True
        return bool(_uia_editable())

    def _send_paste():
        VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002
        try:
            _user32.keybd_event(VK_CONTROL, 0, 0, 0)
            _user32.keybd_event(VK_V, 0, 0, 0)
            _user32.keybd_event(VK_V, 0, KEYUP, 0)
            _user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)
        except Exception as exc:
            print(f"[companion] paste failed: {exc}")

else:
    # ---------------------------------------------------------------------- #
    #  macOS (and Linux) platform helpers — ctypes into system frameworks
    # ---------------------------------------------------------------------- #
    _mac_libobjc = None

    def _mac_objc():
        global _mac_libobjc
        if _mac_libobjc is None:
            _mac_libobjc = ctypes.cdll.LoadLibrary("libobjc.dylib")
            _mac_libobjc.sel_registerName.restype  = ctypes.c_void_p
            _mac_libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
        return _mac_libobjc

    # Not used but kept so callers that pass hwnd don't crash.
    def _apply_base_ex_styles(_hwnd):
        pass

    def _set_click_through(_hwnd, _on):
        pass

    def _system_idle_seconds():
        """Seconds since last HID input via CoreGraphics on macOS."""
        try:
            CG = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            fn = CG.CGEventSourceSecondsSinceLastEventType
            fn.restype  = ctypes.c_double
            fn.argtypes = [ctypes.c_int, ctypes.c_uint32]
            # kCGEventSourceStateHIDSystemState=1, kCGAnyInputEventType=0xFFFFFFFF
            return fn(1, 0xFFFFFFFF)
        except Exception:
            return 0.0

    def _has_paste_target():
        """Check if the frontmost app's focused UI element accepts text input."""
        try:
            import subprocess
            script = (
                'tell application "System Events"\n'
                '  set fe to focused UI element of '
                '(first process whose frontmost is true)\n'
                '  return role of fe\n'
                'end tell'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=0.5)
            role = result.stdout.strip()
            return role in ("AXTextField", "AXTextArea", "AXComboBox",
                            "AXWebArea", "AXScrollArea")
        except Exception:
            return False

    def _send_paste():
        """Simulate Cmd+V via osascript on macOS."""
        try:
            import subprocess
            subprocess.Popen(
                ["osascript", "-e",
                 'tell application "System Events" to keystroke "v" '
                 'using command down'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            print(f"[companion] mac paste failed: {exc}")


# --------------------------------------------------------------------------- #
#  Global hotkeys
# --------------------------------------------------------------------------- #
class Hotkeys(QtCore.QObject):
    toggle = QtCore.Signal()
    digit = QtCore.Signal(int)
    quit = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._alt_down = False
        self._ctrl_down = False
        self._last_alt = 0.0
        self._listener = None

    def start(self):
        if pynput_keyboard is None:
            print("[companion] pynput unavailable - global hotkeys disabled.")
            return
        self._listener = pynput_keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()

    @staticmethod
    def _is_alt(k):
        K = pynput_keyboard.Key
        return k in (K.alt_l, K.alt_r, K.alt_gr, K.alt)

    @staticmethod
    def _is_ctrl(k):
        K = pynput_keyboard.Key
        return k in (K.ctrl_l, K.ctrl_r, K.ctrl)

    def _on_press(self, key):
        if self._is_ctrl(key):
            self._ctrl_down = True
            return
        if self._is_alt(key):
            if not self._alt_down:
                self._alt_down = True
                now = time.monotonic()
                if now - self._last_alt < DOUBLE_TAP_SECONDS:
                    self._last_alt = 0.0
                    self.toggle.emit()
                else:
                    self._last_alt = now
            return
        self._last_alt = 0.0
        ch = getattr(key, "char", None)
        if ch and ch in "1234":
            self.digit.emit(int(ch))
        if ch and ch in ("q", "Q") and self._ctrl_down and self._alt_down:
            self.quit.emit()

    def _on_release(self, key):
        if self._is_alt(key):
            self._alt_down = False
        elif self._is_ctrl(key):
            self._ctrl_down = False


# --------------------------------------------------------------------------- #
#  Overlay
# --------------------------------------------------------------------------- #
class Companion(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Companion")
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint
                            | QtCore.Qt.WindowStaysOnTopHint
                            | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_AlwaysStackOnTop, True)

        geo = self._union_geometry()
        self.setGeometry(geo)
        self.ox, self.oy = geo.x(), geo.y()

        # per-monitor visual scale (we run in physical px; this restores the
        # right on-screen size). Applied as a single painter.scale + cursor
        # division, so all the physics/menu constants stay in "design" px.
        self.s = 1.0
        self._refresh_scale()

        # core state
        self.active = False
        self.suppressed = False          # hidden while an editor window is open
        self.appear = 0.0
        self.interactive = False

        self.cx = self.width() * 0.5
        self.cy = self.height() * 0.5
        self.cvx = self.cvy = 0.0
        self.cspeed = 0.0

        self.x = self.cx
        self.y = self.cy
        self.vx = self.vy = 0.0

        self.t = 0.0
        self.flap_phase = 0.0
        self.blink_t = 1.5
        self.blink = 0.0
        self.sad = 0.0
        self.last_activity = 0.0

        # death
        self.dying = False
        self.death = 0.0

        self.trail = []

        # menu state (drill-down full-circle)
        self.menu_open = False
        self.menu_cx = self.menu_cy = 0.0
        self.level = 0                   # 0 = primaries, 1 = a submenu
        self.active_primary = -1
        self.sub_items = []
        self.primary_hover = -1
        self.sub_hover = -1
        self.primary_dwell = 0.0
        self.ring_t = 0.0                # per-level pop-in ease
        self._last_hover_sig = (None, -2)  # for the menu-cursor tick sound

        # carried item
        self.carry = None
        self.carry_appear = 0.0

        # drag-a-file-onto-the-companion
        self.dragging = False
        self.drag_urls = []
        self.drag_dwell = 0.0
        self.drag_menu = False

        # "shake it" easter egg
        self._vy_sign = 0
        self._vy_flips = []
        self._last_poop = -100.0
        self.surprise_t = -100.0
        self.poops = []                  # [{x,y,vx,vy,t,rot,spin}]

        # toast
        self.toast_text = ""
        self.toast_t = -10.0

        # middle-click "surprise me" idea generator
        self.thinking = False
        self.think_t = 0.0
        self._idea_text = None
        self._idea_done = False
        self.idea_show_text = ""
        self.idea_show_t = -100.0
        self._bubble_on = False          # bubble stays up until "touched"
        self._bubble_armed = False       # armed once the cursor leaves it
        self._bubble_dismiss_t = -1.0    # >=0 while fading out

        self.sfx = sfx_mod.Sfx(store.sfx_dir())
        self.setAcceptDrops(True)
        self._net = None                 # QNetworkAccessManager, lazily created

        self.windows = {}                # editor windows, kept & reused
        self._thumb_cache = {}
        self._hwnd = None
        self._last = time.monotonic()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ #
    def _union_geometry(self):
        rect = QtCore.QRect()
        for screen in QtWidgets.QApplication.screens():
            rect = rect.united(screen.geometry())
        return rect

    def _refresh_scale(self, pt=None):
        if IS_MAC:
            # Qt handles HiDPI (Retina) natively on macOS — no manual scaling.
            self.s = 1.0
            return
        if pt is None:
            pt = QtGui.QCursor.pos()
        scr = QtGui.QGuiApplication.screenAt(pt) or QtGui.QGuiApplication.primaryScreen()
        if scr is not None:
            self.s = max(1.0, scr.logicalDotsPerInch() / 96.0)

    def showEvent(self, event):
        super().showEvent(event)
        if self._hwnd is None:
            if IS_WINDOWS:
                self._hwnd = int(self.winId())
                _apply_base_ex_styles(self._hwnd)
            else:
                self._hwnd = True          # just marks "initialised" on Mac
                self._mac_set_click_through(True)
        self.timer.start(max(1, int(1000 / FPS)))

    def _mac_set_click_through(self, on):
        """Toggle NSWindow.ignoresMouseEvents via the ObjC runtime (no PyObjC needed)."""
        try:
            lib = _mac_objc()
            lib.objc_msgSend.restype  = ctypes.c_void_p
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            ns_view   = ctypes.c_void_p(int(self.winId()))
            sel_win   = lib.sel_registerName(b"window")
            ns_window = lib.objc_msgSend(ns_view, sel_win)
            if not ns_window:
                return
            sel_ignore = lib.sel_registerName(b"setIgnoresMouseEvents:")
            # BOOL argument — use a separate CFUNCTYPE so the ABI is right
            _send = ctypes.CFUNCTYPE(
                ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool,
            )(ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value)
            _send(ns_window, sel_ignore, bool(on))
        except Exception as exc:
            print(f"[companion] mac click-through failed: {exc}")

    # ------------------------------------------------------------------ #
    #  Activation
    # ------------------------------------------------------------------ #
    def set_active(self, value):
        value = bool(value)
        if value == self.active:
            return
        self.active = value
        if value:
            self._refresh_scale()
            gp = QtGui.QCursor.pos()
            self.cx = (gp.x() - self.ox) / self.s
            self.cy = (gp.y() - self.oy) / self.s
            self.x, self.y = self.cx, self.cy - REST_GAP
            self.vx = self.vy = 0.0
            self.trail.clear()
            self.dying = False
            self.death = 0.0
            self.sad = 0.0
            self.last_activity = self.t
            self.raise_()
        else:
            self._reset_menu()
            self.carry = None
            self.thinking = False
            self._bubble_on = False
            self.idea_show_text = ""

    # ------------------------------------------------------------------ #
    #  Physics helper (shared by companion + carried item)
    # ------------------------------------------------------------------ #
    def _spring(self, x, y, vx, vy, dt, freeze_when_menu):
        dx, dy = x - self.cx, y - self.cy
        dist = math.hypot(dx, dy) or 0.0001
        approaching = (self.cvx * dx + self.cvy * dy) > 0
        freeze = (
            (freeze_when_menu and self.menu_open)
            or dist < CLICK_FREEZE_RADIUS
            or (self.cspeed > FAST_SPEED and dist < APPROACH_RADIUS and approaching)
        )
        if freeze:
            tx, ty = x, y
        elif dist > REST_GAP:
            tx = self.cx + dx / dist * REST_GAP
            ty = self.cy + dy / dist * REST_GAP
        else:
            tx, ty = x, y
        ax = (tx - x) * SPRING_K - vx * SPRING_D
        ay = (ty - y) * SPRING_K - vy * SPRING_D
        vx += ax * dt
        vy += ay * dt
        return x + vx * dt, y + vy * dt, vx, vy

    # ------------------------------------------------------------------ #
    #  Per-frame update
    # ------------------------------------------------------------------ #
    def _tick(self):
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        if dt <= 0:
            return
        dt = min(dt, 0.05)
        self.t += dt

        visible = self.active and not self.suppressed
        target_appear = 1.0 if visible else 0.0
        self.appear += (target_appear - self.appear) * min(1.0, dt * 9.0)
        if not visible and self.appear < 0.01:
            self.appear = 0.0
            if self.interactive:
                self._set_interactive(False)
            self.update()
            return

        # cursor (global physical -> local design px) + velocity
        gp = QtGui.QCursor.pos()
        self._refresh_scale(gp)
        ncx = (gp.x() - self.ox) / self.s
        ncy = (gp.y() - self.oy) / self.s
        self.cspeed = math.hypot(ncx - self.cx, ncy - self.cy) / dt
        self.cvx = (ncx - self.cx) / dt
        self.cvy = (ncy - self.cy) / dt
        self.cx, self.cy = ncx, ncy

        hover_comp = math.hypot(self.x - self.cx, self.y - self.cy) < HIT_RADIUS
        hover_carry = (self.carry is not None and
                       math.hypot(self.carry["x"] - self.cx,
                                  self.carry["y"] - self.cy) < HIT_RADIUS)
        moving = self.cspeed > IDLE_SPEED

        # death animation takes over physics
        if self.dying:
            self.death += dt / DEATH_DURATION
            self.vy += GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.death >= 1.0:
                self.death = 1.0
                self.dying = False
                self.set_active(False)
        else:
            self.x, self.y, self.vx, self.vy = self._spring(
                self.x, self.y, self.vx, self.vy, dt, freeze_when_menu=True)

        speed = math.hypot(self.vx, self.vy)

        # carried item physics
        if self.carry is not None:
            c = self.carry
            c["x"], c["y"], c["vx"], c["vy"] = self._spring(
                c["x"], c["y"], c["vx"], c["vy"], dt, freeze_when_menu=False)
            self.carry_appear += (1.0 - self.carry_appear) * min(1.0, dt * 9.0)
        else:
            self.carry_appear += (0.0 - self.carry_appear) * min(1.0, dt * 12.0)

        # wings / blink
        self.flap_phase += dt * (9.0 + min(speed, 1200.0) * 0.02)
        self.blink_t -= dt
        if self.blink_t <= 0:
            self.blink = 1.0
            self.blink_t = 2.2 + (self.t * 1.3 % 2.5)
        self.blink = max(0.0, self.blink - dt * 7.0)

        # "surprise me" think timer: jiggle for a bit, then drop the result once
        # the idea (and any AI refine) is ready — but never before THINK_MIN_DUR.
        if self.thinking:
            self.think_t += dt
            ready = self._idea_done or self.think_t >= THINK_MAX_WAIT
            if self.think_t >= THINK_MIN_DUR and ready and self._idea_text:
                self._deliver_idea()
            elif self.think_t >= THINK_MAX_WAIT and not self._idea_text:
                self.thinking = False        # generation failed; just stop

        # idea bubble stays up until "touched": it arms once the cursor leaves
        # the companion (it's on it right after the middle-click), then dismisses
        # when the cursor returns to touch it. Then a quick fade-out.
        if self._bubble_on:
            if self._bubble_dismiss_t >= 0:
                if self.t - self._bubble_dismiss_t > 0.4:
                    self._bubble_on = False
                    self.idea_show_text = ""
            elif not hover_comp:
                self._bubble_armed = True
            elif self._bubble_armed:
                self._dismiss_bubble()

        # mood: happy if moving / hovered / in a menu / carrying; sad only when
        # genuinely idle and untouched for a while.
        busy = (self.menu_open or self.carry is not None or self.dying
                or self.dragging or self.thinking)
        if moving or hover_comp or busy:
            self.last_activity = self.t
        idle = self.t - self.last_activity
        sad_target = 0.0
        if self.active and not self.suppressed and not busy:
            sad_target = max(0.0, min(1.0, (idle - SAD_DELAY) / SAD_RAMP))
        self.sad += (sad_target - self.sad) * min(1.0, dt * 4.0)

        # auto-sleep (screensaver-style): no keyboard OR mouse input anywhere for
        # 5 minutes -> fade away, like a double-tap Alt. Any input keeps it alive;
        # once asleep, call it back with Alt-Alt (or the tray icon).
        if (self.active and not self.suppressed and not busy
                and _system_idle_seconds() > IDLE_SLEEP_SECONDS):
            self._auto_sleep()
            return

        # trail
        if not self.trail or math.hypot(self.x - self.trail[-1][0],
                                        self.y - self.trail[-1][1]) > 4.0:
            self.trail.append((self.x, self.y, self.t))
        self.trail = [p for p in self.trail if p[2] > self.t - 0.55][-40:]

        # "shake it" easter egg: many fast vertical reversals -> surprised + poop
        if (self.active and not self.menu_open and not self.dying
                and not self.dragging):
            if abs(self.cvy) > SHAKE_VY:
                sign = 1 if self.cvy > 0 else -1
                if self._vy_sign and sign != self._vy_sign:
                    self._vy_flips.append(self.t)
                self._vy_sign = sign
            self._vy_flips = [f for f in self._vy_flips if f > self.t - SHAKE_WINDOW]
            if (len(self._vy_flips) >= SHAKE_FLIPS
                    and self.t - self._last_poop > SHAKE_COOLDOWN):
                self._trigger_poop()

        # poop particles
        if self.poops:
            for po in self.poops:
                po["vy"] += POOP_GRAVITY * dt
                po["x"] += po["vx"] * dt
                po["y"] += po["vy"] * dt
                po["rot"] += po["spin"] * dt
            self.poops = [po for po in self.poops
                          if self.t - po["t"] < POOP_LIFE]

        # drag-a-file-onto-the-companion: dwell over it -> open the menu so the
        # user can drop on Character / Location / Drag&Dropper
        if self.dragging:
            if hover_comp:
                self.drag_dwell += dt
                if not self.menu_open and self.drag_dwell > DRAG_DWELL:
                    self._open_menu()
                    self.drag_menu = True
            elif not self.menu_open:
                self.drag_dwell = 0.0

        # menu navigation
        if self.menu_open:
            self.ring_t += (1.0 - self.ring_t) * min(1.0, dt * 14.0)
            self._update_menu_nav(dt)
            # tick sound when the highlighted item changes
            idx = self.sub_hover if self.level == 1 else self.primary_hover
            sig = (self.level, idx)
            if idx >= 0 and sig != self._last_hover_sig:
                self.sfx.play("cursor")
            self._last_hover_sig = sig
        else:
            self._last_hover_sig = (None, -2)

        # click-through toggle
        want = ((hover_comp or hover_carry or self.menu_open or self.dragging)
                and self.appear > 0.5)
        if want != self.interactive:
            self._set_interactive(want)

        self.update()

    def _set_interactive(self, value):
        self.interactive = value
        if IS_WINDOWS and self._hwnd is not None:
            _set_click_through(self._hwnd, not value)
        elif IS_MAC:
            self._mac_set_click_through(not value)

    # ------------------------------------------------------------------ #
    #  Menu navigation (drill-down, full circle)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _nearest(ang, n):
        step = 360.0 / n
        return int(round((ang + 90.0) / step)) % n

    def _ring_pos(self, i, n, radius):
        a = math.radians(-90.0 + 360.0 / n * i)
        return (self.menu_cx + math.cos(a) * radius,
                self.menu_cy + math.sin(a) * radius)

    def _update_menu_nav(self, dt):
        dx, dy = self.cx - self.menu_cx, self.cy - self.menu_cy
        dist = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))

        if self.level == 0:
            if dist < MENU_DEADZONE:
                self.primary_hover = -1
                self.primary_dwell = 0.0
            else:
                i = self._nearest(ang, len(PRIMARY))
                if i != self.primary_hover:
                    self.primary_hover = i
                    self.primary_dwell = 0.0
                elif not self.dragging:        # while dragging a file, stay on
                    self.primary_dwell += dt   # the primary ring (pick a kind)
                    if self.primary_dwell >= DWELL_OPEN:
                        self._enter_submenu(i)
            self.sub_hover = -1
        else:
            if dist < MENU_DEADZONE:
                self.sub_hover = -1
                self._exit_submenu()
            else:
                self.sub_hover = self._nearest(ang, len(self.sub_items))

    def _enter_submenu(self, primary_index):
        self.level = 1
        self.active_primary = primary_index
        self.sub_items = self._build_submenu(PRIMARY[primary_index][0])
        self.sub_hover = -1
        self.primary_dwell = 0.0
        self.ring_t = 0.0

    def _exit_submenu(self):
        self.level = 0
        self.active_primary = -1
        self.sub_items = []
        self.sub_hover = -1
        self.primary_hover = -1
        self.primary_dwell = 0.0
        self.ring_t = 0.0

    def _build_submenu(self, pid):
        items = []
        if pid == "sauce":
            for s in store.load_sauces()[:SUB_MAX_SAUCES]:
                items.append({"type": "sauce", "label": s["name"],
                              "prompt": s["prompt"]})
        else:
            kind = KIND_OF[pid]
            for path in store.list_items(kind)[:SUB_MAX_ASSETS]:
                items.append({"type": "asset", "label": os.path.basename(path),
                              "path": path, "kind": kind})
        items.append({"type": "editor", "label": EDITOR_LABEL[pid], "id": pid})
        return items

    def _default_item(self, primary_index):
        """First real (asset/sauce) item of a section, or None if empty."""
        for item in self._build_submenu(PRIMARY[primary_index][0]):
            if item["type"] in ("asset", "sauce"):
                return item
        return None

    # ------------------------------------------------------------------ #
    #  Menu open / close / select
    # ------------------------------------------------------------------ #
    def _open_menu(self):
        self.menu_open = True
        self._dismiss_bubble()
        self.menu_cx, self.menu_cy = self.x, self.y
        self.level = 0
        self.active_primary = -1
        self.sub_items = []
        self.primary_hover = -1
        self.sub_hover = -1
        self.primary_dwell = 0.0
        self.ring_t = 0.0
        self.last_activity = self.t
        self._set_interactive(True)

    def _reset_menu(self):
        self.menu_open = False
        self.level = 0
        self.active_primary = -1
        self.sub_items = []
        self.primary_hover = -1
        self.sub_hover = -1
        self.primary_dwell = 0.0

    def _close_menu(self, select):
        if not self.menu_open:
            return
        chosen = None
        if select:
            if self.level == 1 and 0 <= self.sub_hover < len(self.sub_items):
                chosen = self.sub_items[self.sub_hover]
            elif self.level == 0 and self.primary_hover >= 0:
                chosen = self._default_item(self.primary_hover)
        self._reset_menu()
        if chosen:
            self._select(chosen)

    def _select(self, item):
        self.sfx.play("select")
        kind = item["type"]
        if kind == "editor":
            self._open_editor(item["id"])
        elif kind == "asset":
            self._start_carry(item["path"])
        elif kind == "sauce":
            self._apply_sauce(item)

    def _apply_sauce(self, item):
        prompt = item.get("prompt", "")
        name = item.get("label", "sauce")
        QtWidgets.QApplication.clipboard().setText(prompt)
        if _has_paste_target():
            # let the menu close & clipboard settle, then paste into the field
            QtCore.QTimer.singleShot(60, _send_paste)
            self.toast_text = f"Pasted: {name}"
        else:
            self.toast_text = f"Copied: {name}"
        self.toast_t = self.t
        print(f"[companion] sauce -> {self.toast_text}")

    # ------------------------------------------------------------------ #
    #  "Surprise me" idea generator (middle-click -> jiggle -> result)
    # ------------------------------------------------------------------ #
    def _start_thinking(self):
        if self.thinking or self.dying or self.menu_open or not self.active:
            return
        self.thinking = True
        self.think_t = 0.0
        self._dismiss_bubble()           # clear any previous idea bubble
        self.last_activity = self.t
        self.sfx.play("cursor")
        # generation is instant + built to be coherent (genre-matched setting,
        # relationship-matched action) — no AI / network. A short jiggle plays,
        # then the idea drops at THINK_MIN_DUR.
        try:
            self._idea_text = muse.generate()[0]
        except Exception as exc:
            print(f"[muse] generate failed: {exc}")
            self._idea_text = None
        self._idea_done = True

    def _show_bubble(self, text):
        """(Re)show the idea bubble — it then stays up until the companion is
        touched (cursor reaches it) or superseded."""
        self.idea_show_text = text
        self.idea_show_t = self.t
        self._bubble_on = True
        self._bubble_armed = False
        self._bubble_dismiss_t = -1.0

    def _dismiss_bubble(self):
        if self._bubble_on and self._bubble_dismiss_t < 0:
            self._bubble_dismiss_t = self.t      # begin a quick fade-out
            self._bubble_armed = False

    def _deliver_idea(self):
        self.thinking = False
        text = self._idea_text or "(the muse drew a blank)"
        self._show_bubble(text)
        QtWidgets.QApplication.clipboard().setText(text)
        if _has_paste_target():
            QtCore.QTimer.singleShot(60, _send_paste)
            self.toast_text = "✦ Idea pasted"
        else:
            self.toast_text = "✦ Idea copied"
        self.toast_t = self.t
        self.sfx.play("select")
        print(f"[companion] idea -> {text}")

    def _tray_surprise(self):
        if not self.active:
            self.set_active(True)
            QtCore.QTimer.singleShot(420, self._start_thinking)
        else:
            self._start_thinking()

    # ------------------------------------------------------------------ #
    #  Editors  (companion hides while one is open)
    # ------------------------------------------------------------------ #
    def _open_editor(self, pid):
        win = self.windows.get(pid)
        if win is None:
            if pid == "sauce":
                win = editors.SauceEditor()
            else:
                win = editors.GalleryEditor(
                    KIND_OF[pid], EDITOR_LABEL[pid].replace(" editor", "s"),
                    allow_video=(pid == "media"))
            win.closed.connect(self._on_editor_closed)
            self.windows[pid] = win
        if hasattr(win, "refresh"):
            win.refresh()
        self.carry = None
        self.suppressed = True           # hide the companion
        if self.interactive:
            self._set_interactive(False)
        win.open_centered()

    def _on_editor_closed(self):
        # Re-check shortly after; visibility settles after the close event.
        QtCore.QTimer.singleShot(60, self._check_editors)

    def _check_editors(self):
        if any(w.isVisible() for w in self.windows.values()):
            return
        if self.suppressed:
            self.suppressed = False
            self.last_activity = self.t      # comes back happy
            self.raise_()

    # ------------------------------------------------------------------ #
    #  Idle auto-sleep
    # ------------------------------------------------------------------ #
    def _auto_sleep(self):
        """Fade away after a long idle stretch — same as a double-tap Alt."""
        print("[companion] idle for "
              f"{IDLE_SLEEP_SECONDS:.0f}s — going to sleep.")
        self.sfx.play("poof")
        self.set_active(False)

    # ------------------------------------------------------------------ #
    #  Death
    # ------------------------------------------------------------------ #
    def _die(self):
        if self.dying:
            return
        self.sfx.play("death")
        self._reset_menu()
        self.carry = None
        self.thinking = False
        self._bubble_on = False
        self.idea_show_text = ""
        self.dying = True
        self.death = 0.0
        self.vx *= 0.2
        self.vy = -120.0                 # tiny hop before the fall

    # ------------------------------------------------------------------ #
    #  Carry + native file drag
    # ------------------------------------------------------------------ #
    def _start_carry(self, path):
        self._dismiss_bubble()
        self.carry = {"path": path, "pixmap": store.load_pixmap(path),
                      "x": self.x, "y": self.y, "vx": 0.0, "vy": 0.0}
        self.carry_appear = 0.0
        self.last_activity = self.t

    def _begin_native_drag(self):
        c = self.carry
        if c is None:
            return
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(c["path"])])
        drag.setMimeData(mime)
        pm = c["pixmap"]
        if not pm.isNull():
            d = int(CARRY_SIZE * self.s)
            thumb = pm.scaled(d, d, QtCore.Qt.KeepAspectRatio,
                              QtCore.Qt.SmoothTransformation)
            drag.setPixmap(thumb)
            drag.setHotSpot(QtCore.QPoint(thumb.width() // 2, thumb.height() // 2))
        result = drag.exec(QtCore.Qt.CopyAction | QtCore.Qt.MoveAction,
                           QtCore.Qt.CopyAction)
        if result != QtCore.Qt.IgnoreAction:
            self.carry = None
        self._last = time.monotonic()    # avoid a huge dt after the modal loop

    # ------------------------------------------------------------------ #
    #  "Shake it" easter egg
    # ------------------------------------------------------------------ #
    def _trigger_poop(self):
        self._last_poop = self.t
        self._vy_flips = []
        self.surprise_t = self.t
        for _ in range(random.randint(2, 3)):
            self.poops.append({
                "x": self.x + random.uniform(-6, 6),
                "y": self.y + BODY_R * 0.6,
                "vx": random.uniform(-50, 50),
                "vy": random.uniform(20, 90),
                "rot": random.uniform(-20, 20),
                "spin": random.uniform(-160, 160),
                "t": self.t,
            })
        self.sfx.play("poop")

    # ------------------------------------------------------------------ #
    #  Drag a file onto the companion
    # ------------------------------------------------------------------ #
    @staticmethod
    def _droppable(md):
        return md.hasUrls() or md.hasImage()

    def dragEnterEvent(self, event):
        if self.active and self._droppable(event.mimeData()):
            self.drag_urls = [u.toLocalFile() for u in event.mimeData().urls()
                              if u.isLocalFile()]
            self.dragging = True
            self.drag_dwell = 0.0
            self.drag_menu = False
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._droppable(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._end_drag()

    def dropEvent(self, event):
        pid = "media"
        if self.menu_open and self.level == 0 and self.primary_hover >= 0:
            pid = PRIMARY[self.primary_hover][0]
        self._drop_payload(pid, event.mimeData())
        event.acceptProposedAction()
        self._end_drag()

    KIND_NAMES = {"characters": "Characters", "locations": "Locations",
                  "media": "Drag & Drop"}

    def _drop_payload(self, pid, md):
        self._log_drop(md)
        if pid == "sauce":
            pid = "media"
        kind = KIND_OF.get(pid, "media")
        added = {}

        # 1) real local files (dragged from Explorer)
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        for p in paths:
            target = kind
            if kind in ("characters", "locations") and not store.is_image(p):
                target = "media"
            if store.add_files(target, [p]):
                added[target] = added.get(target, 0) + 1

        # 2) a raw bitmap (some browsers put CF_DIB on the drag)
        if not paths and md.hasImage():
            img = md.imageData()
            if isinstance(img, QtGui.QImage) and not img.isNull():
                if store.save_image(kind, img, self._drop_name(md)):
                    added[kind] = added.get(kind, 0) + 1

        if added:
            self._finalize_added(added)
            return

        # 3) no file/bitmap — a URL or data: URI (the common Chrome/web case)
        url = self._extract_url(md)
        if url:
            self.toast_text = "Fetching…"
            self.toast_t = self.t
            self._fetch_url(kind, url)
            return

        self._drop_fail("no file, bitmap, or URL in the drop")

    # ----- helpers for drops ---------------------------------------------- #
    @staticmethod
    def _drop_name(md):
        if md.hasUrls() and md.urls():
            n = os.path.basename(md.urls()[0].path())
            if n:
                return n
        if md.hasText():
            return os.path.basename(md.text().strip().split("?")[0]) or "image"
        return "image"

    def _extract_url(self, md):
        for u in md.urls():
            s = u.toString()
            if s.startswith(("http://", "https://", "data:")):
                return s
        if md.hasHtml():
            m = re.search(r'src\s*=\s*["\']([^"\']+)["\']', md.html(), re.I)
            if m and m.group(1).startswith(("http://", "https://", "data:")):
                return m.group(1)
        if md.hasText():
            t = md.text().strip().split()
            if t and t[0].startswith(("http://", "https://", "data:")):
                return t[0]
        return None

    @staticmethod
    def _ext_from_ct(ct):
        ct = (ct or "").split(";")[0].strip().lower()
        return {
            "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
            "image/webp": ".webp", "image/gif": ".gif", "image/bmp": ".bmp",
            "image/svg+xml": ".svg", "video/mp4": ".mp4", "video/webm": ".webm",
            "video/quicktime": ".mov",
        }.get(ct)

    def _fetch_url(self, kind, url):
        if url.startswith("data:"):
            try:
                header, _, payload = url.partition(",")
                meta = header[5:]
                ct = meta.split(";")[0]
                data = (base64.b64decode(payload) if ";base64" in meta
                        else unquote_to_bytes(payload))
                self._save_fetched(kind, data, "image",
                                   self._ext_from_ct(ct) or ".png", ct)
            except Exception as exc:
                self._drop_fail(f"data URI: {exc}")
            return
        if QtNetwork is None:
            self._drop_fail("QtNetwork unavailable")
            return
        try:
            if self._net is None:
                self._net = QtNetwork.QNetworkAccessManager(self)
            req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
            req.setHeader(QtNetwork.QNetworkRequest.UserAgentHeader,
                          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Companion")
            parts = urlsplit(url)
            if parts.scheme and parts.netloc:
                req.setRawHeader(b"Referer",
                                 f"{parts.scheme}://{parts.netloc}".encode())
            try:
                req.setAttribute(
                    QtNetwork.QNetworkRequest.RedirectPolicyAttribute,
                    QtNetwork.QNetworkRequest.NoLessSafeRedirectPolicy)
            except Exception:
                pass
            reply = self._net.get(req)
            reply.finished.connect(lambda: self._on_fetch(reply, kind, url))
        except Exception as exc:
            self._drop_fail(f"request error: {exc}")

    def _on_fetch(self, reply, kind, url):
        try:
            err = reply.error()
            data = bytes(reply.readAll())
            ct = reply.header(QtNetwork.QNetworkRequest.ContentTypeHeader) or ""
        finally:
            reply.deleteLater()
        if err != QtNetwork.QNetworkReply.NetworkError.NoError or not data:
            self._drop_fail(f"fetch failed ({int(err)}, {len(data)}B) {url[:80]}")
            return
        ext = (self._ext_from_ct(str(ct))
               or os.path.splitext(urlsplit(url).path)[1].lower() or ".png")
        self._save_fetched(kind, data, os.path.basename(urlsplit(url).path), ext, ct)

    def _save_fetched(self, kind, data, name, ext, ct=""):
        target = kind
        is_video = ext in store.VIDEO_EXTS or str(ct).lower().startswith("video")
        if target in ("characters", "locations") and is_video:
            target = "media"
        if store.save_bytes(target, data, name, ext):
            self._finalize_added({target: 1})
        else:
            self._drop_fail("save failed")

    def _finalize_added(self, added):
        for k in added:
            for w in self.windows.values():
                if getattr(w, "kind", None) == k:
                    w.refresh()
        self.toast_text = "Added " + ", ".join(
            f"{c} → {self.KIND_NAMES.get(k, k)}" for k, c in added.items())
        self.toast_t = self.t
        self.sfx.play("select")

    def _drop_fail(self, reason):
        print(f"[companion] drop not added: {reason}")
        self.toast_text = "Couldn't add that"
        self.toast_t = self.t

    def _log_drop(self, md):
        try:
            lines = ["formats: " + ", ".join(md.formats()),
                     f"hasImage={md.hasImage()} hasUrls={md.hasUrls()} "
                     f"hasHtml={md.hasHtml()} hasText={md.hasText()}"]
            if md.hasUrls():
                lines.append("urls: " + " | ".join(u.toString() for u in md.urls()))
            if md.hasText():
                lines.append("text: " + md.text()[:400])
            if md.hasHtml():
                lines.append("html: " + md.html()[:800])
            data_dir = os.path.dirname(store.folder("media"))
            with open(os.path.join(data_dir, "_lastdrop.txt"),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass

    def _end_drag(self):
        self.dragging = False
        self.drag_urls = []
        self.drag_dwell = 0.0
        if self.drag_menu:
            self._reset_menu()
            self.drag_menu = False

    # ------------------------------------------------------------------ #
    #  Mouse (only arrives when click-through is OFF)
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):
        if not self.active or self.dying:
            return
        over_carry = (self.carry is not None and
                      math.hypot(self.carry["x"] - self.cx,
                                 self.carry["y"] - self.cy) < HIT_RADIUS)
        over_comp = math.hypot(self.x - self.cx, self.y - self.cy) < HIT_RADIUS

        if event.button() == QtCore.Qt.RightButton:
            if over_carry:
                self.carry = None
            elif over_comp and not self.menu_open:
                self._die()
            return
        if event.button() == QtCore.Qt.MiddleButton:
            if over_comp and not self.menu_open:
                self._start_thinking()
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        if over_carry:
            self._begin_native_drag()
        elif over_comp and not self.menu_open:
            self._open_menu()
            self.sfx.play("cursor")

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.menu_open:
            self._close_menu(select=True)

    # ------------------------------------------------------------------ #
    #  Hotkey slots
    # ------------------------------------------------------------------ #
    @QtCore.Slot()
    def toggle_active(self):
        going = not self.active
        self.set_active(going)
        self.sfx.play("cursor" if going else "poof")

    @QtCore.Slot(int)
    def on_digit(self, n):
        if self.menu_open and 1 <= n <= len(PRIMARY):
            chosen = self._default_item(n - 1)
            self._reset_menu()
            if chosen:
                self._select(chosen)

    # ================================================================== #
    #  Painting
    # ================================================================== #
    def paintEvent(self, event):
        if self.appear <= 0.0 and self.carry_appear <= 0.0 and not self.poops:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.scale(self.s, self.s)          # design px -> physical px (per monitor)
        if self.appear > 0.0 or self.dying or self.death > 0.0:
            if not self.dying and self.death <= 0.0:
                self._paint_trail(p)
                if self.menu_open:
                    self._paint_menu(p)
            self._paint_companion(p)
            if not self.dying and self.death <= 0.0:
                if self.thinking:
                    self._paint_thinking(p)
                if self._bubble_on:
                    self._paint_idea_bubble(p)
                self._paint_toast(p)
        if self.carry_appear > 0.01 and self.carry is not None:
            self._paint_carry(p)
        if self.poops:
            self._paint_poops(p)
        p.end()

    def _paint_poops(self, p):
        for po in self.poops:
            age = self.t - po["t"]
            a = max(0.0, 1.0 - age / POOP_LIFE)
            p.save()
            p.translate(po["x"], po["y"])
            p.setOpacity(a)
            p.rotate(po["rot"])
            p.setPen(QtCore.Qt.NoPen)
            # three stacked brown blobs (swirl)
            for (dy, w, h, col) in ((6, 13, 8, QtGui.QColor(95, 62, 30)),
                                    (-2, 10, 7, QtGui.QColor(120, 80, 40)),
                                    (-9, 6, 5, QtGui.QColor(140, 96, 52))):
                p.setBrush(col)
                p.drawEllipse(QtCore.QPointF(0, dy), w, h)
            # tiny eyes
            p.setBrush(QtGui.QColor(255, 255, 255))
            p.drawEllipse(QtCore.QPointF(-3.2, 2), 2.2, 2.6)
            p.drawEllipse(QtCore.QPointF(3.2, 2), 2.2, 2.6)
            p.setBrush(QtGui.QColor(20, 20, 20))
            p.drawEllipse(QtCore.QPointF(-3.0, 2.4), 1.0, 1.2)
            p.drawEllipse(QtCore.QPointF(3.4, 2.4), 1.0, 1.2)
            p.restore()
        p.setOpacity(1.0)

    # ----- trail ---------------------------------------------------------- #
    def _paint_trail(self, p):
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        p.setPen(QtCore.Qt.NoPen)
        n = len(self.trail)
        for i, (tx, ty, birth) in enumerate(self.trail):
            age = (self.t - birth) / 0.55
            if age >= 1.0:
                continue
            life = 1.0 - age
            r = (4.0 + 10.0 * (i / max(1, n))) * life * self.appear
            grad = QtGui.QRadialGradient(tx, ty, max(0.1, r))
            c = QtGui.QColor(COL_GLOW)
            c.setAlpha(int(70 * life * life))
            grad.setColorAt(0.0, c)
            c2 = QtGui.QColor(COL_GLOW)
            c2.setAlpha(0)
            grad.setColorAt(1.0, c2)
            p.setBrush(grad)
            p.drawEllipse(QtCore.QPointF(tx, ty), r, r)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    # ----- companion ------------------------------------------------------ #
    def _paint_companion(self, p):
        if self.dying or self.death > 0.001:
            self._paint_dead(p)
            return

        speed = math.hypot(self.vx, self.vy)
        scale = self.appear * (0.6 + 0.4 * self.appear)
        bob = math.sin(self.t * 3.0) * 4.0 * self.appear if speed < 60.0 else 0.0
        ang = math.atan2(self.vy, self.vx)
        stretch = 1.0 + min(speed * 0.00035, 0.45)
        squash = 1.0 / stretch

        # "thinking" jiggle — a fast little wobble while it dreams up an idea
        jx = jy = 0.0
        if self.thinking:
            f = self.think_t
            jx = math.sin(f * 43.0) * JIGGLE_AMP
            jy = math.sin(f * 37.0 + 1.3) * JIGGLE_AMP * 0.7

        p.save()
        p.translate(self.x + jx, self.y + bob + jy)

        pulse = 1.0 + 0.08 * math.sin(self.t * 4.0)
        aura_r = BODY_R * 2.6 * scale * pulse
        ag = QtGui.QRadialGradient(0, 0, aura_r)
        c = QtGui.QColor(COL_GLOW)
        c.setAlpha(90)
        ag.setColorAt(0.0, c)
        c0 = QtGui.QColor(COL_GLOW)
        c0.setAlpha(0)
        ag.setColorAt(1.0, c0)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(ag)
        p.drawEllipse(QtCore.QPointF(0, 0), aura_r, aura_r)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

        p.save()
        if speed > 40:
            p.rotate(math.degrees(ang) * 0.06)
        if self.thinking:
            p.rotate(math.sin(self.think_t * 40.0) * 9.0)
        p.scale(stretch, squash)

        flap = abs(math.sin(self.flap_phase)) * 0.9 + 0.1
        self._draw_wing(p, scale, flap, -1)
        self._draw_wing(p, scale, flap, +1)

        r = BODY_R * scale
        bg = QtGui.QRadialGradient(-r * 0.3, -r * 0.4, r * 1.6)
        bg.setColorAt(0.0, COL_BODY_HI)
        bg.setColorAt(0.6, COL_BODY_LO)
        bg.setColorAt(1.0, COL_BODY_EDGE)
        p.setBrush(bg)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1.5))
        p.drawEllipse(QtCore.QPointF(0, 0), r, r)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 150))
        p.drawEllipse(QtCore.QPointF(-r * 0.35, -r * 0.42), r * 0.22, r * 0.16)
        p.restore()

        self._draw_face(p, scale)
        p.restore()

    def _paint_dead(self, p):
        scale = (0.6 + 0.4 * self.appear)
        r = BODY_R * scale
        p.save()
        p.translate(self.x, self.y)
        p.setOpacity(max(0.0, 1.0 - self.death))
        p.rotate(self.death * 220.0)

        bg = QtGui.QRadialGradient(-r * 0.3, -r * 0.4, r * 1.6)
        bg.setColorAt(0.0, QtGui.QColor(200, 210, 220))
        bg.setColorAt(1.0, QtGui.QColor(90, 110, 140))
        p.setBrush(bg)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 50), 1.5))
        p.drawEllipse(QtCore.QPointF(0, 0), r, r)

        # X_X eyes
        pen = QtGui.QPen(QtGui.QColor(40, 50, 70), max(2.0, r * 0.11))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        e = r * 0.18
        for sx in (-1, 1):
            ex = sx * r * 0.34
            ey = -r * 0.05
            p.drawLine(QtCore.QPointF(ex - e, ey - e), QtCore.QPointF(ex + e, ey + e))
            p.drawLine(QtCore.QPointF(ex - e, ey + e), QtCore.QPointF(ex + e, ey - e))
        # tiny shocked mouth
        p.setBrush(QtGui.QColor(40, 50, 70))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(QtCore.QPointF(0, r * 0.42), r * 0.1, r * 0.13)
        p.restore()

    def _draw_wing(self, p, scale, flap, side):
        p.save()
        r = BODY_R * scale
        p.translate(side * r * 0.55, -r * 0.15)
        p.rotate(side * (20 + flap * 35))
        wg = QtGui.QLinearGradient(0, 0, side * r * 1.6, 0)
        c1 = QtGui.QColor(COL_WING)
        c1.setAlpha(210)
        c2 = QtGui.QColor(COL_ACCENT)
        c2.setAlpha(120)
        wg.setColorAt(0.0, c1)
        wg.setColorAt(1.0, c2)
        p.setBrush(wg)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(QtCore.QPointF(side * r * 0.7, 0), r * 0.95, r * 0.5)
        p.restore()

    def _draw_face(self, p, scale):
        r = BODY_R * scale
        if self.t - self.surprise_t < SURPRISE_DUR:
            self._draw_surprised_face(p, r)
            return
        sad = self.sad
        dx, dy = self.cx - self.x, self.cy - self.y
        d = math.hypot(dx, dy) or 1.0
        gx = max(-1.0, min(1.0, dx / d))
        gy = max(-1.0, min(1.0, dy / d + sad * 0.5))

        eye_dx = r * 0.34
        eye_dy = -r * 0.05
        eye_r = r * 0.20
        open_amt = (1.0 - self.blink) * (1.0 - 0.28 * sad)
        for sx in (-1, 1):
            ex = sx * eye_dx
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 240))
            p.drawEllipse(QtCore.QPointF(ex, eye_dy), eye_r,
                          eye_r * max(0.08, open_amt))
            if open_amt > 0.2:
                p.setBrush(QtGui.QColor(25, 35, 70))
                p.drawEllipse(
                    QtCore.QPointF(ex + gx * eye_r * 0.4, eye_dy + gy * eye_r * 0.4),
                    eye_r * 0.5, eye_r * 0.5 * open_amt)

        if sad > 0.04:
            brow = QtGui.QColor(COL_BROW)
            brow.setAlpha(int(220 * sad))
            pen = QtGui.QPen(brow, max(1.4, r * 0.08))
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            for sx in (-1, 1):
                bx = sx * eye_dx
                by = eye_dy - eye_r * 1.6
                inner = QtCore.QPointF(bx - sx * eye_r * 0.7, by - sad * eye_r * 1.1)
                outer = QtCore.QPointF(bx + sx * eye_r * 0.8, by + sad * eye_r * 0.3)
                p.drawLine(inner, outer)

        p.setBrush(QtCore.Qt.NoBrush)
        pen = QtGui.QPen(COL_FACE, max(1.4, r * 0.07))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        corner_y = r * 0.34 + sad * r * 0.06
        ctrl_y = (r * 0.55) * (1.0 - sad) + (r * 0.10) * sad
        path = QtGui.QPainterPath()
        path.moveTo(-r * 0.22, corner_y)
        path.quadTo(0, ctrl_y, r * 0.22, corner_y)
        p.drawPath(path)

    def _draw_surprised_face(self, p, r):
        # wide eyes + raised brows + little "O" mouth
        eye_dx = r * 0.34
        eye_dy = -r * 0.02
        eye_r = r * 0.28
        p.setPen(QtCore.Qt.NoPen)
        for sx in (-1, 1):
            ex = sx * eye_dx
            p.setBrush(QtGui.QColor(255, 255, 255, 245))
            p.drawEllipse(QtCore.QPointF(ex, eye_dy), eye_r, eye_r)
            p.setBrush(QtGui.QColor(25, 35, 70))
            p.drawEllipse(QtCore.QPointF(ex, eye_dy), eye_r * 0.42, eye_r * 0.42)
        pen = QtGui.QPen(COL_BROW, max(1.4, r * 0.08))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        for sx in (-1, 1):
            bx = sx * eye_dx
            by = eye_dy - eye_r * 1.25
            p.drawLine(QtCore.QPointF(bx - eye_r * 0.7, by),
                       QtCore.QPointF(bx + eye_r * 0.7, by))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(COL_FACE)
        p.drawEllipse(QtCore.QPointF(0, r * 0.45), r * 0.13, r * 0.17)

    # ----- "surprise me" thinking dots + result bubble -------------------- #
    def _paint_thinking(self, p):
        base_x = self.x - 14.0
        base_y = self.y - BODY_R * 2.1
        p.setPen(QtCore.Qt.NoPen)
        for i in range(3):
            s = 0.5 + 0.5 * math.sin(self.think_t * 5.0 - i * 0.7)
            rr = 2.2 + 2.6 * s
            col = QtGui.QColor(COL_ACCENT)
            col.setAlpha(int(255 * (0.35 + 0.65 * s) * min(1.0, self.appear)))
            p.setBrush(col)
            p.drawEllipse(QtCore.QPointF(base_x + i * 14.0, base_y), rr, rr)

    @staticmethod
    def _wrap_text(text, fm, max_w):
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if not cur or fm.horizontalAdvance(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _paint_idea_bubble(self, p):
        age = self.t - self.idea_show_t
        if age < 0:
            return
        fade_in = min(1.0, age / 0.2)
        if self._bubble_dismiss_t >= 0:          # touched -> quick fade-out
            fade_out = max(0.0, 1.0 - (self.t - self._bubble_dismiss_t) / 0.35)
        else:
            fade_out = 1.0                        # otherwise stays up
        a = min(fade_in, fade_out)
        if a <= 0.0:
            return
        max_w, font_px, pad = 300.0, 13, 12.0
        font = p.font()                  # inherit Segoe UI like the rest of the UI
        font.setPixelSize(font_px)
        font.setBold(False)
        fm = QtGui.QFontMetricsF(font)
        lines = self._wrap_text(self.idea_show_text, fm, max_w)
        line_h = fm.height()
        text_w = max((fm.horizontalAdvance(l) for l in lines), default=10.0)
        w = min(max_w, text_w) + pad * 2
        h = line_h * len(lines) + pad * 2
        cx = self.x
        top = self.y - BODY_R * 2.6 - h
        rect = QtCore.QRectF(cx - w / 2, top, w, h)

        p.save()
        p.setOpacity(a)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(18, 22, 32, 238))
        p.drawPath(path)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor(COL_ACCENT), 1.6))
        p.drawPath(path)
        # little pointer toward the companion
        tip = QtGui.QPolygonF([
            QtCore.QPointF(cx - 8, rect.bottom() - 1),
            QtCore.QPointF(cx + 8, rect.bottom() - 1),
            QtCore.QPointF(cx, rect.bottom() + 9)])
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(18, 22, 32, 238))
        p.drawPolygon(tip)

        p.setFont(font)
        p.setPen(QtGui.QColor(238, 243, 252))
        ty = rect.top() + pad + fm.ascent()
        for l in lines:
            lw = fm.horizontalAdvance(l)
            p.drawText(QtCore.QPointF(cx - lw / 2, ty), l)
            ty += line_h
        p.restore()

    # ----- carried item --------------------------------------------------- #
    def _paint_carry(self, p):
        c = self.carry
        a = self.carry_appear
        x, y = c["x"], c["y"]
        bob = math.sin(self.t * 3.4) * 3.0
        size = CARRY_SIZE * (0.7 + 0.3 * a)
        rect = QtCore.QRectF(x - size / 2, y - size / 2 + bob, size, size)

        gg = QtGui.QRadialGradient(rect.center(), size * 0.95)
        gc = QtGui.QColor(COL_ACCENT)
        gc.setAlpha(int(120 * a))
        gg.setColorAt(0.0, gc)
        gc2 = QtGui.QColor(COL_ACCENT)
        gc2.setAlpha(0)
        gg.setColorAt(1.0, gc2)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(gg)
        p.drawEllipse(rect.center(), size * 0.95, size * 0.95)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        p.save()
        p.setClipPath(path)
        pm = c["pixmap"]
        if not pm.isNull():
            scaled = pm.scaled(int(size), int(size),
                               QtCore.Qt.KeepAspectRatioByExpanding,
                               QtCore.Qt.SmoothTransformation)
            p.setOpacity(a)
            p.drawPixmap(int(rect.center().x() - scaled.width() / 2),
                         int(rect.center().y() - scaled.height() / 2), scaled)
            p.setOpacity(1.0)
        else:
            p.fillPath(path, QtGui.QColor(40, 44, 54))
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(220 * a)), 2.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)

        if a > 0.6:
            self._text(p, QtCore.QPointF(x, rect.bottom() + 14), 12,
                       "drag me anywhere",
                       QtGui.QColor(255, 255, 255, int(230 * (a - 0.6) / 0.4)),
                       bold=True, glow=True)

    # ----- menu (no connecting lines) ------------------------------------- #
    def _paint_menu(self, p):
        center = QtCore.QPointF(self.menu_cx, self.menu_cy)
        if self.level == 0:
            n = len(PRIMARY)
            for i, (pid, label, key) in enumerate(PRIMARY):
                cur, ease = self._ring_point(i, n, center, MENU_RADIUS)
                if ease <= 0.001:
                    continue
                hl = (i == self.primary_hover)
                pr = (29.0 if hl else 24.0) * ease
                self._petal_circle(p, cur, pr, hl, ease)
                self._badge(p, cur, pr, key, ease)
                la = int(255 * min(1.0, self.ring_t * 1.4))
                self._text(p, QtCore.QPointF(cur.x(), cur.y() + pr + 14), 13,
                           label, QtGui.QColor(255, 255, 255, la), bold=hl)
        else:
            n = len(self.sub_items)
            for j, item in enumerate(self.sub_items):
                cur, ease = self._ring_point(j, n, center, SUB_RADIUS)
                if ease <= 0.001:
                    continue
                hl = (j == self.sub_hover)
                if item["type"] == "asset":
                    pr = (46.0 if hl else 40.0) * ease    # bigger, easier to hit
                    self._petal_thumb(p, cur, pr, item["path"], hl)
                    continue                              # no filename label
                elif item["type"] == "editor":
                    pr = (31.0 if hl else 26.0) * ease
                    self._petal_circle(p, cur, pr, hl, ease, accent=True)
                    self._gear(p, cur, pr * 0.62)
                else:
                    pr = (31.0 if hl else 26.0) * ease
                    self._petal_circle(p, cur, pr, hl, ease)
                la = int(255 * min(1.0, self.ring_t * 1.4))
                self._text(p, QtCore.QPointF(cur.x(), cur.y() + pr + 14), 12,
                           item["label"], QtGui.QColor(255, 255, 255, la),
                           bold=hl, glow=True)

    def _ring_point(self, i, n, center, radius):
        px, py = self._ring_pos(i, n, radius)
        local = max(0.0, min(1.0, self.ring_t * 1.3 - i * 0.045))
        ease = 1.0 - (1.0 - local) ** 2
        cur = QtCore.QPointF(center.x() + (px - center.x()) * ease,
                             center.y() + (py - center.y()) * ease)
        return cur, ease

    @staticmethod
    def _mix(a, b, t):
        """Blend two QColors (t=0 -> a, t=1 -> b)."""
        return QtGui.QColor(
            int(a.red() + (b.red() - a.red()) * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue() + (b.blue() - a.blue()) * t))

    def _petal_circle(self, p, cur, pr, hl, ease, accent=False):
        # Menu colours follow the active palette: normal petals = body colour,
        # the highlighted petal = the accent ("pop") colour, and the editor
        # petal = a body↔accent blend so it reads as a little different.
        if hl:
            self._glow(p, cur, pr * 2.2, 150)
        pg = QtGui.QRadialGradient(cur.x(), cur.y() - pr * 0.4, pr * 1.8)
        white = QtGui.QColor(255, 255, 255)
        if hl:
            pg.setColorAt(0.0, white)
            pg.setColorAt(1.0, COL_ACCENT)
        elif accent:
            pg.setColorAt(0.0, self._mix(COL_BODY_HI, white, 0.5))
            pg.setColorAt(1.0, self._mix(COL_BODY_LO, COL_ACCENT, 0.5))
        else:
            pg.setColorAt(0.0, self._mix(COL_BODY_HI, white, 0.45))
            pg.setColorAt(1.0, COL_BODY_LO)
        p.setBrush(pg)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.5))
        p.drawEllipse(cur, pr, pr)
        p.setPen(QtCore.Qt.NoPen)

    def _petal_thumb(self, p, cur, pr, path, hl):
        if hl:
            self._glow(p, cur, pr * 2.3, 170)
        d = int(pr * 2)
        p.drawPixmap(int(cur.x() - pr), int(cur.y() - pr), self._circ_thumb(path, d))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 235 if hl else 170),
                            3 if hl else 1.6))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(cur, pr, pr)
        p.setPen(QtCore.Qt.NoPen)
        if store.is_video(path):
            self._play_badge(p, cur, pr * 0.42)

    def _play_badge(self, p, cur, r):
        """A little ▶ inside a translucent disc — marks a thumbnail as video."""
        p.setBrush(QtGui.QColor(0, 0, 0, 130))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(cur, r, r)
        tri = QtGui.QPolygonF([
            QtCore.QPointF(cur.x() - r * 0.32, cur.y() - r * 0.52),
            QtCore.QPointF(cur.x() - r * 0.32, cur.y() + r * 0.52),
            QtCore.QPointF(cur.x() + r * 0.55, cur.y())])
        p.setBrush(QtGui.QColor(255, 255, 255, 235))
        p.drawPolygon(tri)

    def _glow(self, p, cur, r, alpha):
        gg = QtGui.QRadialGradient(cur, r)
        gc = QtGui.QColor(COL_ACCENT)
        gc.setAlpha(alpha)
        gg.setColorAt(0.0, gc)
        gc2 = QtGui.QColor(COL_ACCENT)
        gc2.setAlpha(0)
        gg.setColorAt(1.0, gc2)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        p.setBrush(gg)
        p.drawEllipse(cur, r, r)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def _gear(self, p, cur, r):
        p.save()
        p.translate(cur)
        p.setBrush(QtGui.QColor(40, 50, 90))
        p.setPen(QtCore.Qt.NoPen)
        teeth = 8
        path = QtGui.QPainterPath()
        for k in range(teeth * 2):
            rad = r if k % 2 == 0 else r * 0.66
            a = math.pi * k / teeth
            pt = QtCore.QPointF(math.cos(a) * rad, math.sin(a) * rad)
            path.lineTo(pt) if k else path.moveTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QtGui.QColor(210, 225, 255))
        p.drawEllipse(QtCore.QPointF(0, 0), r * 0.34, r * 0.34)
        p.restore()

    def _badge(self, p, cur, pr, key, ease):
        bc = cur + QtCore.QPointF(pr * 0.72, -pr * 0.72)
        br = pr * 0.42
        p.setBrush(QtGui.QColor(35, 55, 95, int(235 * ease)))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(bc, br, br)
        self._text(p, bc, br * 1.4, key,
                   QtGui.QColor(255, 255, 255, int(255 * ease)), bold=True)

    def _circ_thumb(self, path, d):
        key = (path, d)
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached
        src = store.load_pixmap(path)
        if src.isNull():
            src = store.placeholder_pixmap(path, d)
        scaled = src.scaled(d, d, QtCore.Qt.KeepAspectRatioByExpanding,
                            QtCore.Qt.SmoothTransformation)
        out = QtGui.QPixmap(d, d)
        out.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(out)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        clip = QtGui.QPainterPath()
        clip.addEllipse(0, 0, d, d)
        p.setClipPath(clip)
        p.drawPixmap(int((d - scaled.width()) / 2),
                     int((d - scaled.height()) / 2), scaled)
        p.end()
        self._thumb_cache[key] = out
        return out

    # ----- toast ---------------------------------------------------------- #
    def _paint_toast(self, p):
        age = self.t - self.toast_t
        if age < 0 or age > 1.3:
            return
        a = age / 0.15 if age < 0.15 else max(0.0, 1.0 - (age - 0.15) / 1.15)
        pos = QtCore.QPointF(self.x, self.y - BODY_R * 2.2 - 26.0 * (1.0 - a))
        self._text(p, pos, 16, self.toast_text,
                   QtGui.QColor(255, 255, 255, int(255 * a)), bold=True, glow=True)

    # ----- text helper ---------------------------------------------------- #
    def _text(self, p, center, px, text, color, bold=False, glow=False):
        font = p.font()
        font.setPixelSize(max(1, int(px)))
        font.setBold(bold)
        p.setFont(font)
        fm = QtGui.QFontMetricsF(font)
        rect = fm.boundingRect(text)
        pos = QtCore.QPointF(center.x() - rect.width() / 2,
                             center.y() + rect.height() / 2 - fm.descent())
        if glow:
            p.setPen(QtGui.QColor(20, 40, 80, color.alpha()))
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                p.drawText(pos + QtCore.QPointF(ox, oy), text)
        p.setPen(color)
        p.drawText(pos, text)


# --------------------------------------------------------------------------- #
_APP_NAME = "Companion"


def _autostart_command():
    if getattr(sys, "frozen", False):           # built as an .exe / .app
        return f'"{sys.executable}"'
    exe = sys.executable
    if IS_WINDOWS:
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pyw):
            exe = pyw                            # no console window at boot
    return f'"{exe}" "{os.path.abspath(__file__)}"'


if IS_WINDOWS:
    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def autostart_enabled():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                val, _ = winreg.QueryValueEx(k, _APP_NAME)
                return bool(val)
        except OSError:
            return False

    def set_autostart(enable):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                if enable:
                    winreg.SetValueEx(k, _APP_NAME, 0, winreg.REG_SZ,
                                      _autostart_command())
                else:
                    try:
                        winreg.DeleteValue(k, _APP_NAME)
                    except OSError:
                        pass
            return True
        except OSError as exc:
            print(f"[companion] autostart change failed: {exc}")
            return False

else:
    # macOS: LaunchAgents plist
    _PLIST_LABEL = "io.artlist.Companion"
    _PLIST_PATH  = os.path.expanduser(
        f"~/Library/LaunchAgents/{_PLIST_LABEL}.plist")

    def autostart_enabled():
        return os.path.exists(_PLIST_PATH)

    def set_autostart(enable):
        try:
            if enable:
                parts = _autostart_command().split()
                args_xml = "".join(f"        <string>{a.strip('\"')}</string>\n"
                                   for a in parts)
                plist = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
                    ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    f'    <key>Label</key><string>{_PLIST_LABEL}</string>\n'
                    '    <key>ProgramArguments</key><array>\n'
                    f'{args_xml}'
                    '    </array>\n'
                    '    <key>RunAtLoad</key><true/>\n'
                    '</dict></plist>\n'
                )
                os.makedirs(os.path.dirname(_PLIST_PATH), exist_ok=True)
                with open(_PLIST_PATH, "w", encoding="utf-8") as f:
                    f.write(plist)
            else:
                if os.path.exists(_PLIST_PATH):
                    os.remove(_PLIST_PATH)
            return True
        except OSError as exc:
            print(f"[companion] mac autostart change failed: {exc}")
            return False


def _make_tray_icon():
    pm = QtGui.QPixmap(64, 64)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    g = QtGui.QRadialGradient(26, 22, 34)
    g.setColorAt(0.0, COL_BODY_HI)
    g.setColorAt(0.6, COL_BODY_LO)
    g.setColorAt(1.0, COL_BODY_EDGE)
    p.setBrush(g)
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 70), 2))
    p.drawEllipse(QtCore.QPointF(32, 32), 26, 26)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(25, 35, 70))
    p.drawEllipse(QtCore.QPointF(24, 30), 5, 6)
    p.drawEllipse(QtCore.QPointF(42, 30), 5, 6)
    p.setBrush(QtGui.QColor(255, 255, 255, 160))
    p.drawEllipse(QtCore.QPointF(22, 22), 5, 4)
    p.end()
    return QtGui.QIcon(pm)


def _build_tray(app, widget):
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        print("[companion] system tray not available.")
        return None
    tray = QtWidgets.QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("Companion — click to wake / sleep")
    menu = QtWidgets.QMenu()
    menu.addAction("Wake / Sleep").triggered.connect(widget.toggle_active)
    menu.addAction("✦ Surprise me  (middle-click)").triggered.connect(
        widget._tray_surprise)
    menu.addSeparator()

    # Colour palette picker (exclusive, checkmark on the active one)
    color_menu = menu.addMenu("Color")
    color_group = QtGui.QActionGroup(menu)
    color_group.setExclusive(True)

    def _choose_palette(name):
        set_palette(name)
        store.update_setting("palette", name)
        tray.setIcon(_make_tray_icon())      # recolour the tray icon too
        widget.update()

    for name in PALETTE_ORDER:
        act = color_menu.addAction(name)
        act.setCheckable(True)
        act.setChecked(name == ACTIVE_PALETTE)
        color_group.addAction(act)
        act.triggered.connect(lambda _=False, n=name: _choose_palette(n))

    menu.addSeparator()
    auto = menu.addAction("Start at Login" if IS_MAC else "Start with Windows")
    auto.setCheckable(True)
    auto.setChecked(autostart_enabled())
    auto.toggled.connect(lambda on: (set_autostart(on),
                                      auto.setChecked(autostart_enabled())))
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason in (QtWidgets.QSystemTrayIcon.Trigger,
                      QtWidgets.QSystemTrayIcon.DoubleClick):
            widget.toggle_active()
    tray.activated.connect(on_activated)
    tray.show()
    widget._tray = tray          # keep references alive
    widget._tray_menu = menu
    return tray


if IS_WINDOWS:
    def _acquire_single_instance():
        """Returns the mutex handle, or None if another instance already runs."""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Companion_SingleInstance_Mutex")
        if kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
            return None
        return handle
else:
    import fcntl as _fcntl
    _mac_lock_fh = None

    def _acquire_single_instance():
        """Use a lock file for single-instance enforcement on macOS."""
        global _mac_lock_fh
        lock_path = os.path.join(os.path.expanduser("~"), ".companion.lock")
        try:
            _mac_lock_fh = open(lock_path, "w")
            _fcntl.lockf(_mac_lock_fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            return _mac_lock_fh
        except OSError:
            return None


def main():
    mutex = _acquire_single_instance()
    if mutex is None:
        print("[companion] already running — this instance will exit.")
        return

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    store.ensure_dirs()
    set_palette(store.load_settings().get("palette", "Default"))

    if IS_WINDOWS:
        def _warm_uia():
            try:
                import uiautomation  # noqa: F401
            except Exception:
                pass
        threading.Thread(target=_warm_uia, daemon=True).start()

    # On first run, enable autostart so it always runs in background
    if not store.load_settings().get("autostart_set"):
        set_autostart(True)
        store.update_setting("autostart_set", True)

    widget = Companion()
    widget.show()
    _build_tray(app, widget)

    hotkeys = Hotkeys()
    hotkeys.toggle.connect(widget.toggle_active)
    hotkeys.digit.connect(widget.on_digit)
    hotkeys.quit.connect(app.quit)
    hotkeys.start()

    QtCore.QTimer.singleShot(250, lambda: widget.set_active(True))

    print(__doc__)
    print("[companion] running. Double-tap Alt to sleep/wake. Ctrl+Alt+Q to quit.")

    code = app.exec()
    hotkeys.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
