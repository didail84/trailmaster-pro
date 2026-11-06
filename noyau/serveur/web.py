"""
Pages web du serveur pour le téléphone (étape 5) : connexion, accueil selon
les rôles, saisie des arrivées au chrono, appel des présences, mon poste de
bénévole, mes résultats. HTML simple et formulaires classiques, sans
JavaScript : elles s'ouvrent sur un vieux téléphone.

Chaque page vérifie le rôle (droits.PAGES) et le périmètre (association ou
événement) du compte. Les écritures passent par noyau/donnees et sont
écrites au journal des accès.
"""

import html
from datetime import date, datetime, timedelta
from urllib.parse import quote

from noyau.donnees import comptes as dco
from noyau.serveur import droits as D

CSS = """
:root{--f:#f6f7f5;--c:#fff;--t:#1d2320;--d:#5b6660;--b:#d9ddd9;--a:#2e7d32;--bt:#fff;--r:#c62828;--o:#e65100}
@media (prefers-color-scheme:dark){:root{--f:#121614;--c:#1b201d;--t:#e8ece9;--d:#9aa69f;--b:#2c3530;--a:#66bb6a;--bt:#0b1f0d;--r:#ef5350;--o:#ffa726}}
*{box-sizing:border-box}body{margin:0;background:var(--f);color:var(--t);font:17px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
header{background:var(--c);border-bottom:1px solid var(--b);padding:10px 16px}header a{color:var(--d);text-decoration:none;font-size:15px}
main{padding:12px 16px;max-width:640px;margin:0 auto}h1{font-size:21px;margin:8px 0 12px}h2{font-size:18px;margin:18px 0 8px}
.carte{background:var(--c);border:1px solid var(--b);border-radius:12px;padding:12px 14px;margin:0 0 12px}
a.lien{display:block;padding:12px 14px;margin:0 0 8px;background:var(--c);border:1px solid var(--b);border-radius:12px;color:var(--t);text-decoration:none}
label{display:block;margin:8px 0 4px;color:var(--d);font-size:15px}
input,select{width:100%;font-size:20px;padding:10px;border:1px solid var(--b);border-radius:10px;background:var(--c);color:var(--t)}
input.dossard{font-size:34px;text-align:center;letter-spacing:2px}
button{width:100%;font-size:19px;padding:13px;margin:10px 0 0;border:0;border-radius:10px;background:var(--a);color:var(--bt);font-weight:600}
button.second{background:var(--b);color:var(--t)}
.ok{border-left:5px solid var(--a)}.err{border-left:5px solid var(--r)}.att{border-left:5px solid var(--o)}
.petit{font-size:14px;color:var(--d)}table{width:100%;border-collapse:collapse}td{padding:7px 4px;border-bottom:1px solid var(--b);vertical-align:top}
.droite{text-align:right}.ligne{display:flex;gap:8px}.ligne>*{flex:1}
"""


JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def jour_fr(iso, court=False):
    """« vendredi 06/11/2026 » ou « ven. 06/11 »."""
    d = datetime.fromisoformat(str(iso)[:10])
    return f"{JOURS[d.weekday()][:3]}. {d:%d/%m}" if court else f"{JOURS[d.weekday()]} {d:%d/%m/%Y}"


def page(titre, corps, compte=None):
    nav = ""
    if compte:
        nav = (f"<header><a href='/m/'>🏁 Trail Hub · {html.escape(compte.get('nom_affiche') or compte['identifiant'])}</a>"
               f" &nbsp; <a href='/m/deconnexion' style='float:right'>Se déconnecter</a></header>")
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            f"initial-scale=1'><meta name='color-scheme' content='light dark'><title>{html.escape(titre)}</title><style>{CSS}"
            f"</style></head><body>{nav}<main><h1>{html.escape(titre)}</h1>{corps}</main></body></html>")


def _e(v):
    return html.escape("" if v is None else str(v))


def _champ_csrf(csrf):
    return f"<input type='hidden' name='csrf' value='{_e(csrf)}'>"


def connexion(message="", identifiant=""):
    m = f"<div class='carte err'>{_e(message)}</div>" if message else ""
    return page("Connexion", m + f"""<form method='post' action='/m/connexion' class='carte'>
<label for='i'>Identifiant</label><input id='i' name='identifiant' autocomplete='username' autocapitalize='none' value='{_e(identifiant)}' required>
<label for='p'>Mot de passe</label><input id='p' name='mot_de_passe' type='password' autocomplete='current-password' required>
<button type='submit'>Se connecter</button></form>
<p class='petit'>Le serveur Trail Hub de ton club. Ton compte est créé par le bureau ou l'organisateur.</p>""")


def changer_mot_de_passe(compte, csrf, message="", impose=False):
    m = f"<div class='carte err'>{_e(message)}</div>" if message else ""
    intro = "<p>Choisis ton mot de passe (10 caractères au moins, des lettres et des chiffres).</p>" if impose else ""
    return page("Mot de passe", m + intro + f"""<form method='post' action='/m/mot-de-passe' class='carte'>{_champ_csrf(csrf)}
<label>Mot de passe actuel</label><input name='ancien' type='password' autocomplete='current-password' required>
<label>Nouveau mot de passe</label><input name='nouveau' type='password' autocomplete='new-password' required>
<label>Encore une fois</label><input name='nouveau2' type='password' autocomplete='new-password' required>
<button type='submit'>Enregistrer</button></form>""", compte)


def accueil(compte):
    from noyau.donnees import organisation as dor, agenda_club as dag
    roles = compte["roles"]
    pages = D.pages_autorisees(roles)
    sc, se = D.clubs_de(roles), D.evenements_de(roles)
    blocs = []
    evs = [e for e in dor.evenements() if se is None or e["id"] in se or (sc and e.get("club_id") in sc)]
    evs = [e for e in evs if e["date_debut"] >= (date.today() - timedelta(days=3)).isoformat()][:6]
    for e in evs:
        liens = []
        if "chrono" in pages:
            liens.append(f"<a class='lien' href='/m/chrono?ev={e['id']}'>⏱️ Arrivées au chrono</a>")
        if "poste" in pages:
            liens.append(f"<a class='lien' href='/m/poste?ev={e['id']}'>🙋 Mon poste de bénévole</a>")
        if "incident" in pages:
            liens.append(f"<a class='lien' href='/m/incident?ev={e['id']}'>🚑 Signaler un incident</a>")
        if "commandement" in pages:
            liens.append(f"<a class='lien' href='/m/commandement?ev={e['id']}'>🧭 Tableau de commandement</a>")
        if liens:
            blocs.append(f"<h2>{_e(e['nom'])} · {datetime.fromisoformat(e['date_debut']).strftime('%d/%m/%Y')}</h2>" + "".join(liens))
    if "appel" in pages:
        from noyau.donnees import club as dclub
        auj = date.today()
        clubs = [c for c in dclub.clubs() if sc is None or c["id"] in sc]
        ss = []
        for c in clubs:
            ss += [(c, s) for s in dag.seances(c["id"], auj - timedelta(days=2), auj + timedelta(days=1), avec_annulees=False)]
        if ss:
            blocs.append("<h2>Appel des présences</h2>" + "".join(
                f"<a class='lien' href='/m/appel?seance={s['id']}'>✅ {jour_fr(s['date'], True)} "
                f"{_e(s.get('heure_debut') or '')} · {_e(s['titre'])}<br><span class='petit'>{_e(c['nom'])} · "
                f"{_e(s.get('groupe') or 'toute l’association')}{' · appel fait' if s.get('appel_fait') else ''}</span></a>"
                for c, s in ss))
    if "kids" in pages:
        blocs.append("<a class='lien' href='/m/kids'>🧒 École d'athlé : carnet de progression</a>")
    if "resultats" in pages and compte.get("personne_id"):
        blocs.append("<a class='lien' href='/m/resultats'>🏅 Mes résultats</a>")
    blocs.append("<a class='lien' href='/m/mot-de-passe'>🔑 Changer mon mot de passe</a>")
    if not blocs[:-1]:
        blocs.insert(0, "<div class='carte att'>Ton compte n'a pas encore de rôle : demande au bureau ou à l'organisateur.</div>")
    return page("Trail Hub", "".join(blocs), compte)


# ------------------------------------------------------------------ chrono

def peut_evenement(compte, page_code, evenement_id):
    from noyau.donnees import organisation as dor
    roles = compte["roles"]
    if page_code not in D.pages_autorisees(roles):
        return False
    se, sc = D.evenements_de(roles), D.clubs_de(roles)
    if se is None:
        return True
    ev = dor.evenement(evenement_id)
    if not ev:
        return False
    return any((r["role"] in ("organisateur", "benevole") and r.get("evenement_id") == evenement_id and page_code in D.PAGES[r["role"]])
               or (r["role"] == "bureau" and r.get("club_id") == ev.get("club_id") and page_code in D.PAGES["bureau"])
               for r in roles)


def chrono(compte, csrf, evenement_id, message=None, classe="ok"):
    from noyau.donnees import organisation as dor, chrono as dch
    ev = dor.evenement(evenement_id)
    ins = {i["dossard"]: i for i in dor.inscriptions(evenement_id) if i.get("dossard")}
    eps = {e["id"]: e for e in dor.epreuves(evenement_id)}
    ps = list(reversed(dch.passages(evenement_id)))[:15]
    m = f"<div class='carte {classe}'>{message}</div>" if message else ""
    departs = "".join(f"<tr><td>{_e(e['nom'])}</td><td class='droite'>"
                      f"{datetime.fromisoformat(e['depart_reel']).strftime('%H:%M:%S') if e.get('depart_reel') else '<span class=petit>pas parti</span>'}</td></tr>"
                      for e in eps.values())
    lignes = ""
    for p in ps:
        i = ins.get(p["dossard"])
        lignes += (f"<tr><td>{datetime.fromisoformat(p['heure']).strftime('%H:%M:%S')}</td><td><b>{_e(p['dossard'])}</b></td>"
                   f"<td>{_e((i['prenom'] or '') + ' ' + i['nom']) if i else '<span class=petit>inconnu</span>'}</td></tr>")
    return page(f"Chrono · {ev['nom']}", m + f"""<form method='post' action='/m/chrono?ev={evenement_id}' class='carte'>{_champ_csrf(csrf)}
<label for='d'>Dossard qui passe la ligne</label><input id='d' class='dossard' name='dossard' inputmode='numeric' pattern='[0-9]*' autocomplete='off' autofocus required>
<button type='submit'>Top arrivée</button></form>
<form method='post' action='/m/chrono-annuler?ev={evenement_id}'>{_champ_csrf(csrf)}<button class='second' type='submit'>Annuler mon dernier top</button></form>
<h2>Départs</h2><div class='carte'><table>{departs}</table></div>
<h2>Derniers passages</h2><div class='carte'><table>{lignes or "<tr><td class='petit'>Aucun passage.</td></tr>"}</table></div>
<p class='petit'>L'heure est celle du serveur au moment du top. Un double top de moins de 5 secondes est ignoré.</p>""", compte)


def top_chrono(compte, evenement_id, dossard, adresse=None):
    """Renvoie (message HTML, classe)."""
    from noyau.donnees import chrono as dch, organisation as dor
    try:
        n = int(str(dossard).strip())
    except ValueError:
        return "Numéro de dossard illisible.", "err"
    r = dch.ajouter_passage(evenement_id, n, source=f"web:{compte['identifiant']}")
    dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.chrono", detail=f"ev {evenement_id} dossard {n}",
                    adresse=adresse)
    i = r["inscrit"]
    temps = ""
    if i:
        e = next((x for x in dor.epreuves(evenement_id) if x["id"] == i["epreuve_id"]), None)
        if e and e.get("depart_reel"):
            s = int((datetime.fromisoformat(r["heure"]) - datetime.fromisoformat(e["depart_reel"])).total_seconds())
            temps = f" · {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    texte = (f"<b>{n}</b> · {_e((i['prenom'] or '') + ' ' + i['nom'])} ({_e(i['epreuve'])}){temps}" if i else f"<b>{n}</b>")
    if r["avertissement"]:
        return f"{texte}<br>⚠️ {_e(r['avertissement'])}", "att"
    return f"✅ {texte} à {datetime.fromisoformat(r['heure']).strftime('%H:%M:%S')}", "ok"


def annuler_dernier_top(compte, evenement_id, adresse=None):
    from noyau.donnees import chrono as dch
    src = f"web:{compte['identifiant']}"
    mien = [p for p in dch.passages(evenement_id) if p["source"] == src]
    if not mien:
        return "Aucun top à annuler.", "att"
    dch.annuler_passage(mien[-1]["id"])
    dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.chrono.annuler",
                    detail=f"passage {mien[-1]['id']} dossard {mien[-1]['dossard']}", adresse=adresse)
    return f"Top du dossard {mien[-1]['dossard']} annulé.", "att"


# ------------------------------------------------------------------ appel des présences

def peut_seance(compte, seance_id):
    from noyau.donnees import agenda_club as dag
    s = dag.seance(seance_id)
    if not s or "appel" not in D.pages_autorisees(compte["roles"]):
        return False
    from noyau.serveur import rpc
    club_id = rpc._un(rpc.CLUB["seance_id"], seance_id)
    sc = D.clubs_de(compte["roles"])
    return sc is None or any(r["role"] in ("bureau", "entraineur") and r.get("club_id") == club_id
                             for r in compte["roles"])


def appel(compte, csrf, seance_id, message=None):
    from noyau.donnees import agenda_club as dag
    from noyau.club import agenda as ag
    s = dag.seance(seance_id)
    lignes = dag.appel(seance_id)
    m = f"<div class='carte ok'>{message}</div>" if message else ""
    opts = lambda st: "".join(f"<option value='{k}'{' selected' if k == (st or '') else ''}>{l}</option>"
                              for k, l in [("", "—")] + list(ag.STATUTS_PRESENCE))
    corps = "".join(f"<label>{_e(x['nom'])} {_e(x['prenom'] or '')}{' · invité' if not x['attendu'] else ''}"
                    f"{' · ☎ ' + _e(x['contact_urgence_tel']) if x.get('mineur') and x.get('contact_urgence_tel') else ''}</label>"
                    f"<select name='p{x['personne_id']}'>{opts(x['statut'])}</select>" for x in lignes)
    b = dag.bilan(seance_id)
    return page(f"Appel · {s['titre']}", m + f"""<p class='petit'>{jour_fr(s['date'])}
{_e(s.get('heure_debut') or '')} · {_e(s.get('groupe') or 'toute l’association')} · {_e(s.get('lieu') or '')}</p>
<form method='post' action='/m/appel?seance={seance_id}' class='carte'>{_champ_csrf(csrf)}{corps or "<p>Personne n'est attendu.</p>"}
<button type='submit'>Enregistrer l'appel</button></form>
<p class='petit'>Présents : {b.get('effectif', 0)} · absents : {b.get('absent', 0)} · excusés : {b.get('excuse', 0)} · pas pointés : {b.get('non_pointes', 0)}</p>""", compte)


def enregistrer_appel(compte, seance_id, formulaire, adresse=None):
    from noyau.donnees import agenda_club as dag
    from noyau.club import agenda as ag
    statuts = {}
    for k, v in formulaire.items():
        if k.startswith("p") and k[1:].isdigit():
            statuts[int(k[1:])] = v if v in ag.LIBELLE_PRESENCE else None
    attendus = {x["personne_id"] for x in dag.appel(seance_id)}
    statuts = {pid: st for pid, st in statuts.items() if pid in attendus}
    dag.enregistrer_appel(seance_id, statuts)
    dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.appel", detail=f"séance {seance_id} ({len(statuts)})",
                    adresse=adresse)
    return f"Appel enregistré ({sum(1 for v in statuts.values() if v)} personne(s) pointée(s))."


# ------------------------------------------------------------------ mon poste

def poste(compte, evenement_id):
    from noyau.donnees import organisation as dor, logistique as dl
    ev = dor.evenement(evenement_id)
    pid = compte.get("personne_id")
    mien = [b for b in dl.benevoles(evenement_id) if pid and b["personne_id"] == pid]
    if not mien:
        return page(f"Mon poste · {ev['nom']}", "<div class='carte att'>Ton compte n'est relié à aucun bénévole de cette "
                    "course : demande à l'organisateur.</div>", compte)
    postes = dl.planning_benevole(evenement_id, mien[0]["id"])
    blocs = "".join(
        f"<div class='carte'><b>{_e(p['nom'])}</b><br>{jour_fr(p['jour'], True) if p.get('jour') else ''} "
        f"de {_e(p.get('heure_debut') or '?')} à {_e(p.get('heure_fin') or '?')}<br>{_e(p.get('lieu') or '')}"
        f"{(' · km ' + format(p['km'], 'g')) if p.get('km') else ''}"
        + (f"<p>{_e(p['consignes'])}</p>" if p.get("consignes") else "")
        + (f"<p class='petit'>Avec : {_e(', '.join((b.get('prenom') or '') + ' ' + b['nom'] for b in p['benevoles'] if b['id'] != mien[0]['id']))}</p>"
           if len(p["benevoles"]) > 1 else "") + "</div>" for p in postes)
    return page(f"Mon poste · {ev['nom']}", (blocs or "<div class='carte att'>Pas encore de poste.</div>") +
                (f"<p class='petit'>Contact de l'organisation : {_e(ev.get('contact_email'))}</p>" if ev.get("contact_email") else ""),
                compte)


# ------------------------------------------------------------------ mes résultats

def resultats(compte):
    from noyau.donnees import profils as dpro
    from noyau.club.profils import texte_temps
    rs = dpro.resultats(compte["personne_id"])[:30] if compte.get("personne_id") else []
    for r in rs:
        r["temps"] = texte_temps(r["temps_s"]) if r.get("temps_s") else ("abandon" if r.get("statut") == "abandon" else "")
    lignes = "".join(f"<tr><td>{datetime.fromisoformat(r['date']).strftime('%d/%m/%Y')}</td><td>{_e(r['course'])}"
                     f"{' · ' + _e(r['epreuve']) if r.get('epreuve') else ''}</td><td class='droite'>"
                     f"{_e(r.get('temps') or r.get('statut') or '')}{(' · ' + str(r['classement_general'])) if r.get('classement_general') else ''}"
                     f"</td></tr>" for r in rs)
    return page("Mes résultats", f"<div class='carte'><table>{lignes or '<tr><td>Pas encore de résultat.</td></tr>'}</table></div>", compte)


def erreur(compte, message, code=403):
    return page({403: "Accès refusé", 404: "Introuvable", 400: "Demande invalide", 429: "Patiente"}.get(code, "Erreur"), f"<div class='carte err'>{_e(message)}</div>"
                "<a class='lien' href='/m/'>Retour à l'accueil</a>", compte)


def lien(chemin, **params):
    return chemin + ("?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items()) if params else "")
