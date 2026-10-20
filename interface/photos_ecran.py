"""
Photos des sorties : visionneuse, bandeau de vignettes pour la fiche
d'une sortie, et écran « Photos » (galerie de toutes les photos, avec
filtres, ajout, import d'un dossier et choix de la taille de réduction).
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImageReader, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QInputDialog, QProgressDialog, QApplication, QScrollArea, QAbstractItemView,
)

from data import photos_sorties as ph
from data.database import connexion, obtenir_athletes
from interface.ecran_liste import obtenir_style_ecran

TAILLE_MINIATURE = 150


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------

def _date_fr(texte):
    try:
        return datetime.fromisoformat(str(texte)[:19]).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(texte or "")


def miniature(fichier, cote=TAILLE_MINIATURE):
    """Vignette carrée (recadrée au centre) de la photo, lue réduite pour rester rapide."""
    lecteur = QImageReader(str(ph.chemin_photo(fichier)))
    lecteur.setAutoTransform(True)
    taille = lecteur.size()
    if taille.isValid():
        taille.scale(cote * 2, cote * 2, Qt.AspectRatioMode.KeepAspectRatio)
        lecteur.setScaledSize(taille)
    image = lecteur.read()
    if image.isNull():
        return QPixmap(cote, cote)
    pm = QPixmap.fromImage(image).scaled(
        cote, cote, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation)
    x = max((pm.width() - cote) // 2, 0)
    y = max((pm.height() - cote) // 2, 0)
    return pm.copy(x, y, cote, cote)


def choisir_sortie(parent, athlete_id, date_photo=None):
    """Demande à quelle sortie rattacher une photo. Retourne (ok, activite_id|None)."""
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT id, date, nom, type FROM activites WHERE athlete_id=? ORDER BY date DESC",
                (athlete_id,))
    lignes = cur.fetchall()
    conn.close()
    if date_photo:
        try:
            ref = datetime.fromisoformat(str(date_photo)[:19])
            proches = sorted(lignes, key=lambda l: abs((datetime.fromisoformat(str(l[1])[:19]) - ref).total_seconds()))
            lignes = proches[:40]
        except ValueError:
            lignes = lignes[:40]
    else:
        lignes = lignes[:40]
    choix = ["(aucune sortie)"] + [f"{str(d)[:16]} — {n or t or 'Sortie'}" for _, d, n, t in lignes]
    texte, ok = QInputDialog.getItem(parent, "Rattacher à une sortie",
                                     "Sortie la plus proche en premier :", choix, 1 if lignes else 0, False)
    if not ok:
        return False, None
    i = choix.index(texte)
    return True, (None if i == 0 else lignes[i - 1][0])


def ouvrir_fiche_sortie(parent, activite_id, athlete_id):
    from interface.detail_sortie import DialogueDetailSortie
    DialogueDetailSortie(activite_id, athlete_id, parent).exec()


# ------------------------------------------------------------------
# Visionneuse
# ------------------------------------------------------------------

from interface.outils_ui import notifier


class DialogueVisionneuse(QDialog):

    def __init__(self, photos, index, athlete_id, parent=None, avec_lien_sortie=True):
        super().__init__(parent)
        self.photos = list(photos)
        self.index = index
        self.athlete_id = athlete_id
        self.modifie = False
        self._avec_lien = avec_lien_sortie
        self.setWindowTitle("Photo")
        self.resize(1000, 780)
        self.setStyleSheet(obtenir_style_ecran())

        lay = QVBoxLayout(self)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(400, 300)
        self.image.setStyleSheet("background: #0B0D10; border-radius: 8px;")
        lay.addWidget(self.image, 1)

        self.infos = QLabel("")
        self.infos.setObjectName("texteSecondaire")
        self.infos.setWordWrap(True)
        lay.addWidget(self.infos)

        ligne = QHBoxLayout()
        self.champ_legende = QLineEdit()
        self.champ_legende.setPlaceholderText("Légende (facultative)")
        self.champ_legende.editingFinished.connect(self._enregistrer_legende)
        ligne.addWidget(self.champ_legende, 1)
        lay.addLayout(ligne)

        barre = QHBoxLayout()
        self.b_prec = QPushButton("◀")
        self.b_suiv = QPushButton("▶")
        for b in (self.b_prec, self.b_suiv):
            b.setObjectName("boutonSecondaire")
            b.setFixedWidth(50)
        self.b_prec.clicked.connect(lambda: self._aller(-1))
        self.b_suiv.clicked.connect(lambda: self._aller(1))
        self.compteur = QLabel("")
        self.compteur.setObjectName("texteSecondaire")
        barre.addWidget(self.b_prec)
        barre.addWidget(self.compteur)
        barre.addWidget(self.b_suiv)
        barre.addStretch()
        self.b_sortie = QPushButton("Ouvrir la sortie")
        self.b_sortie.setObjectName("boutonSecondaire")
        self.b_sortie.clicked.connect(self._ouvrir_sortie)
        b_rattacher = QPushButton("Rattacher à une sortie…")
        b_rattacher.setObjectName("boutonSecondaire")
        b_rattacher.clicked.connect(self._rattacher)
        b_suppr = QPushButton("🗑 Supprimer")
        b_suppr.setObjectName("boutonSecondaire")
        b_suppr.clicked.connect(self._supprimer)
        b_fermer = QPushButton("Fermer")
        b_fermer.setObjectName("boutonSecondaire")
        b_fermer.clicked.connect(self.accept)
        for b in (self.b_sortie, b_rattacher, b_suppr, b_fermer):
            barre.addWidget(b)
        lay.addLayout(barre)

        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self._aller(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self._aller(1))
        self._afficher()

    @property
    def courante(self):
        return self.photos[self.index] if self.photos else None

    def _afficher(self):
        p = self.courante
        if p is None:
            self.accept()
            return
        pm = QPixmap(str(ph.chemin_photo(p["fichier"])))
        self._pixmap = pm
        self._ajuster()
        morceaux = []
        if p.get("date_prise"):
            morceaux.append("📅 " + _date_fr(p["date_prise"]))
        nom = p.get("sortie_nom") or self._nom_sortie(p.get("activite_id"))
        morceaux.append(f"🏃 {nom}" if nom else "Pas de sortie rattachée")
        if p.get("latitude") is not None:
            morceaux.append(f"📍 {p['latitude']:.4f}, {p['longitude']:.4f}")
        if p.get("largeur"):
            morceaux.append(f"{p['largeur']} × {p['hauteur']} px")
        self.infos.setText("   ·   ".join(morceaux))
        self.champ_legende.setText(p.get("legende") or "")
        self.compteur.setText(f"{self.index + 1} / {len(self.photos)}")
        self.b_prec.setEnabled(self.index > 0)
        self.b_suiv.setEnabled(self.index < len(self.photos) - 1)
        self.b_sortie.setVisible(self._avec_lien and bool(p.get("activite_id")))

    @staticmethod
    def _nom_sortie(activite_id):
        if not activite_id:
            return None
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT nom, type, date FROM activites WHERE id=?", (activite_id,))
        l = cur.fetchone()
        conn.close()
        return f"{(l[0] or l[1] or 'Sortie')} ({str(l[2])[:10]})" if l else None

    def _ajuster(self):
        if getattr(self, "_pixmap", None) and not self._pixmap.isNull():
            self.image.setPixmap(self._pixmap.scaled(
                self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.image.setText("Fichier introuvable")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajuster()

    def _aller(self, sens):
        self._enregistrer_legende()
        n = self.index + sens
        if 0 <= n < len(self.photos):
            self.index = n
            self._afficher()

    def _enregistrer_legende(self):
        p = self.courante
        if p is None:
            return
        texte = self.champ_legende.text().strip()
        if texte != (p.get("legende") or ""):
            ph.modifier_photo(p["id"], legende=texte or None)
            p["legende"] = texte or None
            self.modifie = True

    def _ouvrir_sortie(self):
        p = self.courante
        if p and p.get("activite_id"):
            ouvrir_fiche_sortie(self, p["activite_id"], self.athlete_id)

    def _rattacher(self):
        p = self.courante
        ok, activite_id = choisir_sortie(self, self.athlete_id, p.get("date_prise"))
        if ok:
            ph.modifier_photo(p["id"], activite_id=activite_id)
            p["activite_id"] = activite_id
            p["sortie_nom"] = None
            self.modifie = True
            self._afficher()

    def _supprimer(self):
        p = self.courante
        if QMessageBox.question(self, "Supprimer la photo",
                                "Supprimer cette photo de TrailMaster Pro ?\n"
                                "(Ton fichier d'origine n'est pas touché.)") != QMessageBox.StandardButton.Yes:
            return
        ph.supprimer_photo(p["id"])
        self.modifie = True
        del self.photos[self.index]
        self.index = min(self.index, len(self.photos) - 1)
        if not self.photos:
            self.accept()
        else:
            self._afficher()


# ------------------------------------------------------------------
# Liste de vignettes (réutilisée par la fiche et par la galerie)
# ------------------------------------------------------------------

class ListeMiniatures(QListWidget):

    def __init__(self, hauteur_min=0, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(QSize(TAILLE_MINIATURE, TAILLE_MINIATURE))
        self.setGridSize(QSize(TAILLE_MINIATURE + 14, TAILLE_MINIATURE + 40))
        self.setSpacing(4)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setStyleSheet("QListWidget { background: transparent; border: none; } "
                           "QListWidget::item { color: #AEB6BD; } "
                           "QListWidget::item:selected { background: rgba(255,255,255,0.10); border-radius: 8px; }")
        if hauteur_min:
            self.setMinimumHeight(hauteur_min)
        self.photos = []

    def charger(self, photos, avec_sortie=False):
        self.clear()
        self.photos = photos
        for p in photos:
            texte = p.get("legende") or ""
            if avec_sortie:
                sortie = p.get("sortie_nom") or ""
                date = (p.get("date_prise") or p.get("sortie_date") or "")[:10]
                date_fr = "/".join(reversed(date.split("-"))) if date else ""
                texte = "\n".join(t for t in (texte, sortie, date_fr) if t)
            it = QListWidgetItem(QIcon(miniature(p["fichier"])), texte)
            it.setToolTip(texte)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.addItem(it)


# ------------------------------------------------------------------
# Bandeau « Photos » de la fiche d'une sortie
# ------------------------------------------------------------------

class PhotosSortie(QFrame):

    def __init__(self, activite_id, athlete_id, au_changement=None, parent=None):
        super().__init__(parent)
        self.activite_id = activite_id
        self.athlete_id = athlete_id
        self._au_changement = au_changement
        self.setObjectName("carteForm")
        lay = QVBoxLayout(self)
        entete = QHBoxLayout()
        titre = QLabel("📷 Photos")
        titre.setObjectName("titreCarte")
        self.b_ajout = QPushButton("＋ Ajouter des photos…")
        self.b_ajout.setObjectName("boutonSecondaire")
        self.b_ajout.clicked.connect(self._ajouter)
        self.b_diapo = QPushButton("▶ Diaporama")
        self.b_diapo.setObjectName("boutonSecondaire")
        self.b_diapo.clicked.connect(self._diaporama)
        self.b_album = QPushButton("📄 Album PDF")
        self.b_album.setObjectName("boutonSecondaire")
        self.b_album.clicked.connect(self._album_pdf)
        entete.addWidget(titre)
        entete.addStretch()
        entete.addWidget(self.b_diapo)
        entete.addWidget(self.b_album)
        entete.addWidget(self.b_ajout)
        lay.addLayout(entete)
        self.note = QLabel("")
        self.note.setObjectName("texteSecondaire")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.liste = ListeMiniatures()
        self.liste.itemActivated.connect(self._ouvrir)
        self.liste.itemDoubleClicked.connect(self._ouvrir)
        lay.addWidget(self.liste)
        self.photos = []
        self.recharger()

    def recharger(self):
        self.photos = ph.photos_de_sortie(self.activite_id)
        self.liste.charger(self.photos)
        n = len(self.photos)
        lignes = max((n + 5) // 6, 1) if n else 0
        self.liste.setFixedHeight(lignes * (TAILLE_MINIATURE + 46) + 8 if n else 0)
        self.liste.setVisible(n > 0)
        self.b_diapo.setVisible(n > 0)
        self.b_album.setVisible(n > 0)
        self.note.setText(
            "Aucune photo pour cette sortie. Les photos sont réduites à "
            f"{ph.taille_max()} pixels (réglable dans l'écran Photos)."
            if not n else f"{n} photo{'s' if n > 1 else ''} — double-clic pour agrandir. "
            "Celles qui ont une position GPS (ou une heure dans la sortie) apparaissent sur le tracé.")

    def _ouvrir(self, item):
        self.ouvrir_photo(self.liste.row(item))

    def _diaporama(self):
        from interface.album import DialogueDiaporama
        if self.photos:
            DialogueDiaporama(self.activite_id, self.photos, self).exec()

    def _album_pdf(self):
        from interface.album import choisir_et_exporter_album
        choisir_et_exporter_album(self, self.activite_id)

    def ouvrir_photo(self, index):
        if not (0 <= index < len(self.photos)):
            return
        v = DialogueVisionneuse(self.photos, index, self.athlete_id, self, avec_lien_sortie=False)
        v.exec()
        self.recharger()
        if self._au_changement:
            self._au_changement()

    def _ajouter(self):
        fichiers, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des photos", str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)")
        if not fichiers:
            return
        ajoutees, deja, erreurs = 0, 0, 0
        for f in fichiers:
            r = ph.ajouter_photo(f, self.athlete_id, activite_id=self.activite_id)
            if r["erreur"]:
                erreurs += 1
            elif r["doublon"]:
                deja += 1
                if r["activite_id"] != self.activite_id:
                    ph.modifier_photo(r["id"], activite_id=self.activite_id)
            else:
                ajoutees += 1
        self.recharger()
        if self._au_changement:
            self._au_changement()
        if erreurs or deja:
            QMessageBox.information(
                self, "Photos",
                f"{ajoutees} photo(s) ajoutée(s)"
                + (f", {deja} déjà présente(s) (rattachée(s) à cette sortie)" if deja else "")
                + (f", {erreurs} illisible(s) ou non prise(s) en charge (les photos HEIC d'iPhone "
                   "doivent d'abord être converties en JPEG)" if erreurs else "") + ".")


# ------------------------------------------------------------------
# Écran « Photos »
# ------------------------------------------------------------------

class Photos(QMainWindow):

    def __init__(self, athlete_id_initial=None):
        super().__init__()
        self.setWindowTitle("TrailMaster Pro – Photos")
        self.resize(1300, 900)
        self.setMinimumSize(1050, 700)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget()
        scroll.setWidget(central)
        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        t = QLabel("📷  Photos")
        t.setObjectName("titrePage")
        s = QLabel("Les photos de tes sorties, réunies au même endroit. Un double-clic agrandit une photo.")
        s.setObjectName("sousTitrePage")
        principal.addWidget(t)
        principal.addWidget(s)

        barre = QHBoxLayout()
        lab = QLabel("Athlète :")
        lab.setObjectName("labelChamp")
        self.combo_athlete = QComboBox()
        self.combo_athlete.addItem("Sélectionner...", None)
        for a in obtenir_athletes():
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])
        barre.addWidget(lab)
        barre.addWidget(self.combo_athlete)
        barre.addStretch()
        principal.addLayout(barre)

        # Actions
        cadre_actions = QFrame()
        cadre_actions.setObjectName("carteForm")
        la = QHBoxLayout(cadre_actions)
        self.b_ajout = QPushButton("＋ Ajouter des photos…")
        self.b_ajout.setObjectName("boutonPrincipal")
        self.b_ajout.clicked.connect(self._ajouter)
        self.b_dossier = QPushButton("📁 Importer un dossier…")
        self.b_dossier.setObjectName("boutonSecondaire")
        self.b_dossier.clicked.connect(self._importer_dossier)
        la.addWidget(self.b_ajout)
        la.addWidget(self.b_dossier)
        la.addStretch()
        la.addWidget(QLabel("Taille des photos enregistrées :"))
        self.combo_taille = QComboBox()
        for v in ph.TAILLES_DISPONIBLES:
            self.combo_taille.addItem(f"{v} pixels" + (" (léger)" if v == 800 else " (plus net)"), v)
        self.combo_taille.setCurrentIndex(self.combo_taille.findData(ph.taille_max()))
        self.combo_taille.currentIndexChanged.connect(
            lambda: ph.definir_taille_max(self.combo_taille.currentData()))
        la.addWidget(self.combo_taille)
        principal.addWidget(cadre_actions)
        self.note_import = QLabel(
            "Le rattachement à une sortie se fait automatiquement par la date de la photo. "
            "WhatsApp efface la date et la position des photos : l'appli lit alors la date dans "
            "le nom du fichier (IMG-20261019-WA0003). Tes fichiers d'origine ne sont jamais modifiés.")
        self.note_import.setObjectName("texteSecondaire")
        self.note_import.setWordWrap(True)
        principal.addWidget(self.note_import)

        # Filtres
        filtres = QHBoxLayout()
        self.combo_annee = QComboBox()
        self.combo_type = QComboBox()
        self.combo_sans = QComboBox()
        self.combo_sans.addItems(["Toutes les photos", "Sans sortie rattachée"])
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher (légende, nom de sortie)…")
        for w, lbl in ((self.combo_annee, "Année :"), (self.combo_type, "Type :")):
            filtres.addWidget(QLabel(lbl))
            filtres.addWidget(w)
        filtres.addWidget(self.combo_sans)
        filtres.addWidget(self.recherche, 1)
        principal.addLayout(filtres)

        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        principal.addWidget(self.compte)

        self.liste = ListeMiniatures(hauteur_min=520)
        self.liste.itemActivated.connect(self._ouvrir)
        self.liste.itemDoubleClicked.connect(self._ouvrir)
        principal.addWidget(self.liste, 1)

        self.setStyleSheet(obtenir_style_ecran() + "#carteForm QLabel { background: transparent; }")
        if athlete_id_initial is not None:
            i = self.combo_athlete.findData(athlete_id_initial)
            if i >= 0:
                self.combo_athlete.setCurrentIndex(i)
        elif self.combo_athlete.count() == 2:
            self.combo_athlete.setCurrentIndex(1)
        self._remplir_filtres()
        self.combo_athlete.currentIndexChanged.connect(lambda: (self._remplir_filtres(), self.actualiser()))
        for c in (self.combo_annee, self.combo_type, self.combo_sans):
            c.currentIndexChanged.connect(self.actualiser)
        self.recherche.textChanged.connect(self.actualiser)
        self.actualiser()

    @property
    def athlete_id(self):
        return self.combo_athlete.currentData()

    def _remplir_filtres(self):
        bloque = [self.combo_annee.blockSignals(True), self.combo_type.blockSignals(True)]
        courant_a, courant_t = self.combo_annee.currentData(), self.combo_type.currentData()
        self.combo_annee.clear()
        self.combo_type.clear()
        self.combo_annee.addItem("Toutes", None)
        self.combo_type.addItem("Tous", None)
        if self.athlete_id is not None:
            annees, types = ph.options_filtres(self.athlete_id)
            for a in annees:
                self.combo_annee.addItem(a, a)
            for ty in types:
                self.combo_type.addItem(ty, ty)
        for combo, valeur in ((self.combo_annee, courant_a), (self.combo_type, courant_t)):
            i = combo.findData(valeur)
            combo.setCurrentIndex(max(i, 0))
        self.combo_annee.blockSignals(bloque[0])
        self.combo_type.blockSignals(bloque[1])

    def actualiser(self):
        if self.athlete_id is None:
            self.liste.charger([])
            self.compte.setText("Choisis un athlète.")
            return
        photos = ph.photos_galerie(
            self.athlete_id, annee=self.combo_annee.currentData(),
            type_sortie=self.combo_type.currentData(),
            sans_sortie=self.combo_sans.currentIndex() == 1,
            texte=self.recherche.text().strip() or None)
        self.liste.charger(photos, avec_sortie=True)
        n = len(photos)
        self.compte.setText(
            f"{n} photo{'s' if n > 1 else ''}" if n else
            "Aucune photo pour l'instant. Utilise « Ajouter des photos » ou « Importer un dossier ».")

    def _ouvrir(self, item):
        v = DialogueVisionneuse(self.liste.photos, self.liste.row(item), self.athlete_id, self)
        v.exec()
        self._remplir_filtres()
        self.actualiser()

    def _ajouter(self):
        if self.athlete_id is None:
            return
        fichiers, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des photos", str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)")
        if fichiers:
            self._importer(fichiers)

    def _importer_dossier(self):
        if self.athlete_id is None:
            return
        dossier = QFileDialog.getExistingDirectory(self, "Choisir un dossier de photos", str(Path.home()))
        if dossier:
            fichiers = sorted(p for p in Path(dossier).rglob("*")
                              if p.is_file() and p.suffix.lower() in ph.EXTENSIONS)
            if not fichiers:
                QMessageBox.information(self, "Photos", "Aucune photo (jpg, png…) dans ce dossier.")
                return
            self._importer(fichiers)

    def _importer(self, fichiers):
        bilan = {"ajoutees": 0, "rattachees": 0, "sans_sortie": 0, "doublons": 0, "erreurs": 0}
        progression = QProgressDialog("Ajout des photos…", "Annuler", 0, len(fichiers), self)
        progression.setWindowModality(Qt.WindowModality.WindowModal)
        progression.setMinimumDuration(400)
        for i, f in enumerate(fichiers):
            progression.setValue(i)
            if progression.wasCanceled():
                break
            QApplication.processEvents()
            r = ph.ajouter_photo(f, self.athlete_id, source="galerie")
            if r["erreur"]:
                bilan["erreurs"] += 1
            elif r["doublon"]:
                bilan["doublons"] += 1
            else:
                bilan["ajoutees"] += 1
                bilan["rattachees" if r["activite_id"] else "sans_sortie"] += 1
        progression.setValue(len(fichiers))
        self._remplir_filtres()
        self.actualiser()
        texte = [f"{bilan['ajoutees']} photo(s) ajoutée(s) : {bilan['rattachees']} rattachée(s) à une sortie, "
                 f"{bilan['sans_sortie']} sans sortie."]
        if bilan["sans_sortie"]:
            texte.append("Pour les photos sans sortie : ouvre-les et utilise « Rattacher à une sortie… » "
                         "(ou filtre « Sans sortie rattachée »).")
        if bilan["doublons"]:
            texte.append(f"{bilan['doublons']} déjà présente(s), ignorée(s).")
        if bilan["erreurs"]:
            texte.append(f"{bilan['erreurs']} illisible(s) ou non prise(s) en charge "
                         "(les photos HEIC d'iPhone doivent d'abord être converties en JPEG).")
        if bilan["erreurs"] or bilan["sans_sortie"]:
            QMessageBox.information(self, "Photos", "\n".join(texte))
        else:
            notifier(texte[0] if texte else "Photos importées", parent=self)
