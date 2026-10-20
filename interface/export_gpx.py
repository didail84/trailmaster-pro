"""
Export d'un parcours (liste de points) vers un fichier GPX standard,
lisible par Garmin Connect, Strava, ou n'importe quelle appli GPS.
"""

from xml.sax.saxutils import escape


def exporter_gpx(nom_parcours, points, chemin_fichier):
    """points : liste de tuples (lat, lon, alt, ...) — seuls les 3
    premiers éléments sont utilisés."""

    lignes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="TrailMaster Pro" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <trk><name>{escape(nom_parcours)}</name><trkseg>",
    ]

    for point in points:
        lat, lon = point[0], point[1]
        alt = point[2] if len(point) > 2 and point[2] is not None else 0
        lignes.append(f'    <trkpt lat="{lat}" lon="{lon}"><ele>{alt}</ele></trkpt>')

    lignes.append("  </trkseg></trk>")
    lignes.append("</gpx>")

    with open(chemin_fichier, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))
