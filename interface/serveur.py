"""
Fenêtre « 🖧 Serveur et comptes » (étape 5) :
  - Ce poste est le serveur : démarrer le serveur sur cet ordinateur (ou voir
    comment l'installer sur le NAS), adresses pour les téléphones, empreinte ;
  - Comptes et rôles : créer un compte, donner un rôle pour une association
    ou un événement, mot de passe provisoire, désactiver ;
  - Journal des accès ;
  - Consentements (accord parental, droit à l'image, géolocalisation) ;
  - Se connecter à un serveur : brancher Club et Organisation sur le NAS.
Aucune requête SQL ici : noyau/donnees/comptes.py et noyau/serveur/.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QTableWidgetItem,
)

from noyau.donnees import comptes as dco, club as dclub, organisation as dor, personnes as dper
from noyau.serveur import droits as D, serveur as S, demarrage as DM
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie

VERT, ORANGE, ROUGE, GRIS = "#2E7D32", "#E65100", "#C62828", "#757575"


class _EcranServeur(_EcranAthlete):

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()
        self.etat_label = QLabel("")
        self.etat_label.setWordWrap(True)
        self.etat_label.setTextFormat(Qt.TextFormat.RichText)
        self.barre.insertWidget(0, self.etat_label, 1)

    def _finir(self):
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        e = DM.etat
        if e["mode"] == "serveur":
            t = f"<span style='color:{VERT}'>● Branché sur le serveur</span> : {e['message']}"
        elif S.actif():
            t = f"<span style='color:{VERT}'>● Ce poste est le serveur</span> ({', '.join(S.infos()['adresses'])})"
        elif e["mode"] == "erreur":
            t = f"<span style='color:{ORANGE}'>● {e['message']}</span>"
        else:
            t = "<span style='color:#888'>● Local</span> : tout est sur cet ordinateur."
        self.etat_label.setText(t)
        self.rafraichir()

    def rafraichir(self):
        pass

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True


# ======================================================================
# Ce poste est le serveur
# ======================================================================

class ServeurLocal(_EcranServeur):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🖧  Serveur", "Une seule base pour le bureau, les entraîneurs et les bénévoles. Le mieux : "
                         "le serveur sur le NAS (toujours allumé, voir « Installer sur le NAS »). Pour un essai ou le "
                         "jour d'une course, cet ordinateur peut aussi servir de serveur.", athlete_id_initial)
        cadre, lc = _cadre("Démarrer le serveur sur cet ordinateur")
        f = QFormLayout()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(S.PORT_DEFAUT)
        self.https = QCheckBox("HTTPS (conseillé : les mots de passe ne passent jamais en clair)")
        self.https.setChecked(True)
        f.addRow("Port", self.port)
        f.addRow("", self.https)
        lc.addLayout(f)
        b = QHBoxLayout()
        self.b_demarrer = _bouton("▶️ Démarrer le serveur", True)
        self.b_demarrer.clicked.connect(self._demarrer)
        self.b_arreter = _bouton("⏹️ Arrêter")
        self.b_arreter.clicked.connect(self._arreter)
        copier = _bouton("📋 Copier l'adresse des téléphones")
        copier.clicked.connect(self._copier)
        for w in (self.b_demarrer, self.b_arreter, copier):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.infos = QLabel("")
        self.infos.setWordWrap(True)
        self.infos.setTextFormat(Qt.TextFormat.RichText)
        self.infos.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lc.addWidget(self.infos)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Premier compte administrateur")
        self.aide_admin = QLabel("")
        self.aide_admin.setWordWrap(True)
        lc.addWidget(self.aide_admin)
        f = QFormLayout()
        self.ident = QLineEdit()
        self.ident.setPlaceholderText("ex. didier")
        self.mdp, self.mdp2 = QLineEdit(), QLineEdit()
        for w in (self.mdp, self.mdp2):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("Identifiant", self.ident)
        f.addRow("Mot de passe", self.mdp)
        f.addRow("Encore une fois", self.mdp2)
        lc.addLayout(f)
        self.b_admin = _bouton("👤 Créer l'administrateur")
        self.b_admin.clicked.connect(self._creer_admin)
        lc.addWidget(self.b_admin)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Installer sur le NAS")
        t = QLabel("Sur le PC Dell sous OpenMediaVault : Python 3 et la bibliothèque cryptography suffisent (pas de "
                   "fenêtre). Le fichier packaging/serveur/LISEZ-MOI.md donne les commandes : copier le logiciel, créer "
                   "l'administrateur avec « trailhub_serveur.py --creer-admin », puis le service qui démarre tout seul. "
                   "Pour reprendre la base actuelle du club, copie ton fichier .db sur le NAS avant de démarrer. "
                   "Le serveur n'écoute que le réseau local : n'ouvre aucun port sur la box (l'accès depuis l'extérieur "
                   "viendra par un tunnel sécurisé).")
        t.setWordWrap(True)
        lc.addWidget(t)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finir()

    def rafraichir(self):
        actif = S.actif()
        self.b_demarrer.setEnabled(not actif and DM.etat["mode"] != "serveur")
        self.b_arreter.setEnabled(actif)
        if actif:
            i = S.infos()
            self.infos.setText("<b>Téléphones</b> (bénévoles, entraîneurs) : " + " · ".join(f"<code>{u}/m/</code>" for u in i["adresses"])
                               + "<br><b>Logiciel de bureau</b> : " + " · ".join(f"<code>{u}</code>" for u in i["adresses"])
                               + (f"<br>Empreinte du certificat : <code>{i['empreinte']}</code>" if i["empreinte"] else "")
                               + "<br>Laisse cet ordinateur allumé et le logiciel ouvert tant que d'autres travaillent.")
        elif DM.etat["mode"] == "serveur":
            self.infos.setText("Ce poste est branché sur un autre serveur : il ne peut pas en être un en même temps.")
        else:
            self.infos.setText("Serveur arrêté.")
        a = dco.a_un_admin()
        self.aide_admin.setText("Il y a déjà un administrateur : les autres comptes se créent dans l'onglet Comptes." if a else
                                "Avant de démarrer : crée ton compte administrateur (il gère les comptes et les rôles).")
        for w in (self.ident, self.mdp, self.mdp2, self.b_admin):
            w.setEnabled(not a and DM.etat["mode"] != "serveur")

    def _creer_admin(self):
        if self.mdp.text() != self.mdp2.text():
            QMessageBox.warning(self, "Administrateur", "Les deux mots de passe sont différents.")
            return
        try:
            cid, _p = dco.creer_compte(self.ident.text(), self.ident.text(), mot_de_passe=self.mdp.text())
            dco.ajouter_role(cid, "admin")
        except dco.ErreurCompte as e:
            QMessageBox.warning(self, "Administrateur", str(e))
            return
        self.mdp.clear()
        self.mdp2.clear()
        QMessageBox.information(self, "Administrateur", "Compte administrateur créé.")
        self.actualiser()

    def _demarrer(self):
        if not dco.a_un_admin():
            QMessageBox.information(self, "Serveur", "Crée d'abord le compte administrateur.")
            return
        try:
            S.demarrer(self.port.value(), self.https.isChecked())
        except OSError as e:
            QMessageBox.warning(self, "Serveur", f"Le serveur n'a pas pu démarrer ({e}). Le port est peut-être déjà pris.")
            return
        self.actualiser()

    def _arreter(self):
        S.arreter()
        self.actualiser()

    def _copier(self):
        if S.actif():
            QGuiApplication.clipboard().setText(S.infos()["adresses"][0] + "/m/")


# ======================================================================
# Comptes et rôles
# ======================================================================

class ComptesServeur(_EcranServeur):

    def __init__(self, athlete_id_initial=None):
        super().__init__("👥  Comptes et rôles", "Un compte par personne. Chaque rôle vaut pour une association "
                         "(bureau, entraîneur, coureur, parent) ou un événement (organisateur, bénévole) : la personne "
                         "ne voit que ça. Le mot de passe provisoire se change à la première connexion.",
                         athlete_id_initial)
        cadre, lc = _cadre("Comptes")
        self.table = _table(["Identifiant", "Nom", "Fiche Personne", "Rôles", "Actif", "Dernière connexion"], 300)
        self.table.itemSelectionChanged.connect(self._roles)
        lc.addWidget(self.table)
        b = QHBoxLayout()
        for t, f, p in (("➕ Compte", self._ajouter, True), ("✏️ Modifier", self._modifier, False),
                        ("🔑 Mot de passe provisoire", self._reinitialiser, False),
                        ("⏸️ Activer / désactiver", self._basculer, False), ("🗑️ Supprimer", self._supprimer, False)):
            w = _bouton(t, p)
            w.clicked.connect(f)
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        cadre, lc = _cadre("Rôles du compte choisi")
        self.table_roles = _table(["Rôle", "Pour", "Ce qu'il permet"], 180)
        lc.addWidget(self.table_roles)
        b = QHBoxLayout()
        aj = _bouton("➕ Donner un rôle", True)
        aj.clicked.connect(self._ajouter_role)
        re = _bouton("Retirer le rôle")
        re.clicked.connect(self._retirer_role)
        b.addWidget(aj)
        b.addWidget(re)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._comptes, self._roles_vus = [], []
        self._finir()

    def rafraichir(self):
        try:
            self._comptes = dco.comptes()
        except Exception as e:                    # branché sur un serveur sans être administrateur
            self._comptes = []
            self.table.setRowCount(0)
            self.table_roles.setRowCount(0)
            self.etat_label.setText(self.etat_label.text() + f"<br><span style='color:{ORANGE}'>{e}</span>")
            return
        pers = {}
        lignes, coul = [], {}
        for r, c in enumerate(self._comptes):
            if c["personne_id"] and c["personne_id"] not in pers:
                f = dper.fiche(c["personne_id"]) or {}
                pers[c["personne_id"]] = f"{f.get('prenom') or ''} {f.get('nom') or ''}".strip()
            if not c["actif"]:
                coul[r] = GRIS
            lignes.append((c["identifiant"], c["nom_affiche"] or "", pers.get(c["personne_id"], ""),
                           ", ".join(D.LIBELLE_ROLE.get(x["role"], x["role"]).split(" (")[0] + (f" · {x['club'] or x['evenement']}"
                                                                                                 if x["club"] or x["evenement"] else "")
                                     for x in c["roles"]),
                           "oui" if c["actif"] else "non",
                           (c["derniere_connexion"] or "").replace("T", " ")[:16]))
        _remplir(self.table, lignes, coul)
        self._roles()

    def _roles(self):
        c = _ligne_choisie(self.table, self._comptes)
        self._roles_vus = c["roles"] if c else []
        _remplir(self.table_roles, [(D.LIBELLE_ROLE.get(x["role"], x["role"]), x["club"] or x["evenement"] or "tout",
                                     self._permet(x["role"])) for x in self._roles_vus])

    @staticmethod
    def _permet(role):
        d = D.DROITS.get(role)
        if d == "*":
            return "tout"
        txt = ", ".join(f"{k}{' (lecture)' if v == 'r' else ''}" for k, v in (d or {}).items())
        pages = ", ".join(sorted(D.PAGES.get(role, set())))
        return (txt + " · " if txt else "") + (f"pages téléphone : {pages}" if pages else "")

    def _spec(self):
        p = [(None, "—")] + [(x["id"], f"{x['nom']} {x['prenom'] or ''}".strip()) for x in dper.lister()]
        return [("texte", "identifiant", "Identifiant", {"aide": "prenom.nom"}), ("texte", "nom_affiche", "Nom affiché", None),
                ("choix", "personne_id", "Fiche Personne", {"choix": p})]

    def _ajouter(self):
        d = DialogueChamps(self, "Nouveau compte", self._spec(), {},
                           lambda c: dco.creer_compte(c["identifiant"], c["nom_affiche"], c["personne_id"]))
        if d.exec():
            _cid, prov = d.resultat
            self._montrer_mdp(d.champs()["identifiant"] or "", prov)
            self.rafraichir()

    def _montrer_mdp(self, ident, mdp):
        QGuiApplication.clipboard().setText(mdp)
        QMessageBox.information(self, "Mot de passe provisoire", f"Compte « {ident} » : mot de passe provisoire\n\n{mdp}\n\n"
                                "(copié). Donne-le à la personne de vive voix ou par SMS : elle le changera à sa première "
                                "connexion. Il ne sera plus affiché.")

    def _modifier(self):
        c = _ligne_choisie(self.table, self._comptes)
        if c:
            spec = [x for x in self._spec() if x[1] != "identifiant"]
            d = DialogueChamps(self, f"Compte {c['identifiant']}", spec, c, lambda v: dco.modifier_compte(c["id"], v))
            if d.exec():
                self.rafraichir()

    def _reinitialiser(self):
        c = _ligne_choisie(self.table, self._comptes)
        if c and QMessageBox.question(self, "Mot de passe", f"Nouveau mot de passe provisoire pour « {c['identifiant']} » ? "
                                      "Ses connexions en cours sont fermées.") == QMessageBox.StandardButton.Yes:
            self._montrer_mdp(c["identifiant"], dco.reinitialiser_mot_de_passe(c["id"]))

    def _basculer(self):
        c = _ligne_choisie(self.table, self._comptes)
        if c:
            dco.modifier_compte(c["id"], {"actif": not c["actif"]})
            self.rafraichir()

    def _supprimer(self):
        c = _ligne_choisie(self.table, self._comptes)
        if c and QMessageBox.question(self, "Compte", f"Supprimer le compte « {c['identifiant']} » ? Le journal garde "
                                      "ses actions.") == QMessageBox.StandardButton.Yes:
            try:
                dco.supprimer_compte(c["id"])
            except dco.ErreurCompte as e:
                QMessageBox.warning(self, "Compte", str(e))
            self.rafraichir()

    def _ajouter_role(self):
        c = _ligne_choisie(self.table, self._comptes)
        if not c:
            QMessageBox.information(self, "Rôle", "Choisis d'abord un compte.")
            return
        clubs = [(None, "—")] + [(x["id"], x["nom"]) for x in dclub.clubs()]
        evs = [(None, "—")] + [(x["id"], f"{x['nom']} ({x['date_debut'][:10]})") for x in dor.evenements()]
        spec = [("choix", "role", "Rôle", {"choix": D.ROLES}),
                ("choix", "club_id", "Association (bureau, entraîneur, coureur, parent)", {"choix": clubs}),
                ("choix", "evenement_id", "Événement (organisateur, bénévole)", {"choix": evs})]
        d = DialogueChamps(self, f"Rôle de {c['identifiant']}", spec, {"role": "benevole"},
                           lambda v: dco.ajouter_role(c["id"], v["role"], v["club_id"], v["evenement_id"]))
        if d.exec():
            self.rafraichir()

    def _retirer_role(self):
        r = _ligne_choisie(self.table_roles, self._roles_vus)
        if r:
            try:
                dco.retirer_role(r["id"])
            except dco.ErreurCompte as e:
                QMessageBox.warning(self, "Rôle", str(e))
            self.rafraichir()


# ======================================================================
# Journal des accès
# ======================================================================

class JournalServeur(_EcranServeur):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📜  Journal des accès", "Connexions, écritures et refus, gardés un an : qui a fait quoi, "
                         "quand et depuis quelle adresse.", athlete_id_initial)
        h = QHBoxLayout()
        self.refus = QCheckBox("Seulement les refus et les échecs")
        self.refus.toggled.connect(lambda _b: self.rafraichir())
        h.addWidget(self.refus)
        h.addStretch()
        self.principal.addLayout(h)
        self.table = _table(["Quand", "Compte", "Action", "Objet", "Détail", "Adresse"], 520)
        self.principal.addWidget(self.table)
        self._finir()

    def rafraichir(self):
        try:
            j = dco.journal(800, seulement_refus=self.refus.isChecked())
        except Exception:
            j = []
        coul = {r: ROUGE for r, l in enumerate(j) if not l["reussi"]}
        _remplir(self.table, [(l["horodatage"].replace("T", " ")[:19], l["identifiant"] or "", l["action"], l["objet"] or "",
                               (l["detail"] or "")[:120], l["adresse"] or "") for l in j], coul)


# ======================================================================
# Consentements
# ======================================================================

class ConsentementsServeur(_EcranServeur):

    def __init__(self, athlete_id_initial=None):
        super().__init__("✍️  Consentements", "Accord parental des mineurs, droit à l'image, géolocalisation : qui a dit "
                         "oui ou non, quand, et pour qui (un parent pour son enfant). Un retrait est gardé avec sa date.",
                         athlete_id_initial)
        self.table = _table(["Personne", "Consentement", "Réponse", "Par", "Date", "Retiré le", "Notes"], 420)
        self.principal.addWidget(self.table)
        b = QHBoxLayout()
        aj = _bouton("➕ Enregistrer un consentement", True)
        aj.clicked.connect(self._ajouter)
        re = _bouton("Retirer")
        re.clicked.connect(self._retirer)
        b.addWidget(aj)
        b.addWidget(re)
        b.addStretch()
        self.principal.addLayout(b)
        self._c = []
        self._finir()

    def rafraichir(self):
        try:
            cid = dclub.club_courant_id()
            self._c = dco.consentements(club_id=cid)
        except Exception:
            self._c = []
        coul = {r: GRIS for r, c in enumerate(self._c) if c["retire_le"]}
        for r, c in enumerate(self._c):
            if not c["donne"]:
                coul[(r, 2)] = ROUGE
        _remplir(self.table, [(f"{c['nom']} {c['prenom'] or ''}", dco.LIBELLE_CONSENTEMENT.get(c["type"], c["type"]),
                               "oui" if c["donne"] else "non", c["donne_par_nom"] or "", c["date"], c["retire_le"] or "",
                               c["notes"] or "") for c in self._c], coul)

    def _ajouter(self):
        p = [(x["id"], f"{x['nom']} {x['prenom'] or ''}".strip()) for x in dper.lister()]
        spec = [("choix", "personne_id", "Personne", {"choix": p}), ("choix", "type", "Consentement", {"choix": dco.TYPES_CONSENTEMENT}),
                ("case", "donne", "Réponse", {"texte": "oui, accepté"}), ("texte", "donne_par_nom", "Donné par (parent…)", None),
                ("date", "date", "Date", None), ("texte", "preuve", "Preuve (formulaire signé, e-mail…)", None),
                ("long", "notes", "Notes", None)]
        d = DialogueChamps(self, "Consentement", spec, {"donne": True, "date": __import__("datetime").date.today().isoformat()},
                           lambda v: dco.enregistrer_consentement(v["personne_id"], v["type"], v["donne"], None,
                                                                  v["donne_par_nom"], v["date"], dclub.club_courant_id(),
                                                                  v["preuve"], v["notes"]))
        if d.exec():
            self.rafraichir()

    def _retirer(self):
        c = _ligne_choisie(self.table, self._c)
        if c and not c["retire_le"]:
            dco.retirer_consentement(c["id"])
            self.rafraichir()


# ======================================================================
# Se connecter à un serveur
# ======================================================================

class ConnexionServeur(_EcranServeur):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔌  Se connecter à un serveur", "Branche les espaces Club et Organisation de ce logiciel sur le "
                         "serveur du club (le NAS). Ton espace Coureur reste sur ton ordinateur. Le basculement se fait au "
                         "prochain démarrage du logiciel.", athlete_id_initial)
        cadre, lc = _cadre("Serveur")
        f = QFormLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://192.168.1.20:8770")
        self.ident = QLineEdit()
        self.mdp = QLineEdit()
        self.mdp.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("Adresse", self.url)
        f.addRow("Identifiant", self.ident)
        f.addRow("Mot de passe", self.mdp)
        lc.addLayout(f)
        b = QHBoxLayout()
        co = _bouton("🔌 Se connecter", True)
        co.clicked.connect(self._connecter)
        oub = _bouton("Revenir en local")
        oub.clicked.connect(self._oublier)
        cp = _bouton("💾 Copie de la base du serveur (page Claude)")
        cp.clicked.connect(self._copie)
        b.addWidget(co)
        b.addWidget(oub)
        b.addWidget(cp)
        b.addStretch()
        lc.addLayout(b)
        self.retour = QLabel("")
        self.retour.setWordWrap(True)
        self.retour.setTextFormat(Qt.TextFormat.RichText)
        self.retour.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lc.addWidget(self.retour)
        self.principal.addWidget(cadre)
        self.principal.addStretch()
        self._finir()

    def rafraichir(self):
        c = DM.configuration()
        if c["url"] and not self.url.text():
            self.url.setText(c["url"])
            self.ident.setText(c["identifiant"])

    def _connecter(self, _x=None, confirmer=True):
        from noyau.serveur import client as C
        url = self.url.text().strip()
        try:
            cl = C.Client(url, delai=10)
            cl.info()
        except (C.ErreurConnexion, C.ErreurServeur) as e:
            self.retour.setText(f"<span style='color:{ROUGE}'>{e}</span>")
            return False
        ancienne = DM.configuration()
        if cl.https and ancienne["url"] == url and ancienne["empreinte"] and ancienne["empreinte"] != cl.empreinte:
            self.retour.setText(f"<span style='color:{ROUGE}'>Le certificat de ce serveur a changé : ce n'est peut-être pas "
                                "ton serveur. Vérifie sur le NAS avant de continuer.</span>")
            return False
        if cl.https and confirmer and QMessageBox.question(
                self, "Serveur", f"Empreinte du certificat du serveur :\n\n{cl.empreinte}\n\nEst-ce la même que celle "
                "affichée sur le serveur (Outils > Serveur, ou le journal du NAS) ?") != QMessageBox.StandardButton.Yes:
            return False
        try:
            compte = cl.connecter(self.ident.text().strip(), self.mdp.text())
        except (C.ErreurConnexion, C.ErreurServeur) as e:
            self.retour.setText(f"<span style='color:{ROUGE}'>{e}</span>")
            return False
        self.mdp.clear()
        DM.enregistrer(url, cl.empreinte, compte["identifiant"], cl.jeton)
        roles = ", ".join(D.LIBELLE_ROLE.get(r["role"], r["role"]).split(" (")[0] + (f" ({r['club'] or r['evenement']})"
                                                                                       if r["club"] or r["evenement"] else "")
                          for r in compte["roles"]) or "aucun rôle pour l'instant"
        self.retour.setText(f"<span style='color:{VERT}'>Connecté en tant que {compte['identifiant']}</span> : {roles}."
                            + (" <b>Mot de passe provisoire : change-le</b> sur la page du serveur (téléphone ou navigateur, "
                               "/m/mot-de-passe)." if compte.get("doit_changer") else "")
                            + "<br>Redémarre le logiciel pour travailler sur le serveur.")
        return True

    def _copie(self):
        from PySide6.QtWidgets import QFileDialog
        cl = DM.etat.get("client")
        if not cl:
            QMessageBox.information(self, "Copie", "Ce logiciel n'est pas branché sur un serveur (redémarre-le après la "
                                    "connexion). Sur le serveur lui-même, ouvre directement sa base dans la page Claude.")
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Copie de la base", "Trail Hub serveur.db", "Base (*.db)")
        if chemin:
            from noyau.serveur import client as C
            try:
                n = cl.telecharger_copie(chemin)
            except (C.ErreurConnexion, C.ErreurServeur) as e:
                QMessageBox.warning(self, "Copie", str(e))
                return
            QMessageBox.information(self, "Copie", f"Copie enregistrée ({n // 1024} Ko), sans les comptes ni le journal. "
                                    "Ouvre-la dans la page Claude.")

    def _oublier(self):
        DM.oublier()
        self.retour.setText("Connexion oubliée : au prochain démarrage, tout sera de nouveau local.")


class ServeurFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Serveur et comptes",
                         onglets=[("🖧 Serveur", ServeurLocal), ("👥 Comptes et rôles", ComptesServeur),
                                  ("📜 Journal", JournalServeur), ("✍️ Consentements", ConsentementsServeur),
                                  ("🔌 Se connecter", ConnexionServeur)],
                         athlete_id_initial=athlete_id_initial)
        self.local, self.comptes, self.journal, self.consentements, self.connexion = self.ecrans
