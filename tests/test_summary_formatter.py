"""Unit tests for Bilingual Client & PSA Ticket Summary Formatter Service."""

import pytest
from src.services.summary_formatter_service import (
    SummaryFormatterService,
    ParsedTicketSections,
)


def test_calculate_billable_hours():
    # 0 seconds -> 0.0h
    assert SummaryFormatterService.calculate_billable_hours(0) == 0.0

    # 1 second to 900 seconds (15 min) -> 0.25h
    assert SummaryFormatterService.calculate_billable_hours(1) == 0.25
    assert SummaryFormatterService.calculate_billable_hours(900) == 0.25

    # 901 seconds (15m 1s) to 1800 seconds (30m) -> 0.50h
    assert SummaryFormatterService.calculate_billable_hours(901) == 0.50
    assert SummaryFormatterService.calculate_billable_hours(1800) == 0.50

    # 35 min (2100 seconds) -> 4 blocks -> 1.00h (Wait: 2100 / 900 = 2.33 -> 3 blocks -> 0.75h)
    assert SummaryFormatterService.calculate_billable_hours(2100) == 0.75


def test_format_time_logged_en_and_fr():
    # 35 min = 2100 seconds
    en_time = SummaryFormatterService.format_time_logged(2100, lang="en")
    assert "00:35:00" in en_time
    assert "0.75h billable" in en_time

    fr_time = SummaryFormatterService.format_time_logged(2100, lang="fr")
    assert "00:35:00" in fr_time
    assert "0,75 h facturable" in fr_time


def test_parse_english_structured_ticket():
    ticket = {
        "ticket_number": "INC-8491",
        "client_name": "Acme Corp / Sarah Connor",
        "title": "VPN connection failing with Error 800",
        "elapsed_seconds": 1800,
        "content_html": """
        <h1>Issue</h1>
        <p>User unable to connect to corporate VPN from home. Error 800 displayed.</p>
        <h2>Troubleshooting</h2>
        <p>- [x] Tested WAN DNS resolution</p>
        <p>- [x] Cleared stale VPN credentials</p>
        <p>- [ ] Check router firmware</p>
        <h2>Resolution</h2>
        <p>Reinstalled Cisco AnyConnect client and imported root CA certificate.</p>
        <h3>Root Cause</h3>
        <p>Expired client authentication certificate in Windows certificate store.</p>
        <h3>Next Steps</h3>
        <p>User tested connection successfully on home Wi-Fi.</p>
        """,
    }

    sections = SummaryFormatterService.parse_ticket(ticket, technician_name="John Tech")

    assert sections.ticket_number == "INC-8491"
    assert sections.client_name == "Acme Corp / Sarah Connor"
    assert sections.title == "VPN connection failing with Error 800"
    assert sections.technician_name == "John Tech"

    assert "Error 800" in sections.issue
    assert "Tested WAN DNS resolution" in sections.work_performed
    assert "Reinstalled Cisco AnyConnect" in sections.resolution
    assert "Expired client authentication" in sections.root_cause
    assert "tested connection successfully" in sections.next_steps


def test_parse_french_structured_ticket():
    ticket = {
        "ticket_number": "BIL-2041",
        "client_name": "Ville de Montréal / Pierre Dupont",
        "title": "Imprimante réseau inaccessible",
        "elapsed_seconds": 2700,  # 45 min
        "content_html": """
        <h1>Problème</h1>
        <p>L'imprimante HP LaserJet 400 n'apparaît plus sur le réseau local.</p>
        <h2>Dépannage</h2>
        <p>- [x] Vérification de l'adresse IP sur le routeur</p>
        <p>- [x] Redémarrage du spouleur d'impression Windows</p>
        <h2>Résolution</h2>
        <p>Attribution d'un bail DHCP statique et réinstallation du pilote PCL6.</p>
        <h3>Cause racine</h3>
        <p>Changement d'adresse IP non réservée suite à une panne de courant.</p>
        <h3>Prochaines étapes</h3>
        <p>L'utilisateur a imprimé une page de test avec succès.</p>
        """,
    }

    sections = SummaryFormatterService.parse_ticket(ticket, technician_name="Marie Curie")

    assert sections.ticket_number == "BIL-2041"
    assert sections.client_name == "Ville de Montréal / Pierre Dupont"
    assert "HP LaserJet 400" in sections.issue
    assert "Vérification de l'adresse IP" in sections.work_performed
    assert "Attribution d'un bail DHCP" in sections.resolution
    assert "Changement d'adresse IP" in sections.root_cause
    assert "page de test avec succès" in sections.next_steps


def test_parse_unstructured_with_checklists():
    ticket = {
        "ticket_number": "1002",
        "client_name": "Globex",
        "title": "User password reset",
        "elapsed_seconds": 600,
        "content_html": """
        <p>User called in locked out after vacation.</p>
        <p>- [x] Verified user identity via manager SMS</p>
        <p>- [x] Reset Active Directory password</p>
        <p>- [x] Forced password change at next logon</p>
        """,
    }

    sections = SummaryFormatterService.parse_ticket(ticket)
    assert sections.ticket_number == "1002"
    assert "locked out" in sections.issue
    assert "Verified user identity" in sections.work_performed
    assert "Reset Active Directory password" in sections.work_performed


def test_parse_ticket_strips_qt_css_styles():
    qt_raw_html = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">
<html><head><meta name="qrichtext" content="1" /><meta charset="utf-8" /><style type="text/css">
p, li { white-space: pre-wrap; }
hr { height: 1px; border-width: 0; }
li.unchecked::marker { content: "\\2610"; }
li.checked::marker { content: "\\2612"; }
</style></head><body style=" font-family:'Segoe UI'; font-size:10pt; font-weight:400; font-style:normal;">
<p>Investigated server connectivity issue.</p>
<p>- [x] Checked NIC link state</p>
<p>- [x] Verified default gateway ping</p>
</body></html>"""

    ticket = {
        "ticket_number": "NET-500",
        "client_name": "Contoso",
        "title": "Server offline",
        "content_html": qt_raw_html,
    }

    sections = SummaryFormatterService.parse_ticket(ticket)
    all_fields = f"{sections.issue} {sections.work_performed} {sections.resolution} {sections.root_cause}"
    assert "white-space" not in all_fields
    assert "pre-wrap" not in all_fields
    assert "border-width" not in all_fields
    assert "::marker" not in all_fields
    assert "2610" not in all_fields
    assert "2612" not in all_fields

    assert "Investigated server connectivity issue." in sections.issue
    assert "Checked NIC link state" in sections.work_performed


def test_format_client_email_en():
    sections = ParsedTicketSections(
        ticket_number="INC-100",
        client_name="Alice Smith",
        title="Email sync error on iPhone",
        elapsed_seconds=1200,
        issue="iPhone Mail app stopped syncing incoming emails.",
        work_performed="Re-authenticated Microsoft 365 Exchange account.",
        resolution="Account credentials refreshed and Modern Auth token re-established.",
        next_steps="Please open the Mail app and ensure your inbox updates.",
        technician_name="Jonathan Decelles",
        technician_email="Jonathan_Decelles1990@hotmail.com",
    )

    plain, rich_html = SummaryFormatterService.format_client_email(sections, lang="en", include_time=False)
    assert "Hello Alice Smith," in plain
    assert "Regarding Ticket #INC-100 — Email sync error on iPhone:" in plain
    assert "Summary of Issue:" in plain
    assert "iPhone Mail app stopped syncing incoming emails." in plain
    assert "Actions Taken & Resolution:" in plain
    assert "Next Steps for You:" in plain
    assert "Jonathan Decelles" in plain
    assert "Jonathan_Decelles1990@hotmail.com" in plain
    assert "IT Support" in plain
    assert "<div" in rich_html


def test_format_client_email_fr():
    sections = ParsedTicketSections(
        ticket_number="BIL-200",
        client_name="Jean Tremblay",
        title="Accès au dossier partagé bloqué",
        elapsed_seconds=1500,
        issue="Message d'accès refusé sur le lecteur Z:.",
        work_performed="Vérification des droits d'accès Active Directory.",
        resolution="Ajout de l'utilisateur au groupe Comptabilité_Lecture.",
        next_steps="Veuillez redémarrer votre session pour appliquer les permissions.",
        technician_name="Jonathan Decelles",
        technician_email="Jonathan_Decelles1990@hotmail.com",
    )

    plain, rich_html = SummaryFormatterService.format_client_email(sections, lang="fr", include_time=True)
    assert "Bonjour Jean Tremblay," in plain
    assert "Concernant le billet #BIL-200 — Accès au dossier partagé bloqué :" in plain
    assert "Description du problème :" in plain
    assert "Actions effectuées et résolution :" in plain
    assert "Prochaines étapes pour vous :" in plain
    assert "Temps consacré :" in plain
    assert "Jonathan Decelles" in plain
    assert "Jonathan_Decelles1990@hotmail.com" in plain
    assert "Support informatique" in plain
    assert "<div" in rich_html


def test_format_psa_note_en_and_fr():
    sections = ParsedTicketSections(
        ticket_number="5541",
        client_name="Initech",
        title="Printer driver fault",
        elapsed_seconds=1800,
        issue="Error code 0x0000011b on network print queue.",
        work_performed="Applied Point and Print RPC registry fix.",
        resolution="Print queue restored; test page printed successfully.",
        root_cause="Microsoft security patch hardening RPC bindings.",
        technician_name="Jonathan Decelles",
        technician_email="Jonathan_Decelles1990@hotmail.com",
    )

    # English PSA
    plain_en, _ = SummaryFormatterService.format_psa_note(sections, lang="en", include_time=True)
    assert "=== TICKET: #5541 | Client: Initech ===" in plain_en
    assert "ISSUE REPORTED:" in plain_en
    assert "WORK PERFORMED / TROUBLESHOOTING:" in plain_en
    assert "ROOT CAUSE:" in plain_en
    assert "RESOLUTION:" in plain_en
    assert "Jonathan Decelles <Jonathan_Decelles1990@hotmail.com>" in plain_en
    assert "0.50h billable" in plain_en

    # French PSA
    plain_fr, _ = SummaryFormatterService.format_psa_note(sections, lang="fr", include_time=True)
    assert "=== BILLET : #5541 | Client : Initech ===" in plain_fr
    assert "PROBLÈME SIGNALÉ :" in plain_fr
    assert "DÉPANNAGE / TRAVAIL EFFECTUÉ :" in plain_fr
    assert "CAUSE RACINE :" in plain_fr
    assert "RÉSOLUTION :" in plain_fr
    assert "Jonathan Decelles <Jonathan_Decelles1990@hotmail.com>" in plain_fr
    assert "0,50 h facturable" in plain_fr


def test_format_escalation_handover_en_and_fr():
    sections = ParsedTicketSections(
        ticket_number="9901",
        client_name="Umbrella Corp",
        title="SQL database timeouts",
        elapsed_seconds=3600,
        issue="Application reporting frequent connection timeouts to SQL Cluster.",
        work_performed="Verified network ping and latency (<1ms). Restarted SQL service.",
        root_cause="Suspected index fragmentation or deadlocks in tempdb.",
        next_steps="Tier 2 DBA review of SQL profiler traces.",
        technician_name="Dave",
    )

    plain_en, _ = SummaryFormatterService.format_escalation_handover(sections, lang="en")
    assert "=== ESCALATION HANDOVER: #9901 ===" in plain_en
    assert "CURRENT SITUATION & IMPACT:" in plain_en
    assert "RECOMMENDED NEXT ACTIONS:" in plain_en

    plain_fr, _ = SummaryFormatterService.format_escalation_handover(sections, lang="fr")
    assert "=== TRANSFERT D'ESCALADE : #9901 ===" in plain_fr
    assert "SITUATION ACTUELLE ET IMPACT :" in plain_fr
    assert "PROCHAINES ACTIONS RECOMMANDÉES :" in plain_fr


def test_summary_formatter_dialog_lifecycle(qapp, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.ui.dialogs.summary_formatter_dialog import SummaryFormatterDialog

    ticket = {
        "ticket_number": "T-770",
        "client_name": "Wayne Enterprises",
        "title": "Batcomputer cooling error",
        "elapsed_seconds": 1800,
        "content_html": "<p>Cooling pump pressure low.</p>",
    }

    copied_texts = []
    monkeypatch.setattr(QApplication.clipboard(), "setText", lambda txt: copied_texts.append(txt))

    dlg = SummaryFormatterDialog(ticket=ticket, default_lang="en")
    dlg.show()

    assert not dlg.isHidden()
    assert dlg.txt_issue.toPlainText() == "Batcomputer cooling error"
    assert "Cooling pump pressure low." in dlg.txt_work.toPlainText()

    # Modify field and verify preview updates
    dlg.txt_resolution.setPlainText("Replaced cryogenic valve.")
    assert "Replaced cryogenic valve." in dlg.preview_edit.toPlainText()

    # Copy plain text
    dlg._copy_plain_text()
    assert len(copied_texts) == 1
    assert copied_texts[-1] == dlg.preview_edit.toPlainText()
    assert "✓" in dlg.lbl_status.text()

    dlg.close()


def test_summary_formatter_dialog_language_and_preset_switching(qapp):
    from src.ui.dialogs.summary_formatter_dialog import SummaryFormatterDialog

    ticket = {
        "ticket_number": "FR-101",
        "client_name": "Stark Industries",
        "title": "Arc Reactor maintenance",
        "elapsed_seconds": 3600,
        "content_html": "<h1>Problème</h1><p>Surchauffe réacteur.</p><h2>Résolution</h2><p>Remplacement du palladium.</p>",
    }

    dlg = SummaryFormatterDialog(ticket=ticket, default_lang="en")

    # Switch to French
    dlg.btn_lang_fr.setChecked(True)
    assert dlg.current_lang == "fr"
    assert "Bonjour Stark Industries," in dlg.preview_edit.toPlainText()
    assert "Remplacement du palladium." in dlg.preview_edit.toPlainText()

    # Switch to PSA preset
    dlg.combo_preset.setCurrentIndex(SummaryFormatterDialog.PRESET_PSA)
    assert "=== BILLET : #FR-101 | Client : Stark Industries ===" in dlg.preview_edit.toPlainText()
    assert "1,00 h facturable" in dlg.preview_edit.toPlainText()

    # Switch to Escalation preset
    dlg.combo_preset.setCurrentIndex(SummaryFormatterDialog.PRESET_ESCALATION)
    assert "=== TRANSFERT D'ESCALADE : #FR-101 ===" in dlg.preview_edit.toPlainText()

    dlg.close()

