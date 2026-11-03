"""Settings configuration dialog for user preferences."""

from typing import Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import APP_NAME


class SettingsDialog(QDialog):
    """Modal dialog for customizing application preferences."""

    def __init__(self, current_settings: Dict[str, str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Preferences")
        self.setMinimumWidth(440)
        self.setModal(True)

        self._settings = current_settings
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

        layout.addLayout(form)

        # Storage and contract approval are deliberately not inferred from a draft.
        self.btn_merge = QPushButton("Merge", self)
        self.btn_merge.setAccessibleName("Merge company directory")
        self.btn_merge.setEnabled(False)
        self.btn_merge.setToolTip("Company Directory Merge is unavailable pending contract and storage approval.")
        layout.addWidget(self.btn_merge)
        self.merge_status = QLabel(
            "Company Directory Merge is unavailable. Profiles are session-only; "
            "contract, storage and backup approval are required.", self
        )
        self.merge_status.setWordWrap(True)
        layout.addWidget(self.merge_status)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Preferences")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def get_settings(self) -> Dict[str, str]:
        """Returns the dictionary of configured settings."""
        return {
            "ticket_prefix": self.txt_prefix.text().strip() or "INC-",
            "auto_save_delay_ms": str(self.spin_debounce.value()),
            "jpeg_quality": str(self.spin_quality.value()),
            "close_tab_action": self.combo_close_action.currentData(),
            "window_opacity": str(self.spin_opacity.value()),
        }

