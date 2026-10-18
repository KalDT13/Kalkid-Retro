# Kalkid Rétro

Gestionnaire de fenêtres multicompte pour **Dofus Rétro** : un seul programme pour passer d'un
personnage à l'autre, basculer automatiquement quand le jeu t'appelle, et (en option) synchroniser
tes actions entre comptes.

> Projet open source (licence MIT). Non affilié à Ankama.

## Fonctions

**Gestion des fenêtres**
- Détection automatique des fenêtres Dofus Rétro, ordre des personnages modifiable par glisser-déposer
- Fenêtre suivante / précédente / personnage principal ★ via raccourcis configurables
- Exclusion d'un personnage des raccourcis et des outils
- Presets (ordre, principal, exclusions, autofocus) enregistrables et rechargeables
- Anti-clignotement des fenêtres dans la barre des tâches

**Vérification des prérequis**
- L'onglet *Prérequis* contrôle Windows, les notifications, les droits d'exécution, les raccourcis
  et indique quoi corriger, avec un bouton qui ouvre le bon réglage Windows

**Autofocus par notifications**
- Passe automatiquement sur le bon personnage quand le jeu envoie une notification Windows :
  combat (« à toi de jouer »), échange, invitation de groupe, message privé
- Réglage par personnage et par type d'événement, mode debug avec journal
- Utilise uniquement les notifications du jeu : aucune lecture réseau, aucun accès aux fichiers du jeu

**Outils optionnels (désactivés par défaut)**
- Clics synchronisés : clic molette = clic gauche au même endroit sur tous les comptes, avec un délai
  aléatoire réglable ; raccourci dédié pour un clic sans délai
- Invitation de groupe : le chef invite tout le monde, chaque invité valide puis invite le suivant,
  avec des délais réglables

## ⚠️ Avertissement : règles d'Ankama

Ankama tolère les outils de **gestion de fenêtres**, mais interdit strictement les **macros**.
Les « outils optionnels » ci-dessus envoient des actions sur plusieurs comptes à la fois : ils
peuvent être considérés comme des macros et **entraîner une sanction sur ton compte**. C'est pourquoi
ils sont **désactivés par défaut** et demandent une confirmation à l'activation.
Tu les utilises à tes risques ; les auteurs déclinent toute responsabilité.

## Installation

1. Télécharge `Kalkid-Retro.exe` depuis la
   [dernière version](https://github.com/KalDT13/Kalkid-Retro/releases/latest) (section **Releases**).
2. Lance-le. Windows SmartScreen peut afficher un avertissement (programme non signé) : *Informations
   complémentaires > Exécuter quand même*. L'application intercepte des raccourcis clavier, ce qui
   déclenche cette alerte sur ce type d'outil.
3. **Pour l'autofocus** :
   - en jeu : *Options > Général > Notification en arrière-plan* ;
   - Windows : *Paramètres > Système > Notifications* activées ;
   - optionnel : couper le son des notifications de l'application Dofus.

Les réglages sont enregistrés dans `%APPDATA%\KalkidRetro\config.json`.

## Lancer depuis les sources

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m kalkid_retro
```

Build de l'exécutable (nécessite `pyinstaller`) :

```bash
python tools/make_icon.py
pyinstaller --noconfirm --onefile --windowed --name Kalkid-Retro --icon assets/kalkid.ico --collect-submodules winsdk run.py
```

Un tag `vX.Y.Z` poussé sur GitHub lance le workflow qui compile l'exe et le publie dans les Releases.

## Contribuer

Le code est public, mais seul le mainteneur peut modifier le dépôt directement. Les propositions
passent par une *pull request*, relue avant d'être acceptée. Les idées et bugs sont les bienvenus
dans les *Issues*.

## Crédits

- Le principe de l'autofocus par notifications Windows a été popularisé par
  [Dracoon](https://github.com/Slyss49/Dracoon-Dofus) (Slyss49). Kalkid Rétro est une implémentation
  indépendante : aucun code de Dracoon n'y est repris.
- Construit avec [PySide6](https://doc.qt.io/qtforpython-6/) et [winsdk](https://github.com/pywinrt/python-winsdk).

## Licence

[MIT](LICENSE)
