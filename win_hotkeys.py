"""Windows global hotkeys via RegisterHotKey on a dedicated message thread."""



from __future__ import annotations



import ctypes

import queue

import sys

import threading

from ctypes import wintypes

from typing import Callable



if sys.platform != "win32":

    raise ImportError("win_hotkeys is Windows-only")



user32 = ctypes.windll.user32

kernel32 = ctypes.windll.kernel32



WM_HOTKEY = 0x0312

PM_REMOVE = 0x0001

MOD_ALT = 0x0001

MOD_CONTROL = 0x0002

MOD_SHIFT = 0x0004

MOD_NOREPEAT = 0x4000



VK_T = 0x54

VK_H = 0x48

VK_J = 0x4A



ID_TYPE = 1

ID_HUMANIZE_SHIFT = 2

ID_HUMANIZE_ALT = 3

ID_TYPE_ALT = 4

ID_HUMANIZE_ALT2 = 5

ID_HUMANIZE_J = 6



user32.RegisterHotKey.argtypes = [

    wintypes.HWND,

    wintypes.INT,

    wintypes.UINT,

    wintypes.UINT,

]

user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, wintypes.INT]

user32.UnregisterHotKey.restype = wintypes.BOOL





class POINT(ctypes.Structure):

    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]





class MSG(ctypes.Structure):

    _fields_ = [

        ("hwnd", wintypes.HWND),

        ("message", wintypes.UINT),

        ("wParam", wintypes.WPARAM),

        ("lParam", wintypes.LPARAM),

        ("time", wintypes.DWORD),

        ("pt", POINT),

    ]





user32.PeekMessageW.argtypes = [

    ctypes.POINTER(MSG),

    wintypes.HWND,

    wintypes.UINT,

    wintypes.UINT,

    wintypes.UINT,

]

user32.PeekMessageW.restype = wintypes.BOOL



BindingSpec = tuple[int, int, int, Callable[[], None]]

BindResult = tuple[int, bool, int]





def hotkey_error_text(code: int) -> str:

    if code == 1409:

        return "already used by another app (or a second Auto Typer instance)"

    if code == 1408:

        return "invalid hotkey"

    if code:

        return f"Win32 error {code}"

    return "unknown error"





class WinHotkeys:

    """RegisterHotKey(NULL) on a worker thread; run callbacks on the Tk main thread."""



    def __init__(self, root) -> None:

        self.root = root

        self._callbacks: dict[int, Callable[[], None]] = {}

        self._cmd_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._result_queue: queue.Queue[list[BindResult]] = queue.Queue()

        self._main_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        self._thread = threading.Thread(target=self._message_loop, name="WinHotkeys", daemon=True)

        self._thread_started = False

        self._pump_started = False



    def clear(self) -> None:

        self._cmd_queue.put(("clear", None))



    def stop(self) -> None:

        self._cmd_queue.put(("stop", None))



    def apply(self, specs: list[BindingSpec]) -> list[BindResult]:

        """Replace all hotkeys. Each spec is (id, modifiers, vk, callback)."""

        if not self._thread_started:

            self._thread.start()

            self._thread_started = True

        self._callbacks.clear()

        for hotkey_id, _mod, _vk, cb in specs:

            self._callbacks[hotkey_id] = cb

        payload = [(hotkey_id, mod | MOD_NOREPEAT, vk) for hotkey_id, mod, vk, _cb in specs]

        self._cmd_queue.put(("apply", payload))

        try:

            results = self._result_queue.get(timeout=5.0)

        except queue.Empty:

            results = [(hotkey_id, False, 0) for hotkey_id, _, _ in payload]

        self._ensure_pump()

        return results



    def start(self) -> list[str]:

        self._ensure_pump()

        return []



    def _ensure_pump(self) -> None:

        if self._pump_started:

            return

        self._pump_started = True

        try:

            self.root.after(0, self._drain_main_queue)

        except Exception:  # noqa: BLE001

            pass



    def _drain_main_queue(self) -> None:

        while True:

            try:

                cb = self._main_queue.get_nowait()

            except queue.Empty:

                break

            try:

                cb()

            except Exception:  # noqa: BLE001

                pass

        try:

            self.root.after(40, self._drain_main_queue)

        except Exception:  # noqa: BLE001

            pass



    def _message_loop(self) -> None:

        registered: list[int] = []

        null_hwnd = wintypes.HWND(0)



        def unregister_all() -> None:

            for hotkey_id in registered:

                user32.UnregisterHotKey(null_hwnd, hotkey_id)

            registered.clear()



        while True:

            try:

                cmd, data = self._cmd_queue.get(timeout=0.02)

            except queue.Empty:

                cmd = None

                data = None



            if cmd == "stop":

                unregister_all()

                break

            if cmd == "clear":

                unregister_all()

            elif cmd == "apply":

                unregister_all()

                results: list[BindResult] = []

                for hotkey_id, modifiers, vk in data:  # type: ignore[union-attr]

                    kernel32.SetLastError(0)

                    ok = bool(user32.RegisterHotKey(null_hwnd, hotkey_id, modifiers, vk))

                    err = int(kernel32.GetLastError()) if not ok else 0

                    if ok:

                        registered.append(hotkey_id)

                    results.append((hotkey_id, ok, err))

                self._result_queue.put(results)



            msg = MSG()

            while user32.PeekMessageW(

                ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE

            ):

                cb = self._callbacks.get(int(msg.wParam))

                if cb:

                    self._main_queue.put(cb)


