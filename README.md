# T-Notes

> Desktop IT technician scratchpad, screenshot annotation studio, and read-only **Microsoft 365 / PowerShell 7** diagnostic workspace built with **PySide6**, **SQLite (WAL + FTS5)**, and **JPEG** media storage.

---

## Table of Contents

1. [Overview](#overview)
2. [How T-Notes Works (Features & Daily Workflow)](#how-t-notes-works-features--daily-workflow)
3. [How to Use the M365 PowerShell Launcher (`Alt+F8`)](#how-to-use-the-m365-powershell-launcher-altf8)
4. [M365 PowerShell Scripts Audit (All 25 Scripts)](#m365-powershell-scripts-audit-all-25-scripts)
5. [Keyboard Shortcuts](#keyboard-shortcuts)
6. [Prerequisites](#prerequisites)
7. [Installation & Running](#installation--running)
8. [Local Data Locations](#local-data-locations)
9. [Testing & Verification](#testing--verification)
10. [Architecture & Project Structure](#architecture--project-structure)

---

## Overview

**T-Notes** (TechPad) is designed for IT helpdesk technicians, systems administrators, and MSP engineers handling multiple concurrent troubleshooting tickets. Rather than juggling scattered plain text files, external paint apps, browser consoles, and standalone PowerShell windows, T-Notes unifies:

- A **Neon Aurora Glass Dark** rich-text multi-tab scratchpad with live telemetry, SQLite WAL + FTS5 persistence, auto-save debouncing, and Windows System Tray quick-summon (`F8`).
- Built-in technician workflow helpers including **Split View** (`Alt+Z`), an always-on-top **Mini-HUD** (`Alt+T`), a **Quick Command Palette** (`Ctrl+K`), a **Smart Entity Extractor & Tech Quick-Tools** (`Ctrl+Alt+Q`), a billable **Ticket Stopwatch**, and **Bilingual (EN/FR) Client & PSA Summary Formatters**.
- A full-screen **Cyber Neon Studio Image Editor** with non-destructive vector callouts, a translucent neon **Highlighter** (`H`), Paint-style text boxes, rotation/resize handles, zoom/pan, and undo/redo.
- An isolated **M365 PowerShell Launcher** (`Alt+F8`) running **25 contract-validated, read-only PowerShell 7 operations** across 11 Microsoft 365 workloads plus **5 guided multi-step triage workflows** against either **Offline Synthetic** fixtures or **Live Tenants**.

---

## How T-Notes Works (Features & Daily Workflow)

### 1. T-Notes Scratchpad Workspace & Visual Motion
- **Multi-Tab Ticket Scratchpads:** Open multiple concurrent tickets across reorderable colored tabs with rainbow hover/press tab glows and matching top-border accents (`Ctrl+T` new tab, double-click tab header to edit ticket number/client/summary). Tab order, active selection, and closed-tab undo (`Ctrl+Shift+T`) are preserved across restarts in SQLite.
- **Side-by-Side Split View (`Alt+Z`):** Edit two ticket scratchpads simultaneously across a draggable horizontal splitter (`Alt+Shift+Z` flips active panes when compressed into compact single-pane mode below 750 px). Drag a tab to the left/right edges to cross-move tickets between panes.
- **Always-on-Top Mini-HUD (`Alt+T`):** Docks T-Notes as a compact `440 px`-wide right-hand overlay pinned above other windows while keeping both top formatting/workflow toolbars visible in responsive compact mode.
- **Background System Tray & Instant Summon (`F8`):** Closing to the tray keeps T-Notes running silently in the background; press `F8` system-wide on Windows to pop it immediately to focus or hide it back.
- **Live Status Bar & Telemetry:** Displays glowing status pills for save state (`● Saved` / `↻ Saving...`), active ticket word/line/checklist/image counts (`lbl_telemetry`), and quick module toggles (`HUD`, `M365 Launcher`/`T-Notes`, `Split`/`Categories`, `History`/`Active Ticket`).
- **Neon Aurora Glass Dark UI:** Glossy multi-stop dark glass toolbars and inputs, preserved rainbow glow around buttons and tabs, animated `2 px` aurora shimmer accent bars, input hover/focus halos, smooth workspace/tab fades, and animated modal entrances.

### 2. Rich-Text Editor, Checklists, Triage Badges & Ticket Stopwatch
- **Formatting & Code Blocks:** Apply Bold/Italic/Underline, text/highlight colors, interactive bullet checklists (`[] ` + `Space`, `Ctrl+Alt+L`, auto-continuing on `Enter`), URL auto-linking (clickable hyperlinks on `Space`/`Enter`), and monospaced dark CLI/PowerShell containers (`Ctrl+Alt+C`).
- **9 Triage Status Pills:** Inject color-coded inline badges via **🏷️ Tag** or `Alt+1`–`Alt+4` (`PASS`, `FAIL`, `WARN`, `INFO`), plus extended workflow pills (`RESOLVED`, `BLOCKED`, `WAITING`, `P1`, `VIP`) searchable via the toolbar menu or Command Palette.
- **In-Note Find & Replace (`Ctrl+F` / `Ctrl+H`):** Floating glass overlay bar with match counter, whole-word/case options, and single/bulk replacement.
- **Built-In Skeletons & Custom Rich Templates:** Insert standard triage structures (**📋 Template**) or create portable rich-text templates with embedded images using `AddTemplateDialog`.
- **Billable Ticket Stopwatch (`⏱️`):** Tracks per-ticket troubleshooting duration in SQLite and displays live minutes right in the tab title (`#INC-101 (14m)`). Uses Win32 `GetLastInputInfo` / `OpenInputDesktop` to auto-pause after workstation lock or 5 minutes of inactivity.

### 3. Technician Productivity Tools (`Ctrl+K` & `Ctrl+Alt+Q`)
- **Quick Command Palette (`Ctrl+K` or `🔍`):** Opens a keyboard-first fuzzy search modal indexing:
  - All open tabs (Primary & Split panes)
  - Core layout & editor actions (New Tab, Split View, HUD, History Drawer, Workspace switch, Summary Formatter)
  - All 9 triage badges and all built-in + custom templates
  - Archived tickets (instant non-destructive restore)
  - Registered M365 operations (switches directly to M365 Launcher and selects the target category & script)
- **Tech Quick-Tools & Smart Entity Extractor (`Ctrl+Alt+Q` or `⚡`):**
  - Automatically scans the active ticket note for deduplicated **Emails / UPNs**, **GUIDs / Entra Object IDs**, **IPv4 addresses**, **Ticket IDs** (`INC-`, `SR-`, `CHG-`, `PRB-`, `TASK-`, `RITM-`, `TKT-`, `CASE-`), and **URLs**.
  - Provides 1-click **Copy**, **Insert into Note**, and **`☁️ Send UPN/GUID to M365 Target`** (populates the M365 target fields and opens the M365 workspace).
  - Includes instant generators for **cryptographically random Temp Passwords** (`8–64` chars via `secrets`), **UUID v4** strings, and **Local + UTC ISO Timestamps**.

### 4. Image Pipeline & Cyber Neon Studio Image Editor
- **Efficient JPEG Storage (`image://local/<uuid>`):** Pasting screenshots (`Win+Shift+S` / `Ctrl+V`) or dropping image files automatically compresses media to JPEG (quality `85`) stored in SQLite `scratchpad_images` BLOBs—never raw BMP/PNG bloat.
- **Inline Image Manipulation:** Click an image in the note editor to resize via bottom-right corner drag handle or press `Delete`/`Backspace` to remove it; double-click (or right-click → **🖼️ Image Editor**) to launch the full editor.
- **Cyber Neon Studio Image Editor (`ResizeImageDialog` & `TextAnnotationDialog`):**
  - Pops up maximized full-screen by default (double-click top bar or `F11` toggles normal `1020×680` mode) with a dedicated futuristic cyber-neon visual theme: colorful multi-stop gradient buttons with diagonal prism click-shine sweeps, continuously color-shifting rainbow borders and laser divider lines, holographic blueprint canvas grid, animated spinboxes/textboxes, and a live tool/zoom HUD readout.
  - Single-line top bar provides:
    - **↖️ Select / Move (`V`):** Move, resize (corner & side handles), edge-drag reposition, nudge (`Arrow Keys`), and free-rotate (`[`, `]`, `Ctrl+R`, or overhead plasma handle with optional `Shift` 15° snap).
    - **✏️ Neon Pen (`P`):** Smooth anti-aliased freehand drawing.
    - **🖍️ Highlighter (`H`):** Wide translucent fluorescent marker (`alpha = 95`) in a single path pass so overlapping strokes stay crisp and underlying text remains readable (`Shift+Drag` snaps straight horizontal/vertical/45° highlight).
    - **📏 Laser Line (`L`), ⭕ Circle (`C`), 🔲 Rectangle (`R`):** Vector shapes (`Shift+Drag` straight snapping for lines).
    - **🔤 Paint-Style Text Box (`T`):** Drag a bounding rectangle to enter multi-line high-contrast shadowed text (`8–96 pt`) with optional dark callout border; double-click placed text in Select mode to re-edit.
    - **Palette & Precision Controls:** 6 color swatches + custom 24-bit picker (`🎨`), 4 stroke widths (`2px`, `4px`, `8px`, `12px`), zoom (`25%–500%`, `Ctrl+Wheel`, right/middle-drag pan), 40-step Undo/Redo/Reset, and proportional dimension presets (`25%`, `50%`, `75%`, `100%`, `Fit to Pane Width`).

### 5. Export, Bilingual Summary Formatter & Email
- **Copy Formatted Note (`Ctrl+Shift+C`):** Copies rich HTML with Base64-inlined images and preserved formatting/checklists to the clipboard.
- **Clean PSA / Ticket Export (`Ctrl+Alt+N` & `Ctrl+Alt+E`):** Exports stripped clean Markdown/plain text to the clipboard (`Ctrl+Alt+N`) or writes dated `.txt` notes into `T-Notes/<YYYY-MM-DD>/` (`Ctrl+Alt+E`).
- **Bilingual EN/FR Summary Formatter & Email (`Ctrl+Alt+M`):** Automatically extracts *Issue*, *Troubleshooting*, *Resolution*, *Root Cause*, and *Next Steps* sections in English or French (`SummaryFormatterDialog`) for Client Resolution Emails, Internal PSA Work Notes (with rounded 15-minute billable time), or Escalation Handovers, or launches a pre-filled `mailto:` draft (`Ctrl+Alt+M`).

### 6. History, FTS5 Search, Automated Backups & Startup
- **Full-Text History Drawer (`Alt+H`):** Instant SQLite FTS5 prefix/token search across active and archived tickets, with non-destructive restore to Primary or Split panes.
- **Rolling Online SQLite Backups & ZIP Export:** Daily automated `sqlite3.Connection.backup()` snapshots (7-day retention) under `%LOCALAPPDATA%\TechPad\backups\` and bulk portable ZIP exports (`tickets/*.md` + `images/` + `manifest.json`) via **Settings (`Ctrl+,`)**.
- **Windows Startup (`HKCU`):** Optional silent `--tray` boot configurable in Preferences.

---

## How to Use the M365 PowerShell Launcher (`Alt+F8`)

Switch between **T-Notes** and the **M365 PowerShell Launcher** at any time by clicking **`M365 Launcher`** / **`T-Notes`** in the bottom status bar or pressing **`Alt+F8`**. Switching automatically saves dirty notes and keeps the current focus ticket open in the right-hand **Active Ticket Sidebar** (using the same live `QTextDocument`, formatting bar, and stopwatch—zero sync lag).

### Workspace Layout (3 Panes)
1. **Left Pane — Category Navigation:** Switch between **📊 Dashboard**, **🏢 Companies & Context**, **11 M365 Operation Categories**, and **⇄ Guided Workflows**.
2. **Center Pane — Operations Workbench:** Contains **Company Selection**, **Authentication & Tenant Context**, **Script Catalog** (with search, risk, and lifecycle filters), typed **Parameters**, **Execution Workspace**, and **Parsed Results**.
3. **Right Pane — Active Ticket Sidebar:** Full live view of the currently focused ticket note where you can click **Insert Result into Ticket** to document diagnostic output immediately.

### Mode A: Offline Synthetic Mode (Safe Local Testing — No Live Tenant Needed)
1. Open the M365 workspace (`Alt+F8`).
2. Click **`🧪 Load Synthetic Snapshot`** (or use **Quick Setup Context** in the Dashboard/Companies card) to load all 25 operations bound to deterministic synthetic fixtures for *Alpine Ski House* (`client@alpine.example`).
3. Browse any category, adjust parameters (e.g., `DaysBack`, `RiskLevel`), click **Run Selected Operation** or **Run Workflow**, and inspect structured JSON/Summary output in **Parsed Results**.

### Mode B: Live Tenant Read-Only Diagnostics (Host-Owned Authentication)
1. **Check Environment Prerequisites:** Ensure **PowerShell 7** (`pwsh` 7.4+) and the read-only Graph/Exchange modules are installed, then switch the top toggle to **Live Pilot** and run **Preflight** to verify module availability.
2. **Select Company & Administrator Profile:** Choose or add a tenant profile (domain, tenant ID, admin UPN) and click **Confirm Company**.
3. **Connect Services via Host-Owned Auth:** Click **Connect Graph** and/or **Connect Exchange Online**. Authentication is owned strictly by the persistent host worker (`pwsh`); individual script files never contain login prompts, credentials, or token storage.
4. **Bind Target User / Object ID:** Type the client email/UPN or Entra Object GUID directly—or while reading a ticket note in T-Notes, press **`Ctrl+Alt+Q`** (`⚡ Tech Quick-Tools`) and click **`☁️ Send UPN/GUID to M365 Target`** to transfer the user's UPN/GUID automatically. Click **Resolve Target** to verify canonical tenant/user identity.
5. **Run Scripts or Guided Workflows:** Execute any individual operation or launch one of the **5 Guided Workflows**; cancel long runs cleanly via **Cancel**, or click **Insert Result into Ticket** to paste formatted findings directly into your active note.

### Guided Multi-Step Workflows (`WORKFLOW_DEFINITIONS`)
| Workflow | Steps Executed in Sequence |
| :--- | :--- |
| **Full User Diagnostic Snapshot (4 Steps)** | `M365.ENTRA.USER_IDENTITY` → `M365.ENTRA.USER_LICENSES` → `M365.ENTRA.USER_SIGNINS` → `M365.EXCHANGE.MAILBOX_SUMMARY` |
| **Security & Access Incident Triage (3 Steps)** | `M365.ENTRA.USER_IDENTITY` → `M365.ENTRA.USER_MFA_AUDIT` → `M365.SECURITY.RISKY_SIGNIN_AUDIT` |
| **Collaboration & Storage Readiness (4 Steps)** | `M365.ENTRA.USER_IDENTITY` → `M365.TEAMS.USER_READINESS` → `M365.SHAREPOINT.ACCESS_DIAGNOSTIC` → `M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC` |
| **Mailbox & Delivery Triage (4 Steps)** | `M365.ENTRA.USER_IDENTITY` → `M365.EXCHANGE.MAILBOX_SUMMARY` → `M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY` → `M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT` |
| **Account Lockout & Auth Triage (4 Steps)** | `M365.ENTRA.USER_IDENTITY` → `M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE` → `M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT` → `M365.ENTRA.USER_MFA_AUDIT` |

---

## M365 PowerShell Scripts Audit (All 25 Scripts)

Every script under `scripts/m365/` conforms to contract baseline **`tnotes.m365 / 0.3.0`** (`APPROVED — IMPLEMENTATION CONTRACT`), uses typed parameters and host-owned authentication boundaries, enforces Win32 Job Object worker isolation, passes SHA-256 manifest verification (`25 / 25` hashes matched), and runs strictly **`read_only`**:

- **Total Standalone Operations:** `25` across `11` categories (`21` Microsoft Graph, `4` Exchange Online)
- **Risk Profile:** `25 / 25` strictly `read_only` (zero tenant write/mutation scripts)
- **Contract Validation:** `450 / 450` contract package checks pass (`python -B docs/contracts/m365/validation/validate_contract.py`)
- **Manifest Integrity:** `25 / 25` `script_sha256` manifest digests match on-disk `.ps1` files

| Category | Script ID | Title | Service | Graph Scopes / Auth | Risk | Script Path |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `entra-id` | `M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP` | Audit Entra Group & Directory Role Memberships | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/entra-id/group-role-membership/Get-GroupAndRoleMembership.ps1` |
| `entra-id` | `M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE` | Audit Password Age, Policy & Hybrid Sync Posture | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/entra-id/password-account-posture/Get-PasswordAndAccountPosture.ps1` |
| `entra-id` | `M365.ENTRA.USER_IDENTITY` | Get-UserIdentity | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/entra-id/user-identity/Get-UserIdentity.ps1` |
| `entra-id` | `M365.ENTRA.USER_MFA_AUDIT` | Inspect User MFA & Conditional Access Sign-Ins | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/entra-id/user-mfa-audit/Get-UserMfaAudit.ps1` |
| `entra-id` | `M365.ENTRA.USER_SIGNINS` | Get-UserSignIns | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/entra-id/user-signins/Get-UserSignIns.ps1` |
| `exchange-online` | `M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY` | Audit Mailbox Forwarding & Auto-Reply Posture | `ExchangeOnline` | EXO Read-Only RBAC | `read_only` | `scripts/m365/exchange-online/forwarding-auto-reply/Get-MailboxForwardingAndAutoReply.ps1` |
| `exchange-online` | `M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT` | Audit Mailbox Delegation & Permissions | `ExchangeOnline` | EXO Read-Only RBAC | `read_only` | `scripts/m365/exchange-online/mailbox-permissions/Get-MailboxPermissionsAudit.ps1` |
| `exchange-online` | `M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD` | Inspect Mailbox Quota, Archive & Litigation Hold | `ExchangeOnline` | EXO Read-Only RBAC | `read_only` | `scripts/m365/exchange-online/mailbox-quota-hold/Get-MailboxQuotaAndHold.ps1` |
| `exchange-online` | `M365.EXCHANGE.MAILBOX_SUMMARY` | Get-MailboxSummary | `ExchangeOnline` | EXO Read-Only RBAC | `read_only` | `scripts/m365/exchange-online/mailbox-summary/Get-MailboxSummary.ps1` |
| `general` | `M365.GENERAL.SERVICE_READINESS_AUDIT` | Cross-Service Provisioning & Readiness Audit | `Graph` | `LicenseAssignment.Read.All`, `User.Read.All` | `read_only` | `scripts/m365/general/service-readiness/Get-ServiceReadinessAudit.ps1` |
| `general` | `M365.GENERAL.TENANT_USER_OVERVIEW` | Cross-Service User & Tenant Health Overview | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/general/tenant-user-overview/Get-TenantUserOverview.ps1` |
| `intune` | `M365.INTUNE.COMPLIANCE_AND_ENROLLMENT` | Inspect Intune Device Management & Compliance Sign-Ins | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/intune/compliance-enrollment/Get-IntuneComplianceDiagnostic.ps1` |
| `intune` | `M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE` | Inventory Endpoint Devices & OS Posture | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/intune/device-inventory/Get-IntuneDeviceInventory.ps1` |
| `licensing` | `M365.LICENSING.SERVICE_PLAN_AUDIT` | Audit Assigned SKUs & Provisioning Service Plans | `Graph` | `LicenseAssignment.Read.All`, `User.Read.All` | `read_only` | `scripts/m365/licensing/service-plan-audit/Get-ServicePlanAudit.ps1` |
| `licensing` | `M365.ENTRA.USER_LICENSES` | Get-UserLicenses | `Graph` | `LicenseAssignment.Read.All` | `read_only` | `scripts/m365/licensing/user-licenses/Get-UserLicenses.ps1` |
| `onedrive` | `M365.ONEDRIVE.CLIENT_SYNC_SIGNINS` | Audit OneDrive Client Sync Sign-Ins | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/onedrive/client-sync-signins/Get-OneDriveClientSyncSignIns.ps1` |
| `onedrive` | `M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC` | Inspect OneDrive Service Plans & Sync Readiness | `Graph` | `LicenseAssignment.Read.All`, `User.Read.All` | `read_only` | `scripts/m365/onedrive/sync-diagnostic/Get-OneDriveSyncDiagnostic.ps1` |
| `other` | `M365.OTHER.UPN_SMTP_ALIGNMENT` | Verify User UPN & Directory Profile Alignment | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/other/upn-smtp-alignment/Get-UpnSmtpAlignment.ps1` |
| `reports` | `M365.REPORTS.USER_ACCESS_AUDIT_REPORT` | Generate Read-Only User Access & Sign-In Audit Report | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/reports/user-access-audit/Get-UserAccessAuditReport.ps1` |
| `security` | `M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT` | Audit Account Lockouts & Legacy Auth Sign-Ins | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/security/legacy-auth-lockout/Get-LegacyAuthAndLockoutAudit.ps1` |
| `security` | `M365.SECURITY.RISKY_SIGNIN_AUDIT` | Audit Risky Sign-Ins & Authentication Failures | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/security/risky-signins/Get-SecurityRiskySignIns.ps1` |
| `sharepoint` | `M365.SHAREPOINT.ACCESS_DIAGNOSTIC` | Inspect SharePoint Online Access & Sign-In Events | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/sharepoint/access-diagnostic/Get-SharePointAccessDiagnostic.ps1` |
| `sharepoint` | `M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE` | Audit External Sharing & Guest B2B Posture | `Graph` | `User.Read.All` | `read_only` | `scripts/m365/sharepoint/external-guest-posture/Get-ExternalSharingAndGuestPosture.ps1` |
| `teams` | `M365.TEAMS.CLIENT_SIGNINS` | Inspect Microsoft Teams Client Sign-In Activity | `Graph` | `AuditLog.Read.All` | `read_only` | `scripts/m365/teams/client-signins/Get-TeamsClientSignIns.ps1` |
| `teams` | `M365.TEAMS.USER_READINESS` | Inspect Teams Licensing & Voice Service Plans | `Graph` | `LicenseAssignment.Read.All`, `User.Read.All` | `read_only` | `scripts/m365/teams/user-readiness/Get-TeamsUserReadiness.ps1` |

---

## Keyboard Shortcuts

All keyboard shortcuts implemented across **T-Notes**, **M365 Launcher**, **Find & Replace**, **Image Editor**, **Command Palette**, **Quick-Tools**, and **Dialogs** are cataloged below. *(Per [`GEMINI.md`](GEMINI.md), every newly assigned or changed shortcut must be kept synchronized here.)*

### Global, Workspace & Window Management
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `F8` | System-Wide (Win32) & App | Summon T-Notes to foreground / toggle window visibility to tray |
| `Alt+F8` | Application-Wide | Toggle between **T-Notes** scratchpad and **M365 Launcher** workspace |
| `Alt+T` | Application-Wide | Toggle Always-on-Top **Mini-HUD** docked right-sidebar mode |
| `Alt+Z` | T-Notes Workspace | Toggle side-by-side **Split View** (or compact single-pane switch below 750 px) |
| `Alt+Shift+Z` | T-Notes (Compact Split) | Switch active editor pane (`Pane 1/2` ↔ `Pane 2/2`) when Split View is narrow |
| `Alt+H` | T-Notes Workspace | Toggle History & FTS5 Archive Side Drawer |
| `Ctrl+Shift+F` | Application-Wide | Open full-page **History Search** workspace and focus search bar |
| `Enter` (in History Search bar) | History Search Page | Run immediate FTS5 search without waiting for debounce |
| `↓` (in History Search bar) | History Search Page | Jump keyboard focus into matching results list |
| `Esc` | History Search Page | Clear active search text, or return to active ticket tabs |
| `Ctrl+K` | Application-Wide | Open **Quick Command Palette** (tabs, archive, templates, badges, M365) |
| `Ctrl+Alt+Q` | Application-Wide | Open **Tech Quick-Tools & Smart Entity Extractor** |
| `Ctrl+S` | T-Notes Workspace | Force immediate SQLite flush/save of all pending and dirty notes |
| `Ctrl+,` | T-Notes Workspace | Open Preferences & Backup Settings dialog |

### Tab Navigation & Management
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `Ctrl+T` | T-Notes Workspace | Create a new ticket scratchpad tab |
| `Ctrl+Shift+T` | T-Notes Workspace | Re-open / restore the most recently closed (archived) ticket tab |
| `Ctrl+W` / `Ctrl+F4` | T-Notes Workspace | Close (archive) the active ticket tab in the focused pane |
| `Ctrl+Tab` / `Ctrl+PageDown` | T-Notes Workspace | Switch to the next tab in the active pane (wraps around) |
| `Ctrl+Shift+Tab` / `Ctrl+PageUp` | T-Notes Workspace | Switch to the previous tab in the active pane (wraps around) |
| `Ctrl+Shift+PageDown` | T-Notes Workspace | Reorder / slide active tab one slot right |
| `Ctrl+Shift+PageUp` | T-Notes Workspace | Reorder / slide active tab one slot left |
| `Ctrl+1` – `Ctrl+8` | T-Notes Workspace | Jump directly to tab `1`–`8` |
| `Ctrl+9` | T-Notes Workspace | Jump to the last tab in the primary pane |
| `Esc` | Tab Bar Drag | Cancel active tab drag/cross-pane move |

### Rich-Text Editor, Formatting, Checklists & Badges
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `Ctrl+B` | Note & Template Editors | Toggle **Bold** formatting |
| `Ctrl+I` | Note & Template Editors | Toggle *Italic* formatting |
| `Ctrl+U` | Note & Template Editors | Toggle <u>Underline</u> formatting |
| `Ctrl+Alt+X` | Toolbar / Editor | Pick foreground text color |
| `Ctrl+Alt+H` | Toolbar / Editor | Pick text highlight background color |
| `Ctrl+Alt+C` | Toolbar / Editor | Insert or format dark monospace CLI / PowerShell code block |
| `Ctrl+Alt+L` | Editor & Toolbar | Insert interactive checklist item (`[ ]`) at cursor |
| `[] ` or `- [ ] ` + `Space` | Editor Typing | Auto-convert typed bracket prefix into interactive clickable checkbox |
| `Enter` (on checklist line) | Editor Typing | Continue checklist on next line (or exit checklist when line is empty) |
| `F5` | T-Notes Workspace | Insert `[YYYY-MM-DD HH:MM:SS]` current timestamp |
| `Ctrl+Alt+I` | Toolbar / Editor | Open file picker to insert JPEG-compressed image |
| `Alt+1` | Toolbar / Editor | Insert **🟢 PASS** badge |
| `Alt+2` | Toolbar / Editor | Insert **🔴 FAIL** badge |
| `Alt+3` | Toolbar / Editor | Insert **🟡 WARN** badge |
| `Alt+4` | Toolbar / Editor | Insert **ℹ️ INFO** badge |
| `Ctrl++` / `Ctrl+=` / `Shift+Wheel Up` | Editor | Zoom editor text/viewport in |
| `Ctrl+-` / `Shift+Wheel Down` | Editor | Zoom editor text/viewport out |
| `Ctrl+0` | Editor | Reset editor zoom to default |
| `Ctrl+Shift+Wheel` | Editor | Horizontal scrollbar scroll |
| `Delete` / `Backspace` (selected image) | Editor | Remove currently selected embedded image |

### In-Note Find & Replace
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `Ctrl+F` | Editor / Main Window | Open Find bar (or toggle Replace row if already open) |
| `Ctrl+H` | Editor / Main Window | Open Find & Replace bar |
| `Enter` (in Find field) | Find & Replace Bar | Jump to next match |
| `Shift+Enter` (in Find field) | Find & Replace Bar | Jump to previous match |
| `Enter` (in Replace field) | Find & Replace Bar | Replace current match and advance |
| `Esc` | Find & Replace Bar | Close Find & Replace bar and return focus to editor |

### Copy, Export & Email
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `Ctrl+Shift+C` | Toolbar / Editor | Copy formatted rich note + Base64 images of the active note to clipboard |
| `Ctrl+Alt+N` | Toolbar | Copy clean plain-text / Markdown PSA ticket note to clipboard |
| `Ctrl+Alt+E` | Toolbar | Export plain-text active ticket note to `T-Notes/<YYYY-MM-DD>/` |
| `Ctrl+Alt+M` | Toolbar | Launch OS default email client draft pre-addressed to your configured Default Email |

### Image Editor (Cyber Neon Studio)
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `V` | Image Editor | Activate **Select / Move & Rotate** tool |
| `P` | Image Editor | Activate **Neon Pen** freehand tool |
| `H` | Image Editor | Activate **Highlighter** translucent marker tool |
| `L` | Image Editor | Activate **Laser Straight Line** tool |
| `C` | Image Editor | Activate **Circle / Ellipse** tool |
| `R` | Image Editor | Activate **Rectangle** tool |
| `T` | Image Editor | Activate **Paint-Style Text Box** tool |
| `Shift+Drag` | Line & Highlighter Tools | Snap stroke to horizontal, vertical, or 45° diagonal angle |
| `Ctrl+R` | Image Editor | Rotate selected annotation (or last item) 90° clockwise |
| `[` / `]` | Image Editor (Selected Item) | Rotate selected item `-15°` counter-clockwise / `+15°` clockwise |
| `Shift+Drag` (Rotation Handle) | Image Editor (Selected Item) | Snap rotation to 15° increments |
| `Arrow Keys` | Image Editor (Selected Item) | Nudge selected annotation by `1 px` |
| `Shift+Arrow Keys` | Image Editor (Selected Item) | Nudge selected annotation by `10 px` |
| `Delete` / `Backspace` | Image Editor (Selected Item) | Remove selected annotation item |
| `Esc` | Image Editor Canvas | Clear current item selection |
| `Ctrl+Z` | Image Editor | Undo last annotation step (up to 40 steps) |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Image Editor | Redo undone annotation step |
| `Ctrl++` / `Ctrl+=` / `Ctrl+Wheel Up` | Image Editor | Zoom canvas in (+25%, up to 500%) |
| `Ctrl+-` / `Ctrl+Wheel Down` | Image Editor | Zoom canvas out (-20%, down to 25%) |
| `Ctrl+0` | Image Editor | Reset canvas zoom to `100%` (1:1 fit) and recenter pan |
| `F11` (or Double-Click Top Bar) | Image Editor | Toggle maximized full-screen vs. `1020×680` window |

### Command Palette & Modal Dialogs
| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `↑` / `↓` | Command Palette Search Box | Navigate matching results without leaving search input |
| `Enter` | Command Palette Search Box | Execute highlighted result and close palette |
| `Esc` | Command Palette, Quick-Tools, Summary Formatter | Dismiss / cancel dialog |

---

## Prerequisites

- **Python:** `>= 3.10` (developed and tested on Python 3.14 on Windows)
- **Python Packages:** See [`requirements.txt`](requirements.txt)
  - `PySide6>=6.6.0`
  - `Pillow>=10.0.0`
  - `jsonschema>=4.23,<5`
  - `referencing>=0.35.0`
  - `pytest>=8.0.0` (test suite)
- **Optional — Microsoft 365 Live Tenant Execution:**
  - **PowerShell 7** (`pwsh` 7.4+)
  - Modules (read-only scopes only):
    - `Microsoft.Graph.Authentication >= 2.0.0`
    - `Microsoft.Graph.Users >= 2.0.0`
    - `Microsoft.Graph.Reports >= 2.0.0`
    - `ExchangeOnlineManagement >= 3.4.0`

---

## Installation & Running

```bash
git clone https://github.com/JDecelles1990/T-Notes.git
cd T-Notes
python -m pip install -r requirements.txt
```

Launch the desktop application:

```bash
python -m src.main
```

Alternative launch options:

```bash
python src/main.py          # Direct script launch
python -m src.main --tray   # Start silently / evaluate tray smart-restore
pythonw src/main.py --tray  # Windows GUI-only tray launch (no console window)
```

---

## Local Data Locations

- **SQLite Database & Daily Backups:**
  - Windows: `%APPDATA%\T-Notes\techpad.db` (snapshots in `%APPDATA%\T-Notes\backups\`; existing `%LOCALAPPDATA%\TechPad\techpad.db` databases are automatically migrated non-destructively on first launch)
  - macOS / Linux: `~/.t-notes/techpad.db`
- **Plain-Text Ticket Exports (`Ctrl+Alt+E`):** `%APPDATA%\T-Notes\exports\<YYYY-MM-DD>\` in packaged builds, or `T-Notes/<YYYY-MM-DD>/` inside the repository folder when run from source

---

## Building a Standalone Windows Executable

Package T-Notes into a clean `--onedir` windowed bundle (`dist\T-Notes\T-Notes.exe`) with bundled QSS/icon assets, Qt JPEG/PNG plugins, and PowerShell 7 host/operation scripts:

```powershell
.\build.ps1 -InstallPyInstaller
```

Subsequent builds (once PyInstaller is installed):

```powershell
.\build.ps1
```

---

## Testing & Verification

Run the Python unit, contract, and UI integration test suite:

```bash
python -m pytest -q
```

Validate the M365 PowerShell contract package:

```bash
python -B docs/contracts/m365/validation/validate_contract.py
```

---

## Architecture & Project Structure

T-Notes enforces strict separation of concerns across UI (`src/ui/`), Services (`src/services/`), Repositories (`src/repositories/`), and Database (`src/database/`): UI components never issue raw SQL queries, SQLite always runs in WAL mode with foreign keys enforced, and M365 PowerShell operations remain decoupled from PySide6 and SQLite.

```text
T-Notes/
├── assets/
│   ├── icons/                # Application icons
│   ├── m365/                 # Contract pins, empty production catalog, synthetic catalog (25 ops)
│   └── styles/               # Neon Aurora Glass Dark theme QSS stylesheet
├── docs/                     # Architecture specs, DB schema, feature docs, ADRs, M365 contracts
├── prototypes/               # Official M365 PowerShell protocol engine helpers
├── scripts/
│   └── m365/                 # 25 read-only PowerShell 7 operations & persistent worker host
├── src/
│   ├── config.py             # Application data & export paths
│   ├── main.py               # Entry point, DB init, autostart, daily backup, GUI launch
│   ├── core/                 # Constants (triage badges/skeletons), debouncers, Win32 global hotkey
│   ├── database/             # SQLite WAL connection manager, schema, migrations
│   ├── repositories/         # Data access & atomic SQL transactions
│   ├── services/             # Scratchpad, images, sessions, summary formatter, M365, TechToolsService
│   └── ui/
│       ├── main_window.py    # Main shell, workspace switcher, HUD, split view, telemetry bar
│       ├── components/       # Editor, Toolbars, TabWidget, Glow/Aurora effects, Transitions, Find bar
│       ├── dialogs/          # Image Editor + CyberNeonFX, Command Palette, Quick-Tools, Settings, Summary
│       └── m365/             # M365 Launcher workspace, Company/Auth context panel, results viewer
├── tests/                    # Pytest unit, service, contract, Image Editor, and UI integration suites
├── AGENTS.md                 # Architectural boundaries & documentation maintenance rules
├── ARCHITECTURE.md           # High-level layered architecture overview
├── GEMINI.md                 # Agent instructions (contract loading & README shortcut sync rules)
├── pyproject.toml            # Project metadata & pytest configuration
├── README.md                 # App guide, M365 launcher manual, script audit & shortcuts reference
└── requirements.txt          # Python runtime & test dependencies
```

For detailed architecture specifications, database schemas, and ADRs, see [`docs/index.md`](docs/index.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md).
