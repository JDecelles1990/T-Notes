# [ADR-0005] Interactive Task Checklists & Dynamic Tab Progress Badges

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author(s):** Application Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians rely heavily on standard operating procedures (SOPs), multi-step incident troubleshooting protocols (e.g., verifying network adapter, checking DNS, pinging gateway, restarting service), and change-management checklists.

In pure rich-text editors without native checklist support:
1. Technicians either type static Unicode checkboxes (`☐`, `☑`) or bullet lists that cannot be toggled with a single click.
2. Checking off an action item requires manually selecting the symbol, deleting it, and typing a replacement character.
3. Multi-task progress across several concurrent tickets is invisible without switching into each tab individually.
4. Exporting notes into ticketing systems (ServiceNow, Jira, ConnectWise Manage, GitHub) produces raw or broken HTML instead of universally recognized Markdown task lists (`- [ ] ` and `- [x] `).

---

## 2. Decision Drivers
- **Frictionless In-Place Interaction:** Checkboxes must toggle between unchecked and completed states with a single mouse click directly inside the note canvas.
- **Visual Strikethrough & Progress Feedback:** Checking off an item should immediately apply dimmed strikethrough styling across the completed step.
- **Multi-Tab Visibility:** The tab header must dynamically reflect real-time task progress (e.g. `☑️3/5` or `✅5/5`) so technicians can monitor concurrent workflows at a glance.
- **Fast Technician Typing Mechanics:** Typing `[] ` or `- [ ] ` at the start of a line must auto-convert to a checklist item; pressing `Enter` must continue the checklist; pressing `Enter` on an empty checkbox must smoothly exit.
- **Clean Ticket Tool Compatibility:** Copying notes for PSA tickets must seamlessly export standard Markdown task lists.

---

## 3. Considered Options

1. **Option 1: Standard HTML `<input type="checkbox">` via `QTextDocument`**
   - *Problem:* Qt's `QTextEdit` and rich-text document engine (`QTextDocument`) do not support form input elements (`<input>`). Rendering checkboxes via form controls requires embedding full WebEngine/Chromium instances (`QWebEngineView`), increasing memory consumption from ~40MB to >250MB.

2. **Option 2: Embedded Custom `QCheckBox` Child Widgets via `QTextCursor.insertHtml()`**
   - *Problem:* Embedding native Qt widgets into `QTextDocument` via `QTextCharFormat` or child widgets breaks text serialization (`toHtml()`), corrupts document undo/redo stacks, and fails to persist correctly into SQLite text columns.

3. **Option 3: Anchored Pseudo-Widgets with Custom URI Scheme (`task://toggle`) & Document Layout Styling**
   - Embed lightweight HTML anchors: `<a href="task://toggle">[ ]</a>` and `<a href="task://toggle">[✔]</a>`.
   - Intercept anchor clicks in `mouseReleaseEvent()` and route `task://` schemes internally without launching the system browser.
   - Update character formats (`setFontStrikeOut`, `setForeground`) directly on the document cursor.
   - Aggregate checklist statistics via regex on the plain text and dispatch Qt signals to the tab bar.

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (Anchored Pseudo-Widgets with Custom URI Scheme `task://toggle`).

### Rationale
- **Zero Memory Overhead:** Checklists remain pure character data within `QTextDocument`. The application remains lightweight (~45MB RAM).
- **Rock-Solid Persistence:** Checkboxes serialize cleanly to standard HTML in SQLite `scratchpads.content_html` and reload perfectly across application restarts.
- **Clean Protocol Routing:** Using `task://toggle` ensures hyperlinks to external websites continue opening in the system browser (`QDesktopServices.openUrl()`), while task anchors toggle instantly in-memory.
- **Seamless Markdown Export:** A simple regex conversion transforms `task://toggle` anchors into standard Markdown `- [ ] ` and `- [x] `, ensuring 100% fidelity when pasted into external PSA portals.

---

## 5. Consequences

### Positive Consequences
- Single-click interactive task toggling directly inside `TechPadEditor`.
- Live visual progress badges on tab headers (`☑️3/5`, `✅5/5`) with rich hover tooltips.
- Natural typing experience with markdown auto-conversion and Enter-continuation.
- Clean, standard Markdown output in "Copy Note for Ticket Tool" (`Ctrl+Alt+N`).

### Negative Consequences / Trade-offs
- Internal anchor tags require a conversion step during plain-text export (implemented in `ScratchpadService.convert_html_to_clean_text()`).

---

## 6. Implementation Notes & Validation
- **Editor Implementation:** `src/ui/components/editor.py` (`TechPadEditor._toggle_checkbox_at`, `insert_checklist_item`, `get_checklist_stats`).
- **Tab Header Integration:** `src/ui/components/tab_widget.py` (`TechPadTabWidget.format_title`, `update_tab_title`).
- **Toolbar & MainWindow Wiring:** `src/ui/components/toolbar.py` (`act_checklist`), `src/ui/main_window.py` (`_on_checklist_stats_changed`).
- **Export Filter:** `src/services/scratchpad_service.py` (`convert_html_to_clean_text`).
- **Automated Tests:** `tests/test_ui_integration.py` (`test_ui_checklist_toolbar_and_insert`, `test_ui_checklist_toggle_and_tab_progress`, `test_ui_checklist_enter_continuation_and_exit`, `test_ui_checklist_typing_space_auto_conversion`) and `tests/test_scratchpad_service.py` (`test_clean_text_checklist_conversion`).
