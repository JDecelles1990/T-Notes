"""Realistic bilingual (EN + FR-CA) synthetic MSP ticket dataset and sandbox database builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
from pathlib import Path
import sqlite3
from typing import Iterable, Sequence

from src.database.connection import DatabaseManager
from src.database.history_fts import (
    assign_ticket_taxonomy,
    list_taxonomy_nodes,
    suggest_taxonomy_for_text,
)
from src.database.migrations import init_database


SMB_CLIENTS: tuple[str, ...] = (
    "Clinique Saint-Laurent",
    "Acier Montérégie",
    "NorthStar Logistics",
    "Cabinet Tremblay & Associés",
    "Apex Manufacturing",
    "Boulangerie Lavoie",
)


@dataclass(frozen=True)
class SyntheticTicketSpec:
    ticket_number: str
    client: str
    title: str
    body_text: str
    tags: str
    language: str  # "EN" or "FR"
    is_archived: bool
    pre_migration: bool
    days_ago: int
    expected_domain: str | None
    expected_symptom: str | None
    expected_resolution: str | None
    has_technical_cues: bool = True

    @property
    def body_html(self) -> str:
        """Build HTML note preserving angle brackets cleanly inside HTML paragraphs."""
        if not self.body_text:
            return ""
        paragraphs = []
        for line in self.body_text.splitlines():
            stripped = line.rstrip()
            if stripped:
                paragraphs.append(f"<p>{html.escape(stripped)}</p>")
            else:
                paragraphs.append("<p><br></p>")
        return "\n".join(paragraphs)


def _long_halo_incident_body() -> str:
    header = (
        "[2026-10-18 08:15] Caller: Plant Supervisor <ops@apexmfg.ca>\n"
        "Reported site-to-site IPsec VPN tunnel and FortiClient SSL VPN disconnect / packet loss at Building B.\n"
        "Ping to gateway 10.42.0.1 shows 28% packet loss and intermittent DNS timeout during ERP sync.\n"
    )
    entries = []
    for i in range(1, 76):
        hr = (8 + (i // 4)) % 24
        mn = (i * 15) % 60
        entries.append(
            f"[Checkpoint {i:02d} | {hr:02d}:{mn:02d}] "
            f"nslookup erp.apexmfg.local -> timeout; tracert hop 3 WAN CPE latency spike {140 + (i % 90)} ms; "
            f"verified FortiGate WAN1 interface link flap, DHCP lease intact on VLAN 20, "
            f"still unreachable across branch FortiClient VPN tunnel.\n"
        )
    footer = (
        "\n[Resolution] Captured PCAP & FortiGate diag debug logs, confirmed Bell Business Fiber ONT optical attenuation -29.4 dBm.\n"
        "Opened ticket #BELL-883412 and escalated to Bell ISP tier 3 vendor dispatch for fiber splice repair.\n"
    )
    body = header + "".join(entries) + footer
    assert len(body) >= 12000
    return body


SYNTHETIC_TICKETS: tuple[SyntheticTicketSpec, ...] = (
    # =========================================================================
    # PRE-MIGRATION ARCHIVED TICKETS (16: 8 EN + 8 FR-CA)
    # =========================================================================
    SyntheticTicketSpec(
        ticket_number="INC-40219",
        client="Acier Montérégie",
        title="Outlook OST corrupt and Autodiscover loop for facturation",
        body_text=(
            "User <j.gagnon@aciermonteregie.ca> reported Outlook stuck in an autodiscover loop with <ErrorCode>503</ErrorCode>.\n"
            "Local cache path inspected: C:\\Users\\m.tremblay\\AppData\\Local\\Microsoft\\Outlook\\profile.ost (48.7 GB).\n"
            "Checked mailbox delegation read-only:\n"
            "Get-MailboxPermission -Identity \"facturation@aciermonteregie.ca\"\n"
            "Resolution: Closed Outlook, renamed OST file to profile.ost.old, and rebuilt OST mail profile cleanly.\n"
            "Verified Exchange Online sync and zero 503 errors after rebuild."
        ),
        tags="m365, outlook, ost, exchange",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=3,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.mail_flow_sync",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="SR-10884",
        client="NorthStar Logistics",
        title="Kyocera warehouse printer not printing - Windows Print Spooler 0x0000011b",
        body_text=(
            "Shipping dock PC cannot print packing slips to Kyocera TASKalfa 4053ci.\n"
            "Attempted test page fails immediately with error 0x0000011b and stuck print queue.\n"
            "Commands run:\n"
            "net stop spooler & del /Q %windir%\\System32\\spool\\PRINTERS\\*.*\n"
            "Resolution: Reinstalled driver (KX v8.4) and restarted spooler service cleanly."
        ),
        tags="printer, spooler, kyocera, 0x0000011b",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=1,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="HALO-9921",
        client="Apex Manufacturing",
        title="FortiClient VPN disconnect and WAN packet loss at Building B",
        body_text=_long_halo_incident_body(),
        tags="vpn, forticlient, bell, escalade",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=22,
        expected_domain="domain.network.vpn_dns_wifi",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.escalated_vendor",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40220",
        client="Clinique Saint-Laurent",
        title="AADSTS50076 MFA prompt loop after phone replacement",
        body_text=(
            "Nurse M. Bouchard replaced her iPhone over the weekend and Entra ID sign-in fails with AADSTS50076.\n"
            "Authenticator prompt loops continuously on Microsoft 365 login.\n"
            "Resolution: Revoked sessions in Entra ID and clicked Require re-register MFA; user paired Microsoft Authenticator."
        ),
        tags="entra, mfa, aadsts50076, authenticator",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=5,
        expected_domain="domain.identity.entra_mfa",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40221",
        client="Cabinet Tremblay & Associés",
        title="Active Directory mapped drive P: missing after GPO change",
        body_text=(
            "Legal assistant reports mapped drive P:\\Dossiers missing after morning sign-in; access denied to UNC share.\n"
            "Checked Event Viewer: Group Policy Drive Maps skipped due to security filtering on OU.\n"
            "Resolution: Updated GPO security filtering policy applied cleanly and ran gpupdate /force twice."
        ),
        tags="ad, gpo, mapped-drive, gpupdate",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=14,
        expected_domain="domain.identity.ad_gpo",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40222",
        client="NorthStar Logistics",
        title="New Teams client freezes on launch and not responding",
        body_text=(
            "Dispatch coordinator reports New Teams hangs at loading screen with high CPU and not responding status.\n"
            "Cleared Teams cache under %LocalAppData%\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache.\n"
            "Resolution: Cleared Teams cache cleanly; Microsoft Teams opens smoothly in <3 seconds."
        ),
        tags="teams, cache, freeze",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=65,
        expected_domain="domain.m365.teams_sharepoint",
        expected_symptom="symptom.performance_crash",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40223",
        client="Apex Manufacturing",
        title="USB-C docking station no display on dual monitors",
        body_text=(
            "Engineering workstation Dell WD19TBS dock dropped external monitors and USB mouse; no display detected.\n"
            "Tested known-good DisplayPort cable and Thunderbolt port; dock power LED blinking fault.\n"
            "Resolution: Replaced dock with spare WD19TBS under Dell warranty RMA."
        ),
        tags="hardware, dock, monitor",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=18,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.hardware_replaced",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40224",
        client="Boulangerie Lavoie",
        title="Defender SmartScreen false positive quarantined POS utility",
        body_text=(
            "Windows Defender alert blocked bakery scale export executable as false positive and user gets access denied.\n"
            "Confirmed SHA-256 hash matches signed vendor release from Mettler Toledo.\n"
            "Resolution: Released from quarantine and excluded in Defender ASR policy."
        ),
        tags="defender, quarantine, false-positive",
        language="EN",
        is_archived=True,
        pre_migration=True,
        days_ago=72,
        expected_domain="domain.security.defender_phishing",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40225",
        client="Clinique Saint-Laurent",
        title="Compte Active Directory verrouillé après changement mot de passe",
        body_text=(
            "La réceptionniste S. Pelletier ne peut plus ouvrir sa session Windows : compte verrouillé toutes les 5 minutes.\n"
            "Vérification sur le contrôleur de domaine : anciens identifiants cachés sur son téléphone.\n"
            "Solution : Déverrouillé le compte dans AD et réinitialisé le mot de passe."
        ),
        tags="ad, verrouille, compte, mdp",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=2,
        expected_domain="domain.identity.ad_gpo",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40226",
        client="Boulangerie Lavoie",
        title="Imprimante Zebra étiquettes hors ligne - spouleur d'impression planté",
        body_text=(
            "L'imprimante d'étiquettes Zebra ZD421 reste en file d'attente bloquée et n'imprime pas depuis Win11.\n"
            "Erreur RPC 0x0000011b observée après mise à jour cumulative.\n"
            "Solution : Nettoyé la file et redémarré le spouleur d'impression puis réinstallé le pilote ZDesigner."
        ),
        tags="imprimante, spouleur, zebra, 0x0000011b",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=4,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40227",
        client="Cabinet Tremblay & Associés",
        title="Déconnexion VPN FortiClient et résolution DNS interne en panne",
        body_text=(
            "Les avocats en télétravail subissent une déconnexion VPN FortiClient et serveur fichiers inaccessible.\n"
            "nslookup sur dc01.tremblay.local retourne délai dépassé via le tunnel.\n"
            "Solution : Corrigé le DNS sur l'interface VPN split tunnel et exécuté ipconfig /flushdns."
        ),
        tags="vpn, forticlient, dns, reseau",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=9,
        expected_domain="domain.network.vpn_dns_wifi",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.dns_network_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40228",
        client="Acier Montérégie",
        title="Bibliothèque SharePoint accès refusé pour équipe projets",
        body_text=(
            "Nouvelle coordonnatrice reçoit accès refusé sur la bibliothèque SharePoint Plans-2026 (lecture seule).\n"
            "Les droits d'accès du dossier partagé n'étaient pas hérités pour son groupe.\n"
            "Solution : Ajouté au groupe de sécurité SG-Projets-RW et droits SharePoint mis à jour."
        ),
        tags="sharepoint, permissions, acces-refuse",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=27,
        expected_domain="domain.m365.teams_sharepoint",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.permissions_updated",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40229",
        client="Clinique Saint-Laurent",
        title="Écran bleu BSOD récurrent sous Windows 11 poste accueil",
        body_text=(
            "Le poste Windows 11 à l'accueil fige puis fait un écran bleu BSOD (CRITICAL_PROCESS_DIED) 2 fois par jour.\n"
            "Observateur d'événements montre des secteurs défectueux sur le disque NVMe.\n"
            "Solution : Remplacé le SSD sous garantie et restauré l'image poste."
        ),
        tags="win11, bsod, ecran-bleu, ssd",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=40,
        expected_domain="domain.endpoint.windows_os",
        expected_symptom="symptom.performance_crash",
        expected_resolution="resolution.hardware_replaced",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40230",
        client="Cabinet Tremblay & Associés",
        title="Nouvel employé préparation poste Autopilot sans licence M365",
        body_text=(
            "Nouvel employé M. Gagné embauche lundi : déploiement Intune Autopilot bloqué (licence manquante sur le compte).\n"
            "Portail d'entreprise affichait erreur d'enrôlement faute de SKU Business Premium.\n"
            "Solution : Attribué la licence M365 Business Premium dans Entra ID et relancé conformité Intune."
        ),
        tags="intune, autopilot, onboarding, licence",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=80,
        expected_domain="domain.endpoint.intune_rmm",
        expected_symptom="symptom.provisioning_onboarding",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40231",
        client="Clinique Saint-Laurent",
        title="Boîte partagée comptabilité ne synchronise pas dans Outlook",
        body_text=(
            "La boîte partagée comptabilite@cliniquesl.ca ne reçoit pas les messages récents dans Outlook.\n"
            "Le fichier OST local était bloqué et la synchronisation Exchange ne progressait plus.\n"
            "Solution : Renommé OST local, vidé le cache Exchange et recréé le profil Outlook."
        ),
        tags="courriel, boite-partagee, outlook, ost",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=6,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.mail_flow_sync",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40232",
        client="Acier Montérégie",
        title="Courriel d'hameçonnage signalé et compte Entra compromis",
        body_text=(
            "Alerte Microsoft Defender : clic sur un lien d'hameçonnage (phishing) par C. Fortin avec connexion risquée.\n"
            "Aucune règle de transfert malveillante ajoutée dans Exchange.\n"
            "Solution : Révoqué les sessions Entra ID, réinitialisé le mot de passe et ré-enregistré MFA."
        ),
        tags="defender, phishing, hameconnage, entra",
        language="FR",
        is_archived=True,
        pre_migration=True,
        days_ago=11,
        expected_domain="domain.security.defender_phishing",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),

    # =========================================================================
    # POST-MIGRATION ARCHIVED TICKETS (16: 8 EN + 8 FR-CA, INCLUDING MINIMAL TICKET)
    # =========================================================================
    SyntheticTicketSpec(
        ticket_number="INC-40233",
        client="NorthStar Logistics",
        title="Shared mailbox dispatch not updating - granted FullAccess permissions",
        body_text=(
            "Dispatcher K. Patel unable to access shared mailbox dispatch@northstar.ca in Outlook.\n"
            "PowerShell check showed missing delegation rights (access denied when expanding folder).\n"
            "Resolution: Ran Add-MailboxPermission -AccessRights FullAccess -AutoMapping:$true; permissions updated."
        ),
        tags="exchange, shared-mailbox, powershell, permissions",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=2,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.permissions_updated",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40234",
        client="Apex Manufacturing",
        title="NinjaRMM agent offline after Windows 11 cumulative update",
        body_text=(
            "Endpoint WKSTN-CAD04 showing offline in NinjaOne RMM dashboard since Tuesday patching.\n"
            "Win11 workstation otherwise reachable via WireGuard VPN; NinjaRMMAgent service stuck in Stopping state.\n"
            "Resolution: Terminated hung PID and restarted Ninja service cleanly in Services."
        ),
        tags="ninjarmm, intune, rmm, service",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=5,
        expected_domain="domain.endpoint.intune_rmm",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40235",
        client="Cabinet Tremblay & Associés",
        title="Windows 11 temporary profile error on partner laptop",
        body_text=(
            "User <m.tremblay@tremblayassocies.ca> signed in and received a temp profile warning; desktop files missing.\n"
            "Inspected Registry ProfileList key and found duplicate .bak SID under C:\\Users\\m.tremblay.\n"
            "Resolution: Removed duplicate ProfileList registry key cleanly and rebooted; original user profile loaded."
        ),
        tags="win11, temp-profile, registry",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=15,
        expected_domain="domain.endpoint.windows_os",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40236",
        client="NorthStar Logistics",
        title="Microsoft 365 Exchange quarantine false positive blocking carrier invoices",
        body_text=(
            "Important PDF invoice notifications from carrier@freightportal.com stopped arriving (blocked mail).\n"
            "Found messages held in Exchange Online mail flow quarantine.\n"
            "Resolution: Released blocked mail and added Exchange transport rule bypass after SPF/DKIM verification."
        ),
        tags="exchange, mail-flow, transport-rule, quarantine",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=19,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.mail_flow_sync",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40237",
        client="Apex Manufacturing",
        title="New hire workstation onboarding and SharePoint access setup",
        body_text=(
            "New hire D. Okafor starting Monday in Production Engineering.\n"
            "Needs Entra ID account provisioning, M365 E3 SKU assignment, and SharePoint Engineering folder access.\n"
            "Resolution: Assigned license M365 E3, completed Intune Autopilot enrollment, and added to security group."
        ),
        tags="onboarding, autopilot, license, m365",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=35,
        expected_domain="domain.endpoint.intune_rmm",
        expected_symptom="symptom.provisioning_onboarding",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40238",
        client="Boulangerie Lavoie",
        title="Office Wi-Fi 802.1X disconnect and stale DHCP lease",
        body_text=(
            "Several laptops in main office lose Wi-Fi 802.1X connection every hour and report no internet.\n"
            "Meraki AP logs show DHCP scope exhaustion and stale ARP entries on office VLAN.\n"
            "Resolution: Expanded DHCP lease pool, updated DNS forwarders, and ran ipconfig /flushdns."
        ),
        tags="wifi, meraki, dhcp, dns",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=48,
        expected_domain="domain.network.vpn_dns_wifi",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.dns_network_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40239",
        client="NorthStar Logistics",
        title="Entra Conditional Access blocking warehouse iPad scanner sign-in",
        body_text=(
            "Shared warehouse tablet prompted AADSTS53003 Conditional Access block when signing into Teams.\n"
            "Device was excluded from compliant Android/iOS kiosk group after enrollment.\n"
            "Resolution: Added kiosk device to Conditional Access excluded compliance policy group."
        ),
        tags="entra, conditional-access, mfa",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=92,
        expected_domain="domain.identity.entra_mfa",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40250",
        client="Boulangerie Lavoie",
        title="Quick callback follow-up",
        body_text="",
        tags="",
        language="EN",
        is_archived=True,
        pre_migration=False,
        days_ago=1,
        expected_domain=None,
        expected_symptom=None,
        expected_resolution=None,
        has_technical_cues=False,
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40240",
        client="Clinique Saint-Laurent",
        title="Synchronisation OneDrive bloquée avec erreur dossier partagé",
        body_text=(
            "Poste de Dre Gagnon : synchronisation OneDrive figée sur 'Traitement des modifications' depuis 3 jours.\n"
            "Impossible d'ouvrir les fichiers SharePoint récents (cache corrompu).\n"
            "Solution : Exécuté OneDrive /reset (%localappdata%\\Microsoft\\OneDrive\\onedrive.exe /reset) et recréé le cache."
        ),
        tags="onedrive, sharepoint, synchronisation",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=3,
        expected_domain="domain.m365.teams_sharepoint",
        expected_symptom="symptom.mail_flow_sync",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40241",
        client="Acier Montérégie",
        title="Écran de récupération BitLocker au démarrage après mise à jour BIOS",
        body_text=(
            "Portable HP EliteBook bloqué sur l'écran bleu de récupération BitLocker suite au déploiement Windows Update.\n"
            "Clé de récupération récupérée dans Entra ID / Intune pour le poste.\n"
            "Solution : Entré la clé BitLocker, suspendu le chiffrement, mis à jour le pilote TPM et redémarré."
        ),
        tags="bitlocker, windows, win11, bios",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=7,
        expected_domain="domain.endpoint.windows_os",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40242",
        client="Cabinet Tremblay & Associés",
        title="Lenteur extrême Explorateur Windows et 100% disque sur poste comptable",
        body_text=(
            "Le poste Windows 11 fige constamment (ne répond pas) lorsque l'utilisateur ouvre l'Explorateur Windows.\n"
            "Indexation Windows Search corrompue + erreurs WMI observées.\n"
            "Solution : Réparé les fichiers système avec DISM /RestoreHealth, SFC /scannow et redémarré le service WSearch."
        ),
        tags="windows, lenteur, dism, sfc",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=12,
        expected_domain="domain.endpoint.windows_os",
        expected_symptom="symptom.performance_crash",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40243",
        client="Boulangerie Lavoie",
        title="Nouvel utilisateur embauche - accès groupe sécurité et boîte partagée",
        body_text=(
            "Arrivée de L. Bédard aux ventes : création de compte complétée mais pas d'accès à ventes@lavoie.ca ni au dossier.\n"
            "Il fallait les droits d'accès au groupe de sécurité Entra ID et FullAccess Exchange.\n"
            "Solution : Ajouté au groupe de sécurité SG-Ventes et accès accordé sur la boîte partagée."
        ),
        tags="onboarding, nouvel-employe, permissions",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=16,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.provisioning_onboarding",
        expected_resolution="resolution.permissions_updated",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40244",
        client="Acier Montérégie",
        title="Alerte Defender EDR et rançongiciel suspect bloqué sur poste usine",
        body_text=(
            "Alerte critique Microsoft Defender XDR sur poste usine-08 : script PowerShell suspect bloqué par ASR.\n"
            "Machine isolée via NinjaRMM le temps d'analyser la quarantaine et les journaux EDR.\n"
            "Solution : Faux positif confirmé (macro ERP signée) -> ajouté exclusion Defender et levé isolation."
        ),
        tags="defender, edr, quarantaine, exclusion",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=24,
        expected_domain="domain.security.defender_phishing",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.policy_license_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40245",
        client="Clinique Saint-Laurent",
        title="Imprimante réseau Kyocera bourrage et défaut rouleau d'entraînement",
        body_text=(
            "L'imprimante Kyocera du secrétariat médical affiche bourrage papier permanent malgré le bac vide.\n"
            "Capteur de prise papier brisé mécaniquement.\n"
            "Solution : Ouvert un billet de service avec le fournisseur support Kyocera pour remplacement du module."
        ),
        tags="imprimante, kyocera, bourrage, fournisseur",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=54,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.escalated_vendor",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40246",
        client="Cabinet Tremblay & Associés",
        title="Mot de passe Active Directory expiré impossible de changer via VPN",
        body_text=(
            "Associé P. Roy travaille de Québec avec mot de passe AD expiré (connexion refusée sur Windows).\n"
            "Mot de passe expiré avant de pouvoir établir le tunnel VPN Kerberos.\n"
            "Solution : Réinitialisé le mot de passe temporaire AD, connecté FortiClient VPN et forcé synchro Entra Connect."
        ),
        tags="ad, mot-de-passe, vpn, kerberos",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=68,
        expected_domain="domain.identity.ad_gpo",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40247",
        client="Apex Manufacturing",
        title="Réunions Microsoft Teams coupées - qualité audio et VLAN Wi-Fi",
        body_text=(
            "Direction rapporte déconnexion fréquente et gel pendant les appels Teams sur le Wi-Fi du 2e étage.\n"
            "Tests de perte de paquets confirment bascule agressive entre points d'accès sur mauvais VLAN.\n"
            "Solution : Ajusté la priorité QoS DSCP et corrigé le routage DNS/VLAN sur les bornes Wi-Fi."
        ),
        tags="teams, wifi, vlan, qos",
        language="FR",
        is_archived=True,
        pre_migration=False,
        days_ago=85,
        expected_domain="domain.network.vpn_dns_wifi",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.dns_network_fix",
    ),

    # =========================================================================
    # ACTIVE WORKSPACE TICKETS (8: 4 EN + 4 FR-CA)
    # =========================================================================
    SyntheticTicketSpec(
        ticket_number="INC-40301",
        client="NorthStar Logistics",
        title="Outlook OST corrupt and mailbox sync stalled - rebuild profile",
        body_text=(
            "Operations manager Outlook not syncing new mail since 09:00.\n"
            "OST size exceeded 49 GB; preparing to rename OST and rebuild Outlook profile."
        ),
        tags="outlook, ost, active",
        language="EN",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.m365.exchange",
        expected_symptom="symptom.mail_flow_sync",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40302",
        client="Clinique Saint-Laurent",
        title="Imprimante réseau bloquée, redémarrage du spooler et mise à jour pilote",
        body_text=(
            "Imprimante accueil ne répond plus, file d'attente bloquée (spouleur d'impression planté).\n"
            "Redémarré le spouleur et réinstallé le pilote universel."
        ),
        tags="imprimante, spouleur, active",
        language="FR",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.service_driver_restart",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40303",
        client="Acier Montérégie",
        title="Entra MFA token reset after lost mobile device",
        body_text=(
            "Employee lost phone; AADSTS50076 login loop during M365 sign-in.\n"
            "Waiting for manager approval before running MFA reset and revoking Entra sessions."
        ),
        tags="entra, mfa, active",
        language="EN",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.identity.entra_mfa",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40304",
        client="Apex Manufacturing",
        title="WireGuard VPN split tunnel DNS timeout to internal ERP",
        body_text=(
            "Remote finance user connects WireGuard VPN but ERP hostname unreachable (DNS timeout).\n"
            "Checking split tunnel DNS suffix and running ipconfig /flushdns."
        ),
        tags="vpn, wireguard, dns, active",
        language="EN",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.network.vpn_dns_wifi",
        expected_symptom="symptom.connectivity",
        expected_resolution="resolution.dns_network_fix",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40305",
        client="Cabinet Tremblay & Associés",
        title="Accès refusé dossier partagé SharePoint après changement de poste",
        body_text=(
            "Collaborateur reçoit accès refusé sur bibliothèque SharePoint Fiscalité.\n"
            "Vérification des droits d'accès et ajout au groupe de sécurité requis."
        ),
        tags="sharepoint, permissions, active",
        language="FR",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.m365.teams_sharepoint",
        expected_symptom="symptom.permissions_access",
        expected_resolution="resolution.permissions_updated",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40306",
        client="Boulangerie Lavoie",
        title="Compte verrouillé Active Directory et réinitialisation mot de passe",
        body_text=(
            "Compte verrouillé à répétition sur le contrôleur de domaine pour p.lavoie.\n"
            "Vérification des journaux de connexion et déverrouillage AD en cours."
        ),
        tags="ad, verrouille, active",
        language="FR",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.identity.ad_gpo",
        expected_symptom="symptom.auth_signin",
        expected_resolution="resolution.token_mfa_reset",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40307",
        client="Clinique Saint-Laurent",
        title="Teams gelé et cache Teams corrompu sur portable Win11",
        body_text=(
            "Médecin signale que Microsoft Teams fige et ne répond pas lors du partage d'écran.\n"
            "Procédure : vider le cache Teams et redémarrer l'application."
        ),
        tags="teams, cache, lenteur, active",
        language="FR",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.m365.teams_sharepoint",
        expected_symptom="symptom.performance_crash",
        expected_resolution="resolution.profile_cache_rebuild",
    ),
    SyntheticTicketSpec(
        ticket_number="INC-40308",
        client="NorthStar Logistics",
        title="Station battery swelling and USB-C dock not detected",
        body_text=(
            "User laptop reports USB-C dock not detected and swollen battery hazard.\n"
            "Scheduling hardware replacement dock and OEM warranty battery swap."
        ),
        tags="hardware, battery, dock, active",
        language="EN",
        is_archived=False,
        pre_migration=False,
        days_ago=0,
        expected_domain="domain.hardware.printers_peripherals",
        expected_symptom="symptom.hardware_print",
        expected_resolution="resolution.hardware_replaced",
    ),
)


def _create_base_pre_migration_schema(conn: sqlite3.Connection) -> None:
    """Create a realistic pre-Step-1 base `scratchpads` schema (PRAGMA user_version = 1)."""
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS scratchpads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            client_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            content_html TEXT DEFAULT '',
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted')),
            tab_order INTEGER DEFAULT 0,
            elapsed_seconds INTEGER DEFAULT 0,
            archived_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        PRAGMA user_version = 1;
        """
    )


def _best_auto_slugs(
    conn: sqlite3.Connection,
    title: str,
    body_text: str,
    *,
    min_score: float = 1.5,
) -> list[str]:
    suggestions = suggest_taxonomy_for_text(title=title, body=body_text, conn=conn, max_per_axis=2)
    picked: list[str] = []
    for axis in ("domain", "symptom", "resolution"):
        for item in suggestions.get(axis, ()):
            if axis == "domain" and item.get("parent_slug") is None:
                continue
            if float(item.get("score", 0.0)) >= min_score:
                picked.append(str(item["slug"]))
                break
    return picked


def populate_synthetic_database(
    db_path: Path | str,
    *,
    now: datetime | None = None,
    auto_tag_post_migration: bool = True,
    specs: Sequence[SyntheticTicketSpec] = SYNTHETIC_TICKETS,
) -> tuple[DatabaseManager, dict[str, int]]:
    """Populate a fresh SQLite DB with realistic pre-migration, post-migration, and active tickets.

    Returns ``(DatabaseManager, {ticket_number: row_id})``.
    """
    ref_now = now or datetime.now(timezone.utc)
    if db_path != ":memory:":
        p = Path(db_path)
        for suffix in ("", "-wal", "-shm"):
            target = Path(f"{p}{suffix}")
            if target.exists():
                target.unlink()

    db_mgr = DatabaseManager(db_path)
    conn = db_mgr.get_connection()
    id_map: dict[str, int] = {}

    # Phase 1: Seed pre-migration archived rows on a v1 scratchpads table BEFORE FTS5 upgrade
    _create_base_pre_migration_schema(conn)
    with conn:
        for spec in specs:
            if not (spec.is_archived and spec.pre_migration):
                continue
            ts = (ref_now - timedelta(days=spec.days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                """
                INSERT INTO scratchpads (
                    ticket_number, client_name, title, tags, content_html,
                    status, tab_order, elapsed_seconds, archived_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'archived', 0, ?, ?, ?, ?)
                """,
                (
                    spec.ticket_number,
                    spec.client,
                    spec.title,
                    spec.tags,
                    spec.body_html,
                    420,
                    ts,
                    ts,
                    ts,
                ),
            )
            id_map[spec.ticket_number] = int(cur.lastrowid)

    # Phase 2: Run full init_database() upgrade (creates FTS5, backfills pre-migration rows,
    # seeds 3-axis taxonomy, creates ticket_embeddings, sets PRAGMA user_version = 4).
    init_database(db_mgr)
    conn = db_mgr.get_connection()

    # Phase 3: Insert post-migration archived tickets + active tickets via live triggers
    active_order = 0
    with conn:
        for spec in specs:
            if spec.is_archived and spec.pre_migration:
                continue
            ts = (ref_now - timedelta(days=spec.days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            if spec.is_archived:
                cur = conn.execute(
                    """
                    INSERT INTO scratchpads (
                        ticket_number, client_name, title, tags, content_html,
                        status, tab_order, elapsed_seconds, archived_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'archived', 0, ?, ?, ?, ?)
                    """,
                    (
                        spec.ticket_number,
                        spec.client,
                        spec.title,
                        spec.tags,
                        spec.body_html,
                        360,
                        ts,
                        ts,
                        ts,
                    ),
                )
                tid = int(cur.lastrowid)
                id_map[spec.ticket_number] = tid
            else:
                cur = conn.execute(
                    """
                    INSERT INTO scratchpads (
                        ticket_number, client_name, title, tags, content_html,
                        status, tab_order, elapsed_seconds, archived_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL, ?, ?)
                    """,
                    (
                        spec.ticket_number,
                        spec.client,
                        spec.title,
                        spec.tags,
                        spec.body_html,
                        active_order,
                        180,
                        ts,
                        ts,
                    ),
                )
                tid = int(cur.lastrowid)
                id_map[spec.ticket_number] = tid
                active_order += 1

    # Optionally auto-tag newly archived post-migration tickets (leaving pre-migration untagged
    # or selectively tagged, and keeping minimal empty ticket INC-40250 untagged).
    if auto_tag_post_migration:
        for spec in specs:
            if spec.is_archived and not spec.pre_migration and spec.has_technical_cues:
                tid = id_map[spec.ticket_number]
                slugs = _best_auto_slugs(conn, spec.title, spec.body_text)
                if slugs:
                    assign_ticket_taxonomy(conn, tid, slugs, source="auto", confidence=0.85, replace_existing=True)

    # Also store active tab session cleanly so launching T-Notes restores the 8 active tabs in order
    active_ids = [id_map[s.ticket_number] for s in specs if not s.is_archived]
    if active_ids:
        with conn:
            conn.execute(
                """
                UPDATE app_session
                SET active_scratchpad_id = ?,
                    primary_scratchpad_ids = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (active_ids[0], ",".join(str(x) for x in active_ids)),
            )

    return db_mgr, id_map


def populate_500_ticket_benchmark_db(
    db_path: Path,
    *,
    target_archived_count: int = 500,
    now: datetime | None = None,
) -> DatabaseManager:
    """Populate a temporary SQLite DB with 500 synthetic archived tickets + taxonomy tags."""
    ref_now = now or datetime.now(timezone.utc)
    if db_path.exists():
        db_path.unlink()
    db_mgr = DatabaseManager(db_path)
    init_database(db_mgr)
    conn = db_mgr.get_connection()

    valid_slugs = {str(n["slug"]) for n in list_taxonomy_nodes(conn, active_only=True)}
    archived_templates = [s for s in SYNTHETIC_TICKETS if s.is_archived and s.has_technical_cues]

    inserted_rows: list[tuple[int, list[str]]] = []
    with conn:
        for idx in range(target_archived_count):
            tmpl = archived_templates[idx % len(archived_templates)]
            t_num = f"INC-{50000 + idx}"
            ts = (ref_now - timedelta(days=(idx % 85))).strftime("%Y-%m-%d %H:%M:%S")
            title = f"{tmpl.title} [Batch #{idx + 1}]"
            body = (
                f"{tmpl.body_html}\n"
                f"<p>Synthetic scale diagnostic token node-{idx:03d} on client host workstation-{idx % 25:02d}.</p>"
            )
            cur = conn.execute(
                """
                INSERT INTO scratchpads (
                    ticket_number, client_name, title, tags, content_html,
                    status, tab_order, elapsed_seconds, archived_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'archived', 0, 300, ?, ?, ?)
                """,
                (t_num, tmpl.client, title, tmpl.tags, body, ts, ts, ts),
            )
            tid = int(cur.lastrowid)
            slugs = [
                s
                for s in (tmpl.expected_domain, tmpl.expected_symptom, tmpl.expected_resolution)
                if s and s in valid_slugs
            ]
            if slugs:
                inserted_rows.append((tid, slugs))

        node_rows = conn.execute("SELECT id, slug FROM taxonomy_nodes").fetchall()
        slug_to_id = {str(r[1]): int(r[0]) for r in node_rows}
        tax_tuples = [
            (tid, slug_to_id[slug], "auto", 0.9)
            for tid, slugs in inserted_rows
            for slug in slugs
            if slug in slug_to_id
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO ticket_taxonomy (ticket_id, node_id, source, confidence) VALUES (?, ?, ?, ?)",
            tax_tuples,
        )

    return db_mgr
