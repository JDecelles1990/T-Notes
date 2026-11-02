# [ADR-0002] Win32 Idle Inactivity & Workstation Lock Auto-Pause for Billing

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author(s):** Systems Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians rely on T-Notes to track active troubleshooting duration per ticket tab for MSP and client billing. However, technicians frequently step away from their desks, get pulled into meetings, or lock their workstations (`Win + L`) without pausing the stopwatch. 

Relying solely on window focus loss (`focusOutEvent` or `QWindow::activeChanged`) is inadequate because technicians frequently work in remote desktop sessions, web portals, command prompts, or hypervisors while keeping their ticket timer running. Conversely, leaving timers running while absent produces inflated, inaccurate billing figures that compromise client trust and PSA accounting.

---

## 2. Decision Drivers
- **Billing Accuracy:** Timers must measure real troubleshooting effort and automatically pause when the technician is genuinely absent.
- **Support for Multi-Window Workflows:** The stopwatch must continue running while the technician actively uses external tools (PowerShell, SSH terminals, browser consoles, RDP).
- **Zero Kernel Driver / Hook Footprint:** Solution must not require low-level keyboard hooks (which trigger antivirus / EDR alerts like CrowdStrike or Defender).
- **Negligible CPU Overhead:** Inactivity checks must execute in sub-millisecond intervals without perceptible performance impact.

---

## 3. Considered Options
1. **Option 1 (Qt Focus & Active Window Tracking):** Pause timer whenever the T-Notes window loses focus.
   - *Problem:* Breaks the core technician workflow where T-Notes sits in the background or on a second monitor while working in remote tools.
2. **Option 2 (Low-Level Windows Hook via `SetWindowsHookEx`):** Monitor all global keystrokes and mouse events system-wide.
   - *Problem:* Flagged by enterprise EDR/antivirus agents as keylogging behavior; security liability.
3. **Option 3 (Win32 `user32.dll` Polling via `ctypes`):** Query `GetLastInputInfo` for system-wide idle milliseconds and `OpenInputDesktop` for workstation lock status on a 1-second timer tick.

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (Win32 `user32.dll` Polling via `ctypes`).

### Rationale
- **System-Wide Activity Without Keylogging:** `GetLastInputInfo` retrieves the tick count of the last user interaction across the entire OS without inspecting the content of keys or mouse clicks. This is fully compliant with enterprise security standards.
- **Lock Screen Detection:** When a technician locks their workstation (`Win + L`), `OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)` fails, allowing the app to instantaneously recognize the locked state.
- **Zero Third-Party Dependencies:** Python's standard `ctypes` module accesses `user32.dll` directly without requiring `pywin32` or external C extensions.
- **Microsecond Execution:** A single call to `GetLastInputInfo` completes in less than 5 microseconds. Polling once per second introduces zero measurable CPU load.

---

## 5. Consequences

### Positive Consequences
- **Automated Billing Protection:** Active timers automatically freeze after 300 seconds (5 minutes) of inactivity or upon screen lock.
- **Preserved Technician Flow:** Timers keep running seamlessly while typing in terminals, browsers, and remote sessions.
- **Clear State Feedback:** When auto-paused, the stopwatch display indicates the paused state and resumes smoothly upon user intervention or tab change.

### Negative Consequences / Trade-offs
- **Windows-Specific Implementation:** `user32.dll` calls require a Windows host. On non-Windows platforms, the method safely catches `AttributeError` or `OSError` and defaults to standard manual timer controls.

---

## 6. Implementation Notes & Validation
- **Implementation:** `src/ui/components/stopwatch_widget.py` (`TicketStopwatchWidget._check_system_idle`).
- **Formatting & Billing Logic:** `src/services/stopwatch_service.py` (`StopwatchService.format_time`).
- **Persistence:** `src/services/scratchpad_service.py` (`update_elapsed_time`).
- **Automated Validation:** Verified via `tests/test_stopwatch_service.py` and `tests/test_ui_integration.py`.

