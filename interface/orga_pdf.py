"""
Documents PDF de la logistique d'une course (étape 4.6) : rétroplanning,
planning des postes, convocations des bénévoles, liste des signaleurs,
plan des ravitaillements et liste de courses, check-list du matériel,
budget, reçu de don, courriers. HTML imprimé par Qt (rien à installer).
"""

import html
from datetime import date

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter

from interface.club_pdf import _imprimer
from noyau.organisation import logistique as L

SAUT = "<div style='page-break-before: always'></div>"


def _e(v):
    return html.escape(str(v if v is not None else ""))


def _euros(v):
    t = f"{float(v or 0):,.2f}".replace(",", " ").replace(".", ",")
    return t + " €"


def _jour(d):
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y") if d else ""
    except ValueError:
        return str(d)


def _entete(titre, ev, sous=""):
    return (f"<div style='font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10pt'>"
            f"<p style='font-size:16pt;font-weight:bold;margin:0'>{_e(titre)}</p>"
            f"<p style='color:#555;margin:2px 0 10px 0'>{_e(ev['nom'])} · {_jour(ev['date_debut'])}"
            f"{' · ' + _e(ev.get('commune')) if ev.get('commune') else ''}{' · ' + _e(sous) if sous else ''}</p>")


def _tableau(entetes, lignes, largeurs=None):
    th = "".join(f"<th align='left' style='background:#eee;padding:4px'{(' width=' + str(largeurs[i]) + '%') if largeurs else ''}>"
                 f"{_e(h)}</th>" for i, h in enumerate(entetes))
    tr = "".join("<tr>" + "".join(f"<td style='padding:4px;border-bottom:1px solid #ddd' valign='top'>{c}</td>" for c in l)
                 + "</tr>" for l in lignes)
    return f"<table width='100%' cellspacing='0' style='border-collapse:collapse'><tr>{th}</tr>{tr}</table>"


def _pied():
    return f"<p style='color:#888;font-size:8pt;margin-top:14px'>Trail Hub Center · imprimé le {date.today().strftime('%d/%m/%Y')}</p></div>"


def rendre(chemin, titre, contenu, paysage=False):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                  QPageLayout.Orientation.Landscape if paysage else QPageLayout.Orientation.Portrait,
                                  QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle(titre)
    _imprimer(pdf, contenu)
    return chemin


# ---------------------------------------------------------------- documents

def html_retroplanning(ev, demarches):
    lignes = [(f"<b>{_e(d['jalon'])}</b><br>{_jour(d['echeance'])}", f"<b>{_e(d['titre'])}</b>"
               + (f"<br><span style='color:#555'>{_e(d.get('conseil'))}</span>" if d.get("conseil") else ""),
               _e(d.get("autorite")), _e(d.get("pieces")),
               _e(L.LIBELLE_STATUT.get(d["statut"], "")) + (f"<br><span style='color:#c62828'>{_e(d['etat'])}</span>"
                                                            if d.get("etat") == "en retard" else ""),
               "☐" if d["statut"] not in L.FINIS else "☑")
              for d in demarches if d["statut"] != "sans_objet"]
    return (_entete("Rétroplanning et démarches", ev) +
            _tableau(["Quand", "Démarche", "Auprès de", "Pièces", "Statut", "Fait"], lignes, [10, 34, 17, 24, 10, 5]) +
            "<p style='color:#555;font-size:8pt'>Rappels réglementaires à jour de novembre 2026 : vérifie toujours auprès de la "
            "mairie, de la préfecture et du comité FFA.</p>" + _pied())


def html_planning_postes(ev, postes):
    lignes = []
    for p in postes:
        noms = ", ".join(f"{b.get('prenom') or ''} {b['nom']}".strip() + (f" ({b['telephone']})" if b.get("telephone") else "")
                         for b in p["benevoles"])
        manque = int(p.get("besoin") or 0) - len(p["benevoles"])
        lignes.append((f"<b>{_e(p['nom'])}</b><br><span style='color:#555'>{_e(p.get('libelle_type'))}</span>",
                       f"{_jour(p.get('jour'))}<br>{_e(p.get('heure_debut') or '')} – {_e(p.get('heure_fin') or '')}",
                       _e(p.get("lieu") or "") + (f" (km {p['km']:g})" if p.get("km") else ""),
                       f"{len(p['benevoles'])} / {p.get('besoin') or 0}"
                       + (f"<br><span style='color:#c62828'>manque {manque}</span>" if manque > 0 else ""),
                       _e(noms) or "<span style='color:#c62828'>personne</span>"))
    return (_entete("Planning des bénévoles", ev) +
            _tableau(["Poste", "Horaires", "Lieu", "Pourvu", "Bénévoles"], lignes, [22, 14, 20, 10, 34]) + _pied())


def html_convocations(ev, benevoles, postes, contact=""):
    """Une page par bénévole : ses postes, horaires, lieux et consignes."""
    pages = []
    for b in benevoles:
        sien = [p for p in postes if any(x["id"] == b["id"] for x in p["benevoles"])]
        if not sien:
            continue
        blocs = "".join(
            f"<p style='font-size:12pt;margin:14px 0 2px 0'><b>{_e(p['nom'])}</b></p>"
            f"<p style='margin:0'>{_jour(p.get('jour'))}, de {_e(p.get('heure_debut') or '?')} à {_e(p.get('heure_fin') or '?')}"
            f" · {_e(p.get('lieu') or '')}{(' (km ' + format(p['km'], 'g') + ')') if p.get('km') else ''}</p>"
            + (f"<p style='margin:4px 0;color:#333'>{_e(p['consignes'])}</p>" if p.get("consignes") else "")
            + (f"<p style='margin:4px 0;color:#555'>Avec : {_e(', '.join((x.get('prenom') or '') + ' ' + x['nom'] for x in p['benevoles'] if x['id'] != b['id']))}</p>"
               if len(p["benevoles"]) > 1 else "")
            for p in sien)
        pages.append(_entete(f"Convocation · {(b.get('prenom') or '')} {b['nom']}".strip(), ev) + blocs +
                     "<p style='margin-top:18px'><b>Rappels</b> : gilet haute visibilité pour les postes sur la route, "
                     "téléphone chargé, eau et vêtements chauds. En cas d'accident : protéger, alerter le PC course, "
                     "ne pas déplacer la personne.</p>"
                     + (f"<p><b>PC course</b> : {_e(contact)}</p>" if contact else "") + "</div>")
    return SAUT.join(pages) or (_entete("Convocations", ev) + "<p>Aucun bénévole n'a encore de poste.</p></div>")


def html_signaleurs(ev, liste, organisateur=""):
    lignes = [(_e(s["nom"]), _e(s.get("prenom") or ""), _jour(s.get("date_naissance")), "", _e(s.get("telephone") or ""),
               _e(s["poste"]) + (f"<br>{_e(s['lieu'])}" if s.get("lieu") else ""), _e(s.get("horaires") or ""))
              for s in liste]
    return (_entete("Liste des signaleurs", ev, organisateur) +
            "<p>Signaleurs majeurs, titulaires du permis de conduire, identifiables (gilet haute visibilité) et munis "
            "d'un panneau ou d'un drapeau. Le numéro de permis est à compléter à la main.</p>" +
            _tableau(["Nom", "Prénom", "Naissance", "N° de permis", "Téléphone", "Poste", "Horaires"], lignes,
                     [15, 13, 11, 16, 13, 20, 12]) + _pied())


def html_ravitaillements(ev, ravitos, courses):
    lignes = [(f"<b>{_e(r['nom'])}</b><br>{_e(r.get('lieu') or '')}", f"{r['km']:g}" if r.get("km") is not None else "",
               _e(r.get("libelle_type")), _e(", ".join(r.get("epreuves") or [])), str(r.get("coureurs") or 0),
               f"{_e(r.get('ouverture') or '')}" + (f"<br>barrière {_e(r['barriere_horaire'])}" if r.get("barriere_horaire") else ""),
               "<br>".join(f"{_e(p)} : {q:g} {_e(u)}" for p, q, u in r.get("quantites") or []))
              for r in ravitos]
    tot = [(_e(p), f"{q:g} {_e(u)}", "☐") for p, (q, u) in sorted(courses.items())]
    return (_entete("Ravitaillements", ev) +
            _tableau(["Ravitaillement", "Km", "Type", "Épreuves", "Coureurs", "Horaires", "Quantités"], lignes,
                     [18, 5, 12, 15, 7, 11, 32]) +
            "<p style='font-size:12pt;font-weight:bold;margin-top:16px'>Liste de courses (tous les ravitaillements)</p>" +
            _tableau(["Produit", "Quantité", "Acheté"], tot, [60, 30, 10]) +
            "<p style='color:#555;font-size:8pt'>Quantités indicatives avec 15 % de marge (plus d'eau de juin à septembre) : "
            "à ajuster après la première édition.</p>" + _pied())


def html_materiel(ev, materiel):
    lignes, cat = [], None
    for m in materiel:
        if m.get("categorie") != cat:
            cat = m.get("categorie")
            lignes.append((f"<b>{_e(cat or 'Divers')}</b>", "", "", "", "", "", ""))
        lignes.append(("☐", _e(m["article"]), f"{m['quantite']} {_e(m.get('unite') or '')}", str(m.get("disponible") or 0),
                       _e(m.get("fournisseur") or ""), _e(m.get("lieu") or ""),
                       _e(L.LIBELLE_STATUT_MATERIEL.get(m.get("statut"), ""))))
    return (_entete("Check-list du matériel", ev) +
            _tableau(["", "Article", "Besoin", "Dispo", "Prêté / loué par", "Où", "Statut"], lignes, [4, 30, 13, 7, 18, 16, 12])
            + _pied())


def html_budget(ev, b):
    def bloc(titre, lignes, tot_p, tot_r):
        rows = [(_e(l.get("categorie") or ""), _e(l["libelle"]) + (" <span style='color:#888'>(par coureur)</span>"
                                                                    if l.get("par_coureur") else ""),
                 _euros(l.get("prevu_total", l.get("prevu"))), _euros(l["realise"]) if l.get("realise") is not None else "")
                for l in lignes]
        rows.append(("", "<b>Total</b>", f"<b>{_euros(tot_p)}</b>", f"<b>{_euros(tot_r)}</b>"))
        return (f"<p style='font-size:12pt;font-weight:bold;margin-top:12px'>{titre}</p>" +
                _tableau(["Catégorie", "Libellé", "Prévu", "Réalisé"], rows, [25, 45, 15, 15]))
    seuil = (f"{b['seuil']} coureurs" if b.get("seuil") else "atteint" if b.get("seuil") == 0 else "impossible au tarif actuel")
    return (_entete("Budget de la course", ev) +
            bloc("Recettes", b["recettes"], b["recettes_prevues"], b["recettes_realisees"]) +
            bloc("Dépenses", b["depenses"], b["depenses_prevues"], b["depenses_realisees"]) +
            f"<p style='font-size:12pt;margin-top:12px'>Solde prévu : <b>{_euros(b['solde_prevu'])}</b> · "
            f"solde réalisé : <b>{_euros(b['solde_realise'])}</b></p>"
            f"<p>Tarif moyen {_euros(b.get('tarif_moyen'))} · seuil de rentabilité : <b>{seuil}</b> "
            f"(dépenses fixes {_euros(b['fixe'])}, coût par coureur {_euros(b['variable_par_coureur'])}).</p>" + _pied())


def html_recu_don(club, p, ev):
    """Reçu au titre des dons à certains organismes d'intérêt général (mentions de l'imprimé officiel : Cerfa
    11580 pour un particulier, 16216 pour une entreprise)."""
    club = club or {}
    av = L.avantage_fiscal(p.get("montant") or p.get("valeur_nature"), bool(p.get("particulier")))
    adresse = " ".join(x for x in (club.get("adresse"), club.get("code_postal"), club.get("ville")) if x) or "[adresse]"
    nature = p.get("type") == "nature"
    montant = p.get("valeur_nature") if nature else p.get("montant")
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10.5pt">
<table width="100%"><tr><td><span style="font-size:15pt;font-weight:bold">Reçu au titre des dons</span><br>
<span style="color:#555">à certains organismes d'intérêt général ({'article 200' if p.get('particulier') else 'article 238 bis'}
du code général des impôts)</span></td>
<td align="right" valign="top"><b>Reçu n° {_e(p.get('recu_numero'))}</b></td></tr></table>
<hr>
<p style="font-weight:bold;margin-top:12px">Bénéficiaire des versements</p>
<p>{_e(club.get('nom') or '[association]')}<br>{_e(adresse)}<br>
Objet : association sportive{(' affiliée à la FFA (n° ' + _e(club['numero_ffa']) + ')') if club.get('numero_ffa') else ''},
organisation du « {_e(ev['nom'])} ».<br>
Organisme d'intérêt général (association loi 1901 à gestion désintéressée).</p>
<p style="font-weight:bold;margin-top:12px">Donateur</p>
<p>{_e(p['nom'])}{('<br>SIREN ' + _e(p['siren'])) if p.get('siren') else ''}<br>{_e(p.get('adresse') or '[adresse du donateur]')}</p>
<p style="font-weight:bold;margin-top:12px">Don</p>
<p>Le bénéficiaire reconnaît avoir reçu au titre des dons et versements ouvrant droit à réduction d'impôt la somme de
<b>{_euros(montant)}</b>{(' (valeur du don en nature : ' + _e(p.get('description_nature')) + ')') if nature else ''}.</p>
<p>Date du versement : <b>{_jour(p.get('date_versement')) or '[date]'}</b><br>
Forme du don : {'don en nature' if nature else 'versement en numéraire'}<br>
Mode de versement : {_e(p.get('mode_versement') or ('—' if nature else '[virement, chèque, espèces]'))}</p>
<p>Le donateur ne reçoit aucune contrepartie, ou des contreparties de faible valeur sans rapport avec le montant du don.</p>
<p style="margin-top:24px">Fait le {date.today().strftime('%d/%m/%Y')}, à {_e(club.get('ville') or '[ville]')}<br><br>
Signature : {_e(club.get('president') or '[président·e]')}</p>
<p style="color:#555;font-size:8.5pt;margin-top:24px">Pour information : réduction d'impôt de {av['taux']} % ({_euros(av['reduction'])}),
plafond {_e(av['plafond'])}. L'association doit être d'intérêt général : en cas de doute, un rescrit fiscal est conseillé.
Les organismes qui délivrent des reçus déclarent chaque année le montant global des dons reçus et le nombre de reçus
délivrés (article 222 bis du livre des procédures fiscales).</p>
</div>"""


def html_courrier(texte):
    corps = "<br>".join(_e(l) for l in texte.splitlines())
    return f"<div style='font-family:Helvetica,Arial,sans-serif;color:#111;font-size:11pt;line-height:140%'>{corps}</div>"
