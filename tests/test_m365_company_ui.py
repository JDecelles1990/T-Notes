"""Qt synthetic controls and isolated Notes workspace protection."""

from uuid import uuid4

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QLineEdit

from src.services.m365_company_service import CompanyDirectory, synthetic_directory
from src.ui.m365.company_context_panel import AdministratorDialog, ProfileDialog
from src.ui.m365.launcher_widget import M365LauncherWidget
from test_ui_integration import main_window


@pytest.fixture
def launcher(qapp):
    widget = M365LauncherWidget()
    widget.resize(800, 900)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


def select_first(panel):
    panel.company_combo.setCurrentIndex(1)
    assert panel.context.company is not None


def test_company_search_and_safe_empty_gui(qapp):
    widget = M365LauncherWidget(company_directory=CompanyDirectory())
    panel = widget.company_panel
    assert panel.company_combo.count() == 1
    assert not panel.confirm_button.isEnabled()
    assert not panel.graph_button.isEnabled()
    assert not panel.edit_company.isEnabled()
    assert panel.add_company.isEnabled()
    assert panel.context.company is None
    widget.deleteLater()


def test_search_selection_confirmation_and_switching(launcher):
    panel = launcher.company_panel
    select_first(panel)
    company = panel.context.company
    assert panel.company_combo.currentData() == company.company_id
    assert company.tenant_id in panel.selected_tenant.text()
    panel.confirm_button.click()
    assert panel.context.confirmed_company
    assert "none" in panel.verified_identity.text()
    panel.graph_button.click()
    assert panel.context.confirmed_company is None
    assert "Graph: simulated" in panel.connection_status.text()
    assert "ExchangeOnline: disconnected" in panel.connection_status.text()
    panel.target_upn.setText("client@alpine.example")
    panel.resolve_button.click()
    assert panel.context.target
    panel.company_search.setText("BIRCH.EX")
    assert panel.company_combo.count() == 2
    assert panel.context.company is None  # Search cannot silently retarget a company.
    assert panel.context.target is None
    assert not panel.target_upn.text()
    assert not panel.graph_button.isEnabled()
    panel.company_combo.setCurrentIndex(1)
    assert panel.context.company.primary_domain == "birch.example"
    assert panel.administrator_combo.count() == 1
    assert not panel.context.administrator_upn


def test_admin_crud_forms_and_default(launcher):
    panel = launcher.company_panel
    select_first(panel)
    company_id = panel.context.company_id
    first = panel.context.company.administrators[0]
    form = AdministratorDialog(panel.directory, company_id, first)
    form.upn.setText("edited@alpine.example")
    form._save()
    assert form.result_administrator.administrator_id == first.administrator_id
    assert panel.directory.get(company_id).administrators[-1].upn == "edited@alpine.example"
    form.deleteLater()
    panel.context.synchronize()
    panel.refresh_administrators()
    panel.admin_default.click()
    assert panel.context.company.preferred_administrator_id == first.administrator_id
    panel.admin_remove.click()
    assert len(panel.context.company.administrators) == 1
    assert panel.context.company.preferred_administrator_id is None
    assert not panel.context.administrator_upn
    assert not panel.graph_button.isEnabled()
    new_form = AdministratorDialog(panel.directory, company_id)
    new_form.upn.setText("BACKUP@ALPINE.EXAMPLE")
    new_form._save()
    assert new_form.result_administrator is None
    assert "unique" in new_form.error.text()
    new_form.upn.setText("third@alpine.example")
    new_form._save()
    assert new_form.result_administrator
    new_form.deleteLater()


def test_profile_form_validation_and_edit_stable_ids(qapp):
    directory = synthetic_directory()
    company = directory.search()[0]
    form = ProfileDialog(directory, company)
    form.fields["tenant_id"].setText("invalid")
    form._save()
    assert form.result_company is None
    assert directory.get(company.company_id) == company
    form.fields["tenant_id"].setText(company.tenant_id)
    form.fields["display_name"].setText("Renamed Example")
    form._save()
    assert form.result_company.company_id == company.company_id
    assert form.result_company.administrators == company.administrators
    assert form.result_company.created_at == company.created_at
    form.deleteLater()
    new_form = ProfileDialog(directory)
    new_form.fields["display_name"].setText("Third Example")
    new_form.fields["tenant_id"].setText(str(uuid4()))
    new_form.fields["primary_domain"].setText("third.example")
    new_form._save()
    assert new_form.result_company and not new_form.result_company.administrators
    new_form.deleteLater()


def test_admin_search_and_no_automatic_authentication(launcher):
    panel = launcher.company_panel
    select_first(panel)
    assert panel.context.administrator_upn == "admin@alpine.example"
    assert panel.context.connections.state("Graph").state == "disconnected"
    panel.administrator_search.setText("BACKUP")
    assert panel.administrator_combo.count() == 2
    assert panel.context.administrator_id is None
    panel.administrator_combo.setCurrentIndex(1)
    assert panel.context.administrator_upn == "backup@alpine.example"
    assert panel.context.connections.state("Graph").state == "disconnected"
    panel.graph_button.click()
    panel.admin_upn.setText("different@alpine.example")
    assert panel.context.administrator_id is None
    assert panel.context.connections.state("Graph").state == "disconnected"
    panel.admin_upn.setText("invalid")
    assert not panel.graph_button.isEnabled()
    assert panel.error.text()


def test_target_fields_mismatch_and_no_verified_claim(launcher):
    panel = launcher.company_panel
    select_first(panel)
    panel.target_upn.setText("client@foreign.example")
    assert "mismatch warning" in panel.target_status.text()
    panel.target_object_id.setText(str(uuid4()))
    panel.resolve_button.click()
    assert "not verified" in panel.target_status.text()
    assert "Verified target: none" in panel.target_status.text()
    assert "none in this synthetic preview" in panel.eligibility_status.text()
    assert panel.context.eligibility().eligible is False
    assert panel.admin_upn.text() != panel.target_upn.text()
    panel.target_upn.setText("bad")
    assert panel.context.target is None
    assert not panel.resolve_button.isEnabled()
    assert all(e.echoMode() == QLineEdit.Normal for e in launcher.findChildren(QLineEdit))


def test_expiry_and_failure_display(launcher):
    panel = launcher.company_panel
    select_first(panel)
    panel.context.connect_synthetic("Graph", seconds=-1)
    panel.context.connect_synthetic("ExchangeOnline", outcome="error")
    panel.refresh_status()
    assert "Graph: expired" in panel.connection_status.text()
    assert "ExchangeOnline: error" in panel.connection_status.text()
    assert "No Microsoft sign-in occurred" in panel.connection_status.text()
    panel.disconnect_button.click()
    assert "Graph: disconnected" in panel.connection_status.text()
    assert "ExchangeOnline: disconnected" in panel.connection_status.text()


@pytest.mark.parametrize("width", [640, 800, 1100])
def test_context_controls_fit_responsive_groups(launcher, qapp, width):
    launcher.resize(width, 900)
    qapp.processEvents()
    launcher.nav_toggle.setChecked(False)
    launcher.ticket_panel_toggle.setChecked(False)
    qapp.processEvents()
    panel = launcher.company_panel
    for widget in (panel.company_combo, panel.admin_upn, panel.administrator_combo, panel.graph_button, panel.target_upn):
        assert widget.parentWidget().rect().contains(widget.geometry())
        assert widget.accessibleName() or widget.text()
    assert launcher.navigation.count() == 14


def test_notes_unchanged_by_company_context(main_window, qapp):
    window = main_window
    window.show()
    editor = window._get_active_editor()
    editor.textCursor().insertText("Company context must not replace this case note.")
    document = editor.document()
    window.flush_all_saves()
    before = window.scratchpad_service.get_ticket(editor.scratchpad_id)["content_html"]
    assert window.show_m365_workspace()
    panel = window.m365_workspace.company_panel
    qapp.processEvents()
    assert panel.timer.isActive()
    select_first(panel)
    panel.graph_button.click()
    panel.target_upn.setText("client@alpine.example")
    panel.resolve_button.click()
    panel.confirm_button.click()
    panel.company_combo.setCurrentIndex(2)
    window.show_notes_workspace()
    qapp.processEvents()
    assert not panel.timer.isActive()
    assert window._get_active_editor() is editor
    assert editor.document() is document
    assert "Company context must not replace" in editor.toPlainText()
    assert window.scratchpad_service.get_ticket(editor.scratchpad_id)["content_html"] == before


def test_exact_30_domain_reproduction_and_name_only_edit(qapp):
    directory = CompanyDirectory()

    # 1. 30 valid domains in exactly 1,975 input characters
    domains = []
    for i in range(30):
        target_len = 65 if i < 26 else 64
        prefix = f"d{i:02d}-"
        suffix = ".example.com"
        mid_len = target_len - len(prefix) - len(suffix)
        domains.append(f"{prefix}{'a' * mid_len}{suffix}")

    joined_input = ",".join(domains)
    assert len(joined_input) == 1975

    form = ProfileDialog(directory)
    form.fields["display_name"].setText("Initial Company")
    form.fields["tenant_id"].setText(str(uuid4()))
    form.fields["primary_domain"].setText("primary.example.com")
    form.fields["additional_verified_domains"].setText(joined_input)
    form._save()
    assert form.result_company is not None
    created = form.result_company
    assert len(created.additional_verified_domains) == 30
    assert created.additional_verified_domains == tuple(domains)
    form.deleteLater()

    # 2. Reopen the company
    reopen_form = ProfileDialog(directory, created)
    reopened_text = reopen_form.fields["additional_verified_domains"].text()
    # Ensure no truncation occurred
    assert len(reopened_text) >= 1975
    for domain in domains:
        assert domain in reopened_text

    # 3. Edit ONLY the company name
    reopen_form.fields["display_name"].setText("Edited Company Name")
    reopen_form._save()
    assert reopen_form.result_company is not None
    saved = reopen_form.result_company
    assert saved.display_name == "Edited Company Name"
    assert saved.additional_verified_domains == tuple(domains)
    # Explicitly check 30th domain is not corrupted or truncated
    assert saved.additional_verified_domains[-1] == domains[-1]
    reopen_form.deleteLater()


def test_domain_boundary_limits_and_explicit_rejection(qapp):
    directory = CompanyDirectory()

    # Boundary: 30 domains with maximum length labels (up to 253 chars each, totaling > 7000 chars)
    max_domains = []
    for i in range(30):
        label1 = f"m{i:02d}" + "a" * 60
        label2 = "b" * 63
        label3 = "c" * 63
        label4 = "d" * 58
        d = f"{label1}.{label2}.{label3}.{label4}.co"
        assert len(d) == 253
        max_domains.append(d)

    form = ProfileDialog(directory)
    form.fields["display_name"].setText("Max Domain Company")
    form.fields["tenant_id"].setText(str(uuid4()))
    form.fields["primary_domain"].setText("primary.example.com")
    form.fields["additional_verified_domains"].setText("\n".join(max_domains))
    form._save()
    assert form.result_company is not None
    max_comp = form.result_company
    assert len(max_comp.additional_verified_domains) == 30
    assert max_comp.additional_verified_domains == tuple(max_domains)
    form.deleteLater()

    # Reopen and edit name with 30 max domains
    reopen_form = ProfileDialog(directory, max_comp)
    assert len(reopen_form.fields["additional_verified_domains"].text()) >= 7590
    reopen_form.fields["display_name"].setText("Max Domain Renamed")
    reopen_form._save()
    assert reopen_form.result_company is not None
    assert reopen_form.result_company.display_name == "Max Domain Renamed"
    assert reopen_form.result_company.additional_verified_domains == tuple(max_domains)
    reopen_form.deleteLater()

    # Explicit rejection: 31 domains (1 above 30 limit)
    form_31 = ProfileDialog(directory)
    form_31.fields["display_name"].setText("31 Domains")
    form_31.fields["tenant_id"].setText(str(uuid4()))
    form_31.fields["primary_domain"].setText("primary.example.com")
    form_31.fields["additional_verified_domains"].setText("\n".join(max_domains + ["extra.example.com"]))
    form_31._save()
    assert form_31.result_company is None
    assert "at most 30 additional domains are supported" in form_31.error.text()
    form_31.deleteLater()

    # Explicit rejection: Domain exceeding 253 chars (254 chars)
    form_254 = ProfileDialog(directory)
    form_254.fields["display_name"].setText("254 Chars")
    form_254.fields["tenant_id"].setText(str(uuid4()))
    form_254.fields["primary_domain"].setText("primary.example.com")
    d254 = ("a" * 63 + ".") * 3 + "d" * 59 + ".co"
    assert len(d254) == 254
    form_254.fields["additional_verified_domains"].setText(d254)
    form_254._save()
    assert form_254.result_company is None
    assert "Enter 1–253 characters without control characters" in form_254.error.text()
    form_254.deleteLater()

    # Explicit rejection: Label exceeding 63 chars (64 chars)
    form_l64 = ProfileDialog(directory)
    form_l64.fields["display_name"].setText("L64 Domain")
    form_l64.fields["tenant_id"].setText(str(uuid4()))
    form_l64.fields["primary_domain"].setText("primary.example.com")
    form_l64.fields["additional_verified_domains"].setText("a" * 64 + ".example.com")
    form_l64._save()
    assert form_l64.result_company is None
    assert "Enter a valid DNS domain" in form_l64.error.text()
    form_l64.deleteLater()

    # Explicit rejection: Duplicate domain (case-insensitive)
    form_dup = ProfileDialog(directory)
    form_dup.fields["display_name"].setText("Dup Domain")
    form_dup.fields["tenant_id"].setText(str(uuid4()))
    form_dup.fields["primary_domain"].setText("primary.example.com")
    form_dup.fields["additional_verified_domains"].setText("dup.example.com\nDUP.EXAMPLE.COM")
    form_dup._save()
    assert form_dup.result_company is None
    assert "Domains must be unique" in form_dup.error.text()
    form_dup.deleteLater()

    # Explicit rejection: Duplicate of primary domain
    form_dup_pri = ProfileDialog(directory)
    form_dup_pri.fields["display_name"].setText("Dup Primary")
    form_dup_pri.fields["tenant_id"].setText(str(uuid4()))
    form_dup_pri.fields["primary_domain"].setText("primary.example.com")
    form_dup_pri.fields["additional_verified_domains"].setText("PRIMARY.EXAMPLE.COM")
    form_dup_pri._save()
    assert form_dup_pri.result_company is None
    assert "Domains must be unique" in form_dup_pri.error.text()
    form_dup_pri.deleteLater()

