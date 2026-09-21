Omarchy custom ISO — uitsluitend eigen ML-DSA-65/87 USB-signer
Onderzoeksdatum: 21 september 2026. Status: brononderzoek; geen aangepaste ISO gebouwd of hardwaretest uitgevoerd.

De aangetroffen broncode gebruikt SDDM voor aanmelden en een eigen Quickshell-vergrendelscherm. De noodzakelijke wijzigingen zitten in de authenticatie, installatie, eerste boot, herstel en pakketlevering. De bestaande cryptografische libraries van de gebruiker worden via een passende PAM-/USB-koppeling aangesloten; dit onderzoek schrijft geen vervanging van die libraries voor.

**Vastgelegde bronversies**

| Repository | Onderzochte branch | Exacte commit |
|---|---|---|
| [omacom/omarchy](https://github.com/omacom/omarchy/tree/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5) | quattro | ab18321bb53563a8a3f8a44f64ebb9c6463fedc5 |
| [omacom/omarchy-iso](https://github.com/omacom/omarchy-iso/tree/7cfb7111a06873d61c45d37034577d4ba08d3f4f) | quattro | 7cfb7111a06873d61c45d37034577d4ba08d3f4f |
| [omacom/omarchy-pkgs](https://github.com/omacom/omarchy-pkgs/tree/1b3cc7703d8cab2a52c36927502da9f8a48e3af6) | master | 1b3cc7703d8cab2a52c36927502da9f8a48e3af6 |

De officiële release-PKGBUILDs in deze snapshot wijzen naar v4.0.4, runtimecommit `c668141e9c42b13c80c9ca4ea108e11708c5e8a5`. Dat is een andere commit dan de nieuwste onderzochte quattro-bron. De bestaande `--local-source`-route bouwt uit het meegegeven lokale checkout. Bron: [pkgbuilds/omarchy/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy/PKGBUILD#L12). De paden hieronder horen bij de vastgelegde commits; ze zijn geen lijst voor oude Omarchy-3/Hyprlock-installaties.

**Aanmelden en schermontgrendeling: verplichte runtimewijzigingen**

Alle paden in deze tabel liggen in `omacom/omarchy`.

| Bestaand bronbestand | Aangetroffen werking en concrete wijziging |
|---|---|
| [bin/omarchy-apply-lock](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-apply-lock#L29) | Genereert nu twee PAM-services: `/etc/pam.d/omarchy-lock-password` met onder meer `pam_unix`/`pam_systemd_home`, en `/etc/pam.d/omarchy-lock-fingerprint`. Vervang dit door uitsluitend signer-authenticatie en ruim de oude services bij migratie op. De nieuwe naam `omarchy-lock-signer` is een voorstel, geen bestaand upstreambestand. |
| [shell/plugins/lock/Service.qml](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/plugins/lock/Service.qml#L225) | Vervang `submitPassword`, wachtwoordpromptafhandeling en fingerprintstart/afronding door één signertransactie. De twee `PamContext`-objecten op regels 373–415 mogen niet naast de signer blijven bestaan. Alleen geverifieerd succes mag `finishUnlock()` bereiken. Pas ook de gevolgde PAM-bestandsnaam en IPC-statusvelden op regels 583–640 aan. |
| [shell/plugins/lock/LockView.qml](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/plugins/lock/LockView.qml#L12) | Verwijder wachtwoordproperties, signalen, focus, maskering en het `TextInput` op regels 148–234; vervang ze door signerstatus en starten/herproberen/annuleren. Verwijder de fingerprintindicator. |
| [default/sddm/omarchy/Main.qml](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/sddm/omarchy/Main.qml#L74) | Vervang het wachtwoordveld en de aanroep met `password.text` door een signeractie. Een PAM-module die zelf de USB-transactie uitvoert kan worden gestart via de normale `sddm.login(currentUser, "", sessionIndex)`-route. De lege invoer is geen toestemming: uitsluitend de signer-PAM-module beslist. |
| [install/login/sddm.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/login/sddm.sh#L1) | Dit script verwijdert momenteel slechts gnome-keyring-auth/passwordregels. Laat het de signer-only authenticatiestack voor `/etc/pam.d/sddm` installeren, rechtstreeks of via één gedeelde auth-installatiehelper. Account- en sessieconfiguratie doelgericht behouden. |
| [shell/plugins/lock/manifest.json](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/plugins/lock/manifest.json#L7) | Pas de beschrijving aan. Behoud `authentication` en `keepLoaded`; die horen bij de afscherming en levensduur van deze service. |

Een extra noodzakelijke correctie staat in `Service.qml` op regels 149–153 en 612–614: momenteel kan een ontbrekend PAM-configuratiebestand verhinderen dat de desktop überhaupt vergrendelt. Voor dit profiel moet vergrendelen blijven werken als de signer, diens library of configuratie ontbreekt; ontgrendelen wordt dan geweigerd.

De SDDM-integratieroute is onderbouwd door upstream [GreeterProxy.cpp](https://github.com/sddm/sddm/blob/da0b64d8e2378c4bce16cbea6cac2ffc89ad1a4a/src/greeter/GreeterProxy.cpp#L111-L127), [Display.cpp](https://github.com/sddm/sddm/blob/da0b64d8e2378c4bce16cbea6cac2ffc89ad1a4a/src/daemon/Display.cpp#L331-L344) en [PamBackend.cpp](https://github.com/sddm/sddm/blob/da0b64d8e2378c4bce16cbea6cac2ffc89ad1a4a/src/helper/backend/PamBackend.cpp#L217-L243). Dit onderbouwt dat een aparte SDDM-C++-fork niet nodig lijkt voor deze PAM-route. De concrete SDDM-binary van de uiteindelijke ISO moet bij de build worden getest.

**ISO-installer: verplichte bronwijzigingen**

Alle paden in deze tabel liggen in `omacom/omarchy-iso`.

| Bestaand bronbestand | Aangetroffen werking en concrete wijziging |
|---|---|
| [configs/airootfs/root/configurator](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/root/configurator#L259) | `user_form()` vraagt nu een wachtwoord en berekent een hash; `user_step()` toont het in het overzicht. Vervang dit door gecontroleerde registratie/bevestiging van de eigen signer. `write_user_files()` (442–479) schrijft nu dezelfde hash voor root en gebruiker: dat moet verdwijnen. Accountidentiteit en lokale verificatiesleutelregistratie gescheiden vastleggen. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/context.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/context.py#L42) | `InstallContext.from_env()` moet het signerbeleid valideren voor handmatige én cidata-invoer. Legacy wachtwoordvelden, `root_enc_password`, `enc_password` en via `auth_config` aangeleverde alternatieven mogen het beleid niet opnieuw inschakelen. Alleen het interactieve formulier veranderen is onvoldoende. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L287) | In `arch_install_system()` accountaanmaak en `set_user_password(root)` wijzigen naar het gekozen accountbeleid zonder bruikbare wachtwoordauthenticatie. Registratie en de aanwezige signer-module controleren. Geen leeg wachtwoord als vervanging gebruiken. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L1408) | In `configure_login()` de tak op regels 1417–1422 verwijderen die bij versleuteling `/etc/sddm.conf.d/autologin.conf` aanmaakt. Autologin moet uit blijven, ook bij encrypted en deferred installs. Het onthouden van gebruikersnaam/sessie is geen authenticatie en kan blijven. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L1456) | `configure_ssh_access()` kan via cidata reguliere `authorized_keys` installeren, sshd activeren en de firewall openen. Voor uitsluitend lokale signerlogin deze route uitsluiten. Als SSH behouden wordt, moet zijn authenticatiebeleid afzonderlijk signergebonden worden; alleen PAM wijzigen sluit SSH-sleutelauthenticatie niet af. |

De gedeelde formuliercode komt uit runtime `install/provisioning/setup-form.sh`: de ISO-builder kopieert die uit het runtimecheckout. Daar hoort dus de gedeelde wijziging thuis.

| Bestaand bronbestand | Aangetroffen werking en concrete wijziging |
|---|---|
| [configs/airootfs/usr/local/bin/omarchy-cidata-load](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/local/bin/omarchy-cidata-load#L46) | Voor een apart signerregistratiebestand de vaste copy-/cleanup-lijsten aanpassen. Metadata kan ook in een gecontroleerd bestaand JSON-formaat worden vervoerd. Traditionele credentials/SSH-invoer afwijzen volgens hetzelfde beleid. |
| [configs/airootfs/root/.automated_script.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/root/.automated_script.sh#L94) | Cidata kan de configurator overslaan. Nieuwe argumenten hier doorgeven indien het enrollmentformaat dat nodig maakt. Voor beveiliging van de live installer moet authenticatie vóór de rootshell/installerroute plaatsvinden. |
| [configs/airootfs/usr/local/bin/omarchy-iso-install](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/local/bin/omarchy-iso-install#L12) | Argument-naar-environment-adapter: alleen wijzigen als nieuwe enrollmentargumenten worden ingevoerd of een provisioningroute verdwijnt. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/main.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/main.py#L48) | Alleen wijzigen als een nieuwe authenticatie-/enrollmentfase nodig is. De registratie moet aanwezig zijn vóór afronding en factorysnapshot, en bij bootintegratie vóór de laatste initramfs/UKI-build. |

**Eerste boot, verwijderen van alternatieve opties en herstel**

De onderstaande paden liggen in `omacom/omarchy`. Ze voorkomen dat een nieuwe gebruiker, eerste boot of reset opnieuw de huidige authenticatiemethoden krijgt.

| Bestaand bronbestand | Noodzakelijke wijziging of voorwaarde |
|---|---|
| [install/provisioning/setup-form.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/provisioning/setup-form.sh#L124) | `omarchy_prompt_password()` is de gedeelde wachtwoordvraag voor account/root/schijf. Vervang de accountauthenticatie door signerregistratie en behandel eventuele schijfsleutels afzonderlijk. |
| [bin/omarchy-provision-owner](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-provision-owner#L631) | `user_form()`/`confirm_form()` vervangen. `create_user()` zet op 740–741 hetzelfde wachtwoord voor user en root. `configure_login()` schrijft op 776 altijd autologin, ook eerst tijdelijk bij onversleutelde installs. Beide credential-/autologinpaden verwijderen. In `run_provisioning()` (1001+) signerregistratie en validatie verplicht laten slagen vóór afronding; user-finalization kan momenteel fouten tolereren en is daarom geen geschikte enige securitygate. |
| [bin/omarchy-provision-first-run](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-provision-first-run#L71) | Verwijder de registratie van `setup-fingerprint.hook` als post-update hook op 73–74. Bij migratie de al geïnstalleerde callback opruimen. |
| [install/user/first-run/setup-fingerprint.hook](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/user/first-run/setup-fingerprint.hook#L5) | De uitnodiging voor fingerprintauthenticatie en het starten van de setuphelper verwijderen/vervangen. |
| [default/omarchy/omarchy-menu.jsonc](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/omarchy/omarchy-menu.jsonc#L180) | Verwijder/vervang fingerprint- en FIDO2-setup (182–183), hun removalentries (299–300), de accountwachtwoordactie `passwd` (379) en, voor het overeenkomstige privilegebeleid, passwordless-sudo (185). De helpers zelf moeten het beleid ook respecteren; alleen menu-items verbergen is onvoldoende. |
| [bin/omarchy-setup-security-fingerprint](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-setup-security-fingerprint#L9) | Verwijderen uit de custombuild of de alternatieve authenticatie onmogelijk maken. Schrijft nu fingerprint/PAM en fallbackgedrag voor sudo/Polkit; regels 59–66 schrijven daarnaast een onafhankelijke fingerprint-lockservice. |
| [bin/omarchy-remove-security-fingerprint](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-remove-security-fingerprint#L9) | Uit de gebruikersinterface verwijderen of aanpassen tot een eenmalige legacy-cleanup die de nieuwe signerpolicy niet raakt. Verwijdert bestaande fingerprintregels en de fingerprint-lockservice. |
| [bin/omarchy-setup-security-fido2](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-setup-security-fido2#L19) | Verwijderen of blokkeren in dit signer-only profiel. `setup_pam_config()` voegt een voldoende U2F-route toe voor sudo/Polkit en kan bij een nieuw Polkit-bestand ook wachtwoordauthenticatie aanmaken. Dit is niet de huidige lockscreenroute. |
| [bin/omarchy-remove-security-fido2](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-remove-security-fido2#L9) | Verwijderen uit het menu of geschikt maken voor legacy-cleanup. Wist U2F-regels; de overige reeds bestaande authenticatie blijft anders staan. |
| [bin/omarchy-system-factory-reset](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-system-factory-reset#L301) | `scrub_factory_accounts()`, `sanitize_factory_baseline()` en `stage_full_reset()` moeten nieuwe accountgebonden signerregistraties en hostbinding volgens het resetbeleid behandelen. De gekloonde factorybaseline moet al de aangepaste pakketten en provisioning bevatten. Het bestaande verwijderen van gebruikerscredentials/rootlock behouden. |
| [bin/omarchy-system-factory-reset-finish](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-system-factory-reset-finish#L83) | `scrub_legacy_degraded_state()` kent de nieuwe signerregistratie nog niet. Resetopruiming aanvullen en daarna gecontroleerde registratie vereisen. |

Factory reset moet de signer-only systeemsoftware behouden. Of jouw apparaatgebonden verificatiesleutel bij een reset blijft gelden of wordt vervangen is enrollmentbeleid; blind alle vertrouwde sleutels wissen en vervolgens elke nieuwe token accepteren zou de eis ‘alleen mijn signer’ verliezen.

Als aanmelden op afstand niet tot dit profiel behoort, moet ook [bin/omarchy-setup-security-sshd](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-setup-security-sshd#L1) geen alternatieve SSH-login kunnen heractiveren. Als SSH behouden wordt, hoort die helper dezelfde afzonderlijk vastgelegde signerpolicy te installeren.

**Sudo en systeemautorisatie: alleen uitbreiden als die ook onder de signer-only eis vallen**

| Bestaand bronbestand | Noodzakelijke wijziging of voorwaarde |
|---|---|
| [shell/plugins/polkit/PolkitAgent.qml](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/plugins/polkit/PolkitAgent.qml#L35) | Password-/fingerprintmodi en passwordinput vervangen door signerstatus en afbreken. De werkelijke beslissing blijft in de Polkit-PAM-policy; een UI-wijziging alleen is onvoldoende. |
| [shell/plugins/polkit/PolkitModel.js](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/plugins/polkit/PolkitModel.js#L1) | Fingerprintpromptdetectie en fingerprint-PAM-detectie verwijderen/vervangen. Algemene labels behouden. |
| [bin/omarchy-sudo-passwordless](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-sudo-passwordless#L60) | Deze helper schrijft echt `NOPASSWD: ALL`. De feature verwijderen/blokkeren als algemene ongeauthenticeerde rootacties uitgesloten moeten zijn. Hij vereist eerst sudo; dit is geen zelfstandige pre-loginroute. |
| [bin/omarchy-sudo-keepalive](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-sudo-keepalive#L6) | Verlengt een reeds verkregen sudo-authcache. Alleen aanpassen als opnieuw tokenauthenticatie per bevoorrechte actie wordt vereist; signer-only login impliceert dat niet automatisch. |
| [etc/tmpfiles.d/omarchy-nopasswd-sudo.conf](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/etc/tmpfiles.d/omarchy-nopasswd-sudo.conf#L5) | Verwijdert tijdelijke grants bij boot. Dit beschermende opruimwerk behouden. |

De bestaande beperkte regels in `etc/sudoers.d/omarchy-dns`, `omarchy-theme-browser` en `omarchy-tzupdate` zijn niet hetzelfde als algemeen `NOPASSWD: ALL`. Ook de gewone geauthenticeerde wheel-sudoregel uit accountaanmaak is geen wachtwoordloze bypass. Een loginwijziging vereist niet het verwijderen van alle systeemautorisatie.

**Migraties: actuele defaults eerst**

Alle 123 migrationbestanden in deze snapshot zijn doorzocht. De relevante oudere paden zijn:
- [migrations/1784818437.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/migrations/1784818437.sh#L17): voegt alleen een lidgate toe als fingerprint-PAM al aanwezig is; bij ondersteuning van bestaande installs aanpassen/overslaan binnen het customprofiel.
- [migrations/1785090473.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/migrations/1785090473.sh#L6): herstelt een ontbrekend libfprint-pakket bij een bestaande fprintd-installatie; geen algemene authenticatie-installatie.
- [migrations/1787494718.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/migrations/1787494718.sh#L1): herstelt ownership van een bestaande FIDO-authfile.
- [migrations/1788025225.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/migrations/1788025225.sh#L1): verwijdert historische ruime grants; behouden.

Er is in deze migrationbodies geen algemene herinstallatie van wachtwoord-PAM of autologin gevonden. Wel installeren actuele helpers en provisioning die functies zoals hierboven beschreven. [bin/omarchy-provision-user](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-provision-user#L123) markeert bij eerste installatie alle migraties als uitgevoerd. Daarom mag de signer-installatie voor een verse ISO nooit uitsluitend in een nieuwe migration zitten. Die hoort in de actuele package/default-/installatieroute.

**De live ISO heeft eigen inlogroutes**

De builder kopieert eerst de Archiso-releng-profile: [builder/build-iso.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/builder/build-iso.sh#L56). Het ingesloten submodule staat op `424e78130db2af6c1ceb55b442d7914b1109ff2b`. Onder `archiso/` zijn de volgende bronnen geverifieerd:

| Geërfd bronpad | Aangetroffen werking |
|---|---|
| [configs/releng/airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf](https://github.com/archlinux/archiso/blob/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/etc/systemd/system/getty%40tty1.service.d/autologin.conf) | Tty1 start automatisch als root. |
| [configs/releng/airootfs/etc/shadow](https://github.com/archlinux/archiso/blob/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/etc/shadow) | Root heeft een lege wachtwoordhash. |
| [configs/releng/airootfs/etc/ssh/sshd_config.d/10-archiso.conf](https://github.com/archlinux/archiso/blob/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/etc/ssh/sshd_config.d/10-archiso.conf) | Staat wachtwoordauthenticatie en rootlogin via SSH toe. |
| [configs/releng/airootfs/etc/systemd/system/multi-user.target.wants/sshd.service](https://github.com/archlinux/archiso/blob/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/etc/systemd/system/multi-user.target.wants/sshd.service) | Activeert sshd. |
| [configs/releng/airootfs/root/.zlogin](https://github.com/archlinux/archiso/blob/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/root/.zlogin) | Start de automatische installer vanuit de reeds geopende rootshell. |

Als ook het installatiemedium zelf uitsluitend jouw signer moet accepteren, wijzig dan `builder/build-iso.sh` om deze geërfde alternatieven uit de samengestelde profile te verwijderen/overschrijven. Voeg de passende live-PAM-configuratie en een geauthenticeerd startpunt toe onder `configs/airootfs/`. Het Archiso-submodule hoeft daarvoor niet geforkt te worden. Alleen een signerknop in de configurator beveiligt de bestaande rootshell niet.

[configs/profiledef.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/profiledef.sh#L33) hoeft alleen te wijzigen voor eigenaars/permissies van nieuwe overlaybestanden. Het is zelf geen authenticatie-implementatie.

**Pakketten, lokale build en updates**

| Bestaand bronbestand | Aangetroffen werking en concrete wijziging |
|---|---|
| [install/omarchy-base.packages](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/omarchy-base.packages#L1) | Voeg het pakket met de signer-PAM-koppeling en eventuele benodigde runtime toe aan de doelinstallatie. De lijst wordt ook voor de offline pakketverzameling gelezen. Als de koppeling al in een bestaand custompakket zit, gebruik die pakketnaam. |
| [builder/build-omarchy-packages.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/builder/build-omarchy-packages.sh#L36) | De lokale build bouwt alleen `omarchy-settings-dev`, `omarchy-dev` en `omarchy-nvim`. Bij een apart nieuw signer-package de build-lijst uitbreiden en zijn builddependencies beschikbaar maken. Een `.so` op de USB wordt niet vanzelf een geïnstalleerde PAM-module. |
| [builder/build-iso.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/builder/build-iso.sh#L121) | Bij een apart signer-package ook toevoegen aan de live package list wanneer de live ISO het nodig heeft. De netwerkdownload-exclusions (213–224) en de lijst lokaal te behouden artifacts voor pruning (254–276) meeveranderen; anders kan het lokale pakket ontbreken of worden vervangen. |
| [pkgbuilds/omarchy-dev/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy-dev/PKGBUILD#L1) | Runtimepackage voor de bestaande `--local-source`-route. Installeert `bin`, `install`, `migrations` en `shell`. Declareer de signerdependency als die verplicht bij deze customruntime hoort. Bestaande runtimebestanden worden al uit het lokale checkout meegenomen. |
| [pkgbuilds/omarchy-settings-dev/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy-settings-dev/PKGBUILD#L219) | Kopieert `etc/` naar `/etc` en SDDM-assets naar `/usr/share/sddm/themes/omarchy`. Verwerk nieuwe authconfiguratie volgens pakketownership; upstream-owned PAM-bestanden niet blind als tweede eigenaar toevoegen. Eigen servicenames/configs kunnen wel eigen packagebestanden zijn. |
| [pkgbuilds/omarchy-settings-dev/omarchy-settings-dev.install](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy-settings-dev/omarchy-settings-dev.install#L5) | Bestaande plaats voor install/upgrade-overrides. Alleen uitbreiden indien dit pakket de nieuwe PAM-policy gaat beheren; bij een afzonderlijk signer-policy-package hoort deze functie daar. Actuele scriptlet overschrijft onder meer faillock/NSS/Plymouth, maar configureert zelf nog geen signer-PAM. |
| [default/pacman/pacman-edge.conf](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/pacman/pacman-edge.conf#L28) | De lokale ISO-route kiest edge. Regel de bron/voorrang van de eigen gewijzigde pakketten of expliciete versiepinning, zodat een latere update ze niet terugzet naar upstream. Dat kan met een lokale/private pakketbron; publiceren is niet vereist. |
| [default/pacman/pacman-stable.conf](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/pacman/pacman-stable.conf#L28) | Hetzelfde als stable als updatekanaal bereikbaar blijft. Niet nodig om ongebruikte kanalen uit te breiden als de custombuild de kanaalkeuze vastlegt. |
| [default/pacman/pacman-rc.conf](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/pacman/pacman-rc.conf#L28) | Hetzelfde voor rc als dit kanaal behouden blijft. |
| [bin/omarchy-refresh-pacman](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-refresh-pacman#L26) | Kopieert de gekozen standaardconfig opnieuw naar `/etc/pacman.conf` en voert een update uit. De custom pakketpolicy moet in die defaults of een behouden hook zitten. Alleen de geïnstalleerde `/etc/pacman.conf` handmatig wijzigen is niet duurzaam. |

Bij een releasevariant horen de overeenkomstige wijzigingen in [pkgbuilds/omarchy/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy/PKGBUILD#L12), [pkgbuilds/omarchy-settings/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy-settings/PKGBUILD#L12) en, indien gebruikt voor de nieuwe policy, [pkgbuilds/omarchy-settings/omarchy-settings.install](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/omarchy-settings/omarchy-settings.install#L5). Runtime en settings moeten dezelfde bronversie gebruiken.

`install/post-install/pacman.sh` kopieert de standaard pacmanconfig bij afronding. `bin/omarchy-update-system-pkgs` vervangt pakketinhoud onder `/usr/share/omarchy`; `bin/omarchy-update` voert vervolgens migraties uit. Deze scripts hoeven niet allemaal herschreven als de pakketbron en meegeleverde defaults het custombeleid correct behouden. Bronnen: [install/post-install/pacman.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/post-install/pacman.sh#L1), [bin/omarchy-update-system-pkgs](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-update-system-pkgs#L28), [bin/omarchy-update](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-update#L42).

De bestaande buildaanroep, vanuit het aangepaste `omarchy-iso`-checkout, is:

```bash
./bin/omarchy-iso-make --local-source ../omarchy ../omarchy-pkgs --no-boot-offer
```

[bin/omarchy-iso-make](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/bin/omarchy-iso-make#L33) ondersteunt dit al. De aanroep bouwt een ISO uit lokale bron; de signerwijzigingen moeten daarvoor eerst in de checkouts en pakketbuilds staan. Dit commando is tijdens het onderzoek niet uitgevoerd.

**PAM-doelbestanden zijn niet allemaal Omarchy-bronbestanden**

De onderstaande absolute paden worden door Arch-pakketten op het systeem geïnstalleerd. Een nieuw bestand in de custom bronstructuur of een installatiestap moet de gewenste policy op deze plaatsen verzorgen. Het zijn geen reeds aanwezige Omarchy-bronbestanden met diezelfde naam.

| Werkelijk doelpad | Toepassing |
|---|---|
| `/etc/pam.d/sddm` | Menselijke grafische login: uitsluitend signer-authenticatie; account/session behouden. |
| `/etc/pam.d/sddm-autologin` | Zelfstandige autologinservice; uitsluiten voor gebruikerslogin en bijbehorende SDDM-configuratie verwijderen. |
| `/etc/pam.d/sddm-greeter` | Serviceaccount van de greeter. Niet blind met menselijke signerlogin vervangen. |
| `/etc/pam.d/login` | TTY-login: dezelfde signerpolicy afdwingen. |
| `/etc/pam.d/system-auth`, `system-login`, `system-local-login`, `system-remote-login`, `system-services`, `other` | Bestaande centrale Arch-policies. De werkelijke include-keten uit de gekozen pakketset lezen; alternatieve menselijke authpaden doelgericht vervangen. Niet alle serviceaccounts op de token laten wachten. |
| `/etc/pam.d/su`, `su-l` | Menselijke accountwisselingen indien binnen het profiel. Eventuele short-circuits vóór de signer, zoals voldoende rootauthenticatie, expliciet beoordelen. |
| `/etc/pam.d/runuser`, `runuser-l` | Ook gebruikt voor rootgestuurde procesuitvoering. Niet gelijkstellen aan een zelfstandige gebruikersinlogmethode. |
| `/etc/pam.d/sudo` | Indien privilegeverhoging ook signer-only moet zijn. Arch gebruikt standaard dezelfde PAM-service voor `sudo -i`; een bestaand `sudo-i`-bestand is hier niet aangetroffen. |
| `/usr/lib/pam.d/polkit-1` | Huidige vendorpolicy. Een custom `/etc/pam.d/polkit-1` is een nieuw overridebestand. |
| `/etc/pam.d/sshd` en `/etc/ssh/sshd_config`/`sshd_config.d/` | Alleen indien SSH behouden blijft; SSH-methodeselectie afzonderlijk afdwingen. |
| `/etc/pam.d/passwd`, `chpasswd`, `newusers` | Wachtwoordbeheer/accountaanmaak. Dit zijn geen gewone loginmethoden, maar provisioning moet ermee in overeenstemming zijn. |

Bestandseigenaars en paden zijn gecontroleerd via de officiële lijsten van [pambase](https://archlinux.org/packages/core/any/pambase/files/), [SDDM](https://archlinux.org/packages/extra/x86_64/sddm/files/), [util-linux](https://archlinux.org/packages/core/x86_64/util-linux/files/), [sudo](https://archlinux.org/packages/core/x86_64/sudo/files/), [Polkit](https://archlinux.org/packages/extra/x86_64/polkit/files/), [OpenSSH](https://archlinux.org/packages/core/x86_64/openssh/files/) en [shadow](https://archlinux.org/packages/core/x86_64/shadow/files/). Die huidige Arch-lijsten bewijzen niet welke versies een later gekozen Omarchy-mirrorsnapshot precies bevat.

Het gaat om verwijderen van alternatieve `auth`-beslissingen. Een `pam_unix`-regel onder `account` of `session` is niet automatisch wachtwoordauthenticatie. Verwijder die dus niet blind. Een wachtwoordhash blokkeren is evenmin hetzelfde als alle andere authenticatieroutes verwijderen. Bronnen: [pam_unix](https://man.archlinux.org/man/pam_unix.8.en), [PAM-configuratie en overrides](https://man.archlinux.org/man/pam.d.5.en). Bij SSH kan sleutelcontrole PAM-auth overslaan, ook als PAM-account/session gebruikt wordt: [sshd_config](https://man.archlinux.org/man/sshd_config.5.en).

Een specifiek integratiepunt is gecontroleerd tegen de Quickshell-commit die [pkgbuilds/quickshell-git/PKGBUILD](https://github.com/omacom/omarchy-pkgs/blob/1b3cc7703d8cab2a52c36927502da9f8a48e3af6/pkgbuilds/quickshell-git/PKGBUILD) vastlegt: `28771c7c74b42e20afca0b1b63980cb46515537c`. Zijn [PAM-subproces](https://github.com/quickshell-mirror/quickshell/blob/28771c7c74b42e20afca0b1b63980cb46515537c/src/services/pam/subprocess.cpp) draait zonder privilegeverhoging en roept alleen PAM-authenticatie aan. De [modulebeschrijving](https://github.com/quickshell-mirror/quickshell/blob/28771c7c74b42e20afca0b1b63980cb46515537c/src/services/pam/module.md) bevestigt dit. Dus:
- De signer-koppeling moet ook vanuit de gebruikerscontext kunnen verifiëren en USB-toegang hebben; een beperkte bevoegde helper is alleen nodig als het gekozen transport/registratiemodel dat vereist.
- Accountregels in de locker-PAM behouden betekent niet dat Quickshell ze uitvoert. Als accountverval/revocation expliciet ook bij schermontgrendeling moet gelden, moet de verifier dat afdwingen of moet Quickshell doelgericht worden uitgebreid.

**Nieuwe integratiebestanden: voorgestelde namen, geen aangetroffen upstreambestanden**

| Voorgesteld nieuw bestand/component | Functie |
|---|---|
| `pkgbuilds/omarchy-usb-signer/PKGBUILD` in de eigen pakketboom | Bestaande verifier/library, PAM-koppeling, eventueel USB-helper en authconfiguratie als installeerbaar pakket leveren. Gebruik een bestaand eigen pakket als dat deze functie al levert. |
| `pam_mldsa_signer.so`, geïnstalleerd onder `/usr/lib/security/` | PAM-adapter naar jouw bestaande ML-DSA-65/87-verificatie en USB-protocol. Alleen nieuw bouwen als jouw bestaande artifacts deze PAM-interface nog niet leveren. |
| Eigen PAM-policybron voor bijvoorbeeld `/etc/pam.d/omarchy-lock-signer` | Enige toegestane locker-authroute, zonder wachtwoord-/fingerprint-/FIDO-alternatief. |
| Eigen registratieconfiguratie en eventuele udevregel | Lokaal vastleggen welke verificatiesleutel, welk algoritme en welk account mogen worden gebruikt; passende USB-rechten. Geen willekeurige ingeplugde token automatisch vertrouwen. |
| Eventuele install/upgrade-hook van het signer-policy-package | Alle beheerde doelbestanden consistent installeren en pakketupdates laten behouden wat de custombuild afdwingt. |

De authenticatietransactie moet een verse uitdaging verifiëren, aan account/dienst binden, het vastgelegde algoritme en de toegestane verificatiesleutel gebruiken en bij afwezigheid, time-out, ongeldig antwoord of modulefout weigeren. De privésleutel hoort niet in de ISO. De exacte bestandsnamen in jouw eigen crypto-/USB-project volgen uit de gekozen bestaande ABI en het USB-protocol; die zijn geen eigenschap van de Omarchy-broncode.

**Schijfontgrendeling vóór login, wanneer die ook uitsluitend via de signer moet lopen**

Dit is een afzonderlijk bootpad. ML-DSA verifieert ondertekening; een handtekening op zichzelf vervangt geen geheim waarmee LUKS de schijf ontsluit. De bestaande tokenfunctie moet dus ook de gekozen beschermde ontgrendelingssleutelroute ondersteunen.

| Bestaand bronbestand | Wijziging of afbakening |
|---|---|
| [etc/mkinitcpio.conf.d/omarchy_hooks.conf](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/etc/mkinitcpio.conf.d/omarchy_hooks.conf#L1) | De huidige hooks bevatten `encrypt` in een udev/initramfs-route. Voeg de gekozen signer-/sleutelvrijgave-integratie met alle benodigde USB- en crypto-runtime aan de initramfs toe; voorkom automatische terugval naar de huidige wachtwoordprompt. Niet stilzwijgend aannemen dat dit al een `sd-encrypt`-installatie is. |
| [configs/airootfs/root/configurator](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/root/configurator#L731) | Protected/pre-mounted en full-disk installatiepaden (ook regels 1109–1129) gebruiken nu het accountwachtwoord voor LUKS. Vervang beide door het gekozen tokengebonden sleutelbeheer. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L860) | Schrijft `/etc/crypttab.initramfs` en `cryptdevice=`-bootparameters voor pre-mounted installs. Aanpassen aan dezelfde tokenontgrendelingsroute. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L1170) | `stage_provisioning_state()` / `_stage_provisioning_luks_unlock()` schrijven een tijdelijk ontgrendelingsgeheim naar `/var/lib/omarchy/provisioning/luks-key` en `/etc/omarchy/provisioning.key`, nemen dat op in initramfs en gebruiken `cryptkey=`. Deze eerste-boot-auto-unlock verwijderen/vervangen als ook vanaf eerste boot uitsluitend de token mag ontgrendelen. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/context.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/context.py#L167) | `_inject_provisioning_encryption_password()` levert de tijdelijke passphrase voor deferred provisioning. Bij behoud van deze feature vervangen door het nieuwe beleid. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py#L1702) | `_validate_provisioning_state()` verwacht nu juist die tijdelijke sleutelbestanden en `cryptkey=`. De validator wijzigen naar de nieuwe voorwaarden. `FACTORY_SCRUB_PATHS` op 1851–1873 aanpassen aan nieuwe registratie-/provisioningbestanden. |
| [bin/omarchy-drive-password](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-drive-password#L15) | Deze beheerfunctie vraagt een nieuwe LUKS-passphrase en roept `cryptsetup luksChangeKey` aan. Verwijderen uit dit profiel of vervangen door tokengebonden sleutelbeheer; bijbehorende menuroute meeveranderen. |

Een nieuwe initramfs-hook/helper en eventueel een cryptsetup-tokencomponent zijn hier nog te kiezen integratiebestanden. Het is niet vastgesteld dat jouw bestaande signing-interface al een LUKS-geheim kan vrijgeven. Als het verzoek alleen login en schermontgrendeling betreft, zijn bovenstaande bootwijzigingen een aparte uitbreiding; de loginpatch moet die niet ongemerkt als voltooid claimen.

**Bestaande bestanden die niet automatisch een functionele patch nodig hebben**

| Bestaand bronbestand | Wijziging of afbakening |
|---|---|
| [install/config/lockscreen-pam.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/config/lockscreen-pam.sh#L1) | Roept alleen `omarchy-apply-lock` aan. De gewijzigde helper wordt al gebruikt. |
| [install/login/all.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/install/login/all.sh#L1) | Roept `sddm.sh` aan; geen nieuwe dispatch nodig als daar de policy wordt geïnstalleerd. |
| [bin/omarchy-refresh-sddm](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-refresh-sddm#L1) | Delegeert naar de bestaande theme-refreshroute. Het aangepaste bronbestand `Main.qml` wordt daar gebruikt. |
| [bin/omarchy-plymouth-set](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-plymouth-set#L294) | Kopieert de SDDM-assets. Alleen aanpassen als nieuwe assets buiten de bestaande vaste lijst worden toegevoegd. |
| [shell/services/AuthServiceStore.js](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/services/AuthServiceStore.js#L1) | Interne afgeschermde opslag voor authservices behouden. |
| [shell/shell.qml](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/shell/shell.qml#L883) | De scheiding tussen authenticatieplugins en andere plugins behouden. |
| [bin/omarchy-system-lock](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-system-lock#L8) | De bestaande `omarchy-shell lock lock`-aanroep kan blijven. |
| [configs/airootfs/usr/share/omarchy-iso/orchestrator/archinstall_adapter.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/configs/airootfs/usr/share/omarchy-iso/orchestrator/archinstall_adapter.py#L242) | De root-useradapter hoeft niet automatisch te wijzigen als inputvalidatie en de caller het nieuwe beleid al volledig afdwingen. |
| [bin/omarchy-iso-make](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/bin/omarchy-iso-make#L33) | Ondersteunt lokale sourcebuild al; hiervoor geen nieuwe buildfrontend nodig. |

Voor strikt vergrendeld hervatten na een lockerfout zijn er aanvullende bestaande wijzigingspunten: [bin/omarchy-system-sleep-lock](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-system-sleep-lock#L93), [bin/omarchy-system-sleep-monitor](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/bin/omarchy-system-sleep-monitor#L13) en eventueel [default/systemd/user/omarchy-sleep-lock.service](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/default/systemd/user/omarchy-sleep-lock.service#L1). De huidige code meldt een mislukte lock maar kan de slaapovergang niet stoppen met alleen zijn delay-inhibitor. Een signerwissel in PAM verandert dit bestaande foutpad niet.

De geërfde live-profile bevat bovendien de symlinks `configs/releng/airootfs/etc/systemd/system/cloud-init.target.wants/cloud-config.service`, `cloud-final.service`, `cloud-init-local.service`, `cloud-init-main.service` en `cloud-init-network.service`. Ze vormen aanvullende configuratie-invoer. Voor een gesloten installerprofiel moeten ze uitgeschakeld worden of dezelfde invoerpolicy krijgen; de exacte paden staan in de [vastgelegde Archiso-boom](https://github.com/archlinux/archiso/tree/424e78130db2af6c1ceb55b442d7914b1109ff2b/configs/releng/airootfs/etc/systemd/system/cloud-init.target.wants).

**Verificatie die bij de implementatie hoort**

Dit onderzoek heeft bestaande broncode en pakketpaden gecontroleerd. Er zijn geen logininstellingen op een gebruikersmachine gewijzigd en er is geen signer-/ISO-test uitgevoerd.

De bestaande tests bevatten aannames over wachtwoorden, fingerprint en gewone SSH-sleutels. Bij de implementatie moeten de betreffende tests worden aangepast of vervangen; een ongewijzigde stocktest bewijst geen signer-only werking.

| Repository | Bestaande relevante tests |
|---|---|
| omacom/omarchy | [test/shell.d/apply-lock-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/apply-lock-test.sh); [test/shell.d/lock-blank-fingerprint-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/lock-blank-fingerprint-test.sh); [test/shell.d/lock-fingerprint-indicator-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/lock-fingerprint-indicator-test.sh); [test/shell.d/lock-password-overflow-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/lock-password-overflow-test.sh); [test/shell.d/polkit-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/polkit-test.sh); [test/shell.d/setup-form-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/setup-form-test.sh); [test/shell.d/provision-user-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/provision-user-test.sh); [test/shell.d/factory-reset-accounts-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/factory-reset-accounts-test.sh); [test/shell.d/security-fido2-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/security-fido2-test.sh); [test/shell.d/security-fido2-remove-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/security-fido2-remove-test.sh); [test/shell.d/fingerprint-invitation-test.sh](https://github.com/omacom/omarchy/blob/ab18321bb53563a8a3f8a44f64ebb9c6463fedc5/test/shell.d/fingerprint-invitation-test.sh) |
| omacom/omarchy-iso | [test/unit/test_configure_ssh_access.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/test/unit/test_configure_ssh_access.py); [test/unit/test_provisioning_state.py](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/test/unit/test_provisioning_state.py); [test/unit/cidata-load-test.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/test/unit/cidata-load-test.sh); [test/integration.d/base-test.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/test/integration.d/base-test.sh); [test/integration.d/factory-reset-test.sh](https://github.com/omacom/omarchy-iso/blob/7cfb7111a06873d61c45d37034577d4ba08d3f4f/test/integration.d/factory-reset-test.sh) |

De doorslaggevende acceptatiegevallen zijn: de eigen toegestane signer werkt bij SDDM, schermontgrendeling en TTY; ontbreken, verkeerde token, verkeerd algoritme, ongeldig/herhaald antwoord, afbreken en ontbrekende module geven geen toegang; password/fingerprint/FIDO/autologin geven geen alternatieve toegang. Herhaal voor eerste boot, de gekozen resetroute en een pakketupdate. Test live-installer en preboot-schijfpad afzonderlijk als die onderdeel van het profiel zijn. Dit zijn uit te voeren acceptatievoorwaarden, geen reeds behaalde resultaten.

**Precieze onderzoeksgrens**

De Omarchy-, ISO- en pakketbronpaden hierboven zijn aan vaste commits gekoppeld. Huidige Arch-bestandspaden zijn via officiële pakketlijsten bevestigd. De volledige huidige Arch-PAM-configuratie-inhoud was via GitLab niet leesbaar door toegangsblokkade; daarom wordt hier geen ongecontroleerd exact include-schema of direct installeerbaar generiek PAM-bestand voorgesteld. Lees voor de definitieve patch de PAM-bestanden uit de daadwerkelijk gekozen ISO-pakketset.

De exacte eigen verifier-exportnamen, USB-transportinterface en eventuele bestaande PAM-adapter zijn niet uit deze Omarchy-broncode af te leiden. Ze bepalen welke eigen buildbestanden aan de vastgestelde integratiepunten worden gekoppeld. De broninspectie levert daarmee de concrete wijzigingskaart; een werkende custom ISO is een volgende implementatie- en verificatiestap.

