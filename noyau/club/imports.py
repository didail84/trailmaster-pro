"""
Lecture des fichiers d'adhérents (étape 4.1) : export HelloAsso, export
des licenciés du SI-FFA ou tout tableau (CSV, Excel) dont les colonnes
portent des noms courants. Rien n'est écrit ici : on renvoie des lignes
prêtes à vérifier puis à importer (noyau/donnees/club.importer).
"""

import csv
import io
import re
import unicodedata

from noyau.donnees.personnes import normaliser_date as _normaliser, ErreurPersonne


def normaliser_date(texte):
    try:
        return _normaliser(texte)
    except ErreurPersonne:
        return None

# champ : noms de colonne possibles (sans accents, minuscules, espaces simples)
SYNONYMES = {
    "nom": ("nom", "nom de famille", "nom adherent", "nom du participant", "nom de l'adherent", "last name"),
    "prenom": ("prenom", "prenom adherent", "prenom du participant", "prenom de l'adherent", "first name"),
    "date_naissance": ("date de naissance", "date naissance", "ne le", "ne(e) le", "naissance", "date de naissance (jj/mm/aaaa)",
                       "birth date"),
    "sexe": ("sexe", "genre", "civilite", "civilite du participant"),
    "email": ("email", "e-mail", "mail", "adresse email", "email adherent", "email payeur", "courriel"),
    "telephone": ("telephone", "tel", "portable", "telephone portable", "numero de telephone", "mobile"),
    "adresse": ("adresse", "adresse postale", "rue"),
    "code_postal": ("code postal", "cp"),
    "ville": ("ville", "commune", "localite"),
    "numero_licence": ("numero de licence", "n° licence", "no licence", "numero licence", "licence", "n licence",
                       "numero de licence ffa", "n° de licence", "num licence"),
    "type_licence": ("type de licence", "type licence", "licence souhaitee", "formule", "tarif", "categorie de licence"),
    "cotisation": ("montant tarif", "montant", "montant total", "prix", "cotisation", "montant paye", "montant de la commande"),
    "paiement_date": ("date de la commande", "date du paiement", "date paiement", "date d'inscription"),
    "paiement_mode": ("moyen de paiement", "mode de paiement", "paiement"),
    "contact_urgence_nom": ("personne a prevenir", "contact d'urgence", "nom contact urgence", "contact urgence"),
    "contact_urgence_tel": ("telephone urgence", "tel urgence", "telephone de la personne a prevenir",
                            "telephone contact urgence"),
    "statut_commande": ("statut de la commande", "statut", "etat du paiement"),
}


def _cle(texte):
    t = unicodedata.normalize("NFD", (texte or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("’", "'").replace("_", " ")
    return re.sub(r"\s+", " ", t).strip(" :*")


def correspondance(entetes):
    """{champ: index de colonne} ; la première colonne qui correspond l'emporte (« Email » avant « Email payeur »)."""
    cles = [_cle(e) for e in entetes]
    res = {}
    for champ, noms in SYNONYMES.items():
        for nom in noms:
            if nom in cles and cles.index(nom) not in res.values():
                res[champ] = cles.index(nom)
                break
        if champ not in res:              # colonne qui commence par le nom (« Numéro de licence FFA (si renouvellement) »)
            for i, c in enumerate(cles):
                if i not in res.values() and any(c.startswith(n) for n in noms if len(n) > 5):
                    res[champ] = i
                    break
    return res


def type_licence_depuis(texte):
    t = _cle(texte)
    for mot, code in (("decouverte", "decouverte"), ("baby", "decouverte"), ("eveil", "decouverte"),
                      ("poussin", "decouverte"), ("competition", "competition"), ("running", "running"),
                      ("hors stade", "running"), ("sante", "sante"), ("marche nordique", "sante"),
                      ("entreprise", "entreprise"), ("encadrement", "encadrement"), ("dirigeant", "encadrement"),
                      ("sans licence", "adherent"), ("adhesion simple", "adherent")):
        if mot in t:
            return code
    return None


def sexe_depuis(texte):
    t = _cle(texte)
    if t in ("f", "femme", "feminin", "madame", "mme", "mlle", "w"):
        return "F"
    if t in ("m", "h", "homme", "masculin", "monsieur", "m."):
        return "H"
    return None


def montant(texte):
    t = (texte or "").replace("€", "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return round(float(t), 2) if t else None
    except ValueError:
        return None


def lire_tableau(contenu, nom_fichier=""):
    """Lignes du fichier (liste de listes de textes). CSV (; , ou tabulation) ou Excel .xlsx (si openpyxl
    est installé)."""
    if nom_fichier.lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError as e:
            raise ValueError("Pour lire un fichier Excel, enregistre-le d'abord en CSV (Fichier > Enregistrer sous).") from e
        classeur = openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
        feuille = classeur.active
        lignes = []
        for row in feuille.iter_rows(values_only=True):
            lignes.append(["" if v is None else (v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v))
                           for v in row])
        return lignes
    if isinstance(contenu, bytes):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texte = contenu.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        texte = contenu
    echantillon = texte[:4000]
    sep = max((";", ",", "\t"), key=lambda s: echantillon.count(s))
    return [l for l in csv.reader(io.StringIO(texte), delimiter=sep) if any(c.strip() for c in l)]


def analyser(lignes):
    """Transforme le tableau en adhérents : {lignes: [{personne: {...}, adhesion: {...}, erreurs: [...]}],
    colonnes: {champ: nom de la colonne}, non_reconnues: [noms]}."""
    if not lignes:
        return {"lignes": [], "colonnes": {}, "non_reconnues": []}
    # l'en-tête est la première ligne qui contient « nom » et « prénom »
    debut = 0
    for i, l in enumerate(lignes[:10]):
        cles = [_cle(c) for c in l]
        if any(c.startswith("nom") for c in cles) and any(c.startswith("prenom") for c in cles):
            debut = i
            break
    entetes = lignes[debut]
    corr = correspondance(entetes)
    res = []
    for l in lignes[debut + 1:]:
        def v(champ):
            i = corr.get(champ)
            return l[i].strip() if i is not None and i < len(l) else ""
        erreurs = []
        nom, prenom = v("nom"), v("prenom")
        if not nom:
            continue
        statut = _cle(v("statut_commande"))
        if statut and any(m in statut for m in ("rembours", "annul", "refus", "echou")):
            continue
        naissance_brute = v("date_naissance")
        naissance = normaliser_date(naissance_brute) if naissance_brute else None
        if naissance_brute and not naissance:
            erreurs.append(f"date de naissance illisible ({naissance_brute})")
        personne = {"nom": nom.strip().upper() if nom.isupper() else nom.strip(), "prenom": prenom.strip(),
                    "date_naissance": naissance, "sexe": sexe_depuis(v("sexe")), "email": v("email") or None,
                    "telephone": v("telephone") or None, "adresse": v("adresse") or None,
                    "code_postal": v("code_postal") or None, "ville": v("ville") or None,
                    "contact_urgence_nom": v("contact_urgence_nom") or None,
                    "contact_urgence_tel": v("contact_urgence_tel") or None}
        lic = re.sub(r"\s", "", v("numero_licence"))
        typ = type_licence_depuis(v("type_licence"))
        cot = montant(v("cotisation"))
        pdate = normaliser_date(v("paiement_date")[:10]) if v("paiement_date") else None
        adhesion = {"numero_licence": lic or None, "type_licence": typ, "tarif": v("type_licence") or None,
                    "cotisation": cot, "montant_paye": cot if cot and (v("paiement_mode") or pdate) else 0,
                    "paiement_mode": v("paiement_mode") or None, "paiement_date": pdate}
        res.append({"personne": personne, "adhesion": adhesion, "erreurs": erreurs})
    noms = {i: n for i, n in enumerate(entetes)}
    return {"lignes": res, "colonnes": {c: noms[i] for c, i in corr.items()},
            "non_reconnues": [n for i, n in noms.items() if i not in corr.values() and n.strip()]}
