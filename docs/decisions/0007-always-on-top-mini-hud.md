# [ADR-0007] Always-on-Top Mini-HUD Mode for Remote Workflows

- **Status:** Accepted
- **Date:** 2026-11-02
- **Author(s):** Systems Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians and MSP engineers routinely troubleshoot systems across remote desktop software (RDP, ScreenConnect, TeamViewer, AnyDesk, Hyper-V/VMware consoles). In these scenarios:
1. Standard full-size windows (1100×750) obscure the remote machine's display.
2. Interacting with the remote session immediately sends normal background note windows behind the remote desktop client.
3. Technicians need a fast, non-intrusive way to keep the active ticket notes, troubleshooting checklists, and billing stopwatch visible and editable on top of full-screen remote sessions.

---

## 2. Decision Drivers
- **Minimal Screen Footprint:** Must shrink to a compact HUD (~440×280) so it occupies less than 15% of a 1080p display.
- **Always-on-Top:** Must float above external windows (`Qt.WindowStaysOnTopHint`) even while typing in remote sessions.
- **Zero Disruption to Active Work:** Active scratchpad notes, stopwatch timing, checklists, and auto-saves must continue uninterrupted.
- **Instant Toggle & State Preservation:** Must toggle via a fast hotkey (`Alt+T`) and seamlessly restore exact window geometry, toolbars, drawer, and split-view panes when returning to normal view.

---

## 3. Decision Outcome
**Chosen Solution:** Implement Always-on-Top Mini-HUD Mode toggled via `Alt+T`, a dedicated ribbon button `📌`, a status bar button `📌 HUD (Alt+T)`, and system tray integration.

### Geometry & Component Transitions
1. **When Entering Mini-HUD Mode (`_enable_mini_hud`):**
   - Saves current window geometry (`saveGeometry()`) and component visibility states.
   - Activates `Qt.WindowStaysOnTopHint`.
   - Relaxes minimum window constraints from 800×500 to 340×200.
   - Resizes window to compact dimensions (440×280).
   - Hides Row 1 formatting ribbon, history drawer, and secondary split-pane.
   - Updates window title to `📌 [HUD] T-Notes — #<ticket_number>`.
2. **When Exiting Mini-HUD Mode (`_disable_mini_hud`):**
   - Deactivates `Qt.WindowStaysOnTopHint`.
   - Restores minimum size to 800×500.
   - Restores exact previous window geometry (`restoreGeometry()`).
   - Restores previous visibility of Row 1 ribbon, history drawer, and split-view panes.
   - Restores standard application window title.

---

## 4. Consequences

### Positive Consequences
- Technicians can take notes and monitor timers during RDP and remote console sessions without window layering battles.
- Combines seamlessly with the opacity slider (60%–100%) for see-through capability over background remote consoles.
- Full keyboard and mouse access to the active note remains active in HUD mode.

