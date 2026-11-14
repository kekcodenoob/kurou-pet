"""Which windows are open, which one you're looking at, and whether it's a distraction.

Windows-only: windows are listed straight from the Win32 API (the same ones
Alt+Tab shows), so apps' hidden helper windows never appear. A browser window's
title only shows its current tab, so its other tabs are read with UI Automation.

A browser window's title is "<page title> - <browser>", and sites put their
name as its own piece of the page title ("cats - YouTube", "Hulu | Home",
"Home / X"). So a page only counts as a site when the site's name is a whole
piece at the start or end, which keeps searches ("apple tv - Google Search")
and articles ("YouTube - Wikipedia") from counting.
"""

import ctypes
import os
import re
import sys
from ctypes import wintypes

import pyautogui
import pywinctl as pwc

# Win32 setup
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GW_OWNER = 4
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# Apps
# Background/system processes that own windows but aren't something you'd work in
IGNORED_APPS = {
    "explorer.exe",
    "textinputhost.exe",
    "applicationframehost.exe",
    "systemsettings.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "lockapp.exe",
}

# Apps where every window is a distraction: always count, never a focus app
DISTRACTION_APPS = {
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games",
    "riotclientservices.exe": "Riot Client",
    "battle.net.exe": "Battle.net",
    "galaxyclient.exe": "GOG Galaxy",
    "ubisoftconnect.exe": "Ubisoft Connect",
    "eadesktop.exe": "EA app",
}

BROWSERS = {
    "firefox.exe", "chrome.exe", "msedge.exe", "brave.exe", "opera.exe", "opera_gx.exe",
    "vivaldi.exe", "chromium.exe", "librewolf.exe", "waterfox.exe", "zen.exe", "floorp.exe",
    "arc.exe", "thorium.exe",
}

# Ends of browser window titles, e.g. "... — Firefox Nightly"
BROWSER_NAMES = {
    "mozilla firefox", "firefox", "firefox nightly", "firefox developer edition", "firefox beta",
    "google chrome", "chrome", "microsoft edge", "brave", "opera", "vivaldi", "chromium",
    "librewolf", "waterfox", "zen browser", "zen", "floorp", "arc", "thorium",
}

# Focus App menu label for a browser window on a distracting tab that also has
# tabs that aren't (the pet can switch it back to one of those)
DISTRACTING_TAB_LABEL = "Distracting tab in focused browser"
TAB_SEARCH_DEPTH = 8  # How deep to look for a browser's tab strip


# Distraction rules
# Sites: platform -> names that appear as their own piece of a page title
SITES = {
    "YouTube": ["YouTube"],
    "Netflix": ["Netflix"],
    "Reddit": ["Reddit"],
    "Twitter": ["Twitter", "X"],
    "Facebook": ["Facebook"],
    "Instagram": ["Instagram"],
    "TikTok": ["TikTok"],
    "Twitch": ["Twitch"],
    "Pinterest": ["Pinterest"],
    "Hulu": ["Hulu"],
    "Disney+": ["Disney+"],
    "Prime Video": ["Prime Video"],
    "HBO Max": ["HBO Max"],
    "Crunchyroll": ["Crunchyroll"],
    "Peacock": ["Peacock"],
    "Paramount+": ["Paramount+"],
    "Apple TV": ["Apple TV", "Apple TV+"],
    "Tubi": ["Tubi"],
}

# Pages that only mention a site: search results and reference pages
NOT_THE_SITE = {
    "google search", "google", "bing", "duckduckgo", "brave search", "yahoo search",
    "yahoo search results", "ecosia", "startpage", "startpage search results", "search",
    "search results", "wikipedia", "google news", "google docs", "google drive",
}

# Game windows (outside browsers), matched as whole words in the title
GAME_TITLES = [
    "Steam",
    "Launcher",
    "v1.0",
    "Early Access",
    "Alpha",
    "Beta",
    "Made with Unity",
    "Unreal Engine",
    "CryEngine",
    "DEMO",
    "Loading Bay",
    "DELTARUNE",
]
GAME_PATTERN = re.compile(r"(?<!\w)(" + "|".join(re.escape(g) for g in GAME_TITLES) + r")(?!\w)", re.I)

# Pieces of a title: " - ", " | ", " — ", " • ", " · ", " / ", or ": "
TITLE_SEPARATORS = re.compile(r"\s+[-–—|•·/]\s+|:\s+")


def page_parts(title, browser):
    """Splits a window title into pieces, dropping the browser's name and "(3) " counts."""
    title = title.replace("​", "").strip()  # Edge puts a zero-width space in its name
    title = re.sub(r"^\(\d+\+?\)\s*", "", title)
    parts = [p.strip() for p in TITLE_SEPARATORS.split(title) if p.strip()]
    if browser:
        while len(parts) > 1 and parts[-1].lower() in BROWSER_NAMES:
            parts.pop()
        # Edge adds the profile: "Page - Personal - Microsoft Edge"
        if len(parts) > 1 and parts[-1].lower() in ("personal", "work"):
            parts.pop()
    return parts


def match_site(parts):
    """Platform whose own page this is (e.g. "YouTube"), or None."""
    if not parts:
        return None
    first, last = parts[0].lower(), parts[-1].lower()
    if last in NOT_THE_SITE or last.endswith(" at duckduckgo"):
        return None  # e.g. "apple tv - Google Search"
    for platform, names in SITES.items():
        for name in names:
            name = name.lower()
            if last == name or first == name:
                return platform
            # "Name (@user) • Instagram photos and videos"
            if len(name) > 1 and last.startswith(name + " "):
                return platform
    if any(re.fullmatch(r"r/\w+", p.lower()) for p in parts):
        return "Reddit"  # "Post title : r/python"
    return None


def match_distraction(app_name, title):
    """Platform a window belongs to (e.g. "YouTube", "Steam"), or None if it's not a distraction."""
    app = (app_name or "").lower()
    if app in DISTRACTION_APPS:
        return DISTRACTION_APPS[app]
    if not title:
        return None
    is_browser = app in BROWSERS
    platform = match_site(page_parts(title, is_browser))
    if platform or is_browser:
        return platform
    game = GAME_PATTERN.search(title)
    if game:
        return "Game Launcher" if game.group(1).lower() == "launcher" else game.group(1)
    return None


def is_distraction_app(app_name):
    return (app_name or "").lower() in DISTRACTION_APPS


# Reading windows
def _title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _process(hwnd):
    """(process id, exe name) of the app that owns a window."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return pid.value, ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return pid.value, os.path.basename(buffer.value)
        return pid.value, ""
    finally:
        kernel32.CloseHandle(handle)


def _shows_in_alt_tab(hwnd):
    """True for real app windows; False for hidden, owned, tool, and cloaked helper windows."""
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return not cloaked.value


def app_windows():
    """[(hwnd, exe name, title)] for every window Alt+Tab would show, front to back."""
    found = []

    def visit(hwnd, _):
        if _shows_in_alt_tab(hwnd):
            title = _title(hwnd)
            if title.strip():
                found.append((hwnd, _process(hwnd)[1], title))
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return found


def active_window():
    """(exe name, title, belongs to this process) of the window the user is in."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", "", False
    pid, app = _process(hwnd)
    return app, _title(hwnd), pid == os.getpid()


# Browser tabs
_uia = None


def _automation():
    """(UIAutomationClient module, IUIAutomation) created on first use, or None if unavailable."""
    global _uia
    if _uia is None:
        try:
            import comtypes.client

            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient

            _uia = (
                UIAutomationClient,
                comtypes.client.CreateObject(
                    UIAutomationClient.CUIAutomation, interface=UIAutomationClient.IUIAutomation
                ),
            )
        except Exception as e:
            print(f"UI Automation unavailable, so browser tabs won't be read: {e}")
            _uia = False
    return _uia or None


def browser_tabs(hwnd):
    """[(tab title, tab element)] for a browser window, or [] if they can't be read.

    Walks down from the window a level at a time, skipping web page contents,
    until it reaches the tab strip.
    """
    automation = _automation()
    if not automation:
        return []
    uia_types, uia = automation
    try:
        walker = uia.ControlViewWalker
        level = [uia.ElementFromHandle(hwnd)]
        for _ in range(TAB_SEARCH_DEPTH):
            tabs, next_level = [], []
            for element in level:
                child = walker.GetFirstChildElement(element)
                while child:
                    kind = child.CurrentControlType
                    if kind == uia_types.UIA_TabItemControlTypeId:
                        if child.CurrentName.strip():
                            tabs.append((child.CurrentName, child))
                    elif kind != uia_types.UIA_DocumentControlTypeId:
                        next_level.append(child)
                    child = walker.GetNextSiblingElement(child)
            if tabs:
                return tabs
            level = next_level
    except Exception as e:
        print(f"Reading browser tabs failed: {e}")
    return []


def select_tab(tab_element):
    """Switches a browser window to the given tab. Returns True if it worked."""
    automation = _automation()
    if not automation:
        return False
    uia_types, _ = automation
    try:
        pattern = tab_element.GetCurrentPattern(uia_types.UIA_SelectionItemPatternId)
        pattern.QueryInterface(uia_types.IUIAutomationSelectionItemPattern).Select()
        return True
    except Exception as e:
        print(f"Switching tabs failed: {e}")
        return False


def work_tab(app_name, hwnd):
    """(title, element) of a tab in this browser window that isn't a distraction, or None."""
    for title, element in browser_tabs(hwnd):
        if is_work_window(app_name, title):
            return title, element
    return None


# What the pet uses
def get_active_distractions():
    """[(platform, title)] if the window the user is in is a distraction, [] if not,
    or None if it's the pet's own window (which says nothing about the user).
    """
    try:
        app, title, own_window = active_window()
    except Exception as e:
        print(f"Window scan error: {e}")
        return []
    if own_window:
        return None
    platform = match_distraction(app, title)
    return [(platform, title)] if platform else []


def is_work_window(app_name, title):
    """A window the pet can send you back to: real, and not a distraction."""
    return bool(title.strip()) and not match_distraction(app_name, title)


def _usable_apps():
    """{exe name: [(hwnd, title)]} for apps that could be a focus app."""
    own_exe = os.path.basename(sys.executable).lower()
    apps = {}
    for hwnd, app, title in app_windows():
        lowered = app.lower()
        if not app or lowered in IGNORED_APPS or lowered == own_exe or is_distraction_app(app):
            continue
        apps.setdefault(app, []).append((hwnd, title))
    return apps


def list_open_apps():
    """{exe name: label} for the Focus App menu.

    The label is the app's first window that isn't a distraction. A browser
    window on a distracting tab still counts if it has a tab that isn't, and is
    labeled DISTRACTING_TAB_LABEL. Apps with only distractions are left out.
    """
    try:
        apps = _usable_apps()
    except Exception as e:
        print(f"App scan error: {e}")
        return {}

    open_apps = {}
    for app, windows in apps.items():
        work = next((title for _, title in windows if is_work_window(app, title)), None)
        if work:
            open_apps[app] = work
        elif app.lower() in BROWSERS and any(work_tab(app, hwnd) for hwnd, _ in windows):
            open_apps[app] = DISTRACTING_TAB_LABEL
    return open_apps


def find_work_window(app_name):
    """(pywinctl Window, tab element to switch to or None) for a part of `app_name`
    that isn't a distraction, or None if there isn't one.
    """
    if is_distraction_app(app_name):
        return None
    windows = _usable_apps().get(app_name, [])
    for hwnd, title in windows:
        if is_work_window(app_name, title):
            return pwc.Window(hwnd), None
    # A browser on a distracting tab: switch it to one of its other tabs
    if app_name.lower() in BROWSERS:
        for hwnd, _ in windows:
            tab = work_tab(app_name, hwnd)
            if tab:
                return pwc.Window(hwnd), tab[1]
    return None


def focus_keeper(app_name):
    """Brings a non-distraction window (or browser tab) of the user's focus app to the front."""
    # Windows only lets a process steal focus after a keypress, so tap Alt first.
    pyautogui.press("alt")
    try:
        found = find_work_window(app_name)
        if found is None:
            print(f"Couldn't focus '{app_name}': nothing open in it that isn't a distraction.")
            return
        target, tab = found
        if target.isMinimized:
            target.restore()
        if tab is not None:
            select_tab(tab)
        target.activate()
    except Exception as e:
        print(f"Focus error: {e}")
