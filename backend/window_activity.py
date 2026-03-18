import win32gui, win32api, win32con
import win32com.client # Module that deals with Component Object Module, the way Windows programs interact
import time

# Getting and utilizing the window handle of what we want the user to focus on:
target_window = "Firefox Nightly"
hwnd = win32gui.FindWindow(None, target_window)

# Making an existing window pop up
def focus_keeper(pop_up_window):
    # Windows blocks background processes with Focus Protection (like time based window pop-ups)
    shell = win32com.client.Dispatch("WScript.Shell") # "Dispatch" tells Windows to find a way to control "WScript.Shell", which deals with Windows' keyboard inputs (among many other things)
    hwnd = win32gui.FindWindow(None, pop_up_window) # Gets handle of target window
    if hwnd:
        shell.SendKeys("%") # Sends "Alt" key (% = Alt in Windows Shell API) to simulate user typing, bypassing Focus Protection
    # Unhides a minimized window
        if win32gui.IsIconic(hwnd): 
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd) # Puts the window to the foreground (pop-up)
    else:
        print(f"Failed to focus \"{pop_up_window}\". Perhaps the window is closed?")

# Looking through all visible windows to get their class and title, then determining if they're distraction windows
def game_hunter(hwnd, ctx):
    window_title = win32gui.GetWindowText(hwnd)
    window_class =  win32gui.GetClassName(hwnd)
    game_title = ["- Steam", "Version", "Launcher","v1.0", "Early Access", "Alpha", "Beta", "Made with Unity", "Unreal Engine", "CryEngine"]
    game_class = ["UnityWndClass", "UnrealWindow", "GodotEngine", "Valve001", "Direct3DWindowClass", "USetupWindowClass", "YYGameMakerYY", "GAMINGSERVICESUI_HOSTING_WINDOW_CLASS","Battle.net Desktop App", "RGSS Player", "DirectDraw", "Direct3D", "LWJGL", "OgreGLWindow", "SDL_app", "GLFW30", "AppWindowClass"]
    social_title = ["Facebook", "Twitter", "Instagram", "Reddit", "YouTube", "TikTok", "Twitch", "Pinterest", "LinkedIn"]
    # Filter for visible windows with titles
    if win32gui.IsWindowVisible(hwnd) and window_title:
        print(f"HWND: {hwnd} | Title: {window_title} | Class: {window_class}")
        is_game = (window_class in game_class or any(keyword in window_title for keyword in game_title))
        if is_game:
            print("This is a game")
            #win32gui.SetWindowText(hwnd, "YOU SHOULDN'T BE HERE") # Changing window name
            ctx.append(window_title) # Adds the name of a game window to "found_distractions", which is the 'ctx' of .EnumWindows
            focus_keeper("Firefox Nightly") # Pops up the target window
            #return False # Tells .EnumWindows to stop once a game is found
        is_social_media = (any(keyword in window_title for keyword in social_title))
        if is_social_media:
            print("This is social media")
            ctx.append(window_title) # Adds the name of a social media window to "found_distractions"
            focus_keeper("Firefox Nightly") # Pops up the target window
    return True 

# Scan windows every 10 seconds to check if the user is still distracted
def regular_scan():
    while True:
        print("Hunting for distractions...")
        found_distractions = []
        win32gui.EnumWindows(game_hunter, found_distractions) # As I understand it: the first parameter (game_hunter) is for what happens during window enumeration. The second parameter is the 'ctx', which carries info from window enumeration
        if len(found_distractions) == 0:
            print("No distractions detected, good job continuing the grind")
        else:
            print(f"Active distraction(s): {found_distractions}. Hunting again in 10 seconds...")
        time.sleep(10)
if __name__ == "__main__":
    regular_scan()

if hwnd:
    print(f"Found existing window \"{target_window}\" with handle: {hwnd}")

    # Getting window name:
    print(win32gui.GetWindowText(hwnd))

    # Getting window class:
    class_name = win32gui.GetClassName(hwnd)
    print(f"Window Class: {class_name}")

    # Getting handle of window's icons in hexidecimal:
    GCLP_HICON = -14
    hicon = win32gui.GetClassLong(hwnd, GCLP_HICON)
    # Masking with 0xFFFFFFFF (for 32-bit) or 0xFFFFFFFFFFFFFFFF (for 64-bit) 
    # forces Python to show the unsigned equivalent.
    print(f"Icon Handle (Hex): {hex(hicon & 0xFFFFFFFFFFFFFFFF)}")

    # Getting "Handle to Device Context" to allow drawing on a window:
    hdc = win32gui.GetDC(hwnd)
    win32gui.DrawIcon(hdc, 10, 10, hicon)
    
    # Getting window color:
    window_color = win32con.COLOR_WINDOW
    print(window_color)

else:
    print(f"Window \"{target_window}\" not found")

# Other method for making a window "pop up" based on input (bringing it to the foreground):
def pop_up_window(window_name):
    while hwnd:
        if window_name.lower() in win32gui.GetWindowText(hwnd).lower():
            # If window is minimized it is restored:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Brings window to foreground:
            win32gui.SetForegroundWindow(hwnd)
            break
        else:
            print("No such window was found")
            break
#pop_up_window("Firefox Nightly")

# Creates a WNDCLASS object
wc = win32gui.WNDCLASS()

# Making a window:
# Callback function to process the Windows messages
def window_proc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_CLOSE:
        win32gui.DestroyWindow(hwnd)
    elif msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def create_window():
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = window_proc
    wc.lpszClassName = "PythonWindowClass"
    # BRUSH color manages window color:
    wc.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)

    class_atom = win32gui.RegisterClass(wc)

    hwnd = win32gui.CreateWindow(
        class_atom,
        "FOCUS!!!",
        win32con.WS_OVERLAPPEDWINDOW,
        100, 100, 500, 400,
        0, 0, 0, None
    )

    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
    win32gui.UpdateWindow(hwnd)

    message = win32gui.GetMessage(None, 0, 0)
    while message[0]:
        win32gui.TranslateMessage(message[1])
        win32gui.DispatchMessage(message[1])
        message = win32gui.GetMessage(None, 0, 0)


if __name__ == "__main__":
    create_window()