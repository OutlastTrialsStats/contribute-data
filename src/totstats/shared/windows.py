"""Windows display metrics and DPI awareness.

The handles come from WinDLL, not from ctypes.windll: windll caches its instances and the
function pointers on them, so reusing it would share argtypes and errcheck with pystray, which
configures the very same functions.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

SM_CXSMICON = 49

_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x00000010

_PROCESS_PER_MONITOR_DPI_AWARE = 2
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# What the notification area asks for at 100% scaling.
DEFAULT_SMALL_ICON = 16

try:
    _user32: ctypes.WinDLL | None = ctypes.WinDLL("user32", use_last_error=True)
    _user32.LoadImageW.restype = wintypes.HANDLE
    _user32.LoadImageW.argtypes = (
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        wintypes.INT, wintypes.INT, wintypes.UINT,
    )
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
except (AttributeError, OSError):  # pragma: no cover - not Windows
    _user32 = None


def enable_dpi_awareness() -> bool:
    """Opt out of Windows' bitmap stretching. Call before creating any window.

    All three fail once awareness is already set — by a manifest or an embedding host — which is
    not an error.
    """
    if _user32 is None:
        return False

    try:
        if _user32.SetProcessDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except (AttributeError, OSError):
        pass

    try:
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE) == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        return bool(_user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def small_icon_size() -> int:
    """The primary monitor's tray icon size: 16 at 100% scaling, 24 at 150%, 32 at 200%."""
    if _user32 is None:
        return DEFAULT_SMALL_ICON
    try:
        return _user32.GetSystemMetrics(SM_CXSMICON) or DEFAULT_SMALL_ICON
    except OSError:
        return DEFAULT_SMALL_ICON


def load_icon(path: Path, size: int) -> int | None:
    """An HICON of exactly `size` from the matching frame of an .ico, or None.

    The caller owns the handle and must pass it to DestroyIcon; LR_SHARED is deliberately not
    used, which would forbid that.
    """
    if _user32 is None:
        return None
    try:
        handle = _user32.LoadImageW(
            None, str(path), _IMAGE_ICON, size, size, _LR_LOADFROMFILE
        )
    except OSError:
        return None
    return handle or None
