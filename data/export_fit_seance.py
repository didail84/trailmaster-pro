"""
E2 — Exporte une séance structurée au format FIT « workout » (fichier
.fit lisible par les montres Garmin : copié dans GARMIN/NewFiles, la séance
apparaît dans Entraînement > Séances de la montre).

Encodeur écrit à la main, sans dépendance. Messages : file_id, workout,
workout_step (durée en temps ou distance, cible d'allure ou de FC,
répétitions regroupées automatiquement quand une paire effort/récupération
identique se répète).
"""

import struct
import time
from datetime import datetime, timezone

EPOCH_FIT = 631065600  # 1989-12-31 00:00:00 UTC

# types de base FIT
ENUM, UINT16, UINT32, STRING, UINT32Z = 0x00, 0x84, 0x86, 0x07, 0x8C

INTENSITE = {"Échauffement": 2, "Effort": 5, "Récupération": 4, "Retour au calme": 3}


def _crc(data, crc=0):
    table = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
    for b in data:
        tmp = table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[b & 0xF]
        tmp = table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[(b >> 4) & 0xF]
    return crc


def _definition(local, global_num, champs):
    """champs : [(num, taille, type_base)]"""
    out = struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(champs))
    for num, taille, base in champs:
        out += struct.pack("<BBB", num, taille, base)
    return out


def _chaine(texte, n):
    b = texte.encode("utf-8")[: n - 1]
    return b + b"\x00" * (n - len(b))


def _allure_en_mm_s(texte):
    try:
        m, s = str(texte).split(":")
        minutes = int(m) + int(s) / 60
        return 1000 / (minutes * 60) * 1000 if minutes > 0 else None
    except (ValueError, TypeError):
        return None


def _etape_fit(index, e):
    """Un workout_step (liste de champs binaires déjà packés)."""
    nom = e.get("type", "")[:15]
    if e.get("mode") == "distance":
        duree_type, duree_val = 1, int(round(float(e["valeur"]) * 100000))  # km -> cm
    else:
        duree_type, duree_val = 0, int(round(float(e["valeur"]) * 60000))  # min -> ms
    cible_type, cible_val, bas, haut = 2, 0, 0, 0  # open
    v = _allure_en_mm_s(e.get("allure_cible"))
    if v:
        cible_type, cible_val, bas, haut = 0, 0, int(v * 0.97), int(v * 1.03)
    elif e.get("fc_cible"):
        fc = int(e["fc_cible"])
        cible_type, cible_val, bas, haut = 1, 0, fc - 5 + 100, fc + 5 + 100
    return struct.pack("<H16sBIBIIIB", index, _chaine(nom, 16), duree_type, duree_val, cible_type, cible_val, bas, haut,
                       INTENSITE.get(e.get("type"), 0))


def _regrouper(etapes):
    """Transforme la liste en pas FIT, avec répétitions : renvoie une liste de
    ('etape', dict) ou ('repete', index_debut, n)."""
    def cle(e):
        return (e.get("type"), e.get("mode"), e.get("valeur"), e.get("allure_cible"), e.get("fc_cible"))

    res, i = [], 0
    while i < len(etapes):
        if i + 3 < len(etapes) and etapes[i].get("type") == "Effort" and etapes[i + 1].get("type") == "Récupération":
            paire = (cle(etapes[i]), cle(etapes[i + 1]))
            n = 1
            while i + 2 * n + 1 < len(etapes) and (cle(etapes[i + 2 * n]), cle(etapes[i + 2 * n + 1])) == paire:
                n += 1
            if n >= 2:
                debut = len(res)
                res.append(("etape", etapes[i]))
                res.append(("etape", etapes[i + 1]))
                res.append(("repete", debut, n))
                i += 2 * n
                continue
        res.append(("etape", etapes[i]))
        i += 1
    return res


def encoder_seance(nom, etapes, sport=1):
    """Renvoie les octets du fichier .fit. sport : 1 = course à pied."""
    if not etapes:
        raise ValueError("La séance n'a aucune étape.")
    pas = _regrouper(etapes)
    maintenant = int(time.time()) - EPOCH_FIT
    corps = b""
    # file_id
    corps += _definition(0, 0, [(0, 1, ENUM), (1, 2, UINT16), (2, 2, UINT16), (3, 4, UINT32Z), (4, 4, UINT32)])
    corps += struct.pack("<BBHHII", 0, 5, 255, 0, 1, maintenant)
    # workout
    corps += _definition(1, 26, [(4, 1, ENUM), (6, 2, UINT16), (8, 32, STRING)])
    corps += struct.pack("<BBH32s", 1, sport, len(pas), _chaine(nom[:31], 32))
    # workout_step
    corps += _definition(2, 27, [(254, 2, UINT16), (0, 16, STRING), (1, 1, ENUM), (2, 4, UINT32),
                                 (3, 1, ENUM), (4, 4, UINT32), (5, 4, UINT32), (6, 4, UINT32), (7, 1, ENUM)])
    for idx, p in enumerate(pas):
        if p[0] == "etape":
            corps += bytes([2]) + _etape_fit(idx, p[1])
        else:
            _, debut, n = p
            corps += bytes([2]) + struct.pack("<H16sBIBIIIB", idx, _chaine("Répéter", 16), 6, debut, 2, n, 0, 0, 0)
    entete = struct.pack("<BBHI4s", 14, 0x20, 2132, len(corps), b".FIT")
    entete += struct.pack("<H", _crc(entete))
    fichier = entete + corps
    return fichier + struct.pack("<H", _crc(fichier))


def nom_fichier(nom, date_texte=None):
    propre = "".join(c if c.isalnum() else "_" for c in nom)[:24].strip("_") or "seance"
    return f"TM_{propre}.fit"
