"""
Ingrédients du « coin fait maison » (barres, gels, boissons) et recettes
de départ.

Valeurs MOYENNES pour 100 g, arrondies, du type de celles de la table
Ciqual de l'Anses : les produits réels varient (une datte Medjool n'est
pas une Deglet Nour). Chaque ingrédient d'une recette peut être corrigé
avec les valeurs de l'étiquette de ton produit.

glucose / fructose : sucres disponibles rangés en deux familles, pour le
rapport glucose:fructose qui compte au-delà de 60 g de glucides par heure.
L'amidon, la maltodextrine, le dextrose et le lactose comptent côté
glucose ; le saccharose (sucre) compte pour moitié de chaque côté.
fvl : fruit, légume ou légumineuse au sens du Nutri-Score.
"""

# code: (nom, kcal, glucides, sucres, fibres, protéines, lipides, AGS, sel, glucose, fructose, fvl, caféine mg)
_BRUT = {
    "eau": ("Eau", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, False, 0),
    "flocons_avoine": ("Flocons d'avoine", 370, 58, 1, 10, 13.5, 7, 1.3, 0.01, 57, 0, False, 0),
    "dattes": ("Dattes séchées", 282, 64, 63, 8, 2.5, 0.4, 0.03, 0.01, 31, 31, True, 0),
    "raisins_secs": ("Raisins secs", 300, 69, 64, 4.5, 3, 0.5, 0.1, 0.05, 31, 33, True, 0),
    "abricots_secs": ("Abricots secs", 240, 55, 50, 7, 3, 0.5, 0.05, 0.03, 30, 18, True, 0),
    "banane": ("Banane mûre", 90, 20, 15, 2.7, 1.2, 0.3, 0.1, 0.0, 13, 6, True, 0),
    "compote_pomme": ("Compote de pomme sans sucre ajouté", 55, 12, 11, 1.5, 0.3, 0.2, 0.03, 0.0, 4, 7, True, 0),
    "miel": ("Miel", 327, 81, 81, 0, 0.4, 0, 0, 0.01, 38, 42, False, 0),
    "sirop_erable": ("Sirop d'érable", 260, 67, 60, 0, 0, 0.1, 0, 0.03, 34, 31, False, 0),
    "sirop_agave": ("Sirop d'agave", 310, 76, 68, 0, 0.1, 0.4, 0, 0.0, 16, 56, False, 0),
    "sirop_riz": ("Sirop de riz", 316, 78, 45, 0, 0.5, 0, 0, 0.03, 78, 0, False, 0),
    "sucre": ("Sucre blanc (saccharose)", 400, 100, 100, 0, 0, 0, 0, 0, 50, 50, False, 0),
    "sucre_roux": ("Sucre de canne roux", 390, 97, 96, 0, 0.1, 0, 0, 0.05, 48, 48, False, 0),
    "maltodextrine": ("Maltodextrine", 380, 95, 7, 0, 0, 0, 0, 0.05, 95, 0, False, 0),
    "dextrose": ("Dextrose (glucose)", 364, 91, 91, 0, 0, 0, 0, 0, 91, 0, False, 0),
    "fructose": ("Fructose en poudre", 400, 100, 100, 0, 0, 0, 0, 0, 0, 100, False, 0),
    "sel": ("Sel fin", 0, 0, 0, 0, 0, 0, 0, 100, 0, 0, False, 0),
    "jus_orange": ("Jus d'orange 100 %", 44, 9.5, 8.7, 0.2, 0.7, 0.1, 0, 0.0, 4.3, 4.6, True, 0),
    "jus_raisin": ("Jus de raisin 100 %", 66, 16, 16, 0.1, 0.3, 0.1, 0, 0.01, 7.8, 8.2, True, 0),
    "jus_pomme": ("Jus de pomme 100 %", 46, 10.5, 10, 0.1, 0.1, 0.1, 0, 0.0, 3.3, 6.4, True, 0),
    "jus_citron": ("Jus de citron", 22, 2.4, 1.5, 0.3, 0.4, 0.2, 0, 0.0, 1.2, 1.0, True, 0),
    "riz_cuit": ("Riz blanc cuit", 140, 31, 0.1, 0.4, 2.7, 0.3, 0.1, 0.0, 31, 0, False, 0),
    "patate_douce": ("Patate douce cuite", 86, 18, 6, 3, 1.5, 0.1, 0.03, 0.05, 14, 2, False, 0),
    "beurre_cacahuete": ("Beurre de cacahuète", 600, 15, 7, 7, 25, 50, 10, 0.5, 11, 2, False, 0),
    "amandes": ("Amandes", 620, 7, 4.5, 12, 25, 53, 4, 0.01, 6, 1, False, 0),
    "noix_cajou": ("Noix de cajou", 600, 27, 6, 3, 18, 46, 8, 0.03, 25, 1, False, 0),
    "graines_chia": ("Graines de chia", 490, 8, 0, 34, 17, 31, 3.3, 0.04, 6, 0, False, 0),
    "cacao": ("Cacao en poudre non sucré", 375, 13, 1, 33, 22, 21, 12.6, 0.05, 12, 0, False, 230),
    "chocolat_noir": ("Chocolat noir 70 %", 570, 32, 28, 11, 8, 42, 25, 0.02, 18, 14, False, 80),
    "lait_demi": ("Lait demi-écrémé", 46, 4.8, 4.8, 0, 3.3, 1.6, 1.0, 0.1, 4.8, 0, False, 0),
    "the_noir": ("Thé noir infusé", 1, 0.2, 0, 0, 0.1, 0, 0, 0.0, 0, 0, False, 20),
    "cafe": ("Café expresso", 2, 0.3, 0, 0, 0.1, 0.2, 0.1, 0.01, 0, 0, False, 200),
    "sirop_fruits": ("Sirop de fruits (grenadine, menthe…)", 290, 72, 72, 0, 0, 0, 0, 0.01, 42, 30, False, 0),
    "bouillon": ("Bouillon de légumes prêt à boire", 5, 0.6, 0.3, 0.1, 0.2, 0.1, 0.03, 0.8, 0.4, 0.1, False, 0),
}
CHAMPS = ("nom", "kcal", "glucides_g", "sucres_g", "fibres_g", "proteines_g", "lipides_g", "ags_g", "sel_g",
          "glucose_g", "fructose_g", "fvl", "cafeine_mg")
INGREDIENTS = {code: dict(zip(CHAMPS, v)) for code, v in _BRUT.items()}
LIQUIDES = {"eau", "jus_orange", "jus_raisin", "jus_pomme", "jus_citron", "lait_demi", "the_noir", "cafe", "bouillon"}
SODIUM_PAR_G_SEL = 393.4      # mg de sodium dans 1 g de sel (NaCl)

CATEGORIES_RECETTE = ("Barre", "Gel", "Boisson", "Boule ou pâte de fruits", "Salé", "Récupération")

# Recettes de départ : (nom, catégorie, nombre de portions, [(ingrédient, grammes)], préparation, conservation)
MODELES = (
    ("Gel miel-citron salé", "Gel", 4,
     [("miel", 100), ("jus_citron", 20), ("eau", 25), ("sel", 0.6)],
     "Mélange le miel tiède, le jus de citron, l'eau et le sel jusqu'à ce que le sel soit dissous. "
     "Verse dans une flasque souple ou des petits sachets.",
     "1 semaine au réfrigérateur, 1 journée dans le sac."),
    ("Gel 2:1 maltodextrine-fructose", "Gel", 4,
     [("maltodextrine", 60), ("fructose", 30), ("eau", 60), ("jus_citron", 10), ("sel", 0.8)],
     "Dissous la maltodextrine et le fructose dans l'eau chaude (pas bouillante), ajoute le citron et le sel. "
     "Laisse épaissir au frais.",
     "1 semaine au réfrigérateur."),
    ("Barres avoine-dattes", "Barre", 8,
     [("flocons_avoine", 120), ("dattes", 200), ("beurre_cacahuete", 40), ("miel", 30), ("cacao", 10), ("sel", 1)],
     "Mixe les dattes dénoyautées avec le beurre de cacahuète et le miel, ajoute les flocons, le cacao et le sel. "
     "Tasse dans un moule tapissé de papier cuisson, 1 h au frais, coupe en 8.",
     "1 semaine au réfrigérateur, emballées une par une."),
    ("Riz cakes salés-sucrés", "Barre", 6,
     [("riz_cuit", 300), ("sirop_erable", 30), ("sel", 1.5), ("beurre_cacahuete", 20)],
     "Mélange le riz encore chaud avec le sirop, le sel et le beurre de cacahuète. Tasse dans un plat, "
     "laisse refroidir, coupe en 6 et emballe dans du papier aluminium.",
     "2 jours au réfrigérateur : à préparer la veille."),
    ("Boules abricot-amande", "Boule ou pâte de fruits", 10,
     [("abricots_secs", 150), ("raisins_secs", 50), ("amandes", 50), ("jus_citron", 10)],
     "Mixe le tout grossièrement, forme 10 boules à la main.",
     "10 jours au réfrigérateur dans une boîte fermée."),
    ("Boisson isotonique maison", "Boisson", 2,
     [("eau", 750), ("jus_orange", 250), ("miel", 30), ("sel", 1.2)],
     "Dissous le miel et le sel dans un peu d'eau tiède, ajoute le jus et le reste de l'eau. Pour 2 bidons de 500 ml.",
     "24 h au réfrigérateur."),
    ("Boisson haute dose 2:1 (90 g par bidon)", "Boisson", 1,
     [("eau", 750), ("maltodextrine", 60), ("fructose", 30), ("sel", 1.5)],
     "Secoue dans le bidon jusqu'à dissolution complète. Pour 1 bidon de 750 ml, soit environ 1 h d'effort long.",
     "À boire dans la journée."),
    ("Boisson de récupération chocolat", "Récupération", 2,
     [("lait_demi", 500), ("cacao", 10), ("miel", 20)],
     "Mélange au fouet ou au shaker. À boire dans l'heure qui suit l'effort.",
     "24 h au réfrigérateur."),
)


def ingredient(code):
    return INGREDIENTS.get(code)
