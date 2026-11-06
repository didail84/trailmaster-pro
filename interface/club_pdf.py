"""
Reçu de cotisation (étape 4.1) : une page A4 avec le club, l'adhérent, la
saison, la licence, le montant et le mode de paiement. Mise en page HTML
imprimée par Qt (pas de bibliothèque à installer).
"""

import html
from datetime import date

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from noyau.club import categories as cat


def _e(v):
    return html.escape(str(v or ""))


def _euros(v):
    t = f"{v or 0:,.2f}".replace(",", " ").replace(".", ",")
    return t + " €"


def _jour(d):
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y") if d else ""
    except ValueError:
        return str(d)


def html_recu(club, a):
    club = club or {}
    adresse_club = " ".join(x for x in (club.get("adresse"), club.get("code_postal"), club.get("ville")) if x)
    c = cat.categorie(a.get("date_naissance"), a.get("saison"))
    lignes = [("Saison", a.get("saison")),
              ("Licence", cat.LIBELLE_LICENCE.get(a.get("type_licence"), "—")),
              ("N° de licence", a.get("numero_licence") or "—"),
              ("Catégorie", f"{c['libelle']} ({c['code']})" if c else "—"),
              ("Tarif", a.get("tarif") or "—"),
              ("Montant reçu", _euros(a.get("montant_paye"))),
              ("Mode de paiement", a.get("paiement_mode") or "—"),
              ("Date du paiement", _jour(a.get("paiement_date")) or "—")]
    tableau = "".join(f"<tr><td style='color:#555;padding:6px 18px 6px 0'>{_e(k)}</td>"
                      f"<td style='padding:6px 0'><b>{_e(v)}</b></td></tr>" for k, v in lignes)
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:11pt">
<table width="100%"><tr>
<td><span style="font-size:18pt;font-weight:bold">{_e(club.get('nom') or 'Club')}</span><br>
<span style="color:#555">{_e(adresse_club)}</span><br>
<span style="color:#555">{_e(' · '.join(x for x in (club.get('email'), club.get('telephone')) if x))}</span><br>
<span style="color:#555">{'Affiliation FFA n° ' + _e(club['numero_ffa']) if club.get('numero_ffa') else ''}</span></td>
<td align="right" valign="top"><span style="font-size:14pt;font-weight:bold">Reçu n° {_e(a.get('recu_numero'))}</span><br>
<span style="color:#555">établi le {date.today().strftime('%d/%m/%Y')}</span></td>
</tr></table>
<hr>
<p style="font-size:14pt;font-weight:bold;margin-top:18px">Reçu de cotisation {_e(a.get('saison'))}</p>
<p>Le club atteste avoir reçu de <b>{_e(a.get('prenom'))} {_e(a.get('nom'))}</b>
{('(né(e) le ' + _jour(a.get('date_naissance')) + ')') if a.get('date_naissance') else ''}
la somme de <b>{_euros(a.get('montant_paye'))}</b> pour son adhésion et sa licence de la saison {_e(a.get('saison'))}.</p>
<table style="margin-top:12px">{tableau}</table>
<p style="margin-top:40px">Pour le club,<br><b>{_e(club.get('president') or '')}</b></p>
<p style="color:#777;font-size:9pt;margin-top:60px">Reçu établi avec Trail Hub Center. Ce reçu atteste un paiement ;
il ne vaut pas reçu fiscal pour don.</p>
</div>"""


def _imprimer(pdf, contenu):
    """Imprime le HTML dans le PDF à la bonne taille : les points (pt) du texte sont calculés pour la
    résolution du PDF, pas pour celle de l'écran."""
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(pdf)
    doc.setHtml(contenu)
    doc.setPageSize(QSizeF(pdf.width(), pdf.height()))
    doc.print_(pdf)


def rendre_recu(chemin, club, adhesion):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle(f"Reçu {adhesion.get('recu_numero')}")
    _imprimer(pdf, html_recu(club, adhesion))
    return chemin


# ----------------------------------------------------------------------
# Feuille d'appel (étape 4.2) : à imprimer pour la séance, avec les
# numéros à prévenir pour l'entraîneur.
# ----------------------------------------------------------------------

def html_feuille_appel(club, seance, lignes):
    from noyau.club import agenda as ag
    club = club or {}
    j = date.fromisoformat(str(seance["date"])[:10])
    jour = f"{ag.JOURS[j.weekday()]} {j.strftime('%d/%m/%Y')}"
    horaire = ""
    if seance.get("heure_debut"):
        horaire = seance["heure_debut"].replace(":", "h") + (f" – {seance['heure_fin'].replace(':', 'h')}"
                                                             if seance.get("heure_fin") else "")
    lettres = {"present": "P", "retard": "R", "excuse": "E", "absent": "A"}
    case = "<td align='center' width='5%' style='border:1px solid #999'>{}</td>"
    corps = ""
    for i, l in enumerate(lignes, 1):
        c = l.get("categorie")
        st = lettres.get(l.get("statut"))
        cases = "".join(case.format("<b>✕</b>" if st == x else "") for x in "PREA")
        corps += (f"<tr><td style='border:1px solid #999;padding:7px 4px'>{i}</td>"
                  f"<td style='border:1px solid #999;padding:7px 4px'><b>{_e(l['nom'])}</b> {_e(l['prenom'])}"
                  f"{'' if l.get('attendu', True) else ' <i>(invité)</i>'}</td>"
                  f"<td style='border:1px solid #999;padding:7px 4px'>{_e(c['code']) if c else ''}</td>{cases}"
                  f"<td style='border:1px solid #999;padding:7px 4px'>{_e(l.get('contact_urgence_tel') or '')}</td>"
                  f"<td style='border:1px solid #999;padding:4px;width:30%'>{_e(l.get('note') or '')}</td></tr>")
    for k in range(len(lignes) + 1, len(lignes) + 4):      # lignes vides pour les venus en plus
        corps += (f"<tr><td style='border:1px solid #999;padding:7px 4px'>{k}</td><td style='border:1px solid #999'>&nbsp;</td>"
                  "<td style='border:1px solid #999'></td>" + case.format("") * 4
                  + "<td style='border:1px solid #999'></td><td style='border:1px solid #999'></td></tr>")
    entete = "".join(f"<th width='{w}' style='border:1px solid #999;padding:4px;background:#eee'>{x}</th>"
                     for x, w in (("N°", "4%"), ("Nom", "28%"), ("Cat.", "6%"), ("P", "5%"), ("R", "5%"), ("E", "5%"),
                                  ("A", "5%"), ("Tél. à prévenir", "15%"), ("Remarque", "27%")))
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10pt">
<table width="100%"><tr><td><span style="font-size:15pt;font-weight:bold">Feuille d'appel</span><br>
<span style="color:#555">{_e(club.get('nom') or '')}</span></td>
<td align="right"><b>{_e(seance['titre'])}</b><br>{_e(jour)}{(' · ' + _e(horaire)) if horaire else ''}<br>
<span style="color:#555">{_e(seance.get('groupe') or 'Tout le club')}{(' · ' + _e(seance['lieu'])) if seance.get('lieu') else ''}
{(' · ' + _e(seance['entraineur'])) if seance.get('entraineur') else ''}</span></td></tr></table>
{('<p style="color:#555"><i>' + _e(seance['contenu']) + '</i></p>') if seance.get('contenu') else ''}
<table cellspacing="0" width="100%" style="margin-top:8px;border-collapse:collapse"><tr>{entete}</tr>{corps}</table>
<p style="color:#555;font-size:9pt;margin-top:10px">P = présent · R = en retard · E = excusé · A = absent.
À reporter dans Trail Hub Center, onglet Présences. Feuille confidentielle : à ne pas laisser traîner.</p>
<p style="margin-top:18px">Entraîneur : ............................................ Signature :</p>
</div>"""


def rendre_feuille_appel(chemin, club, seance, lignes):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle(f"Feuille d'appel {seance['date']}")
    _imprimer(pdf, html_feuille_appel(club, seance, lignes))
    return chemin


# ----------------------------------------------------------------------
# Feuille de retrait des dossards (étape 4.4) : une ligne par coureur
# validé, case « remis » et signature.
# ----------------------------------------------------------------------

def html_retrait_dossards(evenement, inscriptions):
    ev = evenement or {}
    j = date.fromisoformat(str(ev.get("date_debut"))[:10]) if ev.get("date_debut") else None
    bord = "border:1px solid #999;padding:6px 4px"
    corps = ""
    for i in sorted(inscriptions, key=lambda x: (x.get("dossard") or 10 ** 9, x["nom"].lower())):
        d = i.get("dossier") or {}
        manque = "" if d.get("complet", True) else ", ".join(d.get("manques", []))
        corps += (f"<tr><td style='{bord}' align='right'><b>{_e(i.get('dossard') or '')}</b></td>"
                  f"<td style='{bord}'><b>{_e(i['nom'])}</b> {_e(i.get('prenom') or '')}</td>"
                  f"<td style='{bord}'>{_e(i.get('epreuve') or '')}</td><td style='{bord}'>{_e(i.get('taille_tshirt') or '')}</td>"
                  f"<td style='{bord};color:#B71C1C'>{_e(manque)}</td>"
                  f"<td style='{bord}' align='center'>{'✕' if i.get('dossard_retire') else ''}</td>"
                  f"<td style='{bord}'>&nbsp;</td></tr>")
    entete = "".join(f"<th width='{w}' style='{bord};background:#eee'>{x}</th>" for x, w in (
        ("Dossard", "8%"), ("Nom", "28%"), ("Épreuve", "16%"), ("T-shirt", "8%"), ("À régler au retrait", "20%"),
        ("Remis", "6%"), ("Signature", "14%")))
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10pt">
<p><span style="font-size:15pt;font-weight:bold">Retrait des dossards</span><br>
<b>{_e(ev.get('nom') or '')}</b> · {j.strftime('%d/%m/%Y') if j else ''} · {_e(ev.get('commune') or '')}</p>
<table cellspacing="0" width="100%" style="border-collapse:collapse"><tr>{entete}</tr>{corps}</table>
<p style="color:#555;font-size:9pt">Les dossiers incomplets (licence, Pass Prévention Santé, autorisation parentale,
paiement) se règlent avant de remettre le dossard. Feuille confidentielle.</p>
</div>"""


def rendre_retrait_dossards(chemin, evenement, inscriptions):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle("Retrait des dossards")
    _imprimer(pdf, html_retrait_dossards(evenement, inscriptions))
    return chemin


# ----------------------------------------------------------------------
# Classement d'une épreuve (étape 4.5)
# ----------------------------------------------------------------------

def html_classement(evenement, epreuve, lignes):
    ev = evenement or {}
    j = date.fromisoformat(str(ev.get("date_debut"))[:10]) if ev.get("date_debut") else None
    bord = "border:1px solid #bbb;padding:4px 3px"
    corps = ""
    for l in lignes:
        corps += "<tr>" + "".join(f"<td style='{bord}'{a}>{_e(v)}</td>" for v, a in (
            (l.get("rang") or "", " align='right'"), (l.get("dossard") or "", " align='right'"),
            (f"{l['nom']} {l.get('prenom') or ''}", ""), (l["categorie"], ""), (l.get("rang_categorie") or "", " align='right'"),
            (l.get("club") or "", ""), (l["temps"], " align='right'"), (l.get("ecart") or "", " align='right'"),
            ((f"{l['vitesse']:.2f}".replace(".", ",") if l.get("vitesse") else ""), " align='right'"))) + "</tr>"
    entete = "".join(f"<th style='{bord};background:#eee'>{x}</th>" for x in (
        "Clt", "Dos.", "Nom", "Cat.", "Clt cat.", "Club", "Temps", "Écart", "km/h"))
    n = sum(1 for l in lignes if l.get("statut") == "classe")
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:9pt">
<p><span style="font-size:15pt;font-weight:bold">{_e(ev.get('nom') or '')}</span><br>
<b>Classement {_e(epreuve)}</b> · {j.strftime('%d/%m/%Y') if j else ''} · {_e(ev.get('commune') or '')} · {n} classé(s)</p>
<table cellspacing="0" width="100%" style="border-collapse:collapse"><tr>{entete}</tr>{corps}</table>
<p style="color:#777;font-size:8pt">Résultats établis avec Trail Hub Center. ABD : abandon · DSQ : disqualifié · NP : non partant.</p>
</div>"""


def rendre_classement(chemin, evenement, epreuve, lignes):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle(f"Classement {epreuve}")
    _imprimer(pdf, html_classement(evenement, epreuve, lignes))
    return chemin
