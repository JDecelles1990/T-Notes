"""Settings configuration dialog for user preferences, Windows autostart, and backup exports."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import APP_NAME
from src.ui.components.glow_effect import apply_glow_to_buttons


class SettingsDialog(QDialog):
    """Modal dialog for customizing application preferences, startup behavior, and backups."""

    def __init__(
        self,
        current_settings: Dict[str, str],
        parent: Optional[QWidget] = None,
        autostart_service: Optional[Any] = None,
        backup_service: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Preferences")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._settings = current_settings
        self.autostart_service = autostart_service
        self.backup_service = backup_service
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(12)

        # 1. Ticket Prefix
        self.txt_prefix = QLineEdit(self._settings.get("ticket_prefix", "INC-"))
        self.txt_prefix.setPlaceholderText("e.g. INC-, REQ-, T-")
        form.addRow("Default Ticket Prefix:", self.txt_prefix)

        # 2. Auto-Save Delay (ms)
        self.spin_debounce = QSpinBox()
        self.spin_debounce.setRange(500, 5000)
        self.spin_debounce.setSingleStep(250)
        self.spin_debounce.setSuffix(" ms")
        self.spin_debounce.setValue(int(self._settings.get("auto_save_delay_ms", "1500")))
        form.addRow("Auto-Save Delay:", self.spin_debounce)

        # 3. JPEG Compression Quality (%)
        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(50, 100)
        self.spin_quality.setSingleStep(5)
        self.spin_quality.setSuffix("%")
        self.spin_quality.setValue(int(self._settings.get("jpeg_quality", "85")))
        form.addRow("Screenshot JPEG Quality:", self.spin_quality)

        # 4. Close Tab Action
        self.combo_close_action = QComboBox()
        self.combo_close_action.addItem("Prompt (Archive or Delete)", "prompt")
        self.combo_close_action.addItem("Archive Directly to History", "archive")
        current_close = self._settings.get("close_tab_action", "prompt")
        idx = 1 if current_close == "archive" else 0
        self.combo_close_action.setCurrentIndex(idx)
        form.addRow("Tab Close Action:", self.combo_close_action)

        # 5. Default Opacity (%)
        self.spin_opacity = QSpinBox()
        self.spin_opacity.setRange(60, 100)
        self.spin_opacity.setSingleStep(5)
        self.spin_opacity.setSuffix("%")
        self.spin_opacity.setValue(int(self._settings.get("window_opacity", "100")))
        form.addRow("Default Window Opacity:", self.spin_opacity)

        # 6. Windows Startup
        self.chk_autostart = QCheckBox("Start T-Notes automatically when Windows starts")
        if self.autostart_service:
            self.chk_autostart.setChecked(self.autostart_service.is_enabled())
        else:
            self.chk_autostart.setChecked(self._settings.get("autostart_enabled", "false") == "true")
        form.addRow("Windows Startup:", self.chk_autostart)

        # 7. Smart Restore
        self.chk_smart_restore = QCheckBox("Smart Restore (restore previous window / tray state on login)")
        self.chk_smart_restore.setChecked(self._settings.get("smart_restore_enabled", "true") == "true")
        form.addRow("Session Recovery:", self.chk_smart_restore)

        layout.addLayout(form)

        # Backup & Export Group
        backup_group = QGroupBox("Data Safety & Notes Export")
        backup_group.setStyleSheet("""
            QGroupBox {
                color: #9cdcfe;
                font-weight: bold;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 12px;
            }
        """)
        backup_layout = QHBoxLayout(backup_group)
        backup_layout.setSpacing(10)

        self.btn_backup_now = QPushButton("💾 Create Backup Snapshot Now")
        self.btn_backup_now.setToolTip("Creates an immediate SQLite database snapshot (.bak)")
        self.btn_backup_now.clicked.connect(self._on_backup_now_clicked)
        backup_layout.addWidget(self.btn_backup_now)

        self.btn_export_zip = QPushButton("📦 Export All Notes as ZIP...")
        self.btn_export_zip.setToolTip("Exports all tickets and embedded screenshots into a self-contained ZIP archive")
        self.btn_export_zip.clicked.connect(self._on_export_zip_clicked)
        backup_layout.addWidget(self.btn_export_zip)

        layout.addWidget(backup_group)

        # Company Directory Notice
        self.btn_merge = QPushButton("Merge", self)
        self.btn_merge.setAccessibleName("Merge company directory")
        self.btn_merge.setEnabled(False)
        self.btn_merge.setToolTip("Company Directory Merge is unavailable pending contract and storage approval.")
        layout.addWidget(self.btn_merge)

        self.merge_status = QLabel(
            "Company Directory Merge is unavailable. Profiles are session-only; "
            "contract, storage and backup approval are required.", self
        )
        self.merge_status.setStyleSheet("color: #858585; font-size: 9pt;")
        self.merge_status.setWordWrap(True)
        layout.addWidget(self.merge_status)

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Preferences")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save_clicked)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        apply_glow_to_buttons([self])

    def _on_backup_now_clicked(self) -> None:
        """Triggers manual database backup snapshot."""
        if not self.backup_service:
            QMessageBox.information(self, "Backup Snapshot", "Backup service is not available in standalone mode.")
            return

        try:
            path = self.backup_service.create_backup_snapshot()
            QMessageBox.information(
                self,
                "Backup Created",
                f"Successfully created database backup snapshot:\n\n{path}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Backup Error", f"Failed to create backup snapshot: {e}")

    def _on_export_zip_clicked(self) -> None:
        """Prompts destination and exports notes archive."""
        if not self.backup_service:
            QMessageBox.information(self, "Notes Export", "Export service is not available in standalone mode.")
            return

        default_name = f"tnotes_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export All Notes as ZIP",
            default_name,
            "ZIP Archives (*.zip);;All Files (*)",
        )
        if not dest_path:
            return

        try:
            self.backup_service.export_all_notes_to_zip(Path(dest_path))
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported all notes and media to:\n\n{dest_path}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export notes: {e}")

    def _on_save_clicked(self) -> None:
        """Applies autostart registry configuration and accepts dialog."""
        if self.autostart_service:
            try:
                self.autostart_service.set_enabled(self.chk_autostart.isChecked())
            except Exception as e:
                QMessageBox.warning(self, "Autostart Error", f"Could not update Windows startup registry: {e}")

        self.accept()

    def get_settings(self) -> Dict[str, str]:
        """Returns the dictionary of configured settings."""
        return {
            "ticket_prefix": self.txt_prefix.text().strip() or "INC-",
            "auto_save_delay_ms": str(self.spin_debounce.value()),
            "jpeg_quality": str(self.spin_quality.value()),
            "close_tab_action": self.combo_close_action.currentData(),
            "window_opacity": str(self.spin_opacity.value()),
            "autostart_enabled": "true" if self.chk_autostart.isChecked() else "false",
            "smart_restore_enabled": "true" if self.chk_smart_restore.isChecked() else "false",
        }
