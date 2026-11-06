"""Étape 2.3 — modules activables."""
import re
from pathlib import Path

import pytest

from noyau import modules as M
from noyau.outils import evenements as ev


def test_chaque_ecran_du_menu_a_son_module():
    src = (Path(__file__).resolve().parent.parent / "interface" / "tableau_bord.py").read_text(encoding="utf-8")
    menu = set(re.findall(r"self\.(ouvrir_\w+), (?:True|False)\)", src))
    rattaches = {e for m in M.MODULES for e in m.ecrans}
    assert menu and menu == rattaches
    for m in M.MODULES:
        assert m.espace in M.ESPACES and (m.disponible or m.etape)


def test_valeurs_par_defaut(base_vide):
    assert M.est_actif("noyau") and M.est_actif("entrainement") and M.est_actif("suivi")
    assert not M.est_actif("club") and not M.est_actif("inconnu")
    assert M.ecran_visible("ouvrir_meteo") and M.ecran_visible("ouvrir_qui_n_existe_pas")


def test_eteindre_et_rallumer(base_vide):
    recus = []
    abonne = lambda **k: recus.append(k)
    ev.abonner(ev.MODULES_MODIFIES, abonne)
    try:
        M.definir_actif("meteo", False)
        assert not M.est_actif("meteo") and not M.ecran_visible("ouvrir_meteo")
        assert "meteo" not in M.actifs()
        M.definir_actif("meteo", True)
        assert M.ecran_visible("ouvrir_meteo")
        assert recus == [{"code": "meteo", "actif": False}, {"code": "meteo", "actif": True}]
    finally:
        ev.desabonner(ev.MODULES_MODIFIES, abonne)


def test_refus(base_vide):
    for code, actif in (("entrainement", False), ("noyau", False), ("kids", True), ("rien", True)):
        with pytest.raises(ValueError):
            M.definir_actif(code, actif)
    assert M.est_actif("entrainement") and not M.est_actif("kids")
    M.definir_actif("club", True)                    # étape 4.1 : le club s'allume, éteint par défaut
    assert M.est_actif("club") and M.ecran_visible("ouvrir_club")


def test_le_menu_suit_les_modules(base_vide):
    import interface.tableau_bord as tb
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    f = tb.TableauBord()
    try:
        boutons = {e: b for b, e in f._ecran_du_bouton.items()}
        assert not boutons["ouvrir_meteo"].isHidden()
        M.definir_actif("meteo", False)
        assert boutons["ouvrir_meteo"].isHidden() and not boutons["ouvrir_alimentation"].isHidden()
        M.definir_actif("nutrition", False)
        groupe = f._groupes_menu["OUTILS"][0]
        assert not groupe.isHidden()                 # Import & Synchro reste dans OUTILS
        assert all("Météo" not in libelle for libelle, _m, _f in f.liste_commandes())
        M.definir_actif("meteo", True)
        assert not boutons["ouvrir_meteo"].isHidden()
    finally:
        from PySide6.QtCore import QThread, QThreadPool
        for t in f.findChildren(QThread):     # calculs de l'écran Aujourd'hui lancés à la création
            t.wait(20000)
        QThreadPool.globalInstance().waitForDone(20000)
        f.close()
        import shiboken6
        shiboken6.delete(f)      # supprimée tout de suite : ses minuteries (synchro Garmin…) ne partiront jamais
