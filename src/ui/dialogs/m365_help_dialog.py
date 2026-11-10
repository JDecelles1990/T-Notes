"""Modal user guide dialog for the M365 PowerShell Launcher workspace."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.ui.components.glow_effect import install_glow


M365_HELP_GUIDE_HTML = """
<div style="font-family: 'Segoe UI', -apple-system, Roboto, sans-serif; color: #cccccc; line-height: 1.45;">
    <h2 style="color: #58a6ff; margin-top: 0; margin-bottom: 4px;">
        M365 PowerShell Launcher — User Guide
    </h2>
    <p style="color: #8b949e; margin-top: 0; margin-bottom: 12px;">
        Step-by-step workflow for running contract-validated Microsoft 365 diagnostics and inserting results into your Active Ticket note.
    </p>

    <hr style="border: 0; border-top: 1px solid #30363d; margin: 10px 0;">

    <h3 style="color: #79c0ff; margin-bottom: 6px;">1. Load the Script Catalog &amp; Quick Context Setup</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>By default, the production catalog opens in a safe empty state (<b>Catalog preview</b>).</li>
        <li>Click <b>🧪 Load Synthetic Snapshot</b> in the top control bar to load all 17 offline synthetic Microsoft 365 PowerShell 7 operations across all 11 service categories.</li>
        <li>Or click <b>⚡ Quick Setup</b> inside any category card to load the synthetic catalog, select <code>Alpine Ski House</code>, connect <code>Graph</code> + <code>ExchangeOnline</code>, confirm the tenant, and bind <code>client@alpine.example</code> in one click.</li>
    </ul>

    <h3 style="color: #79c0ff; margin-bottom: 6px;">2. Company Selection &amp; Tenant Confirmation</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>In <b>Company Selection</b>, search or choose a client tenant from the dropdown (e.g., <code>Alpine Ski House · alpine.example</code>), or use <b>+ Company</b> / <b>Edit Company</b> to manage session-only tenant metadata.</li>
        <li>Click <b>Confirm Company Selection</b> to lock the target tenant context before running operations.</li>
    </ul>

    <h3 style="color: #79c0ff; margin-bottom: 6px;">3. Authentication &amp; Target Identity</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>Select an administrator account (or click <b>+ Admin</b> / <b>Set Default</b>).</li>
        <li>Click <b>Connect Microsoft Graph (synthetic)</b> and/or <b>Connect Exchange Online (synthetic)</b> depending on the operation's service requirements.</li>
        <li>Enter the target user's <b>Client email / UPN</b> (e.g., <code>client@alpine.example</code>) and click <b>Resolve Target (synthetic)</b> — or run <b>Get-UserIdentity</b> first to automatically bind the user's Entra Object ID for follow-on operations.</li>
    </ul>

    <h3 style="color: #79c0ff; margin-bottom: 6px;">4. Browse Script Catalog &amp; Configure Parameters</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>Select a category in the left <b>☰ Categories</b> list (<code>Entra ID</code>, <code>Licensing</code>, or <code>Exchange Online</code>).</li>
        <li>Filter operations by search keyword, risk level (<code>Read only</code>, <code>Write</code>, <code>High impact</code>), or lifecycle state.</li>
        <li>Select an operation in <b>Script Catalog</b> to view its manifest details, required roles, and schema contract.</li>
        <li>Adjust bounded inputs in <b>Parameters</b> (such as <code>LookbackDays</code>, <code>MaxRecords</code>, <code>IncludeServicePlans</code>, or <code>IncludeNonInteractive</code>).</li>
    </ul>

    <h3 style="color: #79c0ff; margin-bottom: 6px;">5. Run, Cancel &amp; Session Execution History</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>Click <b>▶ Run (Synthetic)</b> in <b>Execution Workspace</b> to execute the operation in an isolated PowerShell 7 worker validated against <code>tnotes.m365 / 0.3.0</code>.</li>
        <li>Click <b>⏹ Cancel</b> to request cooperative cancellation of an active run, or <b>🗑 Clear</b> to reset the RAM-only <b>Session Execution History</b>.</li>
        <li>Click any previous run in <b>Session Execution History</b> to reload its summary and JSON envelope.</li>
    </ul>

    <h3 style="color: #79c0ff; margin-bottom: 6px;">6. Inspect Results &amp; Insert into Active Ticket</h3>
    <ul style="margin-top: 2px; margin-bottom: 10px;">
        <li>In <b>Parsed Results</b>, toggle between the formatted technician summary and <b>{ } Raw JSON</b>.</li>
        <li>Click <b>📥 Insert into Active Ticket</b> to append the validated diagnostic summary into the <b>Active Ticket Notes</b> right sidebar (single-use per run correlation ID to prevent accidental duplicate paste).</li>
        <li>Use the right sidebar's header tools (<b>🗒️</b> Templates, <b>📋</b> Copy/Export Note, <b>...</b> Formatting menu, and <b>⏱️</b> synchronized ticket stopwatch) without leaving the M365 workspace.</li>
    </ul>

    <hr style="border: 0; border-top: 1px solid #30363d; margin: 10px 0;">

    <h3 style="color: #4ec9b0; margin-bottom: 6px;">Synthetic Test Identities Cheat Sheet</h3>
    <table width="100%" cellspacing="0" cellpadding="5" style="border: 1px solid #30363d; border-collapse: collapse; margin-bottom: 10px;">
        <tr style="background-color: #21262d; color: #ffffff;">
            <th align="left" style="border-bottom: 1px solid #30363d;">Target UPN</th>
            <th align="left" style="border-bottom: 1px solid #30363d;">Simulated Behavior</th>
        </tr>
        <tr>
            <td style="border-bottom: 1px solid #30363d;"><code>client@alpine.example</code><br><code>alex.wilber@contoso.example</code></td>
            <td style="border-bottom: 1px solid #30363d;">Standard enabled user — succeeds across Identity, Licenses, Sign-Ins, and Mailbox Summary (exit code <code>0</code>).</td>
        </tr>
        <tr>
            <td style="border-bottom: 1px solid #30363d;"><code>partial.user@alpine.example</code><br><code>megan.bowen@contoso.example</code></td>
            <td style="border-bottom: 1px solid #30363d;">Partial data warning (<code>PROPERTY_UNAVAILABLE</code> / archive warning, exit code <code>2</code>).</td>
        </tr>
        <tr>
            <td style="border-bottom: 1px solid #30363d;"><code>missing@alpine.example</code></td>
            <td style="border-bottom: 1px solid #30363d;">Simulates user not found (<code>TARGET_NOT_FOUND</code>, exit code <code>30</code>).</td>
        </tr>
        <tr>
            <td><code>denied@alpine.example</code></td>
            <td>Simulates insufficient Graph/EXO permissions (<code>ACCESS_DENIED</code>, exit code <code>20</code>).</td>
        </tr>
    </table>

    <h3 style="color: #4ec9b0; margin-bottom: 6px;">Navigation &amp; Keyboard Shortcuts</h3>
    <ul style="margin-top: 2px; margin-bottom: 4px;">
        <li><b>Alt+F8</b> or <b>Back to T-Notes</b>: Switch between T-Notes and the M365 PowerShell Launcher (flushes unsaved notes first).</li>
        <li><b>☰ Categories</b> / <b>Active Ticket</b> buttons: Collapse or expand the left category navigation and right ticket notes panels to maximize workspace width.</li>
        <li><b>Alt+T</b>: Toggle Always-on-Top Mini-HUD mode.</li>
        <li><b>F8</b>: Global system-wide hotkey to minimize or bring T-Notes to the foreground.</li>
    </ul>
</div>
"""


class M365HelpDialog(QDialog):
    """Modal dark-themed guide explaining how to use the M365 PowerShell Launcher workspace."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("M365 PowerShell Launcher — Help & User Guide")
        self.setMinimumSize(640, 520)
        self.resize(720, 600)
        self.setModal(True)
        self.setObjectName("m365HelpDialog")
        self.setStyleSheet("""
            QDialog#m365HelpDialog {
                background-color: #1e1e1e;
                color: #cccccc;
            }
            QTextBrowser#m365HelpBrowser {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 10px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
            QPushButton#btnCloseM365Help {
                background-color: #0e639c;
                color: #ffffff;
                border: 1px solid #1177bb;
                border-radius: 4px;
                font-weight: bold;
                padding: 6px 18px;
            }
            QPushButton#btnCloseM365Help:hover {
                background-color: #1177bb;
            }
            QPushButton#btnCloseM365Help:pressed {
                background-color: #094771;
            }
        """)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.help_browser = QTextBrowser(self)
        self.help_browser.setObjectName("m365HelpBrowser")
        self.help_browser.setAccessibleName("M365 PowerShell Launcher User Guide content")
        self.help_browser.setOpenExternalLinks(False)
        self.help_browser.setHtml(M365_HELP_GUIDE_HTML)
        layout.addWidget(self.help_browser, 1)

        footer = QHBoxLayout()
        lbl_hint = QLabel("Tip: Press Esc or click Close to return to the launcher.", self)
        lbl_hint.setStyleSheet("color: #8b949e; font-size: 9pt;")
        footer.addWidget(lbl_hint)
        footer.addStretch(1)

        self.btn_close = QPushButton("Close", self)
        self.btn_close.setObjectName("btnCloseM365Help")
        self.btn_close.setAccessibleName("Close Help Guide")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)
        install_glow(self.btn_close, "#38bdf8")

        layout.addLayout(footer)

