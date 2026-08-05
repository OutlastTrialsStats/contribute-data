"""Windows display metrics and DPI awareness.

Both live here because they are the same problem seen twice: Windows scales anything that does
not ask for the right size itself. Awareness has to be set before the first window exists, which
is why enable_dpi_awareness() is called from __main__ rather than from whoever needs it.

The user32 and shcore handles are created with WinDLL rather than taken from ctypes.windll.
ctypes caches windll instances and the function pointers hanging off them, so reusing them would
share argtypes and errcheck with pystray, which configures the very same functions.
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

#: What the notification area asks for at 100% scaling, and what to assume if Windows will not say.
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

    Newest API first, because each older one is coarser than the last. All of them fail once
    awareness is already set — by an embedding host or a manifest — which is not an error.
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
    """The edge length the notification area draws icons at: 16 at 100%, 24 at 150%, 32 at 200%.

    Reports the primary monitor's value, which is the one the taskbar lives on.
    """
    if _user32 is None:
        return DEFAULT_SMALL_ICON
    try:
        return _user32.GetSystemMetrics(SM_CXSMICON) or DEFAULT_SMALL_ICON
    except OSError:
        return DEFAULT_SMALL_ICON


def load_icon(path: Path, size: int) -> int | None:
    """An HICON of exactly `size`, taken from the matching frame in an .ico file.

    None when the file is missing or holds no usable frame. The caller owns the handle and must
    pass it to DestroyIcon; LR_SHARED is deliberately not used, which would forbid that.
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
