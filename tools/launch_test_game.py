"""Request Test Document on the already-open SC2 Editor test copy."""

import ctypes
from ctypes import wintypes
import os
from pathlib import PureWindowsPath
import re

TEST_DOCUMENT = 170
WM_COMMAND = 0x0111
EDITOR_EXES = {"sc2editor.exe", "sc2editor_x64.exe"}


def win_api():
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    signatures = (
        (user.EnumWindows, wintypes.BOOL, (enum_proc, wintypes.LPARAM)),
        (user.GetWindow, wintypes.HWND, (wintypes.HWND, wintypes.UINT)),
        (user.IsWindowVisible, wintypes.BOOL, (wintypes.HWND,)),
        (user.IsWindowEnabled, wintypes.BOOL, (wintypes.HWND,)),
        (user.IsIconic, wintypes.BOOL, (wintypes.HWND,)),
        (user.ShowWindow, wintypes.BOOL, (wintypes.HWND, ctypes.c_int)),
        (user.GetWindowTextW, ctypes.c_int, (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)),
        (user.GetWindowThreadProcessId, wintypes.DWORD, (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))),
        (user.PostMessageW, wintypes.BOOL, (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)),
        (kernel.OpenProcess, wintypes.HANDLE, (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)),
        (kernel.QueryFullProcessImageNameW, wintypes.BOOL,
         (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))),
        (kernel.CloseHandle, wintypes.BOOL, (wintypes.HANDLE,)),
    )
    for function, result, arguments in signatures:
        function.restype = result
        function.argtypes = arguments
    return user, kernel, enum_proc


def editor_window(map_stem):
    if os.name != "nt":
        raise ValueError("实机启动需要已打开银河编辑器的 Windows。")
    user, kernel, enum_proc = win_api()
    title_match = re.compile(r"(?<![\w-])" + re.escape(map_stem) + r"(?![\w-])", re.IGNORECASE)
    title = ctypes.create_unicode_buffer(2048)
    path = ctypes.create_unicode_buffer(32768)
    found = []

    @enum_proc
    def visit(window, _):
        if (user.GetWindow(window, 4) or not user.IsWindowVisible(window)
                or not user.IsWindowEnabled(window)):
            return True
        if not user.GetWindowTextW(window, title, len(title)) or not title_match.search(title.value):
            return True
        if "*" in title.value:
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        process = kernel.OpenProcess(0x1000, False, pid)
        if process:
            try:
                length = wintypes.DWORD(len(path))
                if (kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length))
                        and PureWindowsPath(path.value).name.lower() in EDITOR_EXES):
                    found.append((window, pid.value))
            finally:
                kernel.CloseHandle(process)
        return True

    user.EnumWindows(visit, 0)
    if len(found) != 1:
        raise ValueError(f"请在银河编辑器中打开并保存唯一的「{map_stem}」测试副本，关闭弹窗后重试。")
    return found[0]


def request_test_document(map_stem, expected):
    if editor_window(map_stem) != expected:
        raise ValueError("银河编辑器中的活动地图已变更。")
    user, _, _ = win_api()
    window, _ = expected
    if user.IsIconic(window):
        user.ShowWindow(window, 9)
    if not user.PostMessageW(window, WM_COMMAND, TEST_DOCUMENT, 0):
        raise OSError(ctypes.get_last_error(), "银河编辑器未接受测试命令")
