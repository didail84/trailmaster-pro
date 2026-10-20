"""
Import du suivi poids / jambes / fatigue depuis un classeur Excel (.xlsx)
ou un fichier CSV — dans la table suivi_corporel (écran « Poids & fatigue »).

Format attendu (celui du fichier « suivi_poids_jambes_RPE_trail.xlsx »),
une ligne par relevé, première ligne = titres des colonnes :

    Date | Poids (kg) | État des jambes | Fatigue ressentie (RPE /10) | Commentaires

Règles :
- Seules les lignes avec une VRAIE date sont importées (jj/mm/aaaa, aaaa-mm-jj
  ou date Excel). Les lignes du type « Septembre 2026 (date inconnue) » sont
  ignorées et comptées dans le compte rendu : aucune date n'est inventée.
- Une date suivie d'un mot (« 08/10/2026 soir », « 11/10/2026 après trail »)
  devient un relevé distinct de la même journée, avec ce mot dans les notes.
- Réimporter le même fichier ne crée pas de doublons : si un relevé existe
  déjà à cette date, seules les cases VIDES sont complétées, rien n'est écrasé.
- Aucune dépendance : le .xlsx est lu avec la bibliothèque standard.
"""

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from data.database import connexion

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ETATS_JAMBES = ["Normales", "Lourdes", "Fatiguées", "Courbatures", "Douloureuses"]


# ------------------------------------------------------------------
# LECTURE DU FICHIER
# ------------------------------------------------------------------

def _indice_colonne(reference):
    lettres = re.match(r"[A-Z]+", reference).group(0)
    n = 0
    for c in lettres:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def lire_xlsx(chemin):
    """Retourne les lignes (listes de valeurs) de la feuille « Suivi
    quotidien » si elle existe, sinon de la première feuille."""
    with zipfile.ZipFile(chemin) as z:
        chaines = []
        if "xl/sharedStrings.xml" in z.namelist():
            racine = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in racine.findall("m:si", NS):
                chaines.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))

        classeur = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        cible_par_id = {r.get("Id"): r.get("Target") for r in rels}
        feuilles = []
        for s in classeur.find("m:sheets", NS):
            rid = s.get(f"{{{NS_REL}}}id")
            cible = cible_par_id.get(rid, "")
            cible = cible.lstrip("/")
            if not cible.startswith("xl/"):
                cible = "xl/" + cible
            feuilles.append((s.get("name"), cible))
        if not feuilles:
            return []
        choix = next((f for f in feuilles if "suivi" in f[0].lower()), feuilles[0])

        racine = ET.fromstring(z.read(choix[1]))
        lignes = []
        for row in racine.iter(f"{{{NS['m']}}}row"):
            valeurs = {}
            for c in row.findall("m:c", NS):
                idx = _indice_colonne(c.get("r"))
                type_ = c.get("t")
                v = c.find("m:v", NS)
                if type_ == "s" and v is not None:
                    val = chaines[int(v.text)]
                elif type_ == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None and v.text is not None:
                    if type_ in ("str", "b", "e"):
                        val = v.text
                    else:
                        try:
                            val = float(v.text)
                        except ValueError:
                            val = v.text
                else:
                    val = None
                valeurs[idx] = val
            if valeurs:
                largeur = max(valeurs) + 1
                lignes.append([valeurs.get(i) for i in range(largeur)])
        return lignes


def lire_csv(chemin):
    with open(chemin, newline="", encoding="utf-8-sig") as f:
        echantillon = f.read(4096)
        f.seek(0)
        delim = ";" if echantillon.count(";") > echantillon.count(",") else ","
        return [list(l) for l in csv.reader(f, delimiter=delim)]


def lire_fichier(chemin):
    if str(chemin).lower().endswith(".csv"):
        return lire_csv(chemin)
    return lire_xlsx(chemin)


# ------------------------------------------------------------------
# ANALYSE DES LIGNES
# ------------------------------------------------------------------

def _nombre(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def _date_et_qualificatif(valeur):
    """-> (date ISO ou None, qualificatif texte ou '')."""
    if valeur is None or valeur == "":
        return None, ""
    if isinstance(valeur, (int, float)) and 30000 < valeur < 80000:
        d = date(1899, 12, 30) + timedelta(days=int(valeur))
        return d.isoformat(), ""
    if isinstance(valeur, (datetime, date)):
        return valeur.strftime("%Y-%m-%d"), ""
    texte = str(valeur).strip()
    m = re.match(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b\s*(.*)$", texte)
    if m:
        j, mo, a, reste = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).strip()
    else:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\b[ T]*(.*)$", texte)
        if not m:
            return None, ""
        a, mo, j, reste = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).strip()
    try:
        return date(a, mo, j).isoformat(), reste
    except ValueError:
        return None, ""


def _etat_jambes(texte):
    """Rapproche le texte libre d'un des états proposés par l'écran.
    Retourne (état ou None, texte d'origine à garder dans les notes)."""
    if not texte:
        return None, ""
    t = str(texte).strip()
    bas = t.lower()
    if bas in ("non précisé", "non precise", "non précisée"):
        return None, ""
    etat = None
    if bas.startswith("normal"):
        etat = "Normales"  # « Normales le matin ; … tirent plus tard » : l'état du relevé est celui du matin
    elif "douloureu" in bas:
        etat = "Douloureuses"
    elif "courbatur" in bas:
        etat = "Courbatures"
    elif "lourd" in bas:
        etat = "Lourdes"
    elif "tir" in bas or "fatigu" in bas:
        etat = "Fatiguées"
    elif "normal" in bas:
        etat = "Normales"
    # On garde la formulation d'origine dès qu'elle dit plus que l'étiquette.
    garde = "" if (etat and bas.rstrip(".") == etat.lower()) else t
    return etat, garde


def analyser_lignes(lignes):
    """-> (relevés, nb_sans_date, nb_vides). Chaque relevé : dict date,
    qualificatif, poids, etat_jambes, fatigue_generale, notes."""
    if not lignes:
        return [], 0, 0

    entete = [str(c or "").lower() for c in lignes[0]]

    def col(*mots):
        for i, e in enumerate(entete):
            if any(m in e for m in mots):
                return i
        return None

    c_date = col("date")
    c_poids = col("poids")
    c_jambes = col("jambe")
    c_rpe = col("rpe", "fatigue")
    c_comm = col("comment", "note", "remarque")
    if c_date is None:
        raise ValueError("Colonne « Date » introuvable (première ligne = titres des colonnes).")

    def get(ligne, i):
        return ligne[i] if i is not None and i < len(ligne) else None

    releves, sans_date, vides = [], 0, 0
    for ligne in lignes[1:]:
        if not any(c not in (None, "") for c in ligne):
            continue
        d, qualif = _date_et_qualificatif(get(ligne, c_date))
        if d is None:
            sans_date += 1
            continue
        poids = _nombre(get(ligne, c_poids))
        rpe = _nombre(get(ligne, c_rpe))
        etat, texte_jambes = _etat_jambes(get(ligne, c_jambes))
        commentaire = str(get(ligne, c_comm) or "").strip()
        if poids is None and rpe is None and etat is None and not texte_jambes:
            vides += 1  # « Aucune valeur confirmée » : rien à enregistrer
            continue
        morceaux = []
        if qualif:
            morceaux.append(qualif.capitalize())
        if texte_jambes:
            morceaux.append(f"Jambes : {texte_jambes}")
        if commentaire:
            morceaux.append(commentaire)
        releves.append({
            "date": d,
            "qualificatif": qualif.lower(),
            "poids": poids,
            "etat_jambes": etat,
            "fatigue_generale": int(round(rpe)) if rpe is not None else None,
            "notes": " — ".join(morceaux) or None,
        })
    return releves, sans_date, vides


# ------------------------------------------------------------------
# ÉCRITURE EN BASE
# ------------------------------------------------------------------

def importer_releves(athlete_id, releves):
    """Insère ou complète. Retourne (ajoutés, complétés, inchangés)."""
    conn = connexion()
    cur = conn.cursor()
    ajoutes = completes = inchanges = 0
    try:
        for r in releves:
            cur.execute(
                "SELECT id, poids_kg, etat_jambes, fatigue_generale, notes "
                "FROM suivi_corporel WHERE athlete_id=? AND date=? ORDER BY id",
                (athlete_id, r["date"]),
            )
            existants = cur.fetchall()

            if r["qualificatif"]:
                # Relevé distinct (soir, après sortie…) : déjà là si une note
                # de la même journée contient le qualificatif.
                deja = next(
                    (e for e in existants if e[4] and r["qualificatif"] in e[4].lower()), None
                )
                cible = deja
            else:
                # Relevé du matin : on complète le premier relevé du jour sans qualificatif.
                cible = existants[0] if existants else None

            if cible is None:
                cur.execute(
                    "INSERT INTO suivi_corporel "
                    "(athlete_id, date, poids_kg, etat_jambes, fatigue_generale, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (athlete_id, r["date"], r["poids"], r["etat_jambes"],
                     r["fatigue_generale"], r["notes"]),
                )
                ajoutes += 1
                continue

            id_, poids, etat, fat, notes = cible
            maj = {}
            if poids is None and r["poids"] is not None:
                maj["poids_kg"] = r["poids"]
            if not etat and r["etat_jambes"]:
                maj["etat_jambes"] = r["etat_jambes"]
            if fat is None and r["fatigue_generale"] is not None:
                maj["fatigue_generale"] = r["fatigue_generale"]
            if not notes and r["notes"]:
                maj["notes"] = r["notes"]
            if maj:
                sets = ", ".join(f"{k}=?" for k in maj)
                cur.execute(
                    f"UPDATE suivi_corporel SET {sets} WHERE id=?", (*maj.values(), id_)
                )
                completes += 1
            else:
                inchanges += 1
        conn.commit()
    finally:
        conn.close()
    return ajoutes, completes, inchanges


def importer_fichier(athlete_id, chemin):
    """Tout-en-un : lit, analyse, écrit. Retourne un dict de compte rendu."""
    releves, sans_date, vides = analyser_lignes(lire_fichier(chemin))
    ajoutes, completes, inchanges = importer_releves(athlete_id, releves)
    return {
        "lus": len(releves), "ajoutes": ajoutes, "completes": completes,
        "inchanges": inchanges, "sans_date": sans_date, "vides": vides,
    }
