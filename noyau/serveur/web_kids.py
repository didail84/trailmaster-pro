"""
Pages Kids du serveur (chantier D) : l'entraîneur ouvre le carnet d'un enfant de son association et coche les
compétences ; le parent voit seulement le carnet, les badges et les prochaines séances de SES enfants.
"""

import html
from datetime import datetime

from noyau.donnees import comptes as dco, kids as dki, club as dclub
from noyau.serveur import droits as D, web


def _e(v):
    return html.escape("" if v is None else str(v))


def _peut_encadrer(compte, personne_id):
    """Bureau ou entraîneur d'une association où l'enfant est adhérent (ou administrateur)."""
    sc = D.clubs_de(compte["roles"])
    if sc is None:
        return True
    from noyau.serveur import rpc
    clubs, _e2 = rpc.liens_personne(personne_id)
    return any(r["role"] in ("bureau", "entraineur") and r.get("club_id") in clubs for r in compte["roles"])


def _est_parent(compte, personne_id):
    return bool(compte.get("personne_id")) and personne_id in dki.enfants_du_parent(compte["personne_id"])


def _carnet_html(c, csrf=None, modifiable=False, enfant_id=None):
    p = c["personne"]
    blocs = ""
    for n in c["niveaux"]:
        lignes = ""
        for x in n["competences"]:
            if modifiable:
                lignes += (f"<form method='post' action='/m/kids?enfant={enfant_id}'>{web._champ_csrf(csrf)}"
                           f"<input type='hidden' name='competence' value='{x['id']}'><input type='hidden' name='valide' "
                           f"value='{0 if x['validee'] else 1}'><button type='submit' class='{'' if x['validee'] else 'second'}' "
                           f"style='text-align:left;font-size:16px;font-weight:400'>{'✅' if x['validee'] else '⬜'} {_e(x['libelle'])}"
                           f"</button></form>")
            else:
                lignes += f"<tr><td>{'✅' if x['validee'] else '⬜'}</td><td>{_e(x['libelle'])}</td></tr>"
        blocs += (f"<h2>{_e(n['icone'])} {_e(n['libelle'])} · {n['faites']} / {n['total']}</h2>"
                  + (lignes if modifiable else f"<div class='carte'><table>{lignes}</table></div>"))
    badges = " · ".join(_e(b["libelle"]) for b in c["badges"]) or "pas encore"
    return (f"<div class='carte'><b>{_e(p['prenom'])} {_e(p['nom'])}</b><br><span class='petit'>"
            f"{_e(c['categorie']['libelle']) if c['categorie'] else ''} · {c['presences']} entraînement(s)</span>"
            f"<br>🏅 {badges}</div>" + blocs
            + (f"<p class='petit'>Repères FFA : {_e(' ; '.join(c['reperes']))}</p>" if c["reperes"] else "")
            + "<p class='petit'>Chaque enfant progresse à son rythme : pas de classement.</p>")


def gerer_kids(handler, compte, csrf, verbe, chemin, q, f):
    if "kids" not in D.pages_autorisees(compte["roles"]):
        return handler._refus(compte)
    enfant = int(q["enfant"]) if str(q.get("enfant") or "").isdigit() else None
    if enfant is None:
        return handler._envoyer(200, _liste(compte))
    encadre, parent = _peut_encadrer(compte, enfant), _est_parent(compte, enfant)
    if not (encadre or parent):
        return handler._refus(compte)
    msg = ""
    if verbe == "POST" and encadre and str(f.get("competence") or "").isdigit():
        cid = int(f["competence"])
        if f.get("valide") == "1":
            nouveaux = dki.valider(enfant, cid, compte.get("nom_affiche") or compte["identifiant"])
            msg = ("🎉 Nouveau badge : " + ", ".join(nouveaux)) if nouveaux else "Compétence validée."
        else:
            dki.retirer_validation(enfant, cid)
            msg = "Validation retirée."
        dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.kids", detail=f"enfant {enfant} compétence {cid}",
                        adresse=handler._ip())
    c = dki.carnet(enfant)
    corps = (f"<div class='carte ok'>{_e(msg)}</div>" if msg else "") + _carnet_html(c, csrf, encadre, enfant)
    if parent:
        ss = dki.seances_de_l_enfant(enfant)
        corps += "<h2>Prochaines séances</h2><div class='carte'><table>" + ("".join(
            f"<tr><td>{web.jour_fr(s['date'], True)} {_e(s.get('heure_debut') or '')}</td><td>{_e(s['titre'])}"
            f"{' <b>(annulée)</b>' if s.get('annulee') else ''}<br><span class='petit'>{_e(s.get('lieu') or '')}</span></td></tr>"
            for s in ss) or "<tr><td class='petit'>Rien de prévu.</td></tr>") + "</table></div>"
    return handler._envoyer(200, web.page("Carnet de progression", corps, compte))


def _liste(compte):
    liens = []
    if compte.get("personne_id"):
        from noyau.donnees import personnes as dper
        for eid in dki.enfants_du_parent(compte["personne_id"]):
            f = dper.fiche(eid)
            if f:
                liens.append(f"<a class='lien' href='/m/kids?enfant={eid}'>🧒 {_e(f['prenom'])} {_e(f['nom'])}</a>")
    sc = D.clubs_de(compte["roles"])
    if any(r["role"] in ("bureau", "entraineur", "admin") for r in compte["roles"]):
        for c in dclub.clubs():
            if sc is not None and c["id"] not in {r.get("club_id") for r in compte["roles"]
                                                   if r["role"] in ("bureau", "entraineur")}:
                continue
            es = dki.enfants(c["id"])
            if es:
                liens.append(f"<h2>{_e(c['nom'])}</h2>" + "".join(
                    f"<a class='lien' href='/m/kids?enfant={e['personne_id']}'>{_e(e['nom'])} {_e(e['prenom'] or '')}"
                    f"<br><span class='petit'>{_e(e['categorie']['libelle'] if e['categorie'] else '')} · {e['nb_badges']} badge(s)"
                    f"</span></a>" for e in es))
    return web.page("Kids", "".join(liens) or "<div class='carte att'>Aucun enfant à afficher.</div>", compte)


PAGES = {"/m/kids": gerer_kids}
