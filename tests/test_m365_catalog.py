"""Synthetic catalog/schema/GUI tests. No operation scripts or tenant access."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QPlainTextEdit

from src.services.m365_catalog_service import (
    CatalogError, CONTRACT_ROOT, ManifestValidator, M365CatalogService, ROOT,
)
from src.ui.m365.launcher_widget import M365LauncherWidget
from test_ui_integration import main_window


EXPECTED = ["dashboard", "companies", "general", "entra-id", "exchange-online",
            "licensing", "teams", "sharepoint", "onedrive", "intune", "security",
            "reports", "workflows", "other"]


@pytest.fixture
def registration(tmp_path):
    metadata = tmp_path / "metadata"
    library = tmp_path / "library"
    shutil.copytree(ROOT / "assets/m365", metadata)
    library.mkdir()
    original = json.loads((ROOT / "tests/fixtures/m365/manifest.json").read_text())

    def build(manifests=None, entries=None):
        manifests = [copy.deepcopy(original)] if manifests is None else manifests
        registrations = []
        for i, manifest in enumerate(manifests):
            path = library / f"synthetic-{i}.manifest.json"
            raw = json.dumps(manifest).encode()
            path.write_bytes(raw)
            registrations.append({"manifest_path": path.name, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                                  "category_ids": [manifest.get("category", "general")], "lifecycle": "active"})
        if entries:
            entries(registrations)
        (metadata / "catalog.json").write_text(json.dumps({"format_version": 1, "operations": registrations}))
        return M365CatalogService(metadata, library, CONTRACT_ROOT)

    return build, original, metadata, library


def test_exact_category_taxonomy_unique_order_and_empty_production_catalog():
    service = M365CatalogService()
    assert [c.id for c in service.categories] == EXPECTED
    assert len({c.id for c in service.categories}) == 14
    assert [c.order for c in service.categories] == sorted(c.order for c in service.categories)
    assert service.category("general").label == "General"
    assert service.category("other").label == "Other"
    assert all(service.operations(c.id) == () for c in service.categories)
    assert not service.validation_errors
    with pytest.raises(CatalogError):
        service.operation("M365.UNKNOWN.OPERATION")
    with pytest.raises(CatalogError):
        service.category("Personal")


@pytest.mark.parametrize("field,value", [("id", "general"), ("order", 30), ("label", "General"),
                                         ("id", "Bad ID"), ("order", True), ("icon", ""), ("kind", "executable")])
def test_invalid_category_metadata_rejected(registration, field, value):
    _, _, metadata, library = registration
    path = metadata / "categories.json"
    data = json.loads(path.read_text())
    data["categories"][0][field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(CatalogError):
        M365CatalogService(metadata, library)


def test_search_filters_and_single_authoritative_definition(registration):
    build, manifest, _, _ = registration
    second = copy.deepcopy(manifest)
    second.update(script_id="M365.TEST.ARCHIVED", title="Historic inspection")
    service = build([manifest, second], lambda entries: (entries[0].update(category_ids=["general", "other"]),
                                                         entries[1].update(lifecycle="archived")))
    operation = service.operation(manifest["script_id"])
    assert service.operations("general") == (operation,)
    assert service.operations("other") == (operation,)
    for text in ("CATALOG", "cross-service", "diagnostics", "graph", "M365.TEST.CATALOG", "synthetic graph"):
        assert service.operations("general", text) == (operation,)
    assert not service.operations("general", "no match")
    assert not service.operations("general", risk="write")
    assert len(service.operations("general", lifecycle="all")) == 2
    assert service.operations("general", lifecycle="archived")[0].id == second["script_id"]
    assert not operation.eligible
    assert len(operation.disabled_reasons) == 4
    assert "required_roles" in operation.details and "parameters" in operation.details


def test_duplicate_ids_reject_all_conflicting_entries(registration):
    build, manifest, _, _ = registration
    service = build([manifest, manifest])
    assert service.validation_errors
    assert not service.operations("general")
    with pytest.raises(CatalogError):
        service.operation(manifest["script_id"])


@pytest.mark.parametrize("categories", [["unknown"], ["general", "unknown"], ["other", "other"],
                                        ["dashboard"], ["companies"], ["workflows"], ["other"], [], [3]])
def test_bad_category_references_never_fall_back_to_other(registration, categories):
    build, _, _, _ = registration
    service = build(entries=lambda entries: entries[0].update(category_ids=categories))
    assert service.validation_errors
    assert not service.operations("general") and not service.operations("other")


@pytest.mark.parametrize("change", [
    lambda m: m.update(contract_version="1.0.0"),
    lambda m: m.pop("target_policy"),
    lambda m: m.update(script_path="../escape.ps1"),
    lambda m: m.update(expected_output_schema="schemas/operation-data.schema.json#/$defs/unknown"),
    lambda m: m.update(expected_output_schema="schemas/unknown.schema.json#/$defs/user_identity"),
    lambda m: m.update(approval=True),
    lambda m: m.update(connection_requirements=["ExchangeOnline"]),
    lambda m: m.update(required_roles=[{"service": "ExchangeOnline", "any_of": ["Role"]}]),
    lambda m: m["target_policy"]["output_binding"].update(upn_field=None),
    lambda m: m["parameters"][0].update(name="Context"),
    lambda m: m["parameters"].append({**m["parameters"][0], "name": "LIMIT"}),
    lambda m: m["parameters"][0].update(minimum=9, maximum=2),
    lambda m: m["parameters"][0].update(default=True),
    lambda m: m["parameters"][0].update(default=20),
    lambda m: m["parameters"][0].update(minimum=1.5),
    lambda m: m["parameters"][0].update(max_length=10),
    lambda m: m["parameters"][0].update(allowed_values=[1, 1]),
    lambda m: m["parameters"][0].update(allowed_values=[20]),
    lambda m: m["parameters"][0].update(type="string_array", default=[], allowed_values=["a"]),
    lambda m: m.update(risk="write"),
])
def test_invalid_manifests_quarantined_before_presentation(registration, change):
    build, manifest, _, _ = registration
    change(manifest)
    service = build([manifest])
    assert service.validation_errors
    assert not service.operations("general")


@pytest.mark.parametrize("path", ["../outside.json", "C:/outside.json", "general\\bad.json", "%2e%2e/file.json", "missing.json"])
def test_registration_path_rejection(registration, path):
    build, _, _, _ = registration
    service = build(entries=lambda entries: entries[0].update(manifest_path=path))
    assert service.validation_errors and not service.operations("general")


def test_manifest_hash_mismatch_and_duplicate_json_keys(registration):
    build, _, metadata, library = registration
    service = build(entries=lambda entries: entries[0].update(manifest_sha256="f" * 64))
    assert service.validation_errors
    (metadata / "catalog.json").write_text('{"format_version":1,"operations":[],"operations":[]}')
    with pytest.raises(CatalogError, match="Duplicate"):
        M365CatalogService(metadata, library)


def test_schema_pins_reject_drift_without_remote_resolution(tmp_path):
    root = tmp_path / "contract"
    shutil.copytree(CONTRACT_ROOT / "schemas", root / "schemas")
    path = root / "schemas/common.schema.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(CatalogError, match="identity changed"):
        ManifestValidator(root, ROOT / "assets/m365/contract-review-pins.json")


def test_catalog_failure_preserves_back_navigation(qapp, monkeypatch):
    def broken_catalog():
        raise CatalogError("Synthetic invalid registry")
    monkeypatch.setattr("src.ui.m365.launcher_widget.M365CatalogService", broken_catalog)
    widget = M365LauncherWidget()
    try:
        widget.resize(640, 380)
        widget.show()
        qapp.processEvents()
        assert widget.catalog_service is None
        assert widget.back_button.isVisible() and widget.back_button.isEnabled()
        received = []
        widget.back_requested.connect(lambda: received.append(True))
        QTest.mouseClick(widget.back_button, Qt.LeftButton)
        assert received == [True]
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("width,height", [(640, 380), (700, 1000), (853, 480), (1024, 576)])
def test_new_category_controls_fit_narrow_and_portrait_viewports(launcher, qapp, width, height):
    launcher.resize(width, height)
    launcher.navigation.setCurrentRow(13)
    qapp.processEvents()
    assert launcher.width() <= width and launcher.height() <= height
    assert launcher.back_button.isVisible() and launcher.scroll_area.isVisible()
    for control in (launcher.search_input, launcher.risk_filter, launcher.lifecycle_filter,
                    launcher.operation_list, launcher.operation_details):
        assert control.width() <= launcher.scroll_area.viewport().width()
        assert control.accessibleName()
    launcher.nav_toggle.setChecked(False)
    qapp.processEvents()
    assert launcher.navigation.isHidden()
    launcher.nav_toggle.setChecked(True)
    qapp.processEvents()
    assert launcher.navigation.isVisible() and launcher.current_category_id == "other"


@pytest.fixture
def launcher(qapp):
    widget = M365LauncherWidget()
    widget.resize(800, 600)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_all_navigation_ids_keyboard_and_empty_states(launcher, qapp):
    assert [launcher.navigation.item(i).data(Qt.UserRole) for i in range(14)] == EXPECTED
    for i, category_id in enumerate(EXPECTED):
        launcher.navigation.setCurrentRow(i)
        qapp.processEvents()
        assert launcher.current_category_id == category_id
        assert launcher.operation_list.count() == 0
        assert launcher.catalog_status.text()
        assert launcher.category_title.text() == launcher.catalog_service.category(category_id).label
    launcher.navigation.setCurrentRow(1)
    launcher.navigation.setFocus()
    QTest.keyClick(launcher.navigation, Qt.Key_Down)
    assert launcher.current_category_id == "general"
    assert "No approved operations" in launcher.catalog_status.text()
    launcher.search_input.setText("unmatched")
    assert "No operations match" in launcher.catalog_status.text()
    # Labels can change without changing the IDs used for navigation.
    launcher.navigation.currentItem().setText("Renamed label")
    assert launcher.current_category_id == "general"


def test_unapproved_metadata_details_search_and_no_dispatch(registration, qapp, monkeypatch):
    build, _, _, _ = registration
    service = build()
    def forbidden(*args, **kwargs):
        pytest.fail("Catalog controls attempted process or network dispatch")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    widget = M365LauncherWidget(catalog_service=service)
    try:
        widget.show()
        widget.navigation.setCurrentRow(EXPECTED.index("general"))
        qapp.processEvents()
        assert widget.operation_list.count() == 1
        assert "Unavailable" in widget.operation_list.item(0).text()
        assert "trust and approval" in widget.operation_details.toPlainText()
        assert widget.operation_details.isReadOnly()
        assert all(edit.isReadOnly() for edit in widget.findChildren(QPlainTextEdit))
        assert [button.text() for button in widget.findChildren(QPushButton)] == ["Back to T-Notes"]
        QTest.keyClick(widget.operation_list, Qt.Key_Return)
        widget.operation_list.itemDoubleClicked.emit(widget.operation_list.item(0))
        widget.search_input.setText("missing")
        assert widget.operation_list.count() == 0 and not widget.operation_details.toPlainText()
        widget.search_input.clear()
        widget.risk_filter.setCurrentIndex(2)
        assert widget.operation_list.count() == 0
        widget.risk_filter.setCurrentIndex(0)
        assert widget.operation_list.count() == 1
        for row in range(14):
            widget.navigation.setCurrentRow(row)
        assert not hasattr(service, "execute")
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def test_no_production_import_of_provisional_engine_or_process_apis():
    for path in (ROOT / "src/services/m365_catalog_service.py", ROOT / "src/ui/m365/launcher_widget.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        assert not any(name.split(".")[0] in {"subprocess", "socket", "requests", "httpx", "importlib"} for name in imports)
        assert not any("prototype" in name for name in imports)


def test_alt_f8_from_new_catalog_controls_preserves_notes(main_window, qapp):
    main_window.show()
    main_window.activateWindow()
    qapp.processEvents()
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Synthetic catalog workspace regression")
    document = editor.document()
    main_window.show_m365_workspace()
    widget = main_window.m365_workspace
    widget.navigation.setCurrentRow(2)
    widget.search_input.setFocus()
    qapp.processEvents()
    QTest.keyClick(widget.search_input, Qt.Key_F8, Qt.AltModifier)
    qapp.processEvents()
    assert not main_window.is_m365_workspace
    assert main_window._get_active_editor() is editor and editor.document() is document
    assert "Synthetic catalog workspace regression" in editor.toPlainText()
