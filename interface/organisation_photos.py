"""
Onglet « 📷 Photos » de la fenêtre Organisation (étape 7) : importer les
photos d'une course (dossier, zip, lien de partage ; les téléphones des
bénévoles envoient les leurs par le serveur), lire les dossards sur
l'ordinateur, corriger les photos douteuses, puis rendre à chaque coureur
SES photos : page publique par dossard et code, zip par coureur, e-mail.
Une photo n'est rendue que si tous les coureurs reconnus dessus ont accepté
la diffusion de leur image (et, pour un mineur, avec l'autorisation
parentale). Aucune reconnaissance des visages.
Aucune requête SQL ici : noyau/donnees/photos.py.
"""

import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QImage, QPixmap
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
    QDialog, QListWidgetItem, QMessageBox, QProgressBar, QSplitter, QVBoxLayout, QWidget,
)

from noyau.donnees import photos as dph
from noyau.photos import regles as RP, lecture as LEC
from interface.organisation import _EcranOrga
from interface.calendrier_competitions import _bouton, _cadre, _table
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie, _ouvrir_pdf
from interface import orga_pdf as P

VERT, ORANGE, ROUGE, GRIS = "#2E7D32", "#E65100", "#C62828", "#8A949E"
FILTRES = (("a_verifier", "À vérifier"), (None, "Toutes"), ("sans_dossard", "Sans dossard"), ("a_lire", "Pas encore lues"),
           ("lue", "Lues"), ("verifiee", "Vérifiées"), ("masquees", "Masquées"))


# ------------------------------------------------------------------ travaux en tâche de fond

class _Signaux(QObject):
    image = Signal(int, object)                  # photo_id, octets
    importee = Signal(str, object, object)       # nom, octets, lectures (ou None)
    lue = Signal(int, object)                    # photo_id, lectures
    message = Signal(str)
    fini = Signal(str)                           # nature du travail


class _Travail(QRunnable):
    """Un seul fil par travail, qui traite sa liste dans l'ordre (sûr aussi quand le logiciel est branché sur le serveur)."""

    def __init__(self, nature, elements, fonction):
        super().__init__()
        self.nature, self.elements, self.fonction = nature, list(elements), fonction
        self.signaux, self.arret = _Signaux(), False

    def run(self):
        for x in self.elements:
            if self.arret:
                break
            try:
                self.fonction(self, x)
            except Exception as e:               # une photo illisible n'arrête pas le reste
                self.signaux.message.emit(f"{getattr(x, 'name', x)} : {e}")
        self.signaux.fini.emit(self.nature)


def _vignette(tr, pid):
    tr.signaux.image.emit(pid, dph.image(pid, "vignette"))


def _importer(tr, chemin):
    chemin = Path(chemin)
    octets = chemin.read_bytes()
    lect = None
    if tr.lire:
        try:
            lect = LEC.lire(chemin)
        except Exception:
            lect = None
    tr.signaux.importee.emit(chemin.name, octets, lect)


def _lire(tr, pid):
    octets = dph.image(pid, "lecture")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(octets)
    try:
        tr.signaux.lue.emit(pid, LEC.lire(f.name))
    finally:
        Path(f.name).unlink(missing_ok=True)


class PhotosOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📷  Photos par dossard", "Importe les photos de la course : les numéros de dossard sont lus sur "
                         "cet ordinateur, sans Internet. Corrige les photos douteuses, puis rends à chaque coureur SES photos "
                         "(page par dossard et code, zip, e-mail). Une photo n'est rendue que si tous les coureurs visibles "
                         "ont accepté la diffusion de leur image ; aucune reconnaissance des visages.", athlete_id_initial)
        self._photos, self._coureurs, self._pixmaps, self._travaux = [], [], {}, []
        self._lecture_auto = LEC.disponible()
        self._en_attente_vignettes = set()
        # chiffres
        h = QHBoxLayout()
        self.c_photos, self.c_verif, self.c_coureurs, self.c_retenues = (
            self._carte("Photos"), self._carte("À vérifier"), self._carte("Coureurs qui ont des photos"),
            self._carte("Photos retenues (droit à l'image)"))
        for c in (self.c_photos, self.c_verif, self.c_coureurs, self.c_retenues):
            h.addWidget(c)
        self.principal.addLayout(h)
        # import
        cadre, lc = _cadre("Importer")
        b = QHBoxLayout()
        self.photographe = QLineEdit()
        self.photographe.setPlaceholderText("Photographe (facultatif)")
        self.photographe.setMaximumWidth(240)
        bd, bz, bl = _bouton("📁 Un dossier de photos", True), _bouton("🗜️ Un zip"), _bouton("🔗 Un lien de partage")
        bd.clicked.connect(self._importer_dossier)
        bz.clicked.connect(self._importer_zip)
        bl.clicked.connect(self._importer_lien)
        self.b_lire = _bouton("🔎 Lire les photos pas encore lues")
        self.b_lire.clicked.connect(self._lire_restantes)
        self.b_arret = _bouton("Arrêter")
        self.b_arret.clicked.connect(self._arreter)
        for w in (self.photographe, bd, bz, bl, self.b_lire, self.b_arret):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.progres = QProgressBar()
        self.progres.setVisible(False)
        lc.addWidget(self.progres)
        self.etat = QLabel("")
        self.etat.setObjectName("texteSecondaire")
        self.etat.setWordWrap(True)
        lc.addWidget(self.etat)
        self.principal.addWidget(cadre)
        # galerie et correction
        cadre, lc = _cadre("Photos et dossards")
        f = QHBoxLayout()
        self.filtre = QComboBox()
        for v, l in FILTRES:
            self.filtre.addItem(l, v)
        self.dossard = QLineEdit()
        self.dossard.setPlaceholderText("Dossard…")
        self.dossard.setMaximumWidth(110)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        f.addWidget(QLabel("Voir :"))
        f.addWidget(self.filtre)
        f.addWidget(self.dossard)
        f.addWidget(self.compte, 1)
        lc.addLayout(f)
        sp = QSplitter(Qt.Orientation.Horizontal)
        self.galerie = QListWidget()
        self.galerie.setViewMode(QListView.ViewMode.IconMode)
        self.galerie.setIconSize(QSize(170, 120))
        self.galerie.setGridSize(QSize(190, 160))
        self.galerie.setResizeMode(QListView.ResizeMode.Adjust)
        self.galerie.setMovement(QListView.Movement.Static)
        self.galerie.setUniformItemSizes(True)
        self.galerie.setMinimumHeight(430)
        self.galerie.currentRowChanged.connect(self._detail)
        self.galerie.verticalScrollBar().valueChanged.connect(lambda _v: self._charger_vignettes_visibles())
        sp.addWidget(self.galerie)
        droite = QWidget()
        ld = QVBoxLayout(droite)
        ld.setContentsMargins(8, 0, 0, 0)
        self.apercu = QLabel("Choisis une photo.")
        self.apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apercu.setMinimumSize(420, 300)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.saisie = QLineEdit()
        self.saisie.setPlaceholderText("Dossards visibles : 57, 312 (vide = personne de reconnaissable)")
        self.saisie.returnPressed.connect(self._enregistrer_saisie)
        bb = QHBoxLayout()
        self.b_ok = _bouton("✓ Enregistrer et suivante", True)
        self.b_ok.clicked.connect(self._enregistrer_saisie)
        self.b_masquer = _bouton("Masquer")
        self.b_masquer.clicked.connect(self._masquer)
        self.b_suppr = _bouton("Supprimer")
        self.b_suppr.clicked.connect(self._supprimer)
        for w in (self.b_ok, self.b_masquer, self.b_suppr):
            bb.addWidget(w)
        bb.addStretch()
        ld.addWidget(self.apercu, 1)
        ld.addWidget(self.info)
        ld.addWidget(self.saisie)
        ld.addLayout(bb)
        sp.addWidget(droite)
        sp.setSizes([620, 560])
        lc.addWidget(sp, 1)
        self.principal.addWidget(cadre)
        # diffusion
        cadre, lc = _cadre("Rendre les photos aux coureurs")
        o = QHBoxLayout()
        self.ouvertes = QCheckBox("Page publique ouverte (dossard + code personnel)")
        self.ouvertes.toggled.connect(self._ouvrir_page)
        self.lien = QLabel("")
        self.lien.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bc = _bouton("Copier le lien")
        bc.clicked.connect(self._copier_lien)
        badr = _bouton("Adresse publique…")
        badr.clicked.connect(self._adresse)
        o.addWidget(self.ouvertes)
        o.addWidget(self.lien, 1)
        o.addWidget(bc)
        o.addWidget(badr)
        lc.addLayout(o)
        self.table = _table(["Dossard", "Coureur", "Épreuve", "Photos", "Rendues", "Image", "Code", "Envoyé"], 300)
        lc.addWidget(self.table)
        b2 = QHBoxLayout()
        bcodes, bzip, bmail, bvoir = (_bouton("📄 Codes en PDF"), _bouton("🗜️ Un zip par coureur…"),
                                      _bouton("✉️ Envoyer par e-mail…", True), _bouton("Voir ses photos"))
        bcodes.clicked.connect(self._pdf_codes)
        bzip.clicked.connect(self._zips)
        bmail.clicked.connect(self._courriels)
        bvoir.clicked.connect(self._voir_coureur)
        for w in (bmail, bzip, bcodes, bvoir):
            b2.addWidget(w)
        b2.addStretch()
        lc.addLayout(b2)
        aide = QLabel("Le droit à l'image se coche sur chaque inscription (ou s'importe avec la colonne « droit à l'image ») ; "
                      "un licencié peut aussi l'avoir donné sur sa fiche (Serveur et comptes, Consentements). Un coureur qui "
                      "demande le retrait d'une photo : masque-la, elle disparaît de sa page et de celles des autres.")
        aide.setObjectName("texteSecondaire")
        aide.setWordWrap(True)
        lc.addWidget(aide)
        self.principal.addWidget(cadre)
        self.filtre.currentIndexChanged.connect(lambda _i: self._remplir_galerie())
        self.dossard.textChanged.connect(lambda _t: self._remplir_galerie())
        self._finir()

    # ------------------------------------------------------------------ affichage
    def rafraichir(self):
        ev = self.evenement_id
        for w in (self.b_lire,):
            w.setEnabled(bool(ev) and self._lecture_auto)
        self.b_arret.setEnabled(bool(self._travaux))
        if not ev:
            self._photos, self._coureurs = [], []
            self.galerie.clear()
            _remplir(self.table, [])
            return
        d = dph.diffusion(ev)
        self._coureurs = d["coureurs"]
        st = d["statuts"]
        self.c_photos.valeur.setText(str(d["photos"]))
        self.c_photos.detail.setText(f"{st.get('a_lire', 0)} pas encore lue(s) · {st.get('sans_dossard', 0)} sans dossard")
        self.c_verif.valeur.setText(str(st.get("a_verifier", 0)))
        self.c_verif.detail.setText("lecture douteuse : à corriger" if st.get("a_verifier") else "rien à corriger")
        self.c_coureurs.valeur.setText(f"{d['avec_photos']}/{len(self._coureurs)}")
        self.c_coureurs.detail.setText(f"{sum(1 for c in self._coureurs if not c['diffusable'])} sans accord pour l'image")
        self.c_retenues.valeur.setText(str(d["retenues"]))
        self.c_retenues.detail.setText("un coureur dessus n'a pas donné son accord")
        if not self._lecture_auto:
            self.etat.setText("La lecture automatique des dossards n'est pas installée sur cet ordinateur : saisis les "
                              "dossards de chaque photo (Entrée pour passer à la suivante).")
        self.ouvertes.blockSignals(True)
        self.ouvertes.setChecked(bool(d["evenement"]["photos_ouvertes"]))
        self.ouvertes.blockSignals(False)
        self.lien.setText(self._url_publique() or "définis l'adresse publique du serveur →")
        coul = {}
        for r, c in enumerate(self._coureurs):
            coul[(r, 5)] = VERT if c["diffusable"] else ORANGE
        _remplir(self.table, [(c["dossard"], f"{c['nom']} {c['prenom'] or ''}", c["epreuve"], c["nb_photos"], c["nb_diffusables"],
                               "accord" if c["diffusable"] else c["raison"], c["code"] or "", (c["envoye_le"] or "")[:10])
                              for c in self._coureurs], coul)
        self._remplir_galerie()

    def _remplir_galerie(self):
        ev = self.evenement_id
        if not ev:
            return
        garde = self._choisie()["id"] if self._choisie() else None
        d = self.dossard.text().strip()
        self._photos = dph.photos(ev, statut=self.filtre.currentData(), dossard=int(d) if d.isdigit() else None,
                                  avec_masquees=self.filtre.currentData() == "masquees")
        self.galerie.blockSignals(True)
        self.galerie.clear()
        vide = QPixmap(170, 120)
        vide.fill(Qt.GlobalColor.darkGray)
        for p in self._photos:
            it = QListWidgetItem(QIcon(self._pixmaps.get(p["id"], vide)), self._legende(p))
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            if p["statut"] in ("a_verifier", "sans_dossard"):
                it.setForeground(Qt.GlobalColor.darkYellow)
            self.galerie.addItem(it)
        self.galerie.blockSignals(False)
        self.compte.setText(f"{len(self._photos)} photo(s)")
        r = next((k for k, p in enumerate(self._photos) if p["id"] == garde), 0 if self._photos else -1)
        self.galerie.setCurrentRow(r)
        self._detail(r)
        self._charger_vignettes_visibles()

    @staticmethod
    def _legende(p):
        d = ", ".join(map(str, p["dossards"])) or "—"
        return f"{d}\n{RP.LIBELLE_STATUT.get(p['statut'], '')}"

    def _charger_vignettes_visibles(self):
        manque = [p["id"] for p in self._photos if p["id"] not in self._pixmaps and p["id"] not in self._en_attente_vignettes]
        if not manque:
            return
        manque = manque[:120]
        self._en_attente_vignettes |= set(manque)
        t = _Travail("vignettes", manque, _vignette)
        t.signaux.image.connect(self._vignette_recue)
        t.signaux.fini.connect(self._travail_fini)
        self._lancer(t, montrer=False)

    def _vignette_recue(self, pid, octets):
        if not isValid(self):
            return
        im = QImage.fromData(octets)
        if im.isNull():
            return
        pm = QPixmap.fromImage(im)
        self._pixmaps[pid] = pm
        self._en_attente_vignettes.discard(pid)
        for i in range(self.galerie.count()):
            it = self.galerie.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == pid:
                it.setIcon(QIcon(pm))
                break

    def _choisie(self):
        r = self.galerie.currentRow()
        return self._photos[r] if 0 <= r < len(self._photos) else None

    def _detail(self, _r=None):
        p = self._choisie()
        for w in (self.saisie, self.b_ok, self.b_masquer, self.b_suppr):
            w.setEnabled(p is not None)
        if not p:
            self.apercu.setText("Pas de photo dans cette liste." if self.evenement_id else "Choisis un événement.")
            self.apercu.setPixmap(QPixmap())
            self.info.setText("")
            self.saisie.clear()
            return
        try:
            im = QImage.fromData(dph.image(p["id"], "web"))
            self.apercu.setPixmap(QPixmap.fromImage(im).scaled(self.apercu.width() or 560, max(300, self.apercu.height()),
                                                               Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        except Exception as e:
            self.apercu.setText(f"Photo illisible : {e}")
        lu = p.get("lecture") or {}
        doutes = ", ".join(lu.get("doutes") or [])
        self.info.setText(f"<b>{RP.LIBELLE_STATUT.get(p['statut'], '')}</b> · {p['nom_origine'] or ''}"
                          f"{' · ' + p['prise_le'].replace('T', ' ')[:16] if p.get('prise_le') else ''}"
                          f"{' · ' + p['photographe'] if p.get('photographe') else ''}"
                          + (f"<br><span style='color:{ORANGE}'>Lu sans certitude : {doutes}</span>" if doutes else "")
                          + (" · <b>masquée</b>" if p["masquee"] else ""))
        self.saisie.setText(", ".join(map(str, p["dossards"])))
        self.saisie.setFocus()
        self.saisie.selectAll()
        self.b_masquer.setText("Remettre" if p["masquee"] else "Masquer")

    # ------------------------------------------------------------------ correction
    def _enregistrer_saisie(self):
        p = self._choisie()
        if not p:
            return
        try:
            dph.definir_dossards(p["id"], self.saisie.text())
        except dph.ErreurPhotos as e:
            QMessageBox.warning(self, "Photos", str(e))
            return
        r = self.galerie.currentRow()
        nouvelle = dph.photo(p["id"])
        filtre = self.filtre.currentData()
        if filtre in (None, "verifiee") or (self.dossard.text().strip().isdigit() and
                                            int(self.dossard.text()) in nouvelle["dossards"]):
            nouvelle["lecture"] = p.get("lecture")
            self._photos[r] = {**p, **nouvelle}
            self.galerie.item(r).setText(self._legende(self._photos[r]))
            self.galerie.item(r).setForeground(self.galerie.palette().text())
            r += 1
        else:                                            # elle sort de la liste « à vérifier »
            self._photos.pop(r)
            self.galerie.takeItem(r)
        if r < self.galerie.count():
            self.galerie.setCurrentRow(r)
        self._detail()
        self._chiffres_seulement()

    def _chiffres_seulement(self):
        d = dph.tableau(self.evenement_id)
        self.c_verif.valeur.setText(str(d["statuts"].get("a_verifier", 0)))
        self.c_coureurs.valeur.setText(f"{d['coureurs_avec_photos']}/{len(self._coureurs)}")
        self.c_retenues.valeur.setText(str(d["retenues"]))

    def _masquer(self):
        p = self._choisie()
        if p:
            dph.masquer(p["id"], not p["masquee"])
            self.rafraichir()

    def _supprimer(self):
        p = self._choisie()
        if p and QMessageBox.question(self, "Photos", "Supprimer cette photo de Trail Hub (le fichier d'origine que tu as "
                                      "importé reste où il est) ?") == QMessageBox.StandardButton.Yes:
            dph.supprimer_photo(p["id"])
            self._pixmaps.pop(p["id"], None)
            self.rafraichir()

    # ------------------------------------------------------------------ import et lecture
    def _lancer(self, t, montrer=True):
        self._travaux.append(t)
        t.signaux.fini.connect(lambda _n, t=t: self._retirer(t))
        if montrer:
            self.progres.setRange(0, len(t.elements))
            self.progres.setValue(0)
            self.progres.setVisible(True)
        self.b_arret.setEnabled(True)
        QThreadPool.globalInstance().start(t)

    def _retirer(self, t):
        if not isValid(self):
            return
        if t in self._travaux:
            self._travaux.remove(t)
        if t.nature == "vignettes":
            self._en_attente_vignettes -= set(t.elements)
        self.b_arret.setEnabled(bool(self._travaux))
        if not any(x.nature in ("import", "lecture", "zips", "courriels") for x in self._travaux):
            self.progres.setVisible(False)

    def _travail_fini(self, nature):
        if not isValid(self):
            return
        if nature in ("import", "lecture"):
            self.rafraichir()

    def _arreter(self):
        for t in self._travaux:
            t.arret = True
        self.etat.setText("Arrêt demandé : la photo en cours se termine.")

    def _avancer(self, texte=None):
        if not isValid(self):
            return
        self.progres.setValue(self.progres.value() + 1)
        if texte:
            self.etat.setText(texte)

    def _importer_chemins(self, chemins, source):
        ev = self.evenement_id
        if not ev:
            QMessageBox.information(self, "Photos", "Choisis d'abord l'événement.")
            return
        chemins = [c for c in chemins if RP.est_photo(c)]
        if not chemins:
            QMessageBox.information(self, "Photos", "Pas de photo dans ce choix (JPEG, PNG, HEIC…).")
            return
        stats = {"ok": 0, "deja": 0, "erreurs": []}
        photographe = self.photographe.text().strip() or None

        def recue(nom, octets, lect):
            try:
                r = dph.importer_contenu(ev, nom, octets, source, photographe, lect)
                stats["ok" if r["nouvelle"] else "deja"] += 1
            except dph.ErreurPhotos as e:
                stats["erreurs"].append(str(e))
            self._avancer(f"{stats['ok']} photo(s) importée(s)" + (f", {stats['deja']} déjà là" if stats["deja"] else "")
                          + (" · dossards lus au passage" if self._lecture_auto else "")
                          + (f" · {len(stats['erreurs'])} erreur(s)" if stats["erreurs"] else ""))

        t = _Travail("import", chemins, _importer)
        t.lire = self._lecture_auto
        t.signaux.importee.connect(recue)
        t.signaux.message.connect(lambda m: (stats["erreurs"].append(m), self._avancer()))
        t.signaux.fini.connect(self._travail_fini)
        self.etat.setText(f"Import de {len(chemins)} photo(s)…")
        self._lancer(t)

    def _importer_dossier(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des photos de la course")
        if d:
            self._importer_chemins(sorted(str(p) for p in Path(d).rglob("*") if p.is_file()), "dossier")

    def _importer_zip(self, chemin=None, source="zip"):
        if not chemin:
            chemin, _ = QFileDialog.getOpenFileName(self, "Zip des photos", "", "Zip (*.zip)")
        if not chemin:
            return
        import zipfile
        dest = Path(tempfile.mkdtemp(prefix="photos_"))
        try:
            with zipfile.ZipFile(chemin) as z:
                for info in z.infolist():
                    if not info.is_dir() and RP.est_photo(info.filename) and "__MACOSX" not in info.filename:
                        nom = Path(info.filename).name
                        cible = dest / f"{len(list(dest.iterdir())):05d}_{nom}"
                        cible.write_bytes(z.read(info))
        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Photos", "Ce fichier n'est pas un zip lisible.")
            return
        self._importer_chemins(sorted(str(p) for p in dest.iterdir()), source)

    def _importer_lien(self):
        url, ok = QInputDialog.getText(self, "Lien de partage", "Lien du photographe (Dropbox, Google Drive pour un fichier, "
                                       "ou lien direct vers un zip) :")
        if not ok or not url.strip():
            return
        direct, conseil = RP.lien_direct(url)
        if not direct:
            QMessageBox.information(self, "Lien de partage", conseil)
            return
        self.etat.setText("Téléchargement du lien…")

        class _Tel(QRunnable):
            def __init__(s2):
                super().__init__()
                s2.signaux = _Signaux()

            def run(s2):
                try:
                    s2.signaux.fini.emit(dph.telecharger_lien(url))
                except Exception as e:
                    s2.signaux.message.emit(str(e))

        t = _Tel()
        t.signaux.fini.connect(lambda chemin: self._importer_zip(chemin, "lien"))
        t.signaux.message.connect(lambda m: (self.etat.setText(f"Lien : {m}"), QMessageBox.warning(self, "Lien de partage", m)))
        self._garde_tel = t
        QThreadPool.globalInstance().start(t)

    def _lire_restantes(self):
        ids = dph.a_lire(self.evenement_id, n=100000)
        if not ids:
            self.etat.setText("Toutes les photos ont déjà été lues.")
            return

        def lue(pid, lect):
            if lect is not None:
                dph.enregistrer_lecture(pid, lect)
            self._avancer(f"Lecture des dossards : {self.progres.value() + 1}/{self.progres.maximum()}")

        t = _Travail("lecture", ids, _lire)
        t.signaux.lue.connect(lue)
        t.signaux.fini.connect(self._travail_fini)
        self._lancer(t)

    # ------------------------------------------------------------------ diffusion
    def _url_publique(self):
        from data.database import obtenir_parametre
        base_url = (obtenir_parametre("photos_adresse_publique") or "").rstrip("/")
        if not base_url:
            try:
                from noyau.serveur import demarrage as DM
                from data.database import obtenir_parametre as op
                if DM.etat.get("mode") == "serveur" and op("serveur_url"):
                    base_url = op("serveur_url").rstrip("/")
            except Exception:
                pass
        if not base_url or not self.evenement_id:
            return ""
        return f"{base_url}/photos/{dph.evenement_photos(self.evenement_id)['uuid']}"

    def _adresse(self):
        from data.database import obtenir_parametre, definir_parametre
        t, ok = QInputDialog.getText(self, "Adresse publique", "Adresse du serveur du club vue depuis Internet (par exemple "
                                     "https://trail-club.example.fr:8770) :", text=obtenir_parametre("photos_adresse_publique") or "")
        if ok:
            t = t.strip().rstrip("/")
            if t and not t.startswith(("https://", "http://")):
                QMessageBox.warning(self, "Adresse publique", "L'adresse doit commencer par https://")
                return
            definir_parametre("photos_adresse_publique", t)
            self.rafraichir()

    def _copier_lien(self):
        u = self._url_publique()
        if u:
            QGuiApplication.clipboard().setText(u)
            self.etat.setText("Lien copié.")

    def _ouvrir_page(self, oui):
        if not self.evenement_id:
            return
        if oui and not any(c["nb_diffusables"] for c in self._coureurs):
            if QMessageBox.question(self, "Photos", "Aucun coureur n'a encore de photo à recevoir. Ouvrir quand même la "
                                    "page ?") != QMessageBox.StandardButton.Yes:
                self.ouvertes.blockSignals(True)
                self.ouvertes.setChecked(False)
                self.ouvertes.blockSignals(False)
                return
        dph.ouvrir_photos(self.evenement_id, oui)
        self.rafraichir()

    def _coureur_choisi(self):
        return _ligne_choisie(self.table, self._coureurs)

    def _voir_coureur(self):
        c = self._coureur_choisi()
        if c:
            self.filtre.setCurrentIndex(self.filtre.findData(None))
            self.dossard.setText(str(c["dossard"]))

    def _pdf_codes(self):
        if not self.evenement_id:
            return
        ev = dph.evenement_photos(self.evenement_id)
        lignes = [(str(d), P._e(f"{n} {p or ''}"), P._e(e), f"<b style='font-family:monospace;font-size:12pt'>{c}</b>")
                  for d, n, p, e, c in dph.codes(self.evenement_id)]
        u = self._url_publique()
        html = (P._entete("Codes des photos", {"nom": ev["nom"], "date_debut": ev["date_debut"], "commune": ev.get("commune")})
                + (f"<p>Page des photos : <b>{P._e(u)}</b></p>" if u else "")
                + "<p>À remettre avec le dossard (ou à découper) : le code ouvre les photos de ce coureur seulement.</p>"
                + P._tableau(["Dossard", "Coureur", "Épreuve", "Code"], lignes, [12, 44, 24, 20]) + P._pied())
        self.rafraichir()
        _ouvrir_pdf(self, "Codes des photos.pdf", html)

    def _zips(self):
        aenvoyer = [c for c in self._coureurs if c["nb_diffusables"]]
        if not aenvoyer:
            QMessageBox.information(self, "Photos", "Aucun coureur n'a de photo à recevoir pour l'instant.")
            return
        d = QFileDialog.getExistingDirectory(self, "Dossier où ranger un zip par coureur")
        if not d:
            return

        def faire(tr, c):
            (Path(d) / RP.nom_zip(c["dossard"], c["nom"], c["prenom"])).write_bytes(dph.zip_coureur(c["inscription_id"]))
            tr.signaux.message.emit(f"zip : {c['dossard']}")

        t = _Travail("zips", aenvoyer, faire)
        t.signaux.message.connect(lambda m: self._avancer(f"{self.progres.value() + 1}/{len(aenvoyer)} zip(s)"))
        t.signaux.fini.connect(lambda n: (self._travail_fini(n), QDesktopServices.openUrl(QUrl.fromLocalFile(d)),
                                          self.etat.setText(f"{len(aenvoyer)} zip(s) dans {d}.")))
        self._lancer(t)

    def _courriels(self):
        from data.database import obtenir_parametre, definir_parametre
        from noyau.photos import courriel as C
        ev_id = self.evenement_id
        if not ev_id:
            return
        cibles = [c for c in self._coureurs if c["nb_diffusables"] and c.get("email")]
        sans = sum(1 for c in self._coureurs if c["nb_diffusables"] and not c.get("email"))
        if not cibles:
            QMessageBox.information(self, "E-mail", "Aucun coureur avec des photos et une adresse e-mail.")
            return
        cfg = {k: obtenir_parametre(f"smtp_{k}") or "" for k in ("hote", "port", "securite", "identifiant", "expediteur",
                                                                    "nom_expediteur")}
        u = self._url_publique()
        spec = [("texte", "hote", "Serveur d'envoi (SMTP)", {"aide": "smtp.gmail.com, smtp.orange.fr…"}),
                ("entier", "port", "Port", {"min": 1, "max": 65535, "defaut": 587}),
                ("choix", "securite", "Sécurité", {"choix": [("starttls", "STARTTLS (port 587)"), ("ssl", "SSL (port 465)"),
                                                             ("aucune", "Aucune")]}),
                ("texte", "identifiant", "Identifiant", None), ("texte", "mot_de_passe", "Mot de passe (gardé dans le trousseau)", None),
                ("texte", "expediteur", "Adresse de l'expéditeur", None), ("texte", "nom_expediteur", "Nom affiché", None),
                ("case", "renvoyer", "", {"texte": "Renvoyer aussi à ceux qui ont déjà reçu"})]
        d = DialogueChamps(self, f"Envoyer les photos à {len(cibles)} coureur(s)", spec,
                           {**cfg, "port": int(cfg["port"] or 587), "securite": cfg["securite"] or "starttls"}, largeur=560)
        d.message.setStyleSheet("")
        d.message.setText(("Chaque coureur reçoit le lien de la page et son code." if u else
                           "Pas d'adresse publique du serveur : les photos sont jointes au message (15 Mo au plus).")
                          + (f" {sans} coureur(s) sans adresse e-mail : donne-leur le zip ou le code." if sans else ""))
        if not d.exec():
            return
        r = d.resultat
        for k in ("hote", "securite", "identifiant", "expediteur", "nom_expediteur"):
            definir_parametre(f"smtp_{k}", r.get(k) or "")
        definir_parametre("smtp_port", str(r.get("port") or 587))
        mdp = r.get("mot_de_passe") or C.mot_de_passe(r.get("identifiant"))
        if r.get("mot_de_passe"):
            try:
                C.garder_mot_de_passe(r.get("identifiant"), r["mot_de_passe"])
            except Exception:
                pass
        if not r.get("expediteur"):
            QMessageBox.warning(self, "E-mail", "Indique l'adresse de l'expéditeur.")
            return
        liste = [c for c in cibles if r.get("renvoyer") or not c["envoye_le"]]
        if not liste:
            QMessageBox.information(self, "E-mail", "Tout le monde a déjà reçu ses photos.")
            return
        dph.generer_codes(ev_id)
        codes = {c["inscription_id"]: c["code"] for c in dph.diffusion(ev_id)["coureurs"]}
        ev = dph.evenement_photos(ev_id)
        etat = {"smtp": None, "ok": 0, "ko": []}

        def envoyer(tr, c):
            if etat["smtp"] is None:
                etat["smtp"] = C.connexion(r, mdp)
            pieces = []
            if not u:
                pieces = [(f"photo_{k:03d}.jpg", dph.image(p["id"], "web"))
                          for k, p in enumerate(dph.photos_du_coureur(c["inscription_id"]), 1)]
            objet, texte = RP.texte_courriel(ev, c, codes.get(c["inscription_id"]), c["nb_diffusables"], u or None, bool(pieces))
            m = C.message(r["expediteur"], r.get("nom_expediteur"), c["email"], objet, texte, pieces)
            try:
                etat["smtp"].send_message(m)
                dph.noter_envoi(c["inscription_id"], "email")
                etat["ok"] += 1
            except Exception as e:
                dph.noter_envoi(c["inscription_id"], "email", False, str(e))
                etat["ko"].append(f"{c['dossard']} : {e}")
            tr.signaux.message.emit("")

        def fini(n):
            try:
                if etat["smtp"]:
                    etat["smtp"].quit()
            except Exception:
                pass
            self._travail_fini(n)
            self.rafraichir()
            QMessageBox.information(self, "E-mail", f"{etat['ok']} message(s) envoyé(s)."
                                    + (f"\n{len(etat['ko'])} échec(s) : " + "; ".join(etat["ko"][:5]) if etat["ko"] else ""))

        t = _Travail("courriels", liste, envoyer)
        t.signaux.message.connect(lambda m: (self._avancer(f"Envoi {self.progres.value() + 1}/{len(liste)}")
                                             if not m else (etat["ko"].append(m), self._avancer())))
        t.signaux.fini.connect(fini)
        self._lancer(t)


class DialoguePhotos(QDialog):
    """Les photos d'une personne (profil du licencié) : vignettes, et enregistrement dans un dossier."""

    def __init__(self, parent, titre, photo_ids):
        super().__init__(parent)
        self.setWindowTitle(f"Photos · {titre}")
        self.resize(900, 640)
        self.ids = list(photo_ids)
        lay = QVBoxLayout(self)
        self.liste = QListWidget()
        self.liste.setViewMode(QListView.ViewMode.IconMode)
        self.liste.setIconSize(QSize(240, 170))
        self.liste.setResizeMode(QListView.ResizeMode.Adjust)
        self.liste.setMovement(QListView.Movement.Static)
        for pid in self.ids:
            try:
                pm = QPixmap.fromImage(QImage.fromData(dph.image(pid, "vignette")))
            except Exception:
                pm = QPixmap(240, 170)
            self.liste.addItem(QListWidgetItem(QIcon(pm), ""))
        lay.addWidget(self.liste)
        b = QHBoxLayout()
        be = _bouton("Enregistrer dans un dossier…", True)
        be.clicked.connect(self._enregistrer)
        bf = _bouton("Fermer")
        bf.clicked.connect(self.accept)
        b.addStretch()
        b.addWidget(be)
        b.addWidget(bf)
        lay.addLayout(b)

    def _enregistrer(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier")
        if not d:
            return
        for k, pid in enumerate(self.ids, 1):
            (Path(d) / f"photo_{k:03d}.jpg").write_bytes(dph.image(pid, "grande"))
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))
