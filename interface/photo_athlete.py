"""
Gestion des photos de profil des athlètes : copie l'image choisie dans
un dossier géré par l'application (à côté de la base de données), pour
ne pas dépendre de l'emplacement d'origine du fichier (qui pourrait être
déplacé ou supprimé après coup).
"""

import shutil
from pathlib import Path

from data.database import CHEMIN_BDD, definir_photo_athlete


def _dossier_photos():
    dossier = CHEMIN_BDD.parent / "photos"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def enregistrer_photo_athlete(athlete_id, chemin_source):
    """Copie la photo choisie dans le dossier géré par l'appli et
    enregistre son chemin en base. Retourne le chemin enregistré."""

    chemin_source = Path(chemin_source)
    extension = chemin_source.suffix.lower() or ".png"
    destination = _dossier_photos() / f"athlete_{athlete_id}{extension}"

    shutil.copy2(chemin_source, destination)
    definir_photo_athlete(athlete_id, str(destination))

    return str(destination)


def chemin_photo_absolu(photo_path):
    """Retourne le chemin s'il existe encore sur le disque, sinon None
    (fichier déplacé/supprimé après coup, ou aucune photo définie)."""

    if not photo_path:
        return None
    chemin = Path(photo_path)
    return str(chemin) if chemin.exists() else None


def pixmap_circulaire(chemin_photo, taille=80):
    """Retourne un QPixmap carré, recadré en cercle, ou None si le
    fichier est introuvable/invalide."""

    from PySide6.QtGui import QPixmap, QPainter, QPainterPath
    from PySide6.QtCore import Qt

    chemin = chemin_photo_absolu(chemin_photo)
    if not chemin:
        return None

    source = QPixmap(chemin)
    if source.isNull():
        return None

    source = source.scaled(
        taille, taille,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    resultat = QPixmap(taille, taille)
    resultat.fill(Qt.GlobalColor.transparent)

    painter = QPainter(resultat)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    forme = QPainterPath()
    forme.addEllipse(0, 0, taille, taille)
    painter.setClipPath(forme)

    x_decalage = (source.width() - taille) // 2
    y_decalage = (source.height() - taille) // 2
    painter.drawPixmap(-x_decalage, -y_decalage, source)
    painter.end()

    return resultat
