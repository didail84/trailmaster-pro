"""
Jeu d'icônes v109 (trait 1,8 px sur une grille de 24, coins arrondis),
dessinées en SVG et rendues à la volée dans la couleur voulue.

  icone("parcours")                 -> QIcon dans la couleur du texte
  icone("parcours", "#E8590C", 20)  -> QIcon orange de 20 px
  icone_ecran("ouvrir_meteo")       -> l'icône d'un écran du menu
  pixmap_appli(256)                 -> l'icône de l'application (montagne + balise)

Une seule couleur d'accent par espace : orange (coureur), bleu (club),
violet (organisation) — voir theme.COULEURS_ESPACE.
"""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TRACES = {
    "aujourdhui": "M12 8a4 4 0 1 0 0 8 4 4 0 1 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
    "fil": "M4 6h16M4 12h10M4 18h13",
    "tableau": "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
    "journal": "M6 3h11a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2V4a1 1 0 0 1 1-1zM9 8h6M9 12h6",
    "historique": "M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 8v4l3 2",
    "direct": "M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0M12 12v.01M12 16v5",
    "livetrack": "M9 5a3 3 0 1 0 0 6 3 3 0 1 0 0-6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 7a2.4 2.4 0 1 1 0 4.8M18 15c2 .6 3 2.4 3 5",
    "connecteurs": "M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5",
    "parcours": "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14",
    "photos": "M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 1 0 0-7z",
    "plan": "M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM3 9h18M8 2v4M16 2v4",
    "fractionne": "M3 18h3V8h4v10h3V5h4v13h4",
    "renfo": "M6 8v8M18 8v8M3 10v4M21 10v4M6 12h12",
    "forme": "M3 17l5-6 4 4 4-7 5 9",
    "performance": "M3 20l6-10 4 6 3-4 5 8zM8 5h3M15 3v4",
    "bilans": "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "suivi": "M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z",
    "resultats": "M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M9 17h6",
    "courses": "M5 21V4h11l-2 4 2 4H5",
    "calendrier": "M5 4h14v17H5zM5 9h14M9 13h2M13 13h2M9 17h2",
    "sac": "M7 7h10a3 3 0 0 1 3 3v10H4V10a3 3 0 0 1 3-3zM9 7V5a3 3 0 0 1 6 0v2M9 13h6",
    "club": "M5 7h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM8 7V5h8v2M8 13h8",
    "organisation": "M4 5h16v14H4zM4 10h16M10 10v9",
    "analyse": "M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14zM20 20l-4-4M8 13l2-3 2 2 2-3",
    "actualites": "M4 5h13v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2zM17 9h3v10a2 2 0 0 1-2 2M8 9h5M8 13h5",
    "meteo": "M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.5 2A3 3 0 0 0 7 18z",
    "nutrition": "M7 3v8a3 3 0 0 0 6 0V3M10 3v18M17 3c-2 2-2 6 0 8v10",
    "annuaire": "M5 3h12a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2zM5 17h14M9 7h6",
    "bibliotheque": "M4 4h4v16H4zM10 4h4v16h-4zM16 5l3.5-1 3 15.5-3.5 1z",
    "import": "M12 3v12M7 10l5 5 5-5M4 19h16",
    "serveur": "M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01",
    "athletes": "M12 4a4 4 0 1 0 0 8 4 4 0 1 0 0-8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7",
    "personnes": "M9 5a3 3 0 1 0 0 6 3 3 0 1 0 0-6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 7a2.4 2.4 0 1 1 0 4.8M18 15c2 .6 3 2.4 3 5",
    "reglages": "M4 7h10M18 7h2M4 17h4M12 17h8M16 5a2 2 0 1 0 0 4 2 2 0 1 0 0-4zM10 15a2 2 0 1 0 0 4 2 2 0 1 0 0-4z",
    "mise_en_service": "M20 6L9 17l-5-5",
    "recherche": "M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14zM20 20l-4-4",
    "jour_course": "M12 5a8 8 0 1 0 0 16 8 8 0 1 0 0-16zM12 9v4l3 2M9 2h6",
    "duel": "M4 18l5-8 4 5 3-4 4 7M9 5h6",
    "defis": "M12 3l2.5 5 5.5.8-4 3.9.9 5.5L12 15.6 7.1 18.2l.9-5.5-4-3.9 5.5-.8z",
    "semaine": "M5 4h14v17H5zM5 9h14M9 13l2 2 4-4",
    "materiel": "M3 16l7-1 3-5 5 1 3 5v2H3z",
    "montre": "M8 2h8l1 4H7zM7 18h10l-1 4H8zM12 6a6 6 0 1 0 0 12 6 6 0 1 0 0-12zM12 9v3l2 1",
    "agenda": "M5 4h14v17H5zM5 9h14M8 2v4M16 2v4",
    "musique": "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 1 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 1 1 6 0z",
    "detail": "M3 4h18v16H3zM14 4v16",
    "pdf": "M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h6",
    "alerte": "M12 3l10 18H2zM12 10v5M12 18h.01",
}

ICONE_DE_L_ECRAN = {
    "ouvrir_aujourdhui": "aujourdhui", "ouvrir_fil_activite": "fil", "ouvrir_tableau_de_bord": "tableau",
    "ouvrir_journal": "journal", "ouvrir_historique_activites": "historique", "ouvrir_suivi_direct": "direct",
    "ouvrir_livetrack_coach": "livetrack", "ouvrir_connecteurs": "connecteurs", "ouvrir_cartes_et_traces": "parcours",
    "ouvrir_photos": "photos", "ouvrir_planification": "plan", "ouvrir_fractionne": "fractionne",
    "ouvrir_renforcement": "renfo", "ouvrir_analyses_et_forme": "forme", "ouvrir_performance_trail": "performance",
    "ouvrir_bilans_objectifs": "bilans", "ouvrir_suivi": "suivi", "ouvrir_resultats_courses": "resultats",
    "ouvrir_courses_calendrier": "courses", "ouvrir_calendrier_competitions": "calendrier",
    "ouvrir_materiel_course": "sac", "ouvrir_club": "club", "ouvrir_organisation": "organisation",
    "ouvrir_analyse": "analyse", "ouvrir_actualites": "actualites", "ouvrir_meteo": "meteo",
    "ouvrir_alimentation": "nutrition", "ouvrir_annuaire": "annuaire", "ouvrir_bibliotheque": "bibliotheque",
    "ouvrir_import_et_synchro": "import", "ouvrir_serveur": "serveur", "ouvrir_athletes": "athletes",
    "ouvrir_personnes": "personnes", "ouvrir_reglages": "reglages", "ouvrir_mise_en_service": "mise_en_service",
    "ouvrir_jour_de_course": "jour_course", "ouvrir_duel": "duel", "ouvrir_defis_famille": "defis",
    "ouvrir_recherche_globale": "recherche",
}

SVG_APPLI = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 34 34"><rect width="34" height="34" rx="8" fill="{fond}"/>'
             '<path d="M6 26 L14 12.5 L18.5 19 L21.5 15 L28 26 Z" fill="{montagne}"/>'
             '<circle cx="24" cy="9.5" r="2.8" fill="{soleil}"/></svg>')

_cache = {}


def svg(nom, couleur="#17201C", epaisseur=1.8):
    d = TRACES.get(nom, TRACES["fil"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{couleur}" '
            f'stroke-width="{epaisseur}" stroke-linecap="round" stroke-linejoin="round"><path d="{d}"/></svg>')


def _pixmap(code_svg, taille, ratio=2.0):
    pm = QPixmap(int(taille * ratio), int(taille * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    rendu = QSvgRenderer(QByteArray(code_svg.encode("utf-8")))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rendu.render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def pixmap(nom, couleur=None, taille=18):
    if couleur is None:
        from interface.theme import PALETTE
        couleur = PALETTE.get("texte_att", "#2C3530")
    cle = (nom, couleur, taille)
    if cle not in _cache:
        _cache[cle] = _pixmap(svg(nom, couleur), taille)
    return _cache[cle]


def icone(nom, couleur=None, taille=18):
    return QIcon(pixmap(nom, couleur, taille))


def icone_ecran(methode, couleur=None, taille=18):
    nom = ICONE_DE_L_ECRAN.get(methode)
    return icone(nom, couleur, taille) if nom else QIcon()


def pixmap_appli(taille=256, nuit=False):
    code = SVG_APPLI.format(fond="#18211D" if nuit else "#E8590C", montagne="#E8590C" if nuit else "#18211D",
                            soleil="#F5D9C4" if nuit else "#FFF4EC")
    return _pixmap(code, taille, 1.0)


def icone_appli():
    ic = QIcon()
    for t in (16, 32, 64, 128, 256):
        ic.addPixmap(pixmap_appli(t))
    return ic


def sans_emoji(texte):
    """« ☀️  Aujourd'hui » -> « Aujourd'hui » (le menu porte maintenant de vraies icônes)."""
    if "  " in texte:
        debut, reste = texte.split("  ", 1)
        if debut and not any(c.isalnum() for c in debut):
            return reste
    return texte
