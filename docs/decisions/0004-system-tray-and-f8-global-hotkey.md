# [ADR-0004] System Tray Background Execution & System-Wide F8 Quick-Toggle Hotkey

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author(s):** Systems Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians continuously switch between active troubleshooting environments (RDP sessions, hypervisors, web consoles, command prompts) and their ticket scratchpad. 

Having to search for TechPad on the Windows taskbar or re-launch the application from the start menu creates friction during active support calls. Furthermore, if a technician accidentally clicks the window close button (`✕`), terminating the application discards active stopwatch billing timers and requires a cold reboot of the workspace.

---

## 2. Decision Drivers
- **Instantaneous Access:** Technicians need single-keystroke access (`F8`) to pop the scratchpad to the foreground from any application without reaching for the mouse.
- **Toggle Ergonomics:** Pressing `F8` while the application is active should immediately minimize it out of the way; pressing `F8` while minimized or hidden should restore and focus the editor.
- **Accidental Close Protection:** Closing the main window should minimize the app to the Windows system tray rather than terminating the process.
- **Resource Footprint:** Background execution in the tray must consume negligible memory and zero CPU while idle.

---

## 3. Considered Options
1. **Option 1 (Standard Windows Minimize/Maximize Only):** Keep the window on the taskbar with standard `Alt+Tab`.
   - *Problem:* Taskbar clutter; closing the window still terminates the app.
2. **Option 2 (Low-Level Keyboard Hook via `SetWindowsHookEx`):** Install a global keyboard hook to listen for F8.
   - *Problem:* Triggers heuristic alerts in corporate Antivirus and EDR agents (e.g. Defender, CrowdStrike, SentinelOne).
3. **Option 3 (System Tray Integration + Win32 `RegisterHotKey` with `QAbstractNativeEventFilter`):**
   - Configure `QApplication.setQuitOnLastWindowClosed(False)`.
   - Intercept `closeEvent` to hide the window to `QSystemTrayIcon`.
   - Register a system-wide global hotkey on `F8` using `user32.dll:RegisterHotKey` and process `WM_HOTKEY` (0x0312) events via a native Qt event filter.

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (System Tray Integration + Win32 `RegisterHotKey` with `QAbstractNativeEventFilter`).

### Rationale
- **OS-Sanctioned Global Hotkey:** `RegisterHotKey` is Windows' officially supported API for global hotkeys (identical to Windows Terminal or system shortcuts). It never triggers antivirus warnings because it registers a single virtual key code (`VK_F8 = 0x77`) without logging keystrokes.
- **Foreground Activation Rights:** When a global hotkey registered with `RegisterHotKey` is triggered, Windows automatically grants the target application permission to call `SetForegroundWindow`, overcoming Windows' focus-stealing prevention.
- **Persistent Tray Lifecycle:** By setting `app.setQuitOnLastWindowClosed(False)`, closing the window simply hides it (`self.hide()`), keeping active ticket timers and SQLite connections intact. Complete termination is reserved for explicit user action via the tray menu ("Quit TechPad").

---

## 5. Consequences

### Positive Consequences
- **Zero Friction Summoning:** Pressing `F8` instantly brings TechPad to the front and places the cursor directly in the active ticket note editor.
- **Rapid Hiding:** Pressing `F8` while TechPad is active immediately minimizes it, allowing the technician to resume interacting with their background session.
- **Crash/Data Loss Prevention:** Accidentally clicking `✕` never kills background timers or interrupts unsaved drafts.

### Negative Consequences / Trade-offs
- **Windows Dependency for Global Hotkey:** `RegisterHotKey` is Win32-specific. On non-Windows platforms, the application falls back gracefully to in-window `F8` handling via `QShortcut`.

---

## 6. Implementation Notes & Validation
- **Global Hotkey Manager:** `src/core/global_hotkey.py` (`GlobalHotkeyManager`, `WinNativeHotkeyFilter`).
- **System Tray:** `src/ui/components/system_tray.py` (`TechPadSystemTray`, `get_or_create_app_icon`).
- **Window Toggle Logic:** `src/ui/main_window.py` (`toggle_window_visibility`, `closeEvent`, `quit_application`).
- **Automated Validation:** Verified via `tests/test_ui_integration.py` (`test_ui_system_tray_close_to_tray`, `test_ui_f8_toggle_window_visibility`, `test_global_hotkey_manager_lifecycle`).

