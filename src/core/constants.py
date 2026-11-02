"""Constants and default configuration values for TechPad."""

APP_NAME = "TechPad"
APP_VERSION = "1.0.0"

# Auto-save timing
AUTO_SAVE_DEBOUNCE_MS = 1500

# Image compression
JPEG_COMPRESSION_QUALITY = 85
LOCAL_IMAGE_URL_PREFIX = "image://local/"

# Typography
DEFAULT_FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"
MONOSPACE_FONT_FAMILY = "Consolas, 'Courier New', 'Cascadia Code', monospace"

# Status colors
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"

# Log Triage Badges
LOG_BADGES = {
    "PASS": {
        "label": "🟢 PASS",
        "bg_color": "#1b4d24",
        "text_color": "#4ade80",
        "border_color": "#22c55e",
    },
    "FAIL": {
        "label": "🔴 FAIL",
        "bg_color": "#521616",
        "text_color": "#f87171",
        "border_color": "#ef4444",
    },
    "WARN": {
        "label": "🟡 WARN",
        "bg_color": "#543810",
        "text_color": "#facc15",
        "border_color": "#eab308",
    },
    "INFO": {
        "label": "ℹ️ INFO",
        "bg_color": "#1e3a5f",
        "text_color": "#60a5fa",
        "border_color": "#3b82f6",
    },
}

# Technician Note Skeletons (HTML)
TICKET_SKELETONS = {
    "Standard Incident Triage": """
<h3>📋 [ISSUE DESCRIPTION]</h3>
<p><strong>Caller / User:</strong> </p>
<p><strong>Impacted Device / Hostname:</strong> </p>
<p><strong>Symptom / Error:</strong> </p>

<h3>🔍 [DIAGNOSTICS & TROUBLESHOOTING]</h3>
<ul>
    <li>Ping / DNS resolution: </li>
    <li>Service status: </li>
    <li>Recent event log / error code: </li>
</ul>

<h3>🎯 [ROOT CAUSE]</h3>
<p></p>

<h3>✅ [RESOLUTION STEPS]</h3>
<ol>
    <li></li>
</ol>
<p><strong>Verification:</strong> Tested with user, confirmed working.</p>
""",
    "Quick Triage / Quick Fix": """
<p><strong>Ticket Subject:</strong> </p>
<p><strong>User / Host:</strong> </p>
<p><strong>Problem Summary:</strong> </p>
<p><strong>Action Taken:</strong> </p>
<p><strong>Status:</strong> ✅ Resolved</p>
""",
    "Maintenance & Change Plan": """
<h3>🛠️ [CHANGE / MAINTENANCE PLAN]</h3>
<p><strong>Target Host / Infrastructure:</strong> </p>
<p><strong>Maintenance Window:</strong> </p>

<h4>1. Pre-Execution Checks:</h4>
<ul>
    <li>Backup verified: </li>
    <li>Snapshot taken: </li>
</ul>

<h4>2. Execution Steps:</h4>
<ol>
    <li></li>
</ol>

<h4>3. Post-Verification & Health Check:</h4>
<ul>
    <li>Services restarted and listening: </li>
    <li>Connectivity confirmed: </li>
</ul>

<h4>4. Rollback Plan:</h4>
<p></p>
""",
}

