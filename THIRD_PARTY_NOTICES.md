# Composants tiers

TrailMaster Pro est sous licence MIT (voir `LICENSE`). Il embarque ou utilise :

| Composant | Usage | Licence |
|---|---|---|
| [PySide6 / Qt](https://doc.qt.io/qtforpython-6/) | Interface graphique | LGPL v3 |
| [fitparse](https://github.com/dtcooper/python-fitparse) | Lecture des fichiers .FIT de la montre | MIT |
| [cryptography](https://github.com/pyca/cryptography) | Chiffrement | Apache 2.0 / BSD |
| [certifi](https://github.com/certifi/python-certifi) | Certificats SSL | MPL 2.0 |
| [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) | Synchronisation Garmin Connect | MIT |
| [keyring](https://github.com/jaraco/keyring) | Rangement sécurisé des identifiants | MIT |
| [Pillow](https://python-pillow.org) | Lecture et réduction des photos | MIT-CMU (HPND) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (`rapidocr_onnxruntime`, modèles PaddleOCR) | Lecture des dossards sur les photos | Apache 2.0 |
| [ONNX Runtime](https://onnxruntime.ai) | Moteur de la lecture des dossards | MIT |
| [OpenCV](https://opencv.org) (`opencv-python`) | Traitement d'image pour la lecture des dossards | Apache 2.0 |
| [NumPy](https://numpy.org) | Calcul (lecture des dossards) | BSD 3-Clause |
| [Shapely](https://github.com/shapely/shapely), [pyclipper](https://github.com/fonttools/pyclipper), [PyYAML](https://pyyaml.org), [six](https://github.com/benjaminp/six) | Dépendances de RapidOCR | BSD 3-Clause, MIT, MIT, MIT |
| [PyInstaller](https://pyinstaller.org) | Fabrication des applications | GPL v2 avec exception (n'impose rien au logiciel fabriqué) |
| [Leaflet](https://leafletjs.com/) (`interface/assets/leaflet`) | Cartes | BSD 2-Clause |
| [IBM Plex Sans](https://github.com/IBM/plex) (`ressources/polices`) | Police | SIL Open Font License 1.1 |
| [Sora](https://github.com/sora-xor/sora-font) (`ressources/polices`) | Police | SIL Open Font License 1.1 |

Les fonds de carte (OpenStreetMap et autres) restent soumis aux conditions de
leurs fournisseurs : https://www.openstreetmap.org/copyright
