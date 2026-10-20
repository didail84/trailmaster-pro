"""
Contenu de référence pour l'onglet Alimentation : fiches fruits &
légumes et aliments transportables pour courir.

Ce n'est PAS un flux en direct — c'est un contenu rédigé une fois
(valeurs caloriques usuelles, saisons en France métropolitaine,
conseils de consommation) qui peut être mis à jour à la main en
modifiant les listes ci-dessous, exactement comme le calendrier de
courses. Les calories sont des ordres de grandeur habituels pour
100 g (aliment cru, sauf mention contraire), pas des valeurs de
laboratoire.
"""

SAISONS = ["Printemps", "Été", "Automne", "Hiver", "Toute l'année"]

# Chaque entrée : nom, catégorie (Fruit/Légume), calories/100g,
# saison(s), et un conseil de consommation pour un coureur.
FICHES_FRUITS_LEGUMES = [
    {
        "nom": "Banane",
        "categorie": "Fruit",
        "calories": 90,
        "saisons": ["Toute l'année"],
        "conseil": (
            "L'un des meilleurs fruits pour un coureur : riche en glucides "
            "rapidement assimilables et en potassium (utile contre les "
            "crampes). À manger mûre (taches brunes) 1 à 2h avant une "
            "sortie, ou juste après pour la récupération."
        ),
    },
    {
        "nom": "Pomme",
        "categorie": "Fruit",
        "calories": 52,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Riche en fibres et en eau, idéale en collation à distance "
            "d'une séance (les fibres ralentissent la digestion, moins "
            "adapté juste avant l'effort). Avec la peau pour les fibres et "
            "les antioxydants."
        ),
    },
    {
        "nom": "Orange",
        "categorie": "Fruit",
        "calories": 47,
        "saisons": ["Hiver"],
        "conseil": (
            "Bonne source de vitamine C (récupération, immunité) et "
            "d'hydratation. Un fruit de saison hivernale à privilégier "
            "après les sorties froides, pressée ou en quartiers."
        ),
    },
    {
        "nom": "Kiwi",
        "categorie": "Fruit",
        "calories": 61,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Très riche en vitamine C (plus que l'orange à poids égal) et "
            "en potassium. Deux kiwis le soir sont aussi parfois utilisés "
            "pour la qualité du sommeil — pratique vu ton suivi Sommeil."
        ),
    },
    {
        "nom": "Fraise",
        "categorie": "Fruit",
        "calories": 32,
        "saisons": ["Printemps", "Été"],
        "conseil": (
            "Peu calorique, riche en vitamine C et en antioxydants. "
            "Excellente en collation légère d'été, moins utile comme "
            "carburant avant l'effort (faible densité énergétique)."
        ),
    },
    {
        "nom": "Melon",
        "categorie": "Fruit",
        "calories": 34,
        "saisons": ["Été"],
        "conseil": (
            "Très hydratant (>90% d'eau), bon pour compenser les pertes "
            "hydriques des sorties chaudes d'été. À manger frais, pas "
            "idéal juste avant de courir (volume d'eau important)."
        ),
    },
    {
        "nom": "Raisin",
        "categorie": "Fruit",
        "calories": 69,
        "saisons": ["Automne"],
        "conseil": (
            "Sucres rapides concentrés, bon en-cas énergétique de fin "
            "d'été/automne. À consommer avec modération le soir (index "
            "glycémique élevé)."
        ),
    },
    {
        "nom": "Figue",
        "categorie": "Fruit",
        "calories": 74,
        "saisons": ["Été", "Automne"],
        "conseil": (
            "Riche en fibres, en potassium et en sucres naturels — bon "
            "petit boost énergétique. Séchée, c'est aussi une excellente "
            "option transportable pour les sorties longues."
        ),
    },
    {
        "nom": "Poire",
        "categorie": "Fruit",
        "calories": 57,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Riche en fibres douces, bien tolérée digestivement. À "
            "privilégier en collation de récupération plutôt qu'avant "
            "l'effort."
        ),
    },
    {
        "nom": "Abricot",
        "categorie": "Fruit",
        "calories": 48,
        "saisons": ["Été"],
        "conseil": (
            "Riche en bêta-carotène et en potassium. Séché (oreillons), "
            "c'est un très bon aliment de sortie longue, dense en "
            "énergie et facile à transporter."
        ),
    },
    {
        "nom": "Patate douce",
        "categorie": "Légume",
        "calories": 86,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Glucides complexes + potassium + bêta-carotène : un classique "
            "des coureurs pour le repas la veille ou 2-3h avant une sortie "
            "longue, cuite au four ou vapeur."
        ),
    },
    {
        "nom": "Épinard",
        "categorie": "Légume",
        "calories": 23,
        "saisons": ["Printemps", "Automne", "Hiver"],
        "conseil": (
            "Riche en fer et en nitrates naturels (associés à une "
            "meilleure économie d'oxygène à l'effort). Légèrement cuit à "
            "la vapeur pour préserver le fer, à distance de l'effort pour "
            "limiter les fibres avant de courir."
        ),
    },
    {
        "nom": "Betterave",
        "categorie": "Légume",
        "calories": 43,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Riche en nitrates, souvent utilisée par les coureurs (jus de "
            "betterave) dans les jours précédant une course pour "
            "l'endurance. Cuite, en salade ou en jus."
        ),
    },
    {
        "nom": "Brocoli",
        "categorie": "Légume",
        "calories": 34,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Riche en vitamine C, K et en fibres. Bon pour la récupération "
            "générale, à consommer à distance d'une séance (fibres, "
            "digestion plus lente)."
        ),
    },
    {
        "nom": "Courgette",
        "categorie": "Légume",
        "calories": 17,
        "saisons": ["Été"],
        "conseil": (
            "Très peu calorique et hydratante, bien tolérée. Bon légume "
            "d'accompagnement léger les soirs de forte chaleur estivale."
        ),
    },
    {
        "nom": "Carotte",
        "categorie": "Légume",
        "calories": 41,
        "saisons": ["Toute l'année"],
        "conseil": (
            "Riche en bêta-carotène, se conserve bien et disponible toute "
            "l'année. Crue en bâtonnets pour une collation croquante, "
            "cuite pour mieux libérer le bêta-carotène."
        ),
    },
    {
        "nom": "Tomate",
        "categorie": "Légume",
        "calories": 18,
        "saisons": ["Été"],
        "conseil": (
            "Riche en eau et en lycopène (antioxydant, mieux assimilé "
            "cuit qu'cru). Idéale en été pour l'hydratation, en salade "
            "légère après l'effort."
        ),
    },
    {
        "nom": "Poireau",
        "categorie": "Légume",
        "calories": 29,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Diurétique doux, riche en fibres prébiotiques. En soupe ou "
            "fondant, bon plat du soir en période hivernale, à distance "
            "des séances matinales pour éviter les ballonnements."
        ),
    },
    {
        "nom": "Chou-fleur",
        "categorie": "Légume",
        "calories": 25,
        "saisons": ["Automne", "Hiver"],
        "conseil": (
            "Peu calorique, riche en vitamine C. Peut provoquer des "
            "ballonnements chez certains — à éviter la veille d'une "
            "sortie longue ou d'une course."
        ),
    },
    {
        "nom": "Pomme de terre",
        "categorie": "Légume",
        "calories": 77,
        "saisons": ["Toute l'année"],
        "conseil": (
            "Bonne source de glucides complexes et de potassium. Base "
            "classique du repas pré-sortie longue (bouillie ou au four, "
            "avec la peau pour les fibres et minéraux)."
        ),
    },
]


# ------------------------------------------------------------------
# Fiches complémentaires : autres fruits et légumes, fruits secs et
# légumineuses, rangés par saison en France métropolitaine.
# Format compact : (nom, catégorie, kcal/100 g, saisons, conseil).
# Pour en ajouter une, il suffit d'ajouter une ligne ici.
# ------------------------------------------------------------------
P, E, A, H, T = "Printemps", "Été", "Automne", "Hiver", "Toute l'année"

_FICHES_COMPLEMENTAIRES = [
    # ---------------- Fruits de printemps / été ----------------
    ("Cerise", "Fruit", 63, [P, E], "Glucides rapides et antioxydants (anthocyanes) : le jus de cerise acidulée est étudié pour la récupération musculaire. À manger en collation ou après la sortie ; dénoyauter pour les enfants."),
    ("Pêche", "Fruit", 39, [E], "Très hydratante et digeste, apporte potassium et vitamine A. Bonne collation d'été, une heure ou plus avant l'effort ; bien mûre pour limiter les fibres irritantes."),
    ("Nectarine", "Fruit", 44, [E], "Comme la pêche, mais sans peau duveteuse : pratique à emporter. Glucides rapides et eau, utile pour s'hydrater pendant les chaleurs."),
    ("Prune / Reine-claude", "Fruit", 46, [E, A], "Sucres rapides et fibres : en excès, elles peuvent accélérer le transit. À éviter juste avant une course, très bien en collation d'après-séance."),
    ("Mirabelle", "Fruit", 52, [E], "Petit fruit sucré de fin d'été, riche en vitamine A. Se mange facilement en sortie longue en ravitaillement (dénoyautée)."),
    ("Framboise", "Fruit", 52, [E, A], "Peu sucrée, riche en fibres, vitamine C et antioxydants. Idéale au petit-déjeuner ou en dessert de récupération avec du fromage blanc."),
    ("Myrtille", "Fruit", 57, [E], "Très riche en antioxydants (anthocyanes), intéressante pour la récupération. Les myrtilles des bois cueillies en montagne sont une belle récompense de sortie."),
    ("Mûre", "Fruit", 43, [E, A], "Fibres, vitamine C et K, manganèse. Peu calorique : à associer à des glucides (flocons d'avoine, pain) pour la récupération."),
    ("Groseille", "Fruit", 56, [E], "Acide et riche en vitamine C. En petite quantité dans un yaourt ou un fromage blanc après l'effort."),
    ("Cassis", "Fruit", 63, [E], "Record de vitamine C parmi les petits fruits. Souvent en jus ou en compote ; à sucrer peu pour ne garder que l'intérêt nutritionnel."),
    ("Pastèque", "Fruit", 30, [E], "Composée à 92 % d'eau, avec un peu de citrulline : parfaite pour se réhydrater après une sortie par temps chaud. Pauvre en énergie, donc à compléter."),
    ("Melon charentais", "Fruit", 34, [E], "Hydratant et riche en potassium et bêta-carotène. À éviter trop froid et en grande quantité avant une sortie (inconfort digestif possible)."),
    ("Rhubarbe", "Légume", 21, [P, E], "Technique : se cuisine comme un fruit (compote, tarte). Très peu calorique, acide, à sucrer légèrement ; riche en vitamine K."),
    # ---------------- Fruits d'automne / hiver ----------------
    ("Coing", "Fruit", 57, [A], "Se mange cuit (gelée, pâte de fruit, compote) : riche en pectine et en fibres. La pâte de coing est un ravitaillement très digeste en sortie longue."),
    ("Grenade", "Fruit", 83, [A, H], "Antioxydants (punicalagines) et potassium. Le jus est parfois utilisé en récupération ; les grains se mangent en salade ou avec du yaourt."),
    ("Kaki", "Fruit", 70, [A, H], "Riche en glucides, vitamine A et fibres : un bon carburant énergétique d'automne. Bien mûr, sans astringence."),
    ("Clémentine", "Fruit", 47, [A, H], "Vitamine C et eau, très facile à emporter. Un classique d'hiver après les sorties froides ou en ravitaillement de course."),
    ("Mandarine", "Fruit", 53, [A, H], "Proche de la clémentine, un peu plus sucrée. Vitamine C et glucides rapides ; pratique en poche pour la sortie longue."),
    ("Pamplemousse", "Fruit", 42, [H], "Peu calorique, riche en vitamine C. Attention : il interagit avec certains médicaments (statines, antihypertenseurs) — à vérifier avant d'en consommer régulièrement."),
    ("Citron", "Fruit", 29, [H, T], "Vitamine C et jus à presser dans l'eau ou sur les plats. Il n'apporte presque pas de calories : c'est un assaisonnement, pas un carburant."),
    ("Citron vert", "Fruit", 30, [T], "Même usage que le citron, plus parfumé. Un peu de jus dans l'eau de la gourde change le goût sans ajouter de sucre."),
    ("Canneberge (cranberry)", "Fruit", 46, [A], "Surtout consommée séchée ou en jus. Les antioxydants sont intéressants, mais les versions sucrées apportent beaucoup de sucre ajouté : lire l'étiquette."),
    ("Nèfle", "Fruit", 47, [A, H], "Fruit de fin d'automne à manger blet. Fibres et potassium, peu énergétique : une collation d'après-séance."),
    ("Châtaigne", "Fruit", 165, [A], "Fruit sec farineux : glucides complexes et potassium, bien plus énergétique qu'un fruit frais. Excellente en soupe ou en purée la veille d'une sortie longue."),
    # ---------------- Fruits exotiques / importés ----------------
    ("Ananas", "Fruit", 50, [T], "Fruit importé : vitamine C et bromélaïne (digestion). Glucides rapides, bien accepté en course ou en récupération."),
    ("Mangue", "Fruit", 60, [T], "Glucides rapides, vitamine A et C. Mûre, c'est un carburant naturel très agréable après un effort long."),
    ("Papaye", "Fruit", 43, [T], "Digeste, riche en vitamine C et en papaïne (enzyme digestive). Peu calorique, idéale en dessert léger."),
    ("Fruit de la passion", "Fruit", 97, [T], "Plus calorique que la plupart des fruits, riche en fibres et en vitamine C. À manger à la cuillère en dessert."),
    ("Litchi", "Fruit", 66, [T], "Sucres rapides et vitamine C. Un fruit exotique simple à manger en dessert, plus rare en France métropolitaine."),
    ("Avocat", "Fruit", 160, [T], "Graisses mono-insaturées, potassium et vitamine E. Très énergétique, plutôt à éviter juste avant l'effort : excellent le soir ou pour une récupération à long terme."),
    ("Noix de coco (chair)", "Fruit", 354, [T], "Très riche en graisses saturées et en calories. Une petite quantité (copeaux) suffit en collation ; l'eau de coco est une boisson de réhydratation légère."),
    # ---------------- Fruits secs et oléagineux ----------------
    ("Datte", "Fruit", 282, [T], "Fruit sec : glucides très concentrés, potassium et magnésium. Le ravitaillement naturel par excellence (2 à 3 dattes ≈ un gel), facile à porter."),
    ("Abricot sec", "Fruit", 241, [T], "Riche en potassium, fer et glucides. À manger en petite quantité (fibres) pendant la sortie longue, avec de l'eau."),
    ("Pruneau", "Fruit", 239, [T], "Glucides concentrés et fibres : efficace, mais laxatif en quantité. À tester à l'entraînement avant de l'utiliser en course."),
    ("Figue sèche", "Fruit", 249, [T], "Calcium, magnésium, potassium et glucides rapides. Peut être consommée en collation de récupération ou en ravitaillement de sortie longue."),
    ("Raisin sec", "Fruit", 299, [T], "Glucides concentrés très pratiques à emporter. Le mélange raisins secs + amandes est un classique de ravitaillement en trail."),
    ("Amande", "Fruit", 579, [T], "Bonnes graisses, protéines, magnésium et vitamine E. Très énergétique : une petite poignée en collation, pas avant un effort intense."),
    ("Noix", "Fruit", 654, [A, T], "Riche en oméga-3 végétaux et en calories. Une poignée (4 à 5 noix) par jour suffit ; pas adaptée juste avant l'effort à cause des lipides."),
    ("Noisette", "Fruit", 628, [A, T], "Vitamine E, magnésium et graisses mono-insaturées. Se combine bien avec des fruits secs dans un mélange de ravitaillement."),
    # ---------------- Légumes de printemps ----------------
    ("Asperge", "Légume", 20, [P], "Légume diurétique peu calorique, riche en folates et vitamine K. À accompagner de glucides (riz, pommes de terre) pour un vrai repas de récupération."),
    ("Petit pois", "Légume", 80, [P, E], "Plus énergétique que la plupart des légumes : glucides, protéines végétales, fibres et fer. Parfait en accompagnement après l'entraînement."),
    ("Fève", "Légume", 85, [P], "Protéines végétales, fibres et fer : plat de récupération intéressant. À écosser et cuire ; peut ballonner chez certains."),
    ("Radis", "Légume", 16, [P, E], "Très peu calorique, croquant, riche en eau. Un petit plus de fraîcheur dans les repas de printemps."),
    ("Artichaut", "Légume", 47, [P, E], "Riche en fibres (inuline, prébiotique) et antioxydants. À manger loin d'une sortie importante pour éviter ballonnements."),
    ("Oseille", "Légume", 22, [P], "Très acidulée, riche en vitamine C et en fer ; consommée en petite quantité (soupes, sauces)."),
    ("Navet nouveau", "Légume", 20, [P], "Léger, tendre et digeste. À servir en accompagnement ou en soupe de saison."),
    ("Radis noir", "Légume", 25, [A, H], "Légume racine d'hiver qui aide la digestion. À râper en salade ou en crudité."),
    # ---------------- Légumes d'été ----------------
    ("Concombre", "Légume", 12, [E], "Composé à 96 % d'eau : une aide à l'hydratation. Presque aucune énergie, donc à associer à des féculents."),
    ("Aubergine", "Légume", 24, [E], "Légume peu calorique, riche en fibres et en antioxydants (nasunine de la peau). À cuire sans excès d'huile."),
    ("Poivron", "Légume", 28, [E, A], "L'un des légumes les plus riches en vitamine C, surtout le rouge. Cru en salade ou cuit au four pour la récupération."),
    ("Haricot vert", "Légume", 31, [E], "Fibres, vitamine C et K. En accompagnement léger : à consommer plutôt le soir qu'avant une sortie."),
    ("Maïs doux", "Légume", 100, [E, A], "Plus riche en glucides que les autres légumes : un féculent à part entière. Intéressant en salade ou en accompagnement."),
    ("Fenouil", "Légume", 31, [P, A, H], "Digestif (anéthol), riche en potassium et en fibres. Cru en salade ou cuit, en accompagnement léger."),
    ("Salade verte (laitue)", "Légume", 15, [T], "Très peu calorique, riche en eau et en folates. Un accompagnement d'appoint à enrichir de féculents et de protéines."),
    ("Roquette", "Légume", 25, [P, E, A], "Riche en nitrates naturels, qui peuvent favoriser l'oxygénation musculaire (comme la betterave). À mélanger aux salades."),
    ("Cresson", "Légume", 11, [P, H], "Riche en vitamines C et K, en fer et en nitrates. Très léger : à manger cru ou en soupe."),
    ("Blette", "Légume", 19, [P, E, A], "Riche en magnésium et potassium, vitamine K. À cuire comme les épinards ; les côtes se cuisinent à part, comme des asperges."),
    ("Champignon de Paris", "Légume", 22, [T], "Peu calorique, riche en vitamines B et sélénium. À cuire pour une meilleure digestibilité."),
    ("Cèpe / Girolle", "Légume", 30, [E, A], "Champignons de saison, riches en protéines végétales et vitamines B. Ne jamais cueillir sans certitude absolue de l'espèce."),
    # ---------------- Légumes d'automne / hiver ----------------
    ("Potiron / Citrouille", "Légume", 26, [A], "Riche en bêta-carotène, peu calorique. En soupe, c'est un excellent plat de récupération, hydratant et réconfortant."),
    ("Potimarron", "Légume", 34, [A, H], "Goût de châtaigne, riche en bêta-carotène et en fibres. Se cuisine avec la peau en soupe ou rôti."),
    ("Butternut", "Légume", 45, [A, H], "Courge douce plus énergétique que le potiron : glucides complexes et bêta-carotène, très bon en purée ou en soupe."),
    ("Courge spaghetti", "Légume", 31, [A, H], "Peu calorique, à gratiner ou à servir avec une sauce tomate ; bon accompagnement léger."),
    ("Chou rouge", "Légume", 31, [A, H], "Antioxydants (anthocyanes) et vitamine C. Cru en salade ou braisé ; peut ballonner."),
    ("Chou blanc", "Légume", 25, [A, H], "Vitamine C et K, fibres. Cru (coleslaw) ou cuit ; à éviter la veille d'une sortie longue."),
    ("Chou vert / frisé", "Légume", 28, [A, H], "Riche en vitamines C et K, et en calcium. Le chou de saison par excellence en hiver, dans la soupe ou braisé."),
    ("Chou de Bruxelles", "Légume", 43, [A, H], "Fibres, vitamine C et K. Peut être flatulent : à servir à distance des sorties importantes."),
    ("Chou kale", "Légume", 49, [A, H], "Très riche en vitamines A, C, K, en calcium et antioxydants. En salade massée, en soupe ou en chips."),
    ("Chou chinois / pak-choï", "Légume", 13, [A, H, P], "Très peu calorique, croquant, riche en vitamine C et en calcium. Rapide à cuire à la poêle ou en soupe."),
    ("Chou romanesco", "Légume", 25, [A, H], "Comme le chou-fleur, plus riche en vitamine C. Se cuit à la vapeur ou rôti."),
    ("Endive", "Légume", 17, [A, H, P], "Peu calorique, riche en fibres et en potassium. Crue en salade ou braisée ; à associer à des féculents."),
    ("Mâche", "Légume", 21, [A, H], "Riche en vitamines C et B9, en fer et en oméga-3. Une salade d'hiver très complète, rapide à préparer."),
    ("Céleri-rave", "Légume", 42, [A, H], "Fibres, vitamine K et potassium. En remoulade, en purée ou en soupe ; digeste cuit."),
    ("Céleri branche", "Légume", 17, [A, H, T], "Très peu calorique, riche en eau et en potassium. À croquer en crudité ou à mettre dans le bouillon."),
    ("Navet", "Légume", 28, [A, H, P], "Léger, riche en vitamine C. En soupe, en pot-au-feu ou rôti : un accompagnement doux de saison."),
    ("Panais", "Légume", 75, [A, H], "Plus énergétique que la carotte (glucides complexes), riche en fibres et en potassium. En purée ou rôti, bon plat de charge."),
    ("Rutabaga", "Légume", 38, [A, H], "Légume racine ancien riche en vitamine C et en fibres. Se cuisine en purée ou en soupe."),
    ("Topinambour", "Légume", 73, [A, H], "Riche en inuline (prébiotique) ; peut provoquer des gaz chez certains. En petite quantité, à distance de la compétition."),
    ("Salsifis", "Légume", 82, [A, H], "Glucides complexes et fibres, goût fin. Cuit en accompagnement ou en gratin : légume de charge d'hiver."),
    ("Cardon", "Légume", 20, [H], "Légume d'hiver typique des fêtes, très peu calorique et riche en fibres. À cuire longuement."),
    # ---------------- Alliacées et aromates ----------------
    ("Oignon", "Légume", 40, [T], "Base de nombreux plats, riche en fibres prébiotiques. Cuit, il est plus digeste ; cru, il peut gêner la digestion avant l'effort."),
    ("Échalote", "Légume", 72, [T], "Plus fine et plus sucrée que l'oignon. Un assaisonnement de choix, à cuire doucement."),
    ("Ail", "Légume", 130, [T], "Utilisé en petites quantités comme assaisonnement ; composés soufrés intéressants pour l'immunité. Peut rendre l'haleine forte."),
    ("Persil", "Légume", 36, [T], "Riche en vitamines C et K, en fer et en antioxydants. À ajouter en abondance sur les plats : un bon concentré de micronutriments."),
    ("Gingembre", "Légume", 80, [T], "Aide la digestion et limite les nausées en sortie longue ; en infusion ou en poudre dans les boissons chaudes."),
    # ---------------- Légumineuses (cuites) ----------------
    ("Lentilles (cuites)", "Légume", 116, [T], "Protéines végétales, fibres, fer et glucides complexes. Un plat de récupération complet, à servir avec une céréale."),
    ("Pois chiches (cuits)", "Légume", 139, [T], "Protéines, glucides et fibres. Très bons en salade, en houmous ou en soupe ; peuvent ballonner."),
    ("Haricots rouges (cuits)", "Légume", 127, [T], "Protéines végétales, fibres, fer et magnésium. À associer à du riz pour un repas complet."),
    ("Haricots blancs (cuits)", "Légume", 118, [T], "Riches en fibres, protéines et potassium. À rincer avant utilisation (conserves) et à mettre en salade ou en soupe."),
    ("Flageolets (cuits)", "Légume", 112, [T], "Fibres, protéines et fer. Plat de charge classique avec une viande ou une saucisse, à distance d'une course."),
    ("Edamame (cuits)", "Légume", 121, [T], "Protéines complètes pour une source végétale, riches en fibres et en fer. En apéritif ou en salade."),
]

for _nom, _cat, _kcal, _saisons, _conseil in _FICHES_COMPLEMENTAIRES:
    FICHES_FRUITS_LEGUMES.append({
        "nom": _nom, "categorie": _cat, "calories": _kcal,
        "saisons": _saisons, "conseil": _conseil,
    })

import unicodedata as _u
FICHES_FRUITS_LEGUMES.sort(
    key=lambda f: _u.normalize("NFD", f["nom"].lower()).encode("ascii", "ignore").decode()
)


# Aliments transportables recommandés pour courir, par catégorie, avec
# quelques repères de produits bien notés en France (marques/gammes
# fréquemment recommandées par les coureurs et bien notées par les
# utilisateurs) — à ajuster selon tes propres essais et tolérances
# digestives.
ALIMENTS_COURSE = {
    "Compotes en stick": [
        {
            "nom": "Pom'Potes / compotes en gourde nature (pomme)",
            "note": "★★★★☆",
            "raison": "Neutre digestivement, sucres simples, très bien toléré à l'effort — la valeur sûre.",
        },
        {
            "nom": "Compotes gourde pomme-banane",
            "note": "★★★★☆",
            "raison": "Apport de potassium en plus, bon goût, texture facile à avaler en courant.",
        },
        {
            "nom": "Gourdes énergétiques spécial sport (type Aptonia, Overstim's Compot'Energy)",
            "note": "★★★★★",
            "raison": "Formulées pour l'effort (glucides + parfois sodium), pensées pour le trail long — meilleur choix pour les sorties de plusieurs heures.",
        },
    ],
    "Barres énergétiques": [
        {
            "nom": "Barres céréales/fruits secs type Overstim's, Aptonia, Nutrisport",
            "note": "★★★★★",
            "raison": "Bon ratio glucides/index glycémique modéré, formulées pour l'effort prolongé, bien notées par les traileurs.",
        },
        {
            "nom": "Barres de dattes/fruits secs pressés (sans additifs)",
            "note": "★★★★☆",
            "raison": "Naturelles, denses en énergie, bonne alternative pour qui préfère limiter les additifs.",
        },
        {
            "nom": "Barres protéinées classiques (hors effort)",
            "note": "★★★☆☆",
            "raison": "Plus adaptées à la récupération qu'à l'effort — digestion plus lente, à réserver après la sortie.",
        },
    ],
    "Viande / protéines transportables": [
        {
            "nom": "Viande séchée des Grisons / Bündnerfleisch",
            "note": "★★★★☆",
            "raison": "Très dense en protéines, se conserve sans réfrigération, classique des ultra-traileurs sur les très longues distances.",
        },
        {
            "nom": "Billes/dés de jambon sec ou magret séché",
            "note": "★★★★☆",
            "raison": "Apporte du sel (utile en cas de fortes chaleurs/transpiration) en plus des protéines — courant dans les ravitaillements d'ultra-trail.",
        },
        {
            "nom": "Petites saucisses sèches type saucisson sec allégé",
            "note": "★★★☆☆",
            "raison": "Bon dépannage salé sur très longue distance, mais plus gras — à réserver aux efforts de plusieurs heures, pas aux sorties courtes.",
        },
    ],
    "Yaourts / produits laitiers transportables": [
        {
            "nom": "Yaourts à boire (type gourde) nature ou vanille",
            "note": "★★★★☆",
            "raison": "Bon pour la récupération juste après l'effort (protéines + glucides), à emporter au frais plutôt que pendant la course elle-même.",
        },
        {
            "nom": "Petits-suisses / fromage blanc en pot individuel",
            "note": "★★★☆☆",
            "raison": "Bonne récupération protéique, mais nécessite le froid — à réserver au sac isotherme ou pour l'après-course.",
        },
        {
            "nom": "Boissons lactées de récupération (type recovery shake)",
            "note": "★★★★★",
            "raison": "Formulées spécifiquement pour la fenêtre de récupération (ratio glucides/protéines optimisé) — bien notées par les coureurs d'endurance.",
        },
    ],
    "Biscuits": [
        {
            "nom": "Biscuits secs type petit-beurre / sablés nature",
            "note": "★★★☆☆",
            "raison": "Simples, faciles à transporter et à digérer, mais peu de valeur ajoutée nutritionnelle par rapport aux barres sport.",
        },
        {
            "nom": "Barres de céréales type pâtes de fruits/céréales compressées",
            "note": "★★★★☆",
            "raison": "Bon compromis goût/énergie/praticité, largement utilisées dans les ravitaillements de trail.",
        },
        {
            "nom": "Biscuits salés (crackers, type ravitaillement course)",
            "note": "★★★★☆",
            "raison": "Utiles sur ultra-distance pour casser le goût sucré et apporter du sel — classiques des tables de ravitaillement en fin de course.",
        },
    ],
}
