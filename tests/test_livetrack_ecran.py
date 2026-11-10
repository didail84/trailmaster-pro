"""Fenêtre LiveTrack coach : parcours complet à l'écran (sans moteur web : la page s'ouvre dans le navigateur)."""
import sqlite3

import pytest

from noyau.donnees import livetrack as D
from noyau.livetrack import regles as R

LIEN = "https://livetrack.garmin.com/session/8a1f0c2e-1b3d-4c5e-9f00-aaaaaaaaaaaa/token/ABCDEF0123456789"


@pytest.fixture
def fenetre(base_vide, monkeypatch):
    monkeypatch.setenv("TRAILHUB_SANS_VUE_WEB", "1")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from interface.livetrack_coach import LiveTrackCoachFenetre
    f = LiveTrackCoachFenetre()
    yield f
    f.close()


def test_parcours_du_coach(fenetre, base_vide, monkeypatch):
    import interface.livetrack_coach as UI
    avertissements = []
    monkeypatch.setattr(UI.QMessageBox, "warning", lambda *a, **k: avertissements.append(a[2]))
    direct, histo, message = fenetre.direct, fenetre.historique, fenetre.message
    assert direct.table.rowCount() == 0 and "Aucun suivi" in direct.message.text()

    cid = D.creer_coureur({"nom": "Léa Martin", "montre": "Fenix 6 Pro", "athlete_id": 1})
    UI._apres_changement()
    assert direct.coureur.count() == 1 and histo.filtre.count() == 2 and message.coureur.count() == 1

    # un lien qui n'est pas Garmin est refusé avec un message lisible
    direct.lien.setText("https://exemple.com/x")
    direct._suivre()
    assert avertissements and "Garmin" in avertissements[0] and direct.table.rowCount() == 0

    # le message entier du coureur convient
    direct.lien.setText(f"Suis-moi ici : {LIEN} merci !")
    direct._suivre()
    assert direct.table.rowCount() == 1 and direct.lien.text() == ""
    assert direct.table.item(0, 0).text() == "Léa Martin" and direct.table.item(0, 3).text() == "En cours"
    assert direct.vue.lien == LIEN and not direct.vue.integree                       # sans moteur web
    assert direct.boutons["nav"].isEnabled() and direct.boutons["copier"].isEnabled()
    assert histo.table.rowCount() == 1                                                # les autres onglets suivent

    # FC vue sur la page : retenue sur le suivi
    direct.fc.setCurrentIndex(direct.fc.findData(0))
    direct._definir_fc(0)
    assert D.suivis()[0]["fc_visible"] == 0 and direct.table.item(0, 4).text() == "non visible sur la page"

    # la sortie envoyée par la montre est rattachée depuis l'historique
    c = sqlite3.connect(base_vide)
    from datetime import datetime
    c.execute("INSERT INTO activites (athlete_id, date, nom, type, distance, duree, empreinte) VALUES (1, ?, 'Matinale', 'Trail', 14.2, 5400, 'e1')",
              (datetime.now().isoformat(timespec="seconds"),))
    c.commit()
    c.close()
    histo.table.selectRow(0)
    assert "Aucune sortie rattachée" in histo.fiche.toPlainText()
    assert D.activites_candidates(D.suivis()[0]["id"])
    direct._terminer()
    assert direct.table.rowCount() == 0                                                # plus « en cours »
    assert histo.table.item(0, 3).text() == "Terminé"
    D.rattacher_activite(D.suivis()[0]["id"], D.activites_candidates(D.suivis()[0]["id"])[0]["id"])
    UI._apres_changement()
    histo.table.selectRow(0)
    texte = histo.fiche.toPlainText()
    assert "Matinale" in texte and "14,2 km" in texte and "L'analyse s'écrit toute seule" in texte
    assert histo.boutons["detacher"].isEnabled()

    # le fil d'activité affiche le repère
    import interface.fil_activite as FA
    assert "Suivie en direct (Léa Martin)" in FA._repere_livetrack(D.suivis()[0]["activite_id"])


def test_message_et_test_de_configuration(fenetre, base_vide):
    import interface.livetrack_coach as UI
    message = fenetre.message
    D.creer_coureur({"nom": "Léa Martin", "montre": "Fenix 6 Pro", "objectif": "sortie longue"})
    UI._apres_changement()
    t = message.texte.toPlainText()
    assert t.startswith("Bonjour Léa,") and "Fenix 6 Pro" in t and "sortie longue" in t and "LiveTrack" in t
    for code, combo in message.choix.items():
        combo.setCurrentIndex(combo.findData(True))
    message.choix["fc"].setCurrentIndex(message.choix["fc"].findData(False))
    message.note.setText("FC absente")
    message._enregistrer_test()
    assert "fréquence cardiaque n'apparaît pas" in message.bilan.text()
    assert message.historique.rowCount() == 1 and D.dernier_test(D.coureurs()[0]["id"])["note"] == "FC absente"
    message._refaire()
    assert message.texte.toPlainText().startswith("Bonjour Léa,")


def test_module_dans_le_registre_et_le_menu(base_vide):
    from noyau import modules as M
    assert M.est_actif("livetrack_coach") and M.ecran_visible("ouvrir_livetrack_coach")
    assert M.PAR_CODE["livetrack_coach"].espace == "Coureur" and M.PAR_CODE["trail_live"].espace == "Organisation"
    M.definir_actif("livetrack_coach", False)
    assert not M.ecran_visible("ouvrir_livetrack_coach")
    import interface.fil_activite as FA
    assert FA._repere_livetrack(1) is None and FA._lignes_live_recentes() == []          # module éteint : rien dans le fil


def test_lignes_recentes_du_fil(base_vide):
    import interface.fil_activite as FA
    cid = D.creer_coureur({"nom": "Léa"})
    D.ajouter_suivi(cid, LIEN)
    assert FA._lignes_live_recentes() == ["📡 Léa suivi en direct — en cours depuis 0 min"]
