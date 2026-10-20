"""
Info-bulle au survol commune aux graphiques dessinés à la main
(barres, courbes, mini-courbes, profil d'altitude) : un repère vertical
suit la souris et une petite fenêtre indique le jour (ou la période) et
la valeur de chaque mesure — VMA, VO₂max, allure, chrono, charge, poids…

Les graphiques restent dessinés avec QPainter : l'info-bulle est dessinée
par-dessus, dans le même widget, ce qui évite tout clignotement.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen


def formater_valeur(valeur, serie=None):
    """Texte d'une valeur. Une série peut fournir :
       - "format" : fonction valeur -> texte (ex. allure 5.2 -> « 5:12 /km »)
       - "unite"  : suffixe simple (ex. « km/h », « bpm »)."""
    if serie:
        fonction = serie.get("format")
        if callable(fonction):
            try:
                return fonction(valeur)
            except Exception:
                pass
    if isinstance(valeur, float) and not valeur.is_integer():
        texte = f"{valeur:.2f}".rstrip("0").rstrip(".")
    else:
        texte = f"{valeur:g}" if isinstance(valeur, (int, float)) else str(valeur)
    unite = (serie or {}).get("unite")
    return f"{texte} {unite}" if unite else texte


def _allure(v):
    total = int(round(v * 60))
    return f"{total // 60}:{total % 60:02d} /km"


def _chrono(minutes):
    total = int(round(minutes * 60))
    h, reste = divmod(total, 3600)
    m, sec = divmod(reste, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def nom_et_serie(serie):
    """Déduit nom court + format d'une série à partir de son nom, quand les
    écrans n'ont rien précisé : « VMA estimée (km/h) » -> nom « VMA estimée »,
    unité km/h ; « Allure (min/km) » -> 5:12 /km ; « Chrono (min) » -> 1:25:30."""
    import re
    nom = serie.get("nom", "")
    if serie.get("format") or serie.get("unite"):
        return re.sub(r"\s*\([^)]*\)\s*$", "", nom) or nom, serie
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", nom)
    if not m:
        if nom.rstrip().endswith("%"):
            return nom, {**serie, "unite": "%"}
        return nom, serie
    court, unite = m.group(1), m.group(2).strip()
    if not re.search(r"[A-Za-zµ°]", unite) or "zone" in unite.lower():
        return nom, serie  # « Habituel (62) », « (zones 1-2) » : pas une unité
    enrichie = dict(serie)
    if unite == "min/km":
        enrichie["format"] = _allure
    elif unite == "min" and "chrono" in court.lower():
        enrichie["format"] = _chrono
    else:
        enrichie["unite"] = unite
    return court, enrichie


def dessiner_infobulle(painter, zone, x, y, titre, lignes):
    """Dessine l'info-bulle près du point (x, y), sans sortir de `zone`.
    lignes : liste de (couleur_hex ou None, texte)."""
    police = QFont(painter.font())
    police.setPointSizeF(max(police.pointSizeF(), 9))
    painter.setFont(police)
    petit = QFontMetrics(police)
    gras = QFont(police)
    gras.setBold(True)
    metrique_gras = QFontMetrics(gras)

    hauteur_ligne = petit.height() + 3
    largeur_texte = max(
        [metrique_gras.horizontalAdvance(titre)]
        + [petit.horizontalAdvance(t) + (14 if c else 0) for c, t in lignes]
    )
    largeur = largeur_texte + 20
    hauteur = hauteur_ligne * (len(lignes) + 1) + 12

    bx = x + 14
    if bx + largeur > zone.right() - 4:
        bx = x - largeur - 14
    bx = max(zone.left() + 4, bx)
    by = y - hauteur / 2
    by = max(zone.top() + 4, min(by, zone.bottom() - hauteur - 4))

    boite = QRectF(bx, by, largeur, hauteur)
    painter.setPen(QPen(QColor("#3A4046"), 1))
    painter.setBrush(QColor(28, 33, 38, 238))
    painter.drawRoundedRect(boite, 6, 6)

    ligne_y = by + 6 + petit.ascent() + 1
    painter.setFont(gras)
    painter.setPen(QColor("#F2F4F5"))
    painter.drawText(int(bx + 10), int(ligne_y), titre)
    painter.setFont(police)
    ligne_y += hauteur_ligne
    for couleur, texte in lignes:
        decalage = 0
        if couleur:
            painter.setPen(QPen(QColor(couleur), 1))
            painter.setBrush(QColor(couleur))
            painter.drawEllipse(QRectF(bx + 10, ligne_y - petit.ascent() + 3, 8, 8))
            decalage = 14
        painter.setPen(QColor("#D5DADE"))
        painter.drawText(int(bx + 10 + decalage), int(ligne_y), texte)
        ligne_y += hauteur_ligne
