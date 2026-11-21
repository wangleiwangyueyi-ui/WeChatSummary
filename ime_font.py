"""Match the Windows IME's native composition font to a search entry."""
import ctypes
from ctypes import wintypes
from functools import lru_cache
import sys

_IME_START = 0x010D


class LogFont(ctypes.Structure):
    _fields_ = [
        ('height', wintypes.LONG),
        ('width', wintypes.LONG),
        ('escapement', wintypes.LONG),
        ('orientation', wintypes.LONG),
        ('weight', wintypes.LONG),
        ('italic', wintypes.BYTE),
        ('underline', wintypes.BYTE),
        ('strikeout', wintypes.BYTE),
        ('charset', wintypes.BYTE),
        ('out_precision', wintypes.BYTE),
        ('clip_precision', wintypes.BYTE),
        ('quality', wintypes.BYTE),
        ('pitch_family', wintypes.BYTE),
        ('face', wintypes.WCHAR * 32),
    ]


@lru_cache(maxsize=1)
def windows_api():
    imm = ctypes.WinDLL('imm32')
    common = ctypes.WinDLL('comctl32')
    user = ctypes.WinDLL('user32')
    user.GetFocus.restype = wintypes.HWND
    user.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    user.GetKeyboardLayout.restype = wintypes.HANDLE
    args = (wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
    callback = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, *args, ctypes.c_size_t, ctypes.c_size_t)

    imm.ImmGetContext.argtypes = [wintypes.HWND]
    imm.ImmGetContext.restype = wintypes.HANDLE
    imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm.ImmReleaseContext.restype = wintypes.BOOL
    for function in (imm.ImmGetCompositionFontW, imm.ImmSetCompositionFontW):
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(LogFont)]
        function.restype = wintypes.BOOL
    common.SetWindowSubclass.argtypes = [wintypes.HWND, callback, ctypes.c_size_t, ctypes.c_size_t]
    common.SetWindowSubclass.restype = wintypes.BOOL
    common.RemoveWindowSubclass.argtypes = [wintypes.HWND, callback, ctypes.c_size_t]
    common.RemoveWindowSubclass.restype = wintypes.BOOL
    common.DefSubclassProc.argtypes = args
    common.DefSubclassProc.restype = ctypes.c_ssize_t
    return imm, common, user, callback


def set_chinese_composition_font(widget, family, pixel_size):
    if sys.platform != 'win32':
        return
    imm, common, user, callback_type = windows_api()
    subclass_id = widget.winfo_id()
    font = LogFont(weight=400, charset=1, face=family[:31])
    previous_fonts = {}
    attached = None

    def apply_font(hwnd):
        if ((user.GetKeyboardLayout(0) or 0) & 0x3FF) != 4:
            return
        context = imm.ImmGetContext(hwnd)
        if not context:
            return
        try:
            if context not in previous_fonts:
                previous = LogFont()
                if imm.ImmGetCompositionFontW(context, ctypes.byref(previous)):
                    previous_fonts[context] = previous
            imm.ImmSetCompositionFontW(context, ctypes.byref(font))
        finally:
            imm.ImmReleaseContext(hwnd, context)

    @callback_type
    def procedure(handle, message, wparam, lparam, _, _ref):
        if message == _IME_START:
            apply_font(handle)
        return common.DefSubclassProc(handle, message, wparam, lparam)

    def update_size(_):
        font.height = -max(1, round(pixel_size()))

    def focus_out(_):
        nonlocal attached
        if attached:
            common.RemoveWindowSubclass(attached, procedure, subclass_id)
            context = imm.ImmGetContext(attached)
            if context:
                try:
                    previous = previous_fonts.get(context)
                    if previous is not None:
                        imm.ImmSetCompositionFontW(context, ctypes.byref(previous))
                finally:
                    imm.ImmReleaseContext(attached, context)
        attached = None
        previous_fonts.clear()

    def focus_in(event):
        nonlocal attached
        update_size(event)
        # Tk keeps native keyboard focus on the containing window.
        handle = user.GetFocus()
        if handle and handle != attached:
            focus_out(event)
            if common.SetWindowSubclass(handle, procedure, subclass_id, 0):
                attached = handle
        if attached:
            apply_font(attached)

    widget.bind('<Configure>', update_size, add='+')
    widget.bind('<FocusIn>', focus_in, add='+')
    widget.bind('<FocusOut>', focus_out, add='+')
    widget.bind('<Destroy>', focus_out, add='+')
