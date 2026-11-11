"""Bilingual Summary Formatter Dialog for Ticket Resolution & PSA Export."""

from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import APP_NAME
from src.services.summary_formatter_service import (
    SummaryFormatterService,
    ParsedTicketSections,
)
from src.ui.components.glow_effect import apply_glow_to_buttons


class SummaryFormatterDialog(QDialog):
    """Interactive dialog for reviewing, editing, and copying formatted summaries in English or French."""

    PRESET_EMAIL = 0
    PRESET_PSA = 1
    PRESET_ESCALATION = 2

    def __init__(
        self,
        ticket: Dict[str, Any],
        session_service: Optional[Any] = None,
        default_lang: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.ticket = ticket
        self.session_service = session_service

        # Read saved settings
        saved_settings = self.session_service.get_settings() if self.session_service else {}
        self.current_lang = default_lang or saved_settings.get("summary_default_language", "en")
        self.technician_name = saved_settings.get("technician_name", "")
        self.technician_email = saved_settings.get("technician_email", "")

        # Parse sections from ticket
        self.sections: ParsedTicketSections = SummaryFormatterService.parse_ticket(
            self.ticket,
            technician_name=self.technician_name,
            technician_email=self.technician_email,
        )

        self.setWindowTitle(f"Ticket Summary Formatter — {APP_NAME}")
        self.resize(980, 680)
        self.setMinimumSize(820, 520)

        self._setup_ui()
        self._populate_fields()
        self._update_language_ui()
        self._refresh_preview()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # Header bar: Ticket info + Language toggle + Preset combo
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        # Ticket title badge
        t_num = f"#{self.sections.ticket_number}" if self.sections.ticket_number else ""
        c_name = f" — {self.sections.client_name}" if self.sections.client_name else ""
        self.lbl_ticket_info = QLabel(f"<b>Ticket:</b> {t_num}{c_name}")
        self.lbl_ticket_info.setStyleSheet("color: #4fc1ff; font-size: 13px;")
        header_layout.addWidget(self.lbl_ticket_info, 1)

        # Preset Selector
        self.lbl_preset = QLabel("Preset:")
        self.lbl_preset.setStyleSheet("font-weight: bold; color: #dcdcaa;")
        header_layout.addWidget(self.lbl_preset)

        self.combo_preset = QComboBox()
        self.combo_preset.setMinimumWidth(210)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        header_layout.addWidget(self.combo_preset)

        # Language Toggle (Radio Group)
        lang_layout = QHBoxLayout()
        lang_layout.setSpacing(6)
        self.lbl_lang = QLabel("Language:")
        self.lbl_lang.setStyleSheet("font-weight: bold; color: #9cdcfe;")
        lang_layout.addWidget(self.lbl_lang)

        self.btn_lang_en = QRadioButton("🇬🇧 English")
        self.btn_lang_fr = QRadioButton("🇫🇷 Français")
        self.btn_lang_group = QButtonGroup(self)
        self.btn_lang_group.addButton(self.btn_lang_en, 0)
        self.btn_lang_group.addButton(self.btn_lang_fr, 1)

        if self.current_lang == "fr":
            self.btn_lang_fr.setChecked(True)
        else:
            self.btn_lang_en.setChecked(True)

        self.btn_lang_en.toggled.connect(self._on_language_toggled)
        lang_layout.addWidget(self.btn_lang_en)
        lang_layout.addWidget(self.btn_lang_fr)
        header_layout.addLayout(lang_layout)

        main_layout.addLayout(header_layout)

        # Splitter: Left (Inputs) | Right (Preview)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #333333; width: 4px; }")

        # Left Widget: Structured Input Fields
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        # Issue
        self.lbl_issue = QLabel("Issue / Reported Problem:")
        self.lbl_issue.setStyleSheet("font-weight: bold; color: #4ec9b0;")
        left_layout.addWidget(self.lbl_issue)
        self.txt_issue = QPlainTextEdit()
        self.txt_issue.setMaximumHeight(85)
        self.txt_issue.textChanged.connect(self._on_field_edited)
        left_layout.addWidget(self.txt_issue)

        # Work Performed
        self.lbl_work = QLabel("Troubleshooting / Actions Taken:")
        self.lbl_work.setStyleSheet("font-weight: bold; color: #4ec9b0;")
        left_layout.addWidget(self.lbl_work)
        self.txt_work = QPlainTextEdit()
        self.txt_work.setMaximumHeight(110)
        self.txt_work.textChanged.connect(self._on_field_edited)
        left_layout.addWidget(self.txt_work)

        # Resolution
        self.lbl_resolution = QLabel("Resolution / Solution:")
        self.lbl_resolution.setStyleSheet("font-weight: bold; color: #4ec9b0;")
        left_layout.addWidget(self.lbl_resolution)
        self.txt_resolution = QPlainTextEdit()
        self.txt_resolution.setMaximumHeight(85)
        self.txt_resolution.textChanged.connect(self._on_field_edited)
        left_layout.addWidget(self.txt_resolution)

        # Root Cause
        self.lbl_root_cause = QLabel("Root Cause (optional):")
        self.lbl_root_cause.setStyleSheet("color: #858585;")
        left_layout.addWidget(self.lbl_root_cause)
        self.txt_root_cause = QPlainTextEdit()
        self.txt_root_cause.setMaximumHeight(65)
        self.txt_root_cause.textChanged.connect(self._on_field_edited)
        left_layout.addWidget(self.txt_root_cause)

        # Next Steps
        self.lbl_next_steps = QLabel("Next Steps / User Instructions (optional):")
        self.lbl_next_steps.setStyleSheet("color: #858585;")
        left_layout.addWidget(self.lbl_next_steps)
        self.txt_next_steps = QPlainTextEdit()
        self.txt_next_steps.setMaximumHeight(65)
        self.txt_next_steps.textChanged.connect(self._on_field_edited)
        left_layout.addWidget(self.txt_next_steps)

        # Technician Name & Email Row
        tech_row = QHBoxLayout()
        tech_row.setSpacing(8)

        self.lbl_tech = QLabel("Name:")
        self.lbl_tech.setStyleSheet("color: #9cdcfe; font-weight: bold;")
        tech_row.addWidget(self.lbl_tech)
        self.txt_tech = QLineEdit(self.technician_name)
        self.txt_tech.setPlaceholderText("e.g. Jonathan Decelles")
        self.txt_tech.textChanged.connect(self._on_tech_name_changed)
        tech_row.addWidget(self.txt_tech, 1)

        self.lbl_email = QLabel("Email:")
        self.lbl_email.setStyleSheet("color: #9cdcfe; font-weight: bold;")
        tech_row.addWidget(self.lbl_email)
        self.txt_email = QLineEdit(self.technician_email)
        self.txt_email.setPlaceholderText("e.g. Jonathan_Decelles1990@hotmail.com")
        self.txt_email.textChanged.connect(self._on_tech_email_changed)
        tech_row.addWidget(self.txt_email, 1)
        left_layout.addLayout(tech_row)

        # Time Checkbox row
        time_row = QHBoxLayout()
        self.chk_include_time = QCheckBox("Include Logged Time")
        self.chk_include_time.setChecked(True)
        self.chk_include_time.toggled.connect(self._refresh_preview)
        time_row.addWidget(self.chk_include_time)
        left_layout.addLayout(time_row)

        splitter.addWidget(left_widget)

        # Right Widget: Live Output Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        preview_header = QHBoxLayout()
        self.lbl_preview_title = QLabel("Live Output Preview:")
        self.lbl_preview_title.setStyleSheet("font-weight: bold; color: #9cdcfe; font-size: 12px;")
        preview_header.addWidget(self.lbl_preview_title)

        preview_header.addStretch()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #4ec9b0; font-weight: bold;")
        preview_header.addWidget(self.lbl_status)
        right_layout.addLayout(preview_header)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(QFont("Consolas", 10))
        self.preview_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        right_layout.addWidget(self.preview_edit, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([440, 520])
        main_layout.addWidget(splitter, 1)

        # Bottom Action Bar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_copy_plain = QPushButton("📋 Copy Plain Text")
        self.btn_copy_plain.setObjectName("btnPrimary")
        self.btn_copy_plain.setToolTip("Copies summary as plain text (best for ticketing systems and chat)")
        self.btn_copy_plain.clicked.connect(self._copy_plain_text)
        btn_bar.addWidget(self.btn_copy_plain)

        self.btn_copy_rich = QPushButton("📋 Copy Rich Text")
        self.btn_copy_rich.setObjectName("btnPrimary")
        self.btn_copy_rich.setToolTip("Copies summary with rich text formatting (best for Outlook emails)")
        self.btn_copy_rich.clicked.connect(self._copy_rich_text)
        btn_bar.addWidget(self.btn_copy_rich)

        btn_bar.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btnCancel")
        self.btn_close.clicked.connect(self.reject)
        btn_bar.addWidget(self.btn_close)

        main_layout.addLayout(btn_bar)

        # Keyboard shortcuts: Esc to close
        QShortcut(QKeySequence("Escape"), self, self.reject)

        apply_glow_to_buttons([self])

    def _populate_fields(self) -> None:
        """Fills input text areas from parsed sections."""
        self._is_populating = True
        self.txt_issue.setPlainText(self.sections.issue)
        self.txt_work.setPlainText(self.sections.work_performed)
        self.txt_resolution.setPlainText(self.sections.resolution)
        self.txt_root_cause.setPlainText(self.sections.root_cause)
        self.txt_next_steps.setPlainText(self.sections.next_steps)
        self._is_populating = False

    def _update_language_ui(self) -> None:
        """Updates UI labels and combo items to match current_lang."""
        is_fr = self.current_lang == "fr"

        self.lbl_preset.setText("Préréglage :" if is_fr else "Preset:")
        self.lbl_lang.setText("Langue :" if is_fr else "Language:")
        self.lbl_issue.setText("Problème / Symptômes :" if is_fr else "Issue / Reported Problem:")
        self.lbl_work.setText("Dépannage / Actions effectuées :" if is_fr else "Troubleshooting / Actions Taken:")
        self.lbl_resolution.setText("Résolution / Solution :" if is_fr else "Resolution / Solution:")
        self.lbl_root_cause.setText("Cause racine (optionnel) :" if is_fr else "Root Cause (optional):")
        self.lbl_next_steps.setText("Prochaines étapes (optionnel) :" if is_fr else "Next Steps / User Instructions (optional):")
        self.lbl_tech.setText("Nom :" if is_fr else "Name:")
        self.lbl_email.setText("Courriel :" if is_fr else "Email:")
        self.chk_include_time.setText("Inclure le temps consigné" if is_fr else "Include Logged Time")
        self.lbl_preview_title.setText("Aperçu du texte généré :" if is_fr else "Live Output Preview:")

        self.btn_copy_plain.setText("📋 Copier texte brut" if is_fr else "📋 Copy Plain Text")
        self.btn_copy_rich.setText("📋 Copier texte enrichi" if is_fr else "📋 Copy Rich Text")
        self.btn_close.setText("Fermer" if is_fr else "Close")

        # Update presets combo items
        curr_idx = self.combo_preset.currentIndex()
        if curr_idx < 0:
            curr_idx = self.PRESET_EMAIL

        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        if is_fr:
            self.combo_preset.addItem("✉️ Courriel de résolution client", self.PRESET_EMAIL)
            self.combo_preset.addItem("🏢 Note interne PSA", self.PRESET_PSA)
            self.combo_preset.addItem("🚀 Transfert d'escalade", self.PRESET_ESCALATION)
        else:
            self.combo_preset.addItem("✉️ Client Resolution Email", self.PRESET_EMAIL)
            self.combo_preset.addItem("🏢 Internal PSA Note", self.PRESET_PSA)
            self.combo_preset.addItem("🚀 Escalation Handover", self.PRESET_ESCALATION)
        self.combo_preset.setCurrentIndex(curr_idx)
        self.combo_preset.blockSignals(False)

    def _on_language_toggled(self) -> None:
        self.current_lang = "fr" if self.btn_lang_fr.isChecked() else "en"
        self._update_language_ui()
        self._refresh_preview()
        if self.session_service:
            self.session_service.save_settings({"summary_default_language": self.current_lang})

    def _on_preset_changed(self) -> None:
        self._refresh_preview()

    def _on_tech_name_changed(self, text: str) -> None:
        self.technician_name = text.strip()
        self.sections.technician_name = self.technician_name
        self._refresh_preview()
        if self.session_service:
            self.session_service.save_settings({"technician_name": self.technician_name})

    def _on_tech_email_changed(self, text: str) -> None:
        self.technician_email = text.strip()
        self.sections.technician_email = self.technician_email
        self._refresh_preview()
        if self.session_service:
            self.session_service.save_settings({"technician_email": self.technician_email})

    def _on_field_edited(self) -> None:
        """Syncs modified fields into sections dataclass and refreshes preview."""
        if getattr(self, "_is_populating", False):
            return
        self.sections.issue = self.txt_issue.toPlainText().strip()
        self.sections.work_performed = self.txt_work.toPlainText().strip()
        self.sections.resolution = self.txt_resolution.toPlainText().strip()
        self.sections.root_cause = self.txt_root_cause.toPlainText().strip()
        self.sections.next_steps = self.txt_next_steps.toPlainText().strip()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Renders live summary preview according to active preset and language."""
        preset = self.combo_preset.currentData()
        include_time = self.chk_include_time.isChecked()

        if preset == self.PRESET_PSA:
            plain, rich_html = SummaryFormatterService.format_psa_note(
                self.sections,
                lang=self.current_lang,
                include_time=include_time,
            )
        elif preset == self.PRESET_ESCALATION:
            plain, rich_html = SummaryFormatterService.format_escalation_handover(
                self.sections,
                lang=self.current_lang,
                include_time=include_time,
            )
        else:  # PRESET_EMAIL
            plain, rich_html = SummaryFormatterService.format_client_email(
                self.sections,
                lang=self.current_lang,
                include_time=include_time,
            )

        self._current_plain = plain
        self._current_rich = rich_html
        self.preview_edit.setPlainText(plain)

    def _copy_plain_text(self) -> None:
        """Copies generated plain text summary to clipboard."""
        QApplication.clipboard().setText(self._current_plain)
        msg = "✓ Texte copié !" if self.current_lang == "fr" else "✓ Copied Plain Text!"
        self.lbl_status.setText(msg)

    def _copy_rich_text(self) -> None:
        """Copies generated rich HTML summary to clipboard."""
        mime = QMimeData()
        mime.setHtml(self._current_rich)
        mime.setText(self._current_plain)
        QApplication.clipboard().setMimeData(mime)
        msg = "✓ Texte enrichi copié !" if self.current_lang == "fr" else "✓ Copied Rich Text!"
        self.lbl_status.setText(msg)
