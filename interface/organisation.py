"""
Organisation d'un événement (Trail Hub Center, étape 4.4, module
« organisation ») : l'événement et ses épreuves (distance, D+, horaire,
quota, tarifs, plage de dossards), les inscriptions (saisie, import Njuko
ou CSV, adhérents du club) contrôlées selon la réglementation FFA, les
dossards et le retrait des dossards, le tableau de bord.

Fenêtre « 🏁 Organisation » : onze onglets (logistique de l'étape 4.6 dans
interface/organisation_logistique.py, chrono de l'étape 4.5 dans
interface/organisation_chrono.py). Aucune requête SQL ici : tout
passe par noyau/donnees/organisation.py.
"""

import html
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from noyau.donnees import organisation as dor
from noyau.organisation import regles as R
from noyau.club import categories as cat
from interface.conteneur_onglets import ConteneurOnglets
from interface.ecran_liste import configurer_table_redimensionnable, obtenir_style_ecran
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _style_cases, _table

VERT, ORANGE, ROUGE, GRIS = "#2E7D32", "#E65100", "#C62828", "#757575"


def _euros(v):
    t = f"{v or 0:,.2f}".replace(",", " ").replace(".", ",")
    return (t[:-3] if t.endswith(",00") else t) + " €"


def _date(valeur=None, facultative=False):
    """Champ date ; facultatif : (case, champ)."""
    w = QDateEdit(QDate.fromString(str(valeur)[:10], "yyyy-MM-dd") if valeur else QDate.currentDate())
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd/MM/yyyy")
    if not facultative:
        return w
    c = QCheckBox()
    c.setChecked(bool(valeur))
    w.setEnabled(bool(valeur))
    c.toggled.connect(w.setEnabled)
    return c, w


def _ligne(*widgets):
    h = QHBoxLayout()
    for w in widgets:
        h.addWidget(w)
    return h


def _val_date(case, champ):
    return champ.date().toString("yyyy-MM-dd") if case.isChecked() else None


def _montant(valeur=None, vide=False):
    s = QDoubleSpinBox()
    from PySide6.QtCore import QLocale
    s.setLocale(QLocale(QLocale.Language.French, QLocale.Country.France))
    s.setRange(-1 if vide else 0, 10000)
    s.setDecimals(2)
    s.setSuffix(" €")
    if vide:
        s.setSpecialValueText("—")
    s.setValue(valeur if valeur is not None else (-1 if vide else 0))
    return s


def _val_montant(s):
    return None if s.minimum() < 0 and s.value() < 0 else s.value()


def _boutons(d, lay, ok="Enregistrer"):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Save).setText(ok)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)


# ======================================================================
# Base : un sélecteur d'événement au lieu de l'athlète
# ======================================================================

class _EcranOrga(_EcranAthlete):

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()
        self.combo_evenement = QComboBox()
        self.combo_evenement.setMinimumWidth(360)
        self.barre.insertWidget(0, QLabel("Événement :"))
        self.barre.insertWidget(1, self.combo_evenement)

    def _finir(self):
        self._finaliser()
        _style_cases(self)
        self.combo_evenement.currentIndexChanged.connect(self._evenement_change)

    def _remplir_evenements(self, choisir=None):
        actuel = choisir or self.combo_evenement.currentData() or getattr(self._fenetre(), "evenement_id", None)
        self.combo_evenement.blockSignals(True)
        self.combo_evenement.clear()
        evs = dor.evenements()
        for e in evs:
            self.combo_evenement.addItem(f"{e['nom']} · {date.fromisoformat(e['date_debut']).strftime('%d/%m/%Y')} · "
                                         f"{R.LIBELLE_STATUT_EVENEMENT.get(e['statut'], '')}", e["id"])
        if not evs:
            self.combo_evenement.addItem("Pas encore d'événement : crée-le dans l'onglet Événement", None)
        self.combo_evenement.setCurrentIndex(max(0, self.combo_evenement.findData(actuel)))
        self.combo_evenement.blockSignals(False)

    def _evenement_change(self, _i=None):
        f = self._fenetre()
        if f:
            f.choisir(self.combo_evenement.currentData())
        else:
            self.actualiser()

    @property
    def evenement_id(self):
        return self.combo_evenement.currentData()

    def _fenetre(self):
        w = self.parent()
        while w is not None and not isinstance(w, OrganisationFenetre):
            w = w.parent()
        return w

    def actualiser(self, *_):
        self._remplir_evenements()
        self.rafraichir()

    def rafraichir(self):
        pass

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True


# ======================================================================
# Dialogues
# ======================================================================

class DialogueEpreuve(QDialog):

    def __init__(self, parent, evenement_id, epreuve=None):
        super().__init__(parent)
        self.evenement_id, e = evenement_id, epreuve or {}
        self.epreuve_id = e.get("id")
        self.setWindowTitle("Épreuve")
        self.setStyleSheet(obtenir_style_ecran())
        _style_cases(self)
        self.resize(560, 600)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.nom = QLineEdit(e.get("nom") or "")
        self.nom.setPlaceholderText("ex. Trail 25 km, Course enfants, Randonnée")
        self.discipline = QComboBox()
        for c, l in R.DISCIPLINES_EPREUVE:
            self.discipline.addItem(l, c)
        self.discipline.setCurrentIndex(max(0, self.discipline.findData(e.get("discipline") or "trail")))
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0, 400)
        self.distance.setDecimals(1)
        self.distance.setSuffix(" km")
        self.distance.setValue(e.get("distance_km") or 0)
        self.dplus = QSpinBox()
        self.dplus.setRange(0, 30000)
        self.dplus.setSuffix(" m D+")
        self.dplus.setValue(e.get("denivele_m") or 0)
        self.c_date, self.date = _date(e.get("date"), True)
        self.heure = QLineEdit(e.get("heure_depart") or "")
        self.heure.setPlaceholderText("08:30")
        self.quota = QSpinBox()
        self.quota.setRange(0, 100000)
        self.quota.setSpecialValueText("sans limite")
        self.quota.setValue(e.get("quota") or 0)
        self.tarif = _montant(e.get("tarif") or 0)
        self.tarif_lic = _montant(e.get("tarif_licencie"), vide=True)
        self.tarif_tard = _montant(e.get("tarif_tardif"), vide=True)
        self.d0, self.d1 = QSpinBox(), QSpinBox()
        for s, v in ((self.d0, e.get("dossard_debut")), (self.d1, e.get("dossard_fin"))):
            s.setRange(0, 99999)
            s.setSpecialValueText("—")
            s.setValue(v or 0)
        self.cat_min = QComboBox()
        self.cat_min.addItem("selon la réglementation", None)
        for c in cat.CODES[:9]:
            self.cat_min.addItem(f"à partir de {cat.LIBELLE[c]}", c)
        self.cat_min.setCurrentIndex(max(0, self.cat_min.findData(e.get("categorie_min"))))
        self.competitive = QCheckBox("Épreuve chronométrée (contrôle licence ou santé)")
        self.competitive.setChecked(bool(e.get("competitive", 1)))
        self.notes = QLineEdit(e.get("notes") or "")
        self.ke = QLabel("")
        self.ke.setObjectName("texteSecondaire")
        for lib, w in (("Nom", self.nom), ("Discipline", self.discipline), ("Distance", self.distance), ("Dénivelé", self.dplus),
                       ("", self.ke), ("Date (si autre jour)", _ligne(self.c_date, self.date)), ("Départ", self.heure),
                       ("Quota", self.quota), ("Tarif", self.tarif), ("Tarif licencié FFA", self.tarif_lic),
                       ("Tarif tardif", self.tarif_tard), ("Dossards du", _ligne(self.d0, QLabel("au"), self.d1)),
                       ("Âge", self.cat_min), ("", self.competitive), ("Notes", self.notes)):
            f.addRow(lib, w)
        lay.addLayout(f)
        for w in (self.distance, self.dplus):
            w.valueChanged.connect(lambda _v: self._ke())
        self._ke()
        _boutons(self, lay)

    def _ke(self):
        ke = R.km_effort(self.distance.value(), self.dplus.value())
        if not ke:
            self.ke.setText("")
            return
        acces = [cat.LIBELLE[c] for c, m in R.DISTANCE_MAX_ROUTE.items() if ke <= m]
        self.ke.setText(f"{ke:g} km-effort" + (f" · plus de {R.DPLUS_JUNIORS_MIN} m D+ : juniors au minimum"
                                               if self.dplus.value() > R.DPLUS_JUNIORS_MIN else
                                               f" · ouvert dès {acces[0].lower()}" if acces else " · espoirs et plus"))

    def champs(self):
        return {"nom": self.nom.text(), "discipline": self.discipline.currentData(), "distance_km": self.distance.value() or None,
                "denivele_m": self.dplus.value(), "date": _val_date(self.c_date, self.date),
                "heure_depart": self.heure.text().strip() or None, "quota": self.quota.value() or None,
                "tarif": self.tarif.value(), "tarif_licencie": _val_montant(self.tarif_lic),
                "tarif_tardif": _val_montant(self.tarif_tard), "dossard_debut": self.d0.value() or None,
                "dossard_fin": self.d1.value() or None, "categorie_min": self.cat_min.currentData(),
                "competitive": 1 if self.competitive.isChecked() else 0, "notes": self.notes.text().strip() or None}

    def accept(self):
        try:
            dor.enregistrer_epreuve(self.evenement_id, self.champs(), self.epreuve_id)
        except dor.ErreurOrganisation as e:
            QMessageBox.warning(self, "Épreuve", str(e))
            return
        super().accept()


class DialogueInscription(QDialog):

    def __init__(self, parent, evenement_id, inscription=None):
        super().__init__(parent)
        self.evenement_id, i = evenement_id, inscription or {}
        self.inscription_id = i.get("id")
        self._maj = i.get("maj")                         # mode serveur : refus si quelqu'un l'a modifiée entre-temps
        self.ev = dor.evenement(evenement_id)
        self.eps = dor.epreuves(evenement_id)
        self.setWindowTitle("Inscription" if inscription else "Nouvelle inscription")
        self.setStyleSheet(obtenir_style_ecran())
        _style_cases(self)
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        f1, f2 = QFormLayout(), QFormLayout()
        self.epreuve = QComboBox()
        for e in self.eps:
            self.epreuve.addItem(f"{e['nom']} ({e['nb_inscrits']}" + (f"/{e['quota']}" if e["quota"] else "") + ")", e["id"])
        self.epreuve.setCurrentIndex(max(0, self.epreuve.findData(i.get("epreuve_id"))))
        self.nom, self.prenom = QLineEdit(i.get("nom") or ""), QLineEdit(i.get("prenom") or "")
        self.sexe = QComboBox()
        for c, l in ((None, "—"), ("F", "Femme"), ("H", "Homme")):
            self.sexe.addItem(l, c)
        self.sexe.setCurrentIndex(max(0, self.sexe.findData(i.get("sexe"))))
        self.c_naiss, self.naiss = _date(i.get("date_naissance"), True)
        self.naiss.setMaximumDate(QDate.currentDate())
        self.nationalite = QLineEdit(i.get("nationalite") or "")
        self.nationalite.setPlaceholderText("France")
        self.email, self.tel = QLineEdit(i.get("email") or ""), QLineEdit(i.get("telephone") or "")
        self.club = QLineEdit(i.get("club") or "")
        self.urg_nom, self.urg_tel = QLineEdit(i.get("contact_urgence_nom") or ""), QLineEdit(i.get("contact_urgence_tel") or "")
        self.tshirt = QLineEdit(i.get("taille_tshirt") or "")
        for lib, w in (("Épreuve", self.epreuve), ("Nom", self.nom), ("Prénom", self.prenom), ("Sexe", self.sexe),
                       ("Naissance", _ligne(self.c_naiss, self.naiss)), ("Nationalité", self.nationalite),
                       ("E-mail", self.email), ("Téléphone", self.tel), ("Club", self.club), ("À prévenir", self.urg_nom),
                       ("Son téléphone", self.urg_tel), ("Taille t-shirt", self.tshirt)):
            f1.addRow(lib, w)
        self.justif = QComboBox()
        self.justif.addItem("— à fournir —", None)
        for c, l in R.JUSTIFICATIFS:
            self.justif.addItem(l, c)
        self.justif.setCurrentIndex(max(0, self.justif.findData(i.get("justificatif"))))
        self.num_lic = QLineEdit(i.get("numero_licence") or "")
        self.type_lic = QComboBox()
        self.type_lic.addItem("—", None)
        for c, l, _u in cat.TYPES_LICENCE:
            self.type_lic.addItem(l, c)
        self.type_lic.setCurrentIndex(max(0, self.type_lic.findData(i.get("type_licence"))))
        self.federation = QLineEdit(i.get("federation") or "")
        self.c_pps, self.pps = _date(i.get("pps_date"), True)
        self.c_cert, self.cert = _date(i.get("certificat_date"), True)
        self.questionnaire = QCheckBox("Questionnaire de santé et attestation parentale reçus")
        self.questionnaire.setChecked(bool(i.get("questionnaire_mineur")))
        self.autorisation = QCheckBox("Autorisation parentale de participation")
        self.autorisation.setChecked(bool(i.get("autorisation_parentale")))
        self.valide = QCheckBox("Pièce contrôlée par l'organisation")
        self.valide.setChecked(bool(i.get("justificatif_valide")))
        self.statut = QComboBox()
        for c, l in R.STATUTS:
            self.statut.addItem(l, c)
        self.statut.setCurrentIndex(max(0, self.statut.findData(i.get("statut") or "en_attente")))
        self.montant = _montant(i.get("montant"), vide=True)
        self.paye = _montant(i.get("montant_paye") or 0)
        self.mode = QComboBox()
        self.mode.setEditable(True)
        self.mode.addItems(["", "Carte bancaire", "Njuko", "HelloAsso", "Chèque", "Espèces", "Virement", "Gratuit"])
        self.mode.setCurrentText(i.get("paiement_mode") or "")
        self.dossard = QSpinBox()
        self.dossard.setRange(0, 99999)
        self.dossard.setSpecialValueText("—")
        self.dossard.setValue(i.get("dossard") or 0)
        self.notes = QLineEdit(i.get("notes") or "")
        for lib, w in (("Justificatif", self.justif), ("N° de licence", self.num_lic), ("Licence", self.type_lic),
                       ("Autre fédération", self.federation), ("Pass Prévention Santé fait le", _ligne(self.c_pps, self.pps)),
                       ("Certificat médical du", _ligne(self.c_cert, self.cert)), ("", self.questionnaire),
                       ("", self.autorisation), ("", self.valide), ("Statut", self.statut),
                       ("Montant (vide = tarif)", self.montant), ("Payé", self.paye), ("Paiement", self.mode),
                       ("Dossard", self.dossard), ("Notes", self.notes)):
            f2.addRow(lib, w)
        t1, t2 = QLabel("Le participant"), QLabel("Dossier")
        t1.setObjectName("titreCarte")
        t2.setObjectName("titreCarte")
        g.addWidget(t1, 0, 0)
        g.addWidget(t2, 0, 1)
        g.addLayout(f1, 1, 0)
        g.addLayout(f2, 1, 1)
        lay.addLayout(g)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.label)
        _boutons(self, lay)
        for w in (self.epreuve, self.justif, self.type_lic, self.statut, self.sexe):
            w.currentIndexChanged.connect(lambda _i: self._etat())
        for w in (self.num_lic, self.urg_tel, self.nationalite):
            w.textChanged.connect(lambda _t: self._etat())
        for w in (self.c_naiss, self.c_pps, self.c_cert, self.questionnaire, self.autorisation, self.valide):
            w.toggled.connect(lambda _b: self._etat())
        for w in (self.naiss, self.pps, self.cert):
            w.dateChanged.connect(lambda _d: self._etat())
        for w in (self.montant, self.paye):
            w.valueChanged.connect(lambda _v: self._etat())
        self._etat()

    def champs(self):
        e = next((x for x in self.eps if x["id"] == self.epreuve.currentData()), {})
        montant = _val_montant(self.montant)
        if montant is None:
            montant = R.tarif(e, self.justif.currentData() == "licence_ffa", None, self.ev.get("date_tarif_tardif"))
        return {"epreuve_id": self.epreuve.currentData(), "nom": self.nom.text().strip(), "prenom": self.prenom.text().strip(),
                "sexe": self.sexe.currentData(), "date_naissance": _val_date(self.c_naiss, self.naiss),
                "nationalite": self.nationalite.text().strip() or None, "email": self.email.text().strip() or None,
                "telephone": self.tel.text().strip() or None, "club": self.club.text().strip() or None,
                "justificatif": self.justif.currentData(), "numero_licence": self.num_lic.text().strip() or None,
                "type_licence": self.type_lic.currentData(), "federation": self.federation.text().strip() or None,
                "pps_date": _val_date(self.c_pps, self.pps), "certificat_date": _val_date(self.c_cert, self.cert),
                "questionnaire_mineur": 1 if self.questionnaire.isChecked() else 0,
                "autorisation_parentale": 1 if self.autorisation.isChecked() else 0,
                "justificatif_valide": 1 if self.valide.isChecked() else 0,
                "contact_urgence_nom": self.urg_nom.text().strip() or None,
                "contact_urgence_tel": self.urg_tel.text().strip() or None,
                "taille_tshirt": self.tshirt.text().strip() or None, "statut": self.statut.currentData(),
                "montant": montant, "montant_paye": self.paye.value(), "paiement_mode": self.mode.currentText().strip() or None,
                "dossard": self.dossard.value() or None, "notes": self.notes.text().strip() or None}

    def _etat(self):
        e = next((x for x in self.eps if x["id"] == self.epreuve.currentData()), None)
        if not e:
            self.label.setText("Crée d'abord une épreuve.")
            return
        d = R.dossier(self.champs(), e, self.ev)
        c = d["categorie"]
        txt = (f"Catégorie {c['libelle']} ({c['code']}) · " if c else "") + (
            f"<b style='color:{VERT}'>Dossier complet.</b>" if d["complet"] else
            f"<b style='color:{ORANGE}'>Il manque :</b> " + html.escape(", ".join(d["manques"])) + ".")
        if d["avertissements"]:
            txt += "<br><span style='color:#9E9E9E'>À vérifier : " + html.escape(" · ".join(d["avertissements"])) + "</span>"
        self.label.setText(txt)

    def accept(self):
        try:
            dor.enregistrer_inscription(self.champs(), self.inscription_id, getattr(self, "_maj", None))
        except dor.ErreurOrganisation as e:
            QMessageBox.warning(self, "Inscription", str(e))
            return
        super().accept()


# ======================================================================
# Onglet 1 — Événement et épreuves
# ======================================================================

class EvenementOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🏁  Événement et épreuves", "Ton événement : date, lieu, ouverture des inscriptions, règles de "
                         "santé ; ses épreuves avec distance, D+, quota, tarifs et dossards. Publié, il apparaît dans le "
                         "calendrier des courses.", athlete_id_initial)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Nouvel événement", self._nouveau, True), ("💾 Enregistrer", self._enregistrer, True),
                             ("📣 Publier dans le calendrier", self._publier, False), ("🗑 Supprimer", self._supprimer, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        cadre, lc = _cadre("L'événement")
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        f1, f2 = QFormLayout(), QFormLayout()
        self.nom = QLineEdit()
        self.debut = _date()
        self.c_fin, self.fin = _date(None, True)
        self.commune, self.cp, self.lieu = QLineEdit(), QLineEdit(), QLineEdit()
        self.lieu.setPlaceholderText("lieu du départ, parking, salle de retrait des dossards")
        self.site, self.email = QLineEdit(), QLineEdit()
        self.statut = QComboBox()
        for c, l in R.STATUTS_EVENEMENT:
            self.statut.addItem(l, c)
        self.declaration = QLineEdit()
        self.declaration.setPlaceholderText("n° de déclaration au calendrier FFA, label, préfecture")
        self.c_ouv, self.ouv = _date(None, True)
        self.c_clo, self.clo = _date(None, True)
        self.c_tard, self.tard = _date(None, True)
        self.pps = QSpinBox()
        self.pps.setRange(1, 12)
        self.pps.setSuffix(" mois")
        self.autorisation = QCheckBox("Demander une autorisation parentale aux mineurs")
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(80)
        for lib, w in (("Nom", self.nom), ("Date", self.debut), ("Jusqu'au", _ligne(self.c_fin, self.fin)),
                       ("Commune", self.commune), ("Code postal", self.cp), ("Lieu", self.lieu), ("Site", self.site),
                       ("E-mail de contact", self.email)):
            f1.addRow(lib, w)
        for lib, w in (("État", self.statut), ("Déclaration", self.declaration),
                       ("Ouverture des inscriptions", _ligne(self.c_ouv, self.ouv)),
                       ("Clôture", _ligne(self.c_clo, self.clo)), ("Tarif tardif à partir du", _ligne(self.c_tard, self.tard)),
                       ("Pass Prévention Santé valable", self.pps), ("", self.autorisation), ("Description", self.description)):
            f2.addRow(lib, w)
        g.addLayout(f1, 0, 0)
        g.addLayout(f2, 0, 1)
        lc.addLayout(g)
        regle = QLabel("Contrôles d'après la réglementation FFA des manifestations running 2025-2026 : licence Athlé "
                       "Compétition, Running ou Entreprise, ou Pass Prévention Santé (majeurs, 3 mois au plus) ; mineurs "
                       "non licenciés : questionnaire de santé avec les parents ou certificat de moins de six mois ; "
                       "distances maximales par catégorie. Vérifie chaque saison la réglementation en vigueur.")
        regle.setWordWrap(True)
        regle.setObjectName("texteSecondaire")
        lc.addWidget(regle)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Épreuves")
        self.table = _table(["Épreuve", "Discipline", "Distance", "D+", "Km-effort", "Départ", "Inscrits", "Tarifs",
                             "Dossards"], 220)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier_epreuve())
        lc.addWidget(self.table)
        b2 = QHBoxLayout()
        for texte, fn, p in (("➕ Épreuve", self._nouvelle_epreuve, True), ("✏️ Modifier", self._modifier_epreuve, False),
                             ("🗑 Supprimer l'épreuve", self._supprimer_epreuve, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b2.addWidget(w)
        b2.addStretch()
        lc.addLayout(b2)
        self.alerte = QLabel("")
        self.alerte.setWordWrap(True)
        lc.addWidget(self.alerte)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._eps = []
        self._finir()

    def rafraichir(self):
        ev = dor.evenement(self.evenement_id) if self.evenement_id else None
        e = ev or {}
        self.nom.setText(e.get("nom") or "")
        self.debut.setDate(QDate.fromString(e["date_debut"], "yyyy-MM-dd") if e.get("date_debut") else QDate.currentDate())
        for (case, champ), k in (((self.c_fin, self.fin), "date_fin"), ((self.c_ouv, self.ouv), "ouverture_inscriptions"),
                                 ((self.c_clo, self.clo), "cloture_inscriptions"), ((self.c_tard, self.tard), "date_tarif_tardif")):
            case.setChecked(bool(e.get(k)))
            if e.get(k):
                champ.setDate(QDate.fromString(e[k], "yyyy-MM-dd"))
        for w, k in ((self.commune, "commune"), (self.cp, "code_postal"), (self.lieu, "lieu"), (self.site, "site"),
                     (self.email, "contact_email"), (self.declaration, "declaration_ffa")):
            w.setText(e.get(k) or "")
        self.statut.setCurrentIndex(max(0, self.statut.findData(e.get("statut") or "brouillon")))
        self.pps.setValue(e.get("pps_validite_mois") or 3)
        self.autorisation.setChecked(bool(e.get("autorisation_parentale", 1)))
        self.description.setPlainText(e.get("description") or "")
        self._eps = dor.epreuves(self.evenement_id) if ev else []
        t = self.table
        t.setRowCount(len(self._eps))
        for i, x in enumerate(self._eps):
            tarifs = _euros(x["tarif"]) + (f" · licencié {_euros(x['tarif_licencie'])}" if x["tarif_licencie"] is not None
                                           else "") + (f" · tardif {_euros(x['tarif_tardif'])}" if x["tarif_tardif"] is not None
                                                       else "")
            vals = [x["nom"], R.LIBELLE_DISCIPLINE.get(x["discipline"], ""),
                    f"{x['distance_km']:g} km" if x["distance_km"] else "", f"{x['denivele_m']} m" if x["denivele_m"] else "",
                    f"{x['km_effort']:g}" if x["km_effort"] else "", x["heure_depart"] or "",
                    f"{x['nb_inscrits']}" + (f" / {x['quota']}" if x["quota"] else ""), tarifs,
                    f"{x['dossard_debut']} à {x['dossard_fin']}" if x["dossard_debut"] else "—"]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        croise = R.chevauchements(self._eps)
        self.alerte.setText(("⚠️ Plages de dossards qui se chevauchent : " + ", ".join(f"{a} et {b}" for a, b in croise))
                            if croise else ("" if self._eps or not ev else "Ajoute les épreuves de l'événement."))

    def champs(self):
        return {"nom": self.nom.text(), "date_debut": self.debut.date().toString("yyyy-MM-dd"),
                "date_fin": _val_date(self.c_fin, self.fin), "commune": self.commune.text().strip() or None,
                "code_postal": self.cp.text().strip() or None, "lieu": self.lieu.text().strip() or None,
                "site": self.site.text().strip() or None, "contact_email": self.email.text().strip() or None,
                "statut": self.statut.currentData(), "declaration_ffa": self.declaration.text().strip() or None,
                "ouverture_inscriptions": _val_date(self.c_ouv, self.ouv), "cloture_inscriptions": _val_date(self.c_clo, self.clo),
                "date_tarif_tardif": _val_date(self.c_tard, self.tard), "pps_validite_mois": self.pps.value(),
                "autorisation_parentale": 1 if self.autorisation.isChecked() else 0,
                "description": self.description.toPlainText().strip() or None}

    def _nouveau(self):
        d = QDialog(self)
        d.setWindowTitle("Nouvel événement")
        d.setStyleSheet(obtenir_style_ecran())
        f = QFormLayout(d)
        nom, jour, commune = QLineEdit(), _date(), QLineEdit()
        nom.setPlaceholderText("ex. Trail des Dentelles")
        f.addRow("Nom", nom)
        f.addRow("Date", jour)
        f.addRow("Commune", commune)
        lay = QVBoxLayout()
        f.addRow(lay)
        _boutons(d, lay, "Créer")
        if not d.exec():
            return
        try:
            eid = dor.enregistrer_evenement({"nom": nom.text(), "date_debut": jour.date().toString("yyyy-MM-dd"),
                                             "commune": commune.text().strip() or None})
        except dor.ErreurOrganisation as e:
            QMessageBox.warning(self, "Événement", str(e))
            return
        fen = self._fenetre()
        if fen:
            fen.choisir(eid)
        else:
            self._remplir_evenements(eid)
            self.rafraichir()

    def _enregistrer(self):
        if not self.evenement_id:
            return self._nouveau()
        try:
            dor.enregistrer_evenement(self.champs(), self.evenement_id)
        except dor.ErreurOrganisation as e:
            QMessageBox.warning(self, "Événement", str(e))
            return
        self.actualiser()
        QMessageBox.information(self, "Événement", "Événement enregistré.")

    def _publier(self):
        if not self.evenement_id:
            return
        dor.enregistrer_evenement(self.champs(), self.evenement_id)
        r = dor.publier_dans_le_calendrier(self.evenement_id)
        QMessageBox.information(self, "Calendrier", "Événement " + ("ajouté au" if r["ajoutees"] else "mis à jour dans le")
                                + " calendrier des courses (source « Mon organisation »).")

    def _supprimer(self):
        ev = dor.evenement(self.evenement_id) if self.evenement_id else None
        if ev and QMessageBox.question(self, "Supprimer", f"Supprimer « {ev['nom']} », ses épreuves et ses "
                                       f"{ev['nb_inscrits']} inscription(s) ?") == QMessageBox.StandardButton.Yes:
            dor.supprimer_evenement(ev["id"])
            fen = self._fenetre()
            if fen:
                fen.choisir(None)
            else:
                self.actualiser()

    def _courante(self):
        i = self.table.currentRow()
        return self._eps[i] if 0 <= i < len(self._eps) else None

    def _nouvelle_epreuve(self):
        if not self.evenement_id:
            QMessageBox.information(self, "Épreuve", "Crée d'abord l'événement.")
            return
        if DialogueEpreuve(self, self.evenement_id).exec():
            self.rafraichir()

    def _modifier_epreuve(self):
        e = self._courante()
        if e and DialogueEpreuve(self, self.evenement_id, e).exec():
            self.rafraichir()

    def _supprimer_epreuve(self):
        e = self._courante()
        if e:
            try:
                dor.supprimer_epreuve(e["id"])
            except dor.ErreurOrganisation as x:
                QMessageBox.warning(self, "Épreuve", str(x))
            self.rafraichir()


# ======================================================================
# Onglet 2 — Inscriptions
# ======================================================================

class InscriptionsOrga(_EcranOrga):
    COLONNES = ["Dossard", "Nom", "Prénom", "Cat.", "Épreuve", "Club", "Justificatif", "Payé", "Statut", "Dossier"]

    def __init__(self, athlete_id_initial=None):
        super().__init__("📝  Inscriptions", "Les inscrits de chaque épreuve et leur dossier, contrôlé selon la "
                         "réglementation FFA (âge et distance, licence ou Pass Prévention Santé, mineurs, paiement).",
                         athlete_id_initial)
        f = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher (nom, prénom, club, licence, dossard)")
        self.f_epreuve, self.f_statut = QComboBox(), QComboBox()
        self.f_statut.addItem("Tous les statuts (sauf annulées)", None)
        for c, l in R.STATUTS:
            self.f_statut.addItem(l, c)
        self.f_incomplets = QCheckBox("Dossiers incomplets")
        f.addWidget(self.recherche, 2)
        f.addWidget(self.f_epreuve, 1)
        f.addWidget(self.f_statut, 1)
        f.addWidget(self.f_incomplets)
        self.principal.addLayout(f)
        b = QHBoxLayout()
        for texte, fn, p in (("➕ Inscrire", self._nouvelle, True), ("✏️ Fiche", self._modifier, False),
                             ("✅ Valider les dossiers complets", self._valider, False), ("🔁 Statut", self._statut, False),
                             ("💶 Paiement", self._paiement, False), ("🏟️ Inscrire des adhérents", self._adherents, False),
                             ("📥 Importer (Njuko, CSV)", self._importer, False), ("📤 Exporter", self._exporter, False),
                             ("✉️ E-mails des dossiers incomplets", self._relance, False)):
            w = _bouton(texte, p)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch()
        self.principal.addLayout(b)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        self.principal.addWidget(self.compte)
        self.table = _table(self.COLONNES, 480)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._modifier())
        self.principal.addWidget(self.table)
        self.principal.addStretch()
        self._toutes, self._vues = [], []
        self.recherche.textChanged.connect(lambda _t: self._remplir())
        self.f_epreuve.currentIndexChanged.connect(lambda _i: self._remplir())
        self.f_statut.currentIndexChanged.connect(lambda _i: self._remplir())
        self.f_incomplets.toggled.connect(lambda _b: self._remplir())
        self._finir()

    def rafraichir(self):
        g = self.f_epreuve.currentData()
        self.f_epreuve.blockSignals(True)
        self.f_epreuve.clear()
        self.f_epreuve.addItem("Toutes les épreuves", None)
        for e in (dor.epreuves(self.evenement_id) if self.evenement_id else []):
            self.f_epreuve.addItem(e["nom"], e["id"])
        self.f_epreuve.setCurrentIndex(max(0, self.f_epreuve.findData(g)))
        self.f_epreuve.blockSignals(False)
        self._toutes = dor.inscriptions(self.evenement_id) if self.evenement_id else []
        self._remplir()

    def _remplir(self):
        from noyau.club import imports as imp
        q = imp._cle(self.recherche.text())
        ep, st = self.f_epreuve.currentData(), self.f_statut.currentData()
        vues = []
        for i in self._toutes:
            if ep and i["epreuve_id"] != ep:
                continue
            if (st and i["statut"] != st) or (not st and i["statut"] == "annulee"):
                continue
            if self.f_incomplets.isChecked() and i["dossier"]["complet"]:
                continue
            if q and q not in imp._cle(f"{i['nom']} {i['prenom']} {i['prenom']} {i['nom']} {i.get('club') or ''} "
                                       f"{i.get('numero_licence') or ''} {i.get('dossard') or ''}"):
                continue
            vues.append(i)
        self._vues = vues
        t = self.table
        t.setRowCount(len(vues))
        for r, i in enumerate(vues):
            c, d = i["dossier"]["categorie"], i["dossier"]
            vals = [str(i["dossard"] or ""), i["nom"], i.get("prenom") or "", (c["code"] + (i.get("sexe") or "")[:1]) if c else "?",
                    i["epreuve"], i.get("club") or "", R.LIBELLE_JUSTIFICATIF.get(i.get("justificatif"), "à fournir"),
                    f"{_euros(i.get('montant_paye'))} / {_euros(i.get('montant'))}", R.LIBELLE_STATUT[i["statut"]],
                    "✅ complet" if d["complet"] else "⚠️ " + ", ".join(d["manques"])]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 9:
                    it.setForeground(QColor(VERT if d["complet"] else ORANGE))
                    if d["avertissements"]:
                        it.setToolTip("\n".join(d["avertissements"]))
                if j == 8:
                    it.setForeground(QColor({"validee": VERT, "liste_attente": ORANGE, "annulee": GRIS}.get(i["statut"],
                                                                                                         "#BDBDBD")))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        if t.columnWidth(9) > 420:
            t.setColumnWidth(9, 420)
        actifs = [i for i in self._toutes if i["statut"] != "annulee"]
        self.compte.setText(f"{len(vues)} affichée(s) · {len(actifs)} inscription(s), "
                            f"{sum(1 for i in actifs if not i['dossier']['complet'])} dossier(s) incomplet(s)")

    def _selection(self):
        lignes = sorted({x.row() for x in self.table.selectedIndexes()})
        return [self._vues[l] for l in lignes if l < len(self._vues)]

    def _nouvelle(self):
        if not self.evenement_id or not dor.epreuves(self.evenement_id):
            QMessageBox.information(self, "Inscription", "Crée d'abord l'événement et ses épreuves.")
            return
        if DialogueInscription(self, self.evenement_id).exec():
            self.rafraichir()

    def _modifier(self):
        s = self._selection()
        if s and DialogueInscription(self, self.evenement_id, s[0]).exec():
            self.rafraichir()

    def _valider(self):
        if self.evenement_id:
            n = dor.valider_complets(self.evenement_id)
            QMessageBox.information(self, "Valider", f"{n} inscription(s) validée(s). Les dossiers incomplets restent en "
                                    "attente.")
            self.rafraichir()

    def _statut(self):
        s = self._selection()
        if not s:
            return
        d = QDialog(self)
        d.setWindowTitle("Statut")
        d.setStyleSheet(obtenir_style_ecran())
        lay = QVBoxLayout(d)
        combo = QComboBox()
        for c, l in R.STATUTS:
            combo.addItem(l, c)
        lay.addWidget(QLabel(f"Nouveau statut pour {len(s)} inscription(s) :"))
        lay.addWidget(combo)
        _boutons(d, lay, "Changer")
        if d.exec():
            dor.changer_statut([x["id"] for x in s], combo.currentData())
            self.rafraichir()

    def _paiement(self):
        s = self._selection()
        if not s:
            return
        i = s[0]
        d = QDialog(self)
        d.setWindowTitle(f"Paiement — {i.get('prenom') or ''} {i['nom']}")
        d.setStyleSheet(obtenir_style_ecran())
        f = QFormLayout(d)
        m = _montant(max(0, (i.get("montant") or 0) - (i.get("montant_paye") or 0)))
        mode = QComboBox()
        mode.addItems(["Carte bancaire", "Espèces", "Chèque", "Virement", "Njuko", "HelloAsso"])
        f.addRow("Montant reçu", m)
        f.addRow("Mode", mode)
        lay = QVBoxLayout()
        f.addRow(lay)
        _boutons(d, lay, "Enregistrer")
        if d.exec():
            try:
                dor.enregistrer_paiement(i["id"], m.value(), mode.currentText())
            except dor.ErreurOrganisation as e:
                QMessageBox.warning(self, "Paiement", str(e))
            self.rafraichir()

    def _adherents(self):
        eps = dor.epreuves(self.evenement_id) if self.evenement_id else []
        if not eps:
            return
        from noyau.donnees import club as dclub
        ev = dor.evenement(self.evenement_id)
        club = dclub.club_principal()
        adh = [a for a in dclub.adhesions(club["id"], cat.saison_de(ev["date_debut"]))
               if a["statut"] != "annulee"] if club else []
        if not adh:
            QMessageBox.information(self, "Adhérents", "Pas d'adhérent pour la saison de l'événement (module Club).")
            return
        d = QDialog(self)
        d.setWindowTitle("Inscrire des adhérents du club")
        d.setStyleSheet(obtenir_style_ecran())
        d.resize(520, 600)
        lay = QVBoxLayout(d)
        combo = QComboBox()
        for e in eps:
            combo.addItem(e["nom"], e["id"])
        lay.addWidget(QLabel("Épreuve :"))
        lay.addWidget(combo)
        liste = QListWidget()
        for a in adh:
            c = a["categorie"]
            it = QListWidgetItem(f"{a['nom']} {a['prenom']}" + (f" · {c['code']}" if c else "") +
                                 (f" · {a['groupes']}" if a["groupes"] else ""))
            it.setData(Qt.ItemDataRole.UserRole, a["personne_id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            liste.addItem(it)
        lay.addWidget(liste)
        _boutons(d, lay, "Inscrire")
        if not d.exec():
            return
        ids = [liste.item(k).data(Qt.ItemDataRole.UserRole) for k in range(liste.count())
               if liste.item(k).checkState() == Qt.CheckState.Checked]
        r = dor.inscrire_adherents(combo.currentData(), ids)
        QMessageBox.information(self, "Adhérents", f"{r['ajoutees']} adhérent(s) inscrit(s) avec leur licence."
                                + ("\n\n" + "\n".join(r["erreurs"][:10]) if r["erreurs"] else ""))
        self.rafraichir()

    def _importer(self):
        if not self.evenement_id or not dor.epreuves(self.evenement_id):
            QMessageBox.information(self, "Import", "Crée d'abord l'événement et ses épreuves.")
            return
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier des inscrits", "", "Tableaux (*.csv *.txt *.xlsx)")
        if chemin:
            self.importer_fichier(chemin)

    def importer_fichier(self, chemin, confirmer=True):
        try:
            a = dor.analyser_import(Path(chemin).read_bytes(), chemin, self.evenement_id)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import", str(e))
            return None
        ok = sum(1 for l in a["lignes"] if l["epreuve_id"])
        texte = (f"{len(a['lignes'])} inscrit(s) lus, {ok} rattaché(s) à une épreuve.\n\nColonnes reconnues : "
                 + ", ".join(f"{k} ← « {v} »" for k, v in a["colonnes"].items()))
        if a["epreuves_inconnues"]:
            texte += ("\n\nÉpreuves non reconnues : " + ", ".join(a["epreuves_inconnues"]) + " (donne aux épreuves le même "
                      "nom ou la même distance que dans le fichier).")
        if confirmer and QMessageBox.question(self, "Import", texte + "\n\nImporter ?") != QMessageBox.StandardButton.Yes:
            return None
        src = "njuko" if "njuko" in Path(chemin).name.lower() else "import"
        r = dor.importer(a["lignes"], src)
        if confirmer:
            QMessageBox.information(self, "Import", f"{r['ajoutees']} inscription(s) ajoutée(s), {r['deja']} déjà présente(s)."
                                    + ("\n\nÀ revoir :\n" + "\n".join(r["erreurs"][:15]) if r["erreurs"] else ""))
        self.rafraichir()
        return r

    def _exporter(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les inscrits", "Inscriptions.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(dor.export_csv(self._vues, "complet"), encoding="utf-8")
            QMessageBox.information(self, "Export", f"{len(self._vues)} inscription(s) exportée(s) (la liste affichée).")

    def _relance(self):
        emails = sorted({i["email"] for i in self._toutes if i.get("email") and i["statut"] != "annulee"
                         and not i["dossier"]["complet"]})
        QGuiApplication.clipboard().setText("; ".join(emails))
        QMessageBox.information(self, "Relance", f"{len(emails)} adresse(s) copiée(s) : envoie-leur ce qui manque à leur "
                                "dossier (en copie cachée).")


# ======================================================================
# Onglet 3 — Dossards
# ======================================================================

class DossardsOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔢  Dossards", "Les plages de dossards de chaque épreuve, l'attribution aux inscriptions "
                         "validées, le retrait des dossards le jour J et la liste de départ.", athlete_id_initial)
        cadre, lc = _cadre("Plages par épreuve")
        self.table_ep = _table(["Épreuve", "Plage", "Validées", "Avec dossard", "Numéros libres"], 160)
        lc.addWidget(self.table_ep)
        b = QHBoxLayout()
        self.ordre = QComboBox()
        self.ordre.addItem("par ordre alphabétique", "nom")
        self.ordre.addItem("par ordre d'inscription", "inscription")
        att = _bouton("🔢 Attribuer les dossards", True)
        att.clicked.connect(self._attribuer)
        ret = _bouton("↩️ Retirer les numéros (dossards non remis)")
        ret.clicked.connect(self._retirer)
        dep = _bouton("📤 Liste de départ (CSV)")
        dep.clicked.connect(self._liste_depart)
        pdf = _bouton("📄 Feuille de retrait des dossards (PDF)")
        pdf.clicked.connect(self._pdf)
        for w in (self.ordre, att, ret, dep, pdf):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        lc.addWidget(self.label)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Retrait des dossards (coche quand le coureur repart avec son dossard)")
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Nom ou dossard")
        self.recherche.textChanged.connect(lambda _t: self._remplir_retrait())
        lc.addWidget(self.recherche)
        self.table = _table(["Remis", "Dossard", "Nom", "Prénom", "Épreuve", "Taille t-shirt", "Dossier"], 360)
        self.table.cellClicked.connect(self._clic_retrait)
        lc.addWidget(self.table)
        self.compte = QLabel("")
        self.compte.setObjectName("texteSecondaire")
        lc.addWidget(self.compte)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._ins, self._vues = [], []
        self._finir()

    def rafraichir(self):
        eps = dor.epreuves(self.evenement_id) if self.evenement_id else []
        self._ins = [i for i in (dor.inscriptions(self.evenement_id) if self.evenement_id else []) if i["statut"] == "validee"]
        t = self.table_ep
        t.setRowCount(len(eps))
        for r, e in enumerate(eps):
            val = [i for i in self._ins if i["epreuve_id"] == e["id"]]
            avec = sum(1 for i in val if i["dossard"])
            plage = (e["dossard_fin"] - e["dossard_debut"] + 1) if e["dossard_debut"] and e["dossard_fin"] else None
            for j, v in enumerate((e["nom"], f"{e['dossard_debut']} à {e['dossard_fin']}" if plage else "à définir (Événement)",
                                   str(len(val)), str(avec), str(plage - avec) if plage else "—")):
                it = QTableWidgetItem(v)
                if j == 4 and plage and plage - avec < len(val) - avec:
                    it.setForeground(QColor(ROUGE))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        croise = R.chevauchements(eps)
        self.label.setText("⚠️ Plages qui se chevauchent : " + ", ".join(f"{a} et {b}" for a, b in croise) if croise else
                           "Seules les inscriptions validées reçoivent un dossard (onglet Inscriptions, « Valider les "
                           "dossiers complets »).")
        self._remplir_retrait()

    def _remplir_retrait(self):
        q = self.recherche.text().strip().lower()
        self._vues = [i for i in sorted(self._ins, key=lambda x: (x["dossard"] or 10 ** 9, x["nom"].lower()))
                      if not q or q in f"{i['nom']} {i.get('prenom') or ''} {i['dossard'] or ''}".lower()]
        t = self.table
        t.setRowCount(len(self._vues))
        for r, i in enumerate(self._vues):
            for j, v in enumerate(("✅" if i["dossard_retire"] else "☐", str(i["dossard"] or "—"), i["nom"], i.get("prenom") or "",
                                   i["epreuve"], i.get("taille_tshirt") or "",
                                   "complet" if i["dossier"]["complet"] else "⚠️ " + ", ".join(i["dossier"]["manques"]))):
                it = QTableWidgetItem(v)
                if j == 6:
                    it.setForeground(QColor(VERT if i["dossier"]["complet"] else ORANGE))
                t.setItem(r, j, it)
        t.resizeColumnsToContents()
        remis = sum(1 for i in self._ins if i["dossard_retire"])
        self.compte.setText(f"{remis} dossard(s) remis sur {len(self._ins)} inscription(s) validée(s).")

    def _clic_retrait(self, r, c):
        if c != 0 or r >= len(self._vues):
            return
        i = self._vues[r]
        if not i["dossard"]:
            QMessageBox.information(self, "Retrait", "Attribue d'abord les dossards.")
            return
        dor.marquer_retrait(i["id"], not i["dossard_retire"])
        i["dossard_retire"] = 0 if i["dossard_retire"] else 1
        self._remplir_retrait()

    def _attribuer(self):
        if not self.evenement_id:
            return
        try:
            r = dor.attribuer_dossards(self.evenement_id, None, self.ordre.currentData())
        except dor.ErreurOrganisation as e:
            QMessageBox.warning(self, "Dossards", str(e))
            return
        QMessageBox.information(self, "Dossards", f"{r['attribues']} dossard(s) attribué(s)."
                                + (f"\n\nPlus de numéro libre ou pas de plage : {', '.join(r['sans_place'])}." if r["sans_place"]
                                   else ""))
        self.rafraichir()

    def _retirer(self):
        if self.evenement_id and QMessageBox.question(self, "Dossards", "Enlever les numéros des dossards pas encore remis ? "
                                                      "(Pour refaire l'attribution.)") == QMessageBox.StandardButton.Yes:
            n = dor.retirer_dossards(self.evenement_id)
            QMessageBox.information(self, "Dossards", f"{n} numéro(s) retiré(s).")
            self.rafraichir()

    def _liste_depart(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Liste de départ", "Liste de depart.csv", "CSV (*.csv)")
        if chemin:
            Path(chemin).write_text(dor.export_csv(self._ins, "depart"), encoding="utf-8")
            QMessageBox.information(self, "Liste de départ", "Liste exportée : dossard, identité, catégorie, club, épreuve "
                                    "(le format attendu par la plupart des logiciels de chronométrage).")

    def _pdf(self):
        if not self.evenement_id:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Feuille de retrait", "Retrait des dossards.pdf", "PDF (*.pdf)")
        if chemin:
            from interface.club_pdf import rendre_retrait_dossards
            rendre_retrait_dossards(chemin, dor.evenement(self.evenement_id), self._ins)
            QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))


# ======================================================================
# Onglet 4 — Tableau de bord
# ======================================================================

class TableauOrga(_EcranOrga):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📊  Tableau de bord de l'événement", "Inscrits par épreuve et places restantes, dossiers à "
                         "compléter, recettes, catégories et clubs représentés.", athlete_id_initial)
        ligne = QHBoxLayout()
        self.cartes = {}
        for k, t in (("inscrits", "Inscrits"), ("valides", "Validés"), ("incomplets", "Dossiers incomplets"),
                     ("recette", "Encaissé"), ("dossards", "Dossards attribués")):
            self.cartes[k] = self._carte(t)
            ligne.addWidget(self.cartes[k], 1)
        self.principal.addLayout(ligne)
        cadre, lc = _cadre("Par épreuve")
        self.table = _table(["Épreuve", "Inscrits", "Quota", "Places", "Validés", "Liste d'attente", "Incomplets", "Femmes",
                             "Hommes", "Encaissé", "Reste"], 180)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre)
        l2 = QHBoxLayout()
        cadre, lc = _cadre("Par catégorie")
        self.table_cat = _table(["Catégorie", "Inscrits"], 220)
        lc.addWidget(self.table_cat)
        l2.addWidget(cadre, 1)
        cadre, lc = _cadre("Clubs représentés")
        self.table_clubs = _table(["Club", "Inscrits"], 220)
        lc.addWidget(self.table_clubs)
        l2.addWidget(cadre, 1)
        self.principal.addLayout(l2)
        cadre, lc = _cadre("Logistique")
        self.logistique = QLabel("")
        self.logistique.setWordWrap(True)
        self.logistique.setTextFormat(Qt.TextFormat.RichText)
        lc.addWidget(self.logistique)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finir()

    def _logistique(self):
        from noyau.donnees import logistique as dl
        t = dl.tableau(self.evenement_id)
        d, b, p = t["demarches"], t["budget"], t["partenaires"]
        retard = "".join(f"<br>&nbsp;&nbsp;⚠️ {html.escape(x['titre'])} ({x['jalon']})" for x in t["en_retard"][:6])
        prochaines = "".join(f"<br>&nbsp;&nbsp;• {html.escape(x['titre'])} : {date.fromisoformat(x['echeance']).strftime('%d/%m')}"
                             for x in t["prochaines"][:3])
        seuil = "—" if b["seuil"] is None else f"{b['seuil']} coureurs"
        self.logistique.setText(
            f"<b>Démarches</b> : {d['faites']} faites sur {d['total']}, "
            f"<span style='color:{ROUGE if d['en_retard'] else VERT}'>{d['en_retard']} en retard</span>, "
            f"{d['bientot']} dans les 15 jours.{retard}{prochaines}<br>"
            f"<b>Bénévoles</b> : {t['benevoles']} ; places pourvues {t['pourvus']} sur {t['besoin']}"
            f"{' ; ' + str(len(t['manques'])) + ' poste(s) à compléter' if t['manques'] else ''}"
            f"{' ; ' + str(len(t['conflits']) + len(t['alertes'])) + ' point(s) à vérifier' if t['conflits'] or t['alertes'] else ''}.<br>"
            f"<b>Ravitaillements</b> : {t['ravitaillements']} · <b>Matériel</b> : {t['materiel']['articles']} articles, "
            f"{t['materiel']['manquants']} où il en manque.<br>"
            f"<b>Partenaires</b> : {p['accords']} accord(s) sur {p['total']}, {_euros(p['montant'])}"
            f"{' ; ' + str(p['a_relancer']) + ' à relancer' if p['a_relancer'] else ''}.<br>"
            f"<b>Budget</b> : solde prévu {_euros(b['solde_prevu'])}, seuil de rentabilité {seuil}.<br>"
            f"<b>Secours du public</b> : {html.escape(t['dps']['texte'])}")

    def rafraichir(self):
        if self.evenement_id:
            self._logistique()
        else:
            self.logistique.setText("")
        if not self.evenement_id:
            for c in self.cartes.values():
                c.valeur.setText("—")
            self.table.setRowCount(0)
            return
        ch = dor.chiffres(self.evenement_id)
        t = ch["total"]
        c = self.cartes
        c["inscrits"].valeur.setText(str(t["inscrits"]))
        c["inscrits"].detail.setText(f"{t['femmes']} femmes, {t['hommes']} hommes")
        c["valides"].valeur.setText(str(t["valides"]))
        c["valides"].detail.setText(f"{t['attente']} en liste d'attente")
        c["incomplets"].valeur.setText(str(t["incomplets"]))
        c["incomplets"].detail.setText("licence, santé, âge, autorisation, paiement")
        c["recette"].valeur.setText(_euros(t["recette"]))
        c["recette"].detail.setText(f"reste {_euros(t['reste'])} à encaisser")
        c["dossards"].valeur.setText(str(t["dossards"]))
        c["dossards"].detail.setText(f"sur {t['valides']} validé(s)")
        tb = self.table
        tb.setRowCount(len(ch["epreuves"]))
        for r, p in enumerate(ch["epreuves"]):
            for j, v in enumerate((p["epreuve"], str(p["inscrits"]), str(p["quota"] or "—"),
                                   str(p["places"]) if p["places"] is not None else "—", str(p["valides"]), str(p["attente"]),
                                   str(p["incomplets"]), str(p["femmes"]), str(p["hommes"]), _euros(p["recette"]),
                                   _euros(p["reste"]))):
                it = QTableWidgetItem(v)
                if j == 3 and p["places"] is not None and p["places"] <= 0:
                    it.setForeground(QColor(ROUGE))
                tb.setItem(r, j, it)
        tb.resizeColumnsToContents()
        for table, donnees in ((self.table_cat, [(cat.LIBELLE.get(k, "Inconnue"), n) for k, n in ch["categories"].items()]),
                               (self.table_clubs, list(ch["clubs"].items())[:25])):
            table.setRowCount(len(donnees))
            for r, (k, n) in enumerate(donnees):
                table.setItem(r, 0, QTableWidgetItem(k))
                table.setItem(r, 1, QTableWidgetItem(str(n)))
            table.resizeColumnsToContents()


class OrganisationFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        from interface.organisation_chrono import ChronoOrga, ClassementsOrga      # étape 4.5
        from interface.organisation_logistique import (                            # étape 4.6
            DemarchesOrga, BenevolesOrga, RavitosOrga, MaterielOrga, PartenairesOrga)
        from interface.organisation_commandement import CommandementOrga                # étape 6
        self.evenement_id = None
        super().__init__(titre="Organisation",
                         onglets=[("🏁 Événement", EvenementOrga), ("📋 Démarches", DemarchesOrga),
                                  ("📝 Inscriptions", InscriptionsOrga), ("🙋 Bénévoles", BenevolesOrga),
                                  ("🍌 Ravitaillements", RavitosOrga), ("📦 Matériel", MaterielOrga),
                                  ("🤝 Partenaires et budget", PartenairesOrga), ("🔢 Dossards", DossardsOrga),
                                  ("🧭 Jour de course", CommandementOrga), ("⏱️ Chrono", ChronoOrga),
                                  ("🏆 Classements", ClassementsOrga), ("📊 Tableau de bord", TableauOrga)],
                         athlete_id_initial=athlete_id_initial)
        (self.evenement_ecran, self.demarches, self.inscriptions, self.benevoles, self.ravitaillements, self.materiel,
         self.partenaires, self.dossards, self.commandement, self.chrono, self.classements, self.tableau) = self.ecrans
        self.evenement_id = self.evenement_ecran.evenement_id

    def choisir(self, evenement_id):
        self.evenement_id = evenement_id
        for e in self.ecrans:
            e._remplir_evenements(evenement_id)
            e.rafraichir()

