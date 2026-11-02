# [ADR-0003] Application-Level Event Filtering for Hardware-Agnostic Shortcut Navigation

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author(s):** Systems Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
T-Notes supports extensive browser-style keyboard shortcuts (`Ctrl+Tab`, `Ctrl+Shift+Tab`, `Ctrl+Shift+PageUp`, `Ctrl+Shift+PageDown`, `Ctrl+1`..`9`, `Ctrl+W`, `Ctrl+Shift+T`). 

During testing across different hardware keyboards (especially Lenovo, Dell, and HP business laptops), `Ctrl+Shift+PageUp` and `Ctrl+Shift+PageDown` consistently failed to slide tabs. Investigation revealed two compounding issues:
1. **Windows Hardware Keypad Modifiers:** Many Windows keyboard firmware drivers inject `Qt.KeypadModifier` alongside `Qt.ControlModifier` and `Qt.ShiftModifier` when physical PageUp/PageDown keys are pressed. Standard `QKeySequence` bindings and `QShortcut` objects fail exact equality checks when unexpected modifier bits are present.
2. **Focus Swallowing in Child Widgets:** When `TechPadEditor` (`QTextEdit`) holds active focus, text navigation key events are consumed by the editor cursor engine before reaching window-level `keyPressEvent` handlers or action shortcuts.

---

## 2. Decision Drivers
- **100% Hardware Consistency:** Shortcuts must execute reliably across all physical keyboards, external USB keyboards, and virtual/RDP environments.
- **Focus Resilience:** Tab navigation and sliding must work immediately while typing in the rich-text note editor without requiring the user to click outside or change focus.
- **Immediate Post-Navigation Focus:** Moving tabs or cycling focus must keep the text editor active and ready for input.

---

## 3. Considered Options
1. **Option 1 (Individual Widget `keyPressEvent` Overrides):** Subclass both `TechPadEditor` and `TechPadTabBar` to intercept shortcuts and forward them to the parent window.
   - *Problem:* Violates DRY principle; brittle if new widgets (search fields, dialogs) are added later.
2. **Option 2 (Window-Level `QShortcut` Bindings):** Define `QShortcut(QKeySequence("Ctrl+Shift+PageDown"), self)` on `MainWindow`.
   - *Problem:* Fails when hardware drivers emit `Qt.KeypadModifier` (`0x20000000`). Qt rejects the match because `Qt.ControlModifier | Qt.ShiftModifier | Qt.KeypadModifier != Qt.ControlModifier | Qt.ShiftModifier`.
3. **Option 3 (Application-Wide `eventFilter` with Bitwise Modifier Masking):** Install an `eventFilter` directly on `QApplication.instance()` and isolate modifier keys with bitwise `&`.

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (Application-Wide `eventFilter` with Bitwise Modifier Masking).

### Rationale
- **Intercepts Before Any Widget Consumes the Event:** The `QApplication` event filter receives the `QEvent.KeyPress` event before it is dispatched to `TechPadEditor`, ensuring shortcuts cannot be swallowed.
- **Hardware-Agnostic Bitwise Checking:** Instead of checking exact enum equality (`mods == Qt.ControlModifier | Qt.ShiftModifier`), we evaluate bitwise presence:
  ```python
  mods = event.modifiers()
  has_ctrl = bool(mods & Qt.ControlModifier)
  has_shift = bool(mods & Qt.ShiftModifier)
  ```
  This makes shortcut triggers completely immune to auxiliary flags like `Qt.KeypadModifier`, `Qt.GroupSwitchModifier`, or num-lock states.
- **Automatic Re-Focusing:** After processing tab sliding or tab index changes, the event filter returns `True` (halting propagation) and immediately calls `current_editor.setFocus()`, providing a seamless typing experience.

---

## 5. Consequences

### Positive Consequences
- **Rock-Solid Shortcut Reliability:** Browser shortcuts function identically regardless of laptop vendor, keyboard layout, or active focus widget.
- **Single Source of Truth:** All tab-switching and tab-reordering shortcuts are maintained in one clean event filter method.
- **Zero Input Stutter:** Unhandled events return `False` immediately, ensuring standard typing performance is not degraded.

### Negative Consequences / Trade-offs
- **Central Event Traffic:** Because the filter is attached to `QApplication.instance()`, it receives events for all top-level windows. We mitigate this by checking `event.type() == QEvent.KeyPress` at the very top and immediately returning `False` for non-matching key types.

---

## 6. Implementation Notes & Validation
- **Implementation:** `src/ui/main_window.py` (`MainWindow.eventFilter`).
- **Tab Manipulation Logic:** `src/ui/components/tab_widget.py` (`move_tab_left`, `move_tab_right`).
- **Automated Validation:** Verified via `tests/test_ui_integration.py` (`test_event_filter_keypad_modifier_tab_sliding`).
