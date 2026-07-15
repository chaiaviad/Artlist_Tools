"""
Local storage for the Companion.

* characters / locations / media : each is a folder under data/. Files are
  copied in on add. Display order is explicit (persisted in _order.json per
  kind) so the editor can re-order by drag & drop; newly added items go to the
  front ("latest first"). The menu shows only the first few; the editor keeps
  all of them.
* sauces : name -> text prompt, persisted in data/sauces.json (seeded with the
  defaults below on first run). The menu shows only names.
"""

import os
import sys
import json
import shutil
import time
import ctypes

IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"

if IS_WINDOWS:
    from ctypes import wintypes

from PySide6 import QtGui, QtCore


def _app_base():
    # When built as an .exe, keep editable data next to the .exe (so people's
    # added characters/sauces/SFX persist and are visible). In dev, use ./data.
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "CompanionData")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _bundled_dir():
    # read-only resources packed into the .exe (PyInstaller _MEIPASS), else ./data
    return getattr(sys, "_MEIPASS",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))


_BASE = _app_base()

KINDS = {
    "characters": os.path.join(_BASE, "characters"),
    "locations": os.path.join(_BASE, "locations"),
    "media": os.path.join(_BASE, "media"),
}
_ORDER_FILE = "_order.json"
_SAUCES_FILE = os.path.join(_BASE, "sauces.json")
_SETTINGS_FILE = os.path.join(_BASE, "settings.json")
SFX_DIR = os.path.join(_BASE, "SFX")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".wmv"}


# --------------------------------------------------------------------------- #
#  Default sauces (name -> prompt)
# --------------------------------------------------------------------------- #
DEFAULT_SAUCES = [
    {"name": "Image sauce", "prompt":
     "Add fog and filmgrain. a cinematic shot made by verner herzog, shot by "
     "swedish akira kurasawa. medium shot dutch angle realistic, stylized by "
     "billy wilder, halation lens. do not add greens. cinematic shot "
     "colorgrading professional. meticulously composed environment, crisp "
     "detail, photoreal yet stylized, no text, no graphics, no watermark, "
     "shallow depth of field. Slight lens blur, chromatic fringing."},
    {"name": "Upscale", "prompt":
     "reframe the camera to empathize the scene. camera position and framing "
     "composition are perfect, rule of third and the golden rule composed "
     "composition. character references attached. people skin textures are "
     "real. Avoid a look of a painting. Avoid a look of CGI.\n\n"
     "Add haze and filmgrain. shallow depth of field. a cinematic shot made by "
     "Verner Herzog, shot by Swedish Akira Kurosawa. medium shot Dutch angle "
     "realistic, stylized by Billy wilder, halation lens. do not add greens. "
     "cinematic shot colorgrading professional. meticulously composed "
     "environment, crisp detail, photoreal yet stylized, no text, no graphics, "
     "no watermark, shallow depth of field. Slight lens blur, chromatic "
     "fringing.\n\nGenerate a high-resolution frame using this image as "
     "reference, 8k detail. Changing the content is forbidden."},
    {"name": "Seedance", "prompt":
     "一部2020年代的电影, from mike flanagan film:\n\n内容：\n\n"
     "Storyboard cinematic sequence. Add small filmgrain. meticulously composed "
     "environment, crisp detail, photoreal yet stylized, no text, no graphics, "
     "no watermark, shallow depth of field. Slight lens blur, chromatic "
     "fringing. avoid bad acting, avoid morphing, avoid background music. Avoid "
     "continuity problems. Each shot is necessary for the storytelling and adds "
     "drama to the sequence. Lighting is cinematic contrast in the style of "
     "storaro and nestor almendros and the color grading is also cinematic. "
     "closeups are detailed and hyper realistic, and longshot expose well "
     "thought location and Mise-en-scène. Directed by nolan and flanagan. Avoid "
     "NSFW audio or video. avoid bad physics, avoid static camera. avoid "
     "natural color grading. Closeups empathize the hero and not the background "
     "characters.\n\nNo background music."},
    {"name": "Oneshot", "prompt":
     "一部2020年代的电影, from mike flanagan film：\n\n内容：\n\n"
     "create a one-shot single shot static camera. Add small filmgrain. "
     "meticulously composed environment, crisp detail, photoreal yet stylized, "
     "no text, no graphics, no watermark, shallow depth of field. Slight lens "
     "blur, chromatic fringing. avoid bad acting, avoid morphing, avoid "
     "background music. Avoid continuity problems. single shot never cuts, "
     "avoid editing. Lighting is cinematic contrast in the style of storaro and "
     "nestor almendros and the color grading is also cinematic. single longshot "
     "that exposes awell thought location. Directed by nolan and flanagan. "
     "avoid bad physics, avoid camera movements. avoid changing the shot to "
     "another. avoid natural color grading."},
    {"name": "Crazy colorful", "prompt":
     "2020 film in the style of 一2000年代的冒险电影 liminal lighting from Storaro, "
     "perspective lens and scene blocking, suspense drama mixed with taika "
     "waititi camera works. The colors are immersive and expressive, and the "
     "composition homages skilled art masterpieces in framing and angle. color "
     "grading is never monochromatic, colors are never gray. must be Tarsem "
     "colorful :\n\n内容：. \n \nStoryboard cinematic sequence. Add small "
     "filmgrain. meticulously composed environment, crisp detail, photoreal yet "
     "stylized, no text, no graphics, no watermark, shallow depth of field. "
     "Slight lens blur, chromatic fringing. avoid bad acting, avoid morphing. "
     "Avoid continuity problems. Each shot is necessary for the storytelling "
     "and adds drama to the sequence. Lighting is cinematic contrast in the "
     "style of storaro and nestor almendros and the color grading is also "
     "cinematic. closeups are detailed and hyper realistic, and longshot expose "
     "well thought location and Mise-en-scène. Directed by nolan and flanagan. "
     "Avoid NSFW audio or video. avoid bad physics, avoid static camera. avoid "
     "natural color grading. Closeups empathize the hero and not the background "
     "characters.\n\nNo music;"},
]


# --------------------------------------------------------------------------- #
def ensure_dirs():
    for path in KINDS.values():
        os.makedirs(path, exist_ok=True)
    os.makedirs(_BASE, exist_ok=True)
    os.makedirs(SFX_DIR, exist_ok=True)
    _seed_sfx()


def _seed_sfx():
    # On a fresh .exe run, copy the bundled SFX into the persistent folder so it
    # has sound out of the box (and people can still add/replace their own).
    try:
        have = any(f.lower().endswith(".wav") for f in os.listdir(SFX_DIR))
    except OSError:
        have = False
    if have:
        return
    src = os.path.join(_bundled_dir(), "SFX")
    if os.path.isdir(src) and os.path.abspath(src) != os.path.abspath(SFX_DIR):
        for f in os.listdir(src):
            if f.lower().endswith(".wav"):
                try:
                    shutil.copy2(os.path.join(src, f), os.path.join(SFX_DIR, f))
                except OSError:
                    pass


def folder(kind):
    return KINDS[kind]


def sfx_dir():
    return SFX_DIR


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def is_video(path):
    return ext_of(path) in VIDEO_EXTS


def is_image(path):
    return ext_of(path) in IMAGE_EXTS


def is_media(path):
    e = ext_of(path)
    return e in IMAGE_EXTS or e in VIDEO_EXTS


def accepts(kind, path):
    # Drag & Dropper ("media") is a general stash — it holds ANY file type so
    # you can grab it back out later. Characters/locations are image-only.
    if kind == "media":
        return True
    return ext_of(path) in IMAGE_EXTS


# --------------------------------------------------------------------------- #
#  Ordering
# --------------------------------------------------------------------------- #
def _order_path(kind):
    return os.path.join(KINDS[kind], _ORDER_FILE)


def _load_order(kind):
    try:
        with open(_order_path(kind), "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_order(kind, names):
    try:
        with open(_order_path(kind), "w", encoding="utf-8") as f:
            json.dump(list(names), f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[store] order save failed: {exc}")


def list_items(kind):
    """Stored file paths for a kind, in display order (front = newest/top)."""
    d = KINDS[kind]
    if not os.path.isdir(d):
        return []
    present = [f for f in os.listdir(d)
               if os.path.isfile(os.path.join(d, f))
               and f != _ORDER_FILE and accepts(kind, f)]
    present_set = set(present)
    order = _load_order(kind)
    ordered = [f for f in order if f in present_set]
    known = set(ordered)
    extras = [f for f in present if f not in known]
    extras.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    final = extras + ordered          # externally-added files surface on top
    return [os.path.join(d, f) for f in final]


def set_order(kind, paths):
    """Persist a new display order (paths or basenames)."""
    names = [os.path.basename(p) for p in paths]
    _save_order(kind, names)


def _unique_dest(dest_dir, name):
    base, ext = os.path.splitext(name)
    candidate = name
    i = 1
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{base}_{i}{ext}"
        i += 1
    return os.path.join(dest_dir, candidate)


def add_files(kind, paths):
    """Copy files into a kind's folder (newest go to the front). Returns stored paths."""
    d = KINDS[kind]
    os.makedirs(d, exist_ok=True)
    added = []
    for src in paths:
        if not os.path.isfile(src) or not accepts(kind, src):
            continue
        dest = _unique_dest(d, os.path.basename(src))
        try:
            shutil.copy2(src, dest)
            now = time.time()
            os.utime(dest, (now, now))
            added.append(os.path.basename(dest))
        except OSError as exc:
            print(f"[store] add failed for {src}: {exc}")
    if added:
        order = _load_order(kind)
        order = added + [o for o in order if o not in set(added)]
        _save_order(kind, order)
    return [os.path.join(d, n) for n in added]


def save_image(kind, qimage, name="image"):
    """Save a raw QImage (e.g. an image dragged out of a browser) into a kind."""
    if qimage is None or qimage.isNull():
        return None
    d = KINDS[kind]
    os.makedirs(d, exist_ok=True)
    base = os.path.basename(str(name)).split("?")[0].strip() or "image"
    if ext_of(base) not in IMAGE_EXTS:
        base += ".png"
    dest = _unique_dest(d, base)
    if not qimage.save(dest):
        if not qimage.save(dest, "PNG"):
            return None
    now = time.time()
    try:
        os.utime(dest, (now, now))
    except OSError:
        pass
    order = _load_order(kind)
    bn = os.path.basename(dest)
    _save_order(kind, [bn] + [o for o in order if o != bn])
    return dest


def save_bytes(kind, data, name="image", ext=".png"):
    """Save raw bytes (e.g. an image fetched from a dragged URL) into a kind."""
    if not data:
        return None
    d = KINDS[kind]
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(str(name)).split("?")[0].strip())[0]
    base = base or "image"
    if not ext.startswith("."):
        ext = "." + ext
    dest = _unique_dest(d, base + ext)
    try:
        with open(dest, "wb") as f:
            f.write(data)
    except OSError as exc:
        print(f"[store] save_bytes failed: {exc}")
        return None
    now = time.time()
    try:
        os.utime(dest, (now, now))
    except OSError:
        pass
    bn = os.path.basename(dest)
    order = _load_order(kind)
    _save_order(kind, [bn] + [o for o in order if o != bn])
    return dest


def delete(paths):
    by_kind = {}
    for p in paths:
        try:
            os.remove(p)
        except OSError as exc:
            print(f"[store] delete failed for {p}: {exc}")
            continue
        d = os.path.dirname(p)
        by_kind.setdefault(d, []).append(os.path.basename(p))
    # prune order files
    for kind, kdir in KINDS.items():
        if kdir in by_kind:
            removed = set(by_kind[kdir])
            order = [o for o in _load_order(kind) if o not in removed]
            _save_order(kind, order)


# --------------------------------------------------------------------------- #
#  Sauces (name + prompt)
# --------------------------------------------------------------------------- #
def load_sauces():
    try:
        with open(_SAUCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = [{"name": str(d.get("name", "")), "prompt": str(d.get("prompt", ""))}
               for d in data if isinstance(d, dict)]
        if out:
            return out
    except (OSError, ValueError):
        pass
    save_sauces(DEFAULT_SAUCES)
    return [dict(s) for s in DEFAULT_SAUCES]


def save_sauces(sauces):
    os.makedirs(_BASE, exist_ok=True)
    try:
        with open(_SAUCES_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sauces), f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[store] sauces save failed: {exc}")


# --------------------------------------------------------------------------- #
#  Settings (palette choice, etc.)
# --------------------------------------------------------------------------- #
def load_settings():
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(d):
    os.makedirs(_BASE, exist_ok=True)
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(d), f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[store] settings save failed: {exc}")


def update_setting(key, value):
    s = load_settings()
    s[key] = value
    save_settings(s)


# --------------------------------------------------------------------------- #
#  Thumbnails — real video frames / file-type icons
#
#  Windows: IShellItemImageFactory (same engine as Explorer, no extra deps).
#  macOS:   qlmanage Quick Look (system utility, always present).
#  Both fall back to None; load_pixmap() then shows a placeholder.
#  Results are cached by (path, mtime, size).
# --------------------------------------------------------------------------- #
_thumb_cache = {}

if IS_WINDOWS:
    _co_init_done = False

    class _SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    class _BITMAP(ctypes.Structure):
        _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                    ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                    ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                    ("bmBits", ctypes.c_void_p)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                    ("biBitCount", ctypes.c_ushort),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    class _BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                    ("bmiColors", ctypes.c_uint32 * 3)]

    def _shell_apis():
        ole32  = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        gdi32  = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        ole32.IIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_GUID)]
        ole32.IIDFromString.restype  = ctypes.c_long
        shell32.SHCreateItemFromParsingName.argtypes = [
            ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
        gdi32.GetObjectW.argtypes  = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetObjectW.restype   = ctypes.c_int
        gdi32.GetDIBits.argtypes   = [ctypes.c_void_p, wintypes.HANDLE, ctypes.c_uint,
                                      ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_uint]
        gdi32.GetDIBits.restype    = ctypes.c_int
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        user32.GetDC.argtypes      = [ctypes.c_void_p]
        user32.GetDC.restype       = ctypes.c_void_p
        user32.ReleaseDC.argtypes  = [ctypes.c_void_p, ctypes.c_void_p]
        return ole32, shell32, gdi32, user32

    def _hbitmap_to_qimage(hbm, gdi32, user32):
        bm = _BITMAP()
        if gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)) == 0:
            return None
        w, h = bm.bmWidth, bm.bmHeight
        if w <= 0 or h <= 0:
            return None
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth       = w
        bmi.bmiHeader.biHeight      = -h   # negative => top-down rows
        bmi.bmiHeader.biPlanes      = 1
        bmi.bmiHeader.biBitCount    = 32
        bmi.bmiHeader.biCompression = 0    # BI_RGB
        buf  = ctypes.create_string_buffer(w * h * 4)
        hdc  = user32.GetDC(None)
        lines = gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
        user32.ReleaseDC(None, hdc)
        if lines == 0:
            return None
        img = QtGui.QImage(bytes(buf), w, h, QtGui.QImage.Format_RGB32)
        return img.copy()

    def _shell_thumbnail(path, size):
        global _co_init_done
        try:
            ole32, shell32, gdi32, user32 = _shell_apis()
            if not _co_init_done:
                ole32.CoInitialize(None)
                _co_init_done = True
            iid = _GUID()
            if ole32.IIDFromString("{BCC18B79-BA16-442F-80C4-8A59C30C463B}",
                                   ctypes.byref(iid)) != 0:
                return None
            factory = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(
                    path, None, ctypes.byref(iid), ctypes.byref(factory)) != 0:
                return None
            if not factory:
                return None
            try:
                vtbl   = ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0]
                funcs  = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))
                get_image = ctypes.WINFUNCTYPE(
                    ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_uint32,
                    ctypes.POINTER(wintypes.HANDLE))(funcs[3])
                release   = ctypes.WINFUNCTYPE(
                    ctypes.c_ulong, ctypes.c_void_p)(funcs[2])
                hbm = wintypes.HANDLE()
                hr  = get_image(factory, _SIZE(size, size), 0, ctypes.byref(hbm))
            finally:
                release(factory)
            if hr != 0 or not hbm:
                return None
            img = _hbitmap_to_qimage(hbm, gdi32, user32)
            gdi32.DeleteObject(hbm)
            if img is None or img.isNull():
                return None
            return QtGui.QPixmap.fromImage(img)
        except Exception as exc:
            print(f"[store] shell thumbnail failed for {path}: {exc}")
            return None

    def win_thumbnail(path, size=256):
        """Real Windows thumbnail (video frame / icon). Cached."""
        try:
            path  = os.path.abspath(path)
            mtime = int(os.path.getmtime(path))
        except OSError:
            return None
        key = (path, mtime, int(size))
        if key in _thumb_cache:
            return _thumb_cache[key]
        pm = _shell_thumbnail(path, int(size))
        _thumb_cache[key] = pm
        return pm

else:
    def _ql_thumbnail(path, size=256):
        """Use macOS Quick Look (qlmanage) to generate a thumbnail."""
        try:
            import subprocess, tempfile, glob
            with tempfile.TemporaryDirectory() as td:
                subprocess.run(
                    ["qlmanage", "-t", "-s", str(int(size)), "-o", td, path],
                    capture_output=True, timeout=6)
                files = (glob.glob(os.path.join(td, "*.png")) +
                         glob.glob(os.path.join(td, "*.jpg")))
                if files:
                    pm = QtGui.QPixmap(files[0])
                    if not pm.isNull():
                        return pm
        except Exception as exc:
            print(f"[store] ql thumbnail failed for {path}: {exc}")
        return None

    def win_thumbnail(path, size=256):
        """Alias so call-sites that use win_thumbnail work on Mac too."""
        try:
            path  = os.path.abspath(path)
            mtime = int(os.path.getmtime(path))
        except OSError:
            return None
        key = (path, mtime, int(size))
        if key in _thumb_cache:
            return _thumb_cache[key]
        pm = _ql_thumbnail(path, int(size))
        _thumb_cache[key] = pm
        return pm


# --------------------------------------------------------------------------- #
#  Pixmaps
# --------------------------------------------------------------------------- #
def load_pixmap(path):
    if is_video(path):
        pm = win_thumbnail(path, 256)
        if pm is not None and not pm.isNull():
            return pm
        return placeholder_pixmap(path, 256)
    pm = QtGui.QPixmap(path)
    if not pm.isNull():
        return pm
    # not a directly-loadable image (e.g. an arbitrary file in the media stash)
    # — try the shell for a real icon/preview before giving up.
    sh = win_thumbnail(path, 256)
    if sh is not None and not sh.isNull():
        return sh
    return placeholder_pixmap(path, 256)


def placeholder_pixmap(path, size):
    size = int(size)
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtGui.QColor(28, 30, 36))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    if is_video(path):
        p.setBrush(QtGui.QColor(90, 150, 240))
        p.setPen(QtCore.Qt.NoPen)
        c = size / 2.0
        r = size * 0.22
        tri = QtGui.QPolygonF([
            QtCore.QPointF(c - r * 0.5, c - r),
            QtCore.QPointF(c - r * 0.5, c + r),
            QtCore.QPointF(c + r, c),
        ])
        p.drawPolygon(tri)
    else:
        pen = QtGui.QPen(QtGui.QColor(110, 116, 128), max(2, size * 0.02))
        p.setPen(pen)
        m = size * 0.28
        p.drawRect(QtCore.QRectF(m, m, size - 2 * m, size - 2 * m))
        p.drawLine(QtCore.QPointF(m, size - m), QtCore.QPointF(size - m, m))
    f = p.font()
    f.setPixelSize(max(10, int(size * 0.11)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QtGui.QColor(200, 205, 214))
    p.drawText(pm.rect(), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter,
               ext_of(path).lstrip("."))
    p.end()
    return pm
