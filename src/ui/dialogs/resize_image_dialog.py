"""Modal dialog for resizing embedded images with aspect ratio locking and quick presets."""

from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ResizeImageDialog(QDialog):
    """Dialog allowing technicians to resize an image proportionally, unconstrained, or via presets."""

    def __init__(
        self,
        current_width: int,
        current_height: int,
        original_width: int,
        original_height: int,
        max_pane_width: int = 800,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Resize Image")
        self.setMinimumWidth(380)
        self.setModal(True)

        self._orig_w = max(1, original_width)
        self._orig_h = max(1, original_height)
        self._curr_w = max(1, current_width)
        self._curr_h = max(1, current_height)
        self._max_pane_w = max(50, max_pane_width)
        self._aspect_ratio = self._orig_w / self._orig_h

        self._updating = False

        self._setup_ui()
        self._apply_styling()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header info
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        lbl_title = QLabel("📐 Resize Image Dimensions")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 11pt; color: #9cdcfe;")
        header_layout.addWidget(lbl_title)

        info_text = f"Original Size: <b>{self._orig_w} × {self._orig_h} px</b> | Current: <b>{self._curr_w} × {self._curr_h} px</b>"
        self.lbl_info = QLabel(info_text)
        self.lbl_info.setStyleSheet("color: #888888; font-size: 9pt;")
        header_layout.addWidget(self.lbl_info)
        layout.addWidget(header_frame)

        # Form fields for Width and Height
        form = QFormLayout()
        form.setSpacing(10)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(20, 5000)
        self.spin_width.setSingleStep(10)
        self.spin_width.setSuffix(" px")
        self.spin_width.setValue(self._curr_w)
        self.spin_width.valueChanged.connect(self._on_width_changed)
        form.addRow("Width:", self.spin_width)

        self.spin_height = QSpinBox()
        self.spin_height.setRange(20, 5000)
        self.spin_height.setSingleStep(10)
        self.spin_height.setSuffix(" px")
        self.spin_height.setValue(self._curr_h)
        self.spin_height.valueChanged.connect(self._on_height_changed)
        form.addRow("Height:", self.spin_height)

        layout.addLayout(form)

        # Lock Aspect Ratio
        self.chk_lock_aspect = QCheckBox("🔗 Lock aspect ratio")
        self.chk_lock_aspect.setChecked(True)
        self.chk_lock_aspect.setStyleSheet("color: #cccccc; font-size: 9pt;")
        layout.addWidget(self.chk_lock_aspect)

        # Quick Presets
        preset_box = QFrame()
        preset_layout = QVBoxLayout(preset_box)
        preset_layout.setContentsMargins(0, 4, 0, 4)
        preset_layout.setSpacing(6)

        lbl_presets = QLabel("Quick Presets:")
        lbl_presets.setStyleSheet("color: #9cdcfe; font-weight: bold; font-size: 9pt;")
        preset_layout.addWidget(lbl_presets)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)

        for label, pct in [("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked=False, p=pct: self._apply_preset_percentage(p))
            presets_row.addWidget(btn)

        self.btn_fit_pane = QPushButton("Fit to Pane Width")
        self.btn_fit_pane.setFixedHeight(26)
        self.btn_fit_pane.setToolTip(f"Scales image to fit editor pane (max {self._max_pane_w} px)")
        self.btn_fit_pane.clicked.connect(self._apply_preset_fit_pane)
        presets_row.addWidget(self.btn_fit_pane)

        preset_layout.addLayout(presets_row)
        layout.addWidget(preset_box)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #cccccc;
            }
            QLabel {
                color: #cccccc;
            }
            QSpinBox {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QSpinBox:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #333333;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #007acc;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0e639c;
            }
        """)

    def _on_width_changed(self, new_w: int) -> None:
        if self._updating or not self.chk_lock_aspect.isChecked():
            return
        self._updating = True
        try:
            new_h = max(20, int(round(new_w / self._aspect_ratio)))
            self.spin_height.setValue(new_h)
        finally:
            self._updating = False

    def _on_height_changed(self, new_h: int) -> None:
        if self._updating or not self.chk_lock_aspect.isChecked():
            return
        self._updating = True
        try:
            new_w = max(20, int(round(new_h * self._aspect_ratio)))
            self.spin_width.setValue(new_w)
        finally:
            self._updating = False

    def _apply_preset_percentage(self, pct: float) -> None:
        self._updating = True
        try:
            new_w = max(20, int(round(self._orig_w * pct)))
            new_h = max(20, int(round(self._orig_h * pct)))
            self.spin_width.setValue(new_w)
            self.spin_height.setValue(new_h)
        finally:
            self._updating = False

    def _apply_preset_fit_pane(self) -> None:
        self._updating = True
        try:
            target_w = max(50, min(self._orig_w, self._max_pane_w))
            target_h = max(20, int(round(target_w / self._aspect_ratio)))
            self.spin_width.setValue(target_w)
            self.spin_height.setValue(target_h)
        finally:
            self._updating = False

    def get_dimensions(self) -> Tuple[int, int]:
        """Returns the configured (width, height) in pixels."""
        return self.spin_width.value(), self.spin_height.value()

