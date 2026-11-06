"""
Accès aux données de l'Espace Club (étape 4.1) : le club, ses groupes, les
adhésions de chaque saison et les tarifs. Un adhérent est une fiche
Personne (noyau/donnees/personnes.py) avec le rôle « licencié » : le club
ne tient pas un second fichier de membres.
"""

from datetime import date

from noyau.donnees import base, personnes as dper
from noyau.club import categories as cat, adhesions as regles

CHAMPS_CLUB = ("nom", "sigle", "numero_ffa", "ligue", "comite", "adresse", "code_postal", "ville", "email",
               "telephone", "site", "president", "logo_path", "notes", "zone_vacances")
CHAMPS_ADHESION = ("type_licence", "numero_licence", "date_licence", "statut", "sante_type", "sante_date",
                   "autorisation_parentale", "droit_image", "tarif", "cotisation", "montant_paye", "paiement_mode",
                   "paiement_date", "recu_numero", "source", "notes")


class ErreurClub(Exception):
    """Message lisible ; rien n'a été modifié."""


# ------------------------------------------------------------------
# Club
# ------------------------------------------------------------------

def club_principal():
    """Le club (dict) ou None s'il n'est pas encore créé."""
    l = base.lire_un(f"SELECT id, {', '.join(CHAMPS_CLUB)} FROM clubs ORDER BY id LIMIT 1")
    return dict(zip(("id",) + CHAMPS_CLUB, l)) if l else None


def enregistrer_club(champs, club_id=None):
    propres = {k: (str(champs[k]).strip() or None) if champs.get(k) is not None else None
               for k in CHAMPS_CLUB if k in champs}
    if not propres.get("nom") and (club_id is None or "nom" in propres):
        raise ErreurClub("Donne le nom du club.")
    if club_id is None:
        return base.inserer("clubs", propres)
    base.ecrire(f"UPDATE clubs SET {', '.join(c + '=?' for c in base.verifier_colonnes(list(propres)))} WHERE id=?",
                tuple(propres.values()) + (club_id,))
    return club_id


def club_id_ou_creer():
    c = club_principal()
    return c["id"] if c else enregistrer_club({"nom": "Mon club"})


# ------------------------------------------------------------------
# Groupes
# ------------------------------------------------------------------

def groupes(club_id, avec_inactifs=False):
    lignes = base.lire_tous(
        "SELECT g.id, g.nom, g.description, g.couleur, g.entraineur_id, g.actif, "
        "(SELECT p.prenom || ' ' || p.nom FROM personnes p WHERE p.id = g.entraineur_id), "
        "(SELECT COUNT(*) FROM groupes_membres m WHERE m.groupe_id = g.id) "
        "FROM groupes g WHERE g.club_id=? " + ("" if avec_inactifs else "AND g.actif=1 ") +
        "ORDER BY g.nom COLLATE NOCASE", (club_id,))
    cles = ("id", "nom", "description", "couleur", "entraineur_id", "actif", "entraineur", "nb_membres")
    return [dict(zip(cles, l)) for l in lignes]


def enregistrer_groupe(club_id, champs, groupe_id=None):
    nom = (champs.get("nom") or "").strip()
    if not nom:
        raise ErreurClub("Donne un nom au groupe.")
    deja = base.lire_un("SELECT id FROM groupes WHERE club_id=? AND nom=? COLLATE NOCASE", (club_id, nom))
    if deja and deja[0] != groupe_id:
        raise ErreurClub(f"Le groupe « {nom} » existe déjà.")
    v = {"nom": nom, "description": champs.get("description") or "", "couleur": champs.get("couleur"),
         "entraineur_id": champs.get("entraineur_id"), "actif": 1 if champs.get("actif", True) else 0}
    if groupe_id is None:
        groupe_id = base.inserer("groupes", {"club_id": club_id, **v})
    else:
        base.ecrire("UPDATE groupes SET nom=?, description=?, couleur=?, entraineur_id=?, actif=? WHERE id=?",
                    tuple(v.values()) + (groupe_id,))
    if v["entraineur_id"]:
        dper_roles = dper.roles(v["entraineur_id"])
        if "entraineur" not in dper_roles:
            dper.definir_roles(v["entraineur_id"], list(dper_roles) + ["entraineur"])
    return groupe_id


def supprimer_groupe(groupe_id):
    base.ecrire("DELETE FROM groupes WHERE id=?", (groupe_id,))


def membres_du_groupe(groupe_id):
    return [r[0] for r in base.lire_tous("SELECT personne_id FROM groupes_membres WHERE groupe_id=?", (groupe_id,))]


def definir_groupes(personne_id, groupe_ids, club_id):
    """Les groupes du club auxquels appartient la personne (remplace les précédents)."""
    with base.transaction() as cur:
        base.ecrire("DELETE FROM groupes_membres WHERE personne_id=? AND groupe_id IN "
                    "(SELECT id FROM groupes WHERE club_id=?)", (personne_id, club_id), cur)
        for g in set(groupe_ids or []):
            base.ecrire("INSERT OR IGNORE INTO groupes_membres (groupe_id, personne_id) VALUES (?,?)", (g, personne_id), cur)


def groupes_de(personne_id):
    return [r[0] for r in base.lire_tous("SELECT groupe_id FROM groupes_membres WHERE personne_id=?", (personne_id,))]


# ------------------------------------------------------------------
# Adhésions
# ------------------------------------------------------------------

_COLS = ("a.id", "a.personne_id", "a.saison", "a.type_licence", "a.numero_licence", "a.date_licence", "a.statut",
         "a.sante_type", "a.sante_date", "a.autorisation_parentale", "a.droit_image", "a.tarif", "a.cotisation",
         "a.montant_paye", "a.paiement_mode", "a.paiement_date", "a.recu_numero", "a.source", "a.notes",
         "p.nom", "p.prenom", "p.date_naissance", "p.sexe", "p.email", "p.telephone", "p.ville",
         "p.contact_urgence_nom", "p.contact_urgence_tel",
         "(SELECT group_concat(g.nom, ', ') FROM groupes_membres m JOIN groupes g ON g.id = m.groupe_id "
         "WHERE m.personne_id = p.id AND g.club_id = a.club_id)")
_CLES = ("id", "personne_id", "saison", "type_licence", "numero_licence", "date_licence", "statut", "sante_type",
         "sante_date", "autorisation_parentale", "droit_image", "tarif", "cotisation", "montant_paye", "paiement_mode",
         "paiement_date", "recu_numero", "source", "notes", "nom", "prenom", "date_naissance", "sexe", "email",
         "telephone", "ville", "contact_urgence_nom", "contact_urgence_tel", "groupes")


def _completer(a):
    a["mineur"] = dper.est_mineur(a["date_naissance"])
    a["categorie"] = cat.categorie(a["date_naissance"], a["saison"])
    a["dossier"] = regles.dossier(a, a["saison"])
    a["reste"] = regles.reste_a_payer(a)
    return a


def adhesions(club_id, saison, groupe_id=None):
    """Adhésions de la saison avec la fiche de la personne, sa catégorie et l'état de son dossier."""
    sql = (f"SELECT {', '.join(_COLS)} FROM adhesions a JOIN personnes p ON p.id = a.personne_id "
           "WHERE a.club_id=? AND a.saison=?")
    params = [club_id, saison]
    if groupe_id is not None:
        sql += " AND a.personne_id IN (SELECT personne_id FROM groupes_membres WHERE groupe_id=?)"
        params.append(groupe_id)
    sql += " ORDER BY p.nom COLLATE NOCASE, p.prenom COLLATE NOCASE"
    return [_completer(dict(zip(_CLES, l))) for l in base.lire_tous(sql, tuple(params))]


def adhesion(adhesion_id):
    l = base.lire_un(f"SELECT {', '.join(_COLS)} FROM adhesions a JOIN personnes p ON p.id = a.personne_id "
                     "WHERE a.id=?", (adhesion_id,))
    return _completer(dict(zip(_CLES, l))) if l else None


def adhesions_de_la_personne(personne_id):
    lignes = base.lire_tous(f"SELECT {', '.join(_COLS)} FROM adhesions a JOIN personnes p ON p.id = a.personne_id "
                            "WHERE a.personne_id=? ORDER BY a.saison DESC", (personne_id,))
    return [_completer(dict(zip(_CLES, l))) for l in lignes]


def saisons(club_id):
    """Saisons qui ont des adhésions + la saison en cours, de la plus récente à la plus ancienne."""
    s = {r[0] for r in base.lire_tous("SELECT DISTINCT saison FROM adhesions WHERE club_id=?", (club_id,))}
    s.add(cat.saison_de())
    return sorted(s, reverse=True)


def _verifier_adhesion(v):
    if v.get("type_licence") and v["type_licence"] not in cat.LIBELLE_LICENCE:
        raise ErreurClub("Type de licence inconnu.")
    if v.get("statut") and v["statut"] not in regles.LIBELLE_STATUT:
        raise ErreurClub("Statut inconnu.")
    if v.get("sante_type") and v["sante_type"] not in regles.LIBELLE_SANTE:
        raise ErreurClub("Pièce de santé inconnue.")
    for k in ("cotisation", "montant_paye"):
        if v.get(k) is not None and v[k] < 0:
            raise ErreurClub("Les montants ne peuvent pas être négatifs.")
    if v.get("numero_licence"):
        v["numero_licence"] = "".join(str(v["numero_licence"]).split())


def enregistrer_adhesion(club_id, personne_id, saison, champs, adhesion_id=None):
    v = {k: champs.get(k) for k in CHAMPS_ADHESION if k in champs}
    _verifier_adhesion(v)
    if adhesion_id is None:
        if base.lire_un("SELECT 1 FROM adhesions WHERE club_id=? AND personne_id=? AND saison=?",
                        (club_id, personne_id, saison)):
            raise ErreurClub(f"Cette personne a déjà une adhésion pour {saison}.")
        aid = base.inserer("adhesions", {"club_id": club_id, "personne_id": personne_id, "saison": saison,
                                         "statut": v.pop("statut", None) or "en_cours", **v})
    else:
        if v:
            base.ecrire(f"UPDATE adhesions SET {', '.join(c + '=?' for c in base.verifier_colonnes(list(v)))} WHERE id=?",
                        tuple(v.values()) + (adhesion_id,))
        aid = adhesion_id
    cot, paye, recu = base.lire_un("SELECT cotisation, montant_paye, recu_numero FROM adhesions WHERE id=?", (aid,))
    if cot and (paye or 0) >= cot - 0.005 and not recu:
        base.ecrire("UPDATE adhesions SET recu_numero=? WHERE id=?", (prochain_recu(saison), aid))
    r = dper.roles(personne_id)
    if "licencie" not in r:
        dper.definir_roles(personne_id, list(r) + ["licencie"])
    return aid


def supprimer_adhesion(adhesion_id):
    base.ecrire("DELETE FROM adhesions WHERE id=?", (adhesion_id,))


def nouvel_adherent(club_id, saison, personne, adhesion_champs, groupe_ids=()):
    """Crée la fiche Personne (rôle licencié) et son adhésion ; renvoie (personne_id, adhesion_id).
    Les doublons sont vérifiés par l'écran avant l'appel (dper.doublons_possibles)."""
    pid = dper.creer(personne, ["licencie"])
    aid = enregistrer_adhesion(club_id, pid, saison, adhesion_champs)
    if groupe_ids:
        definir_groupes(pid, groupe_ids, club_id)
    return pid, aid


def renouveler(club_id, saison_source, saison_cible, personne_ids=None):
    """Crée les adhésions de `saison_cible` pour les adhérents de `saison_source` qui n'en ont pas encore :
    même type et numéro de licence, tarif de la nouvelle saison s'il existe ; santé, autorisation et
    paiement à refaire. Renvoie le nombre d'adhésions créées."""
    tarifs = tarifs_de(club_id, saison_cible)
    n = 0
    with base.transaction() as cur:
        for a in adhesions(club_id, saison_source):
            if a["statut"] == "annulee" or (personne_ids is not None and a["personne_id"] not in personne_ids):
                continue
            if base.lire_un("SELECT 1 FROM adhesions WHERE club_id=? AND personne_id=? AND saison=?",
                            (club_id, a["personne_id"], saison_cible), cur):
                continue
            t = regles.tarif_pour(tarifs, a["type_licence"])
            base.inserer("adhesions", {"club_id": club_id, "personne_id": a["personne_id"], "saison": saison_cible,
                                       "type_licence": a["type_licence"], "numero_licence": a["numero_licence"],
                                       "statut": "en_cours", "tarif": t["libelle"] if t else a["tarif"],
                                       "cotisation": t["montant"] if t else a["cotisation"], "montant_paye": 0,
                                       "droit_image": a["droit_image"], "source": "renouvellement"}, cur)
            n += 1
    return n


def enregistrer_paiement(adhesion_id, montant, mode=None, jour=None):
    """Ajoute un paiement (cumulé) ; attribue un numéro de reçu si la cotisation est soldée."""
    a = adhesion(adhesion_id)
    if not a:
        raise ErreurClub("Adhésion introuvable.")
    if montant is None or montant <= 0:
        raise ErreurClub("Le montant doit être positif.")
    paye = round((a["montant_paye"] or 0) + montant, 2)
    champs = {"montant_paye": paye, "paiement_mode": mode or a["paiement_mode"],
              "paiement_date": jour or date.today().isoformat()}
    if not a["recu_numero"] and a["cotisation"] and paye >= a["cotisation"] - 0.005:
        champs["recu_numero"] = prochain_recu(a["saison"])
    base.ecrire(f"UPDATE adhesions SET {', '.join(c + '=?' for c in champs)} WHERE id=?",
                tuple(champs.values()) + (adhesion_id,))
    return champs.get("recu_numero") or a["recu_numero"]


def prochain_recu(saison):
    """Numéro de reçu suivant pour la saison : « 2026-27-0001 »."""
    prefixe = f"{saison[:4]}-{saison[-2:]}-"
    nums = [int(r[0][len(prefixe):]) for r in base.lire_tous(
        "SELECT recu_numero FROM adhesions WHERE recu_numero LIKE ?", (prefixe + "%",)) if r[0][len(prefixe):].isdigit()]
    return f"{prefixe}{(max(nums) + 1 if nums else 1):04d}"


# ------------------------------------------------------------------
# Tarifs
# ------------------------------------------------------------------

def tarifs_de(club_id, saison):
    return [dict(zip(("id", "libelle", "type_licence", "montant"), l)) for l in base.lire_tous(
        "SELECT id, libelle, type_licence, montant FROM tarifs_cotisation WHERE club_id=? AND saison=? "
        "ORDER BY montant DESC", (club_id, saison))]


def enregistrer_tarif(club_id, saison, libelle, montant, type_licence=None, tarif_id=None):
    libelle = (libelle or "").strip()
    if not libelle or montant is None or montant < 0:
        raise ErreurClub("Donne un nom et un montant positif au tarif.")
    if tarif_id is None:
        if base.lire_un("SELECT 1 FROM tarifs_cotisation WHERE club_id=? AND saison=? AND libelle=?",
                        (club_id, saison, libelle)):
            raise ErreurClub(f"Le tarif « {libelle} » existe déjà pour {saison}.")
        return base.inserer("tarifs_cotisation", {"club_id": club_id, "saison": saison, "libelle": libelle,
                                                  "montant": montant, "type_licence": type_licence})
    base.ecrire("UPDATE tarifs_cotisation SET libelle=?, montant=?, type_licence=? WHERE id=?",
                (libelle, montant, type_licence, tarif_id))
    return tarif_id


def supprimer_tarif(tarif_id):
    base.ecrire("DELETE FROM tarifs_cotisation WHERE id=?", (tarif_id,))


def copier_tarifs(club_id, saison_source, saison_cible):
    n = 0
    existants = {t["libelle"] for t in tarifs_de(club_id, saison_cible)}
    for t in tarifs_de(club_id, saison_source):
        if t["libelle"] not in existants:
            enregistrer_tarif(club_id, saison_cible, t["libelle"], t["montant"], t["type_licence"])
            n += 1
    return n


# ------------------------------------------------------------------
# Import d'un fichier d'adhérents
# ------------------------------------------------------------------

def _chercher_personne(p, numero_licence):
    if numero_licence:
        l = base.lire_un("SELECT personne_id FROM adhesions WHERE numero_licence=? ORDER BY saison DESC LIMIT 1",
                         (numero_licence,))
        if l:
            return l[0]
    if not p.get("nom"):
        return None
    d = dper.doublons_possibles(p["nom"], p.get("prenom") or "", p.get("date_naissance"))
    return d[0]["id"] if len(d) == 1 else None


def importer(club_id, saison, lignes, source="import"):
    """lignes : celles de noyau/club/imports.analyser. Chaque personne déjà connue (même numéro de licence,
    ou même nom, prénom et date de naissance) est complétée sans écraser ce qui est saisi ; les autres
    sont créées. Renvoie {crees, completes, adhesions, deja, erreurs: [texte]}."""
    rapport = {"crees": 0, "completes": 0, "adhesions": 0, "deja": 0, "erreurs": []}
    tarifs = tarifs_de(club_id, saison)
    for k, l in enumerate(lignes, 1):
        p, a = dict(l["personne"]), dict(l["adhesion"])
        try:
            pid = _chercher_personne(p, a.get("numero_licence"))
            if pid is None:
                pid = dper.creer({k2: v for k2, v in p.items() if v}, ["licencie"])
                rapport["crees"] += 1
            else:
                f = dper.fiche(pid)
                vides = {k2: v for k2, v in p.items() if v and not f.get(k2)}
                if vides:
                    dper.modifier(pid, vides)
                    rapport["completes"] += 1
            if base.lire_un("SELECT 1 FROM adhesions WHERE club_id=? AND personne_id=? AND saison=?",
                            (club_id, pid, saison)):
                rapport["deja"] += 1
                continue
            if not a.get("cotisation"):
                t = regles.tarif_pour(tarifs, a.get("type_licence"))
                if t:
                    a["cotisation"], a["tarif"] = t["montant"], a.get("tarif") or t["libelle"]
            enregistrer_adhesion(club_id, pid, saison, {**{k2: v for k2, v in a.items() if v is not None},
                                                         "source": source})
            rapport["adhesions"] += 1
        except (dper.ErreurPersonne, ErreurClub) as e:
            rapport["erreurs"].append(f"Ligne {k} ({p.get('prenom', '')} {p.get('nom', '')}) : {e}")
    return rapport


def export_csv(adhs):
    """Texte CSV (séparateur ;) de la liste des adhérents, pour un tableur."""
    import csv
    import io
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["Nom", "Prénom", "Naissance", "Sexe", "Catégorie", "Licence", "N° licence", "Groupes", "E-mail",
                "Téléphone", "Ville", "Contact d'urgence", "Tél. urgence", "Cotisation", "Payé", "Reste",
                "Dossier", "Manques"])
    for a in adhs:
        c = a["categorie"]
        w.writerow([a["nom"], a["prenom"], a["date_naissance"] or "", a["sexe"] or "", c["code"] if c else "",
                    cat.LIBELLE_LICENCE.get(a["type_licence"], ""), a["numero_licence"] or "", a["groupes"] or "",
                    a["email"] or "", a["telephone"] or "", a["ville"] or "", a["contact_urgence_nom"] or "",
                    a["contact_urgence_tel"] or "", f"{a['cotisation'] or 0:.2f}".replace(".", ","),
                    f"{a['montant_paye'] or 0:.2f}".replace(".", ","), f"{a['reste']:.2f}".replace(".", ","),
                    "complet" if a["dossier"]["complet"] else "incomplet", " ; ".join(a["dossier"]["manques"])])
    return "﻿" + sortie.getvalue()
