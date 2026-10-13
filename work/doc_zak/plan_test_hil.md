# Plan de test HIL — STM32F7508-DK

## 1. Objectif et principe

Automatiser depuis un PC la programmation, le pilotage et la vérification du projet sur la carte STM32F7508-DK. Le PC orchestre les scénarios avec pytest ; un firmware dédié reçoit les commandes par UART, appelle les pilotes de la carte et renvoie des résultats. ST-LINK/OpenOCD ou DFU servent à programmer la cible. Les instruments externes complètent les contrôles lorsque le résultat doit être vérifié physiquement.

```text
PC : runner + pytest + adaptateurs
       ├── ST-LINK/OpenOCD ou DFU ── programmation/reset ──┐
       ├── port série virtuel ── commandes/résultats ──────┤
       └── instruments optionnels ── mesures ──────────────┤
                                                          ▼
STM32F7508-DK : firmware de bench → pilotes existants → périphériques
```

## 2. Répartition des dossiers et fichiers

Les applications produit restent dans `dev/`. Le firmware de validation et les tests Python sont regroupés dans `tests/`. Le firmware de bench réutilise les pilotes `dev/common/` et le BSP `stm32f7508-dk/` ; il ne duplique pas leur code.

```text
.
├── Makefile                         # Déclarer les sources et cibles du firmware HIL
├── dev/
│   ├── apps/                        # Applications existantes, inchangées
│   └── common/                      # Pilotes partagés par les applications et le bench
│       └── uart/
│           ├── uart.c               # Étendre avec la réception UART si nécessaire
│           └── uart.h
├── stm32f7508-dk/                   # BSP, startup, linker, programmation et reset
└── tests/
    ├── firmware/
    │   └── hil-bench/
    │       ├── main.c               # Initialisation et boucle de commandes
    │       ├── protocol.c           # Réception/décodage et réponses
    │       ├── protocol.h
    │       ├── dispatch.c           # Routage commande vers service
    │       ├── dispatch.h
    │       ├── commands.c           # Commandes de validation des périphériques
    │       └── commands.h
    └── host/
        └── hil/
            ├── pyproject.toml        # Dépendances Python et configuration pytest
            ├── pytest.ini            # Marqueurs et options de test
            ├── run_hil.py            # Point d’entrée d’une campagne
            ├── config/
            │   └── bench.yaml        # Port, débit, délais et options matérielles
            ├── adapters/
            │   ├── serial_adapter.py # Dialogue avec le firmware
            │   ├── programmer.py     # Build/flash par les outils du dépôt
            │   ├── board.py          # Reset et préparation de la carte
            │   └── instruments.py    # Mesures optionnelles
            ├── fixtures/
            │   └── board_fixtures.py # Connexion et cycle de vie pytest
            └── cases/
                ├── test_startup.py
                ├── test_uart_clock.py
                ├── test_led.py
                ├── test_lcd.py
                ├── test_qspi.py
                ├── test_bootloader.py
                └── test_dfu.py
```

### Responsabilité des fichiers

- `main.c` initialise l’UART, les services nécessaires et exécute la boucle principale du banc.
- `protocol.*` définit le format des commandes et réponses, leur décodage et les erreurs de protocole.
- `dispatch.*` associe chaque commande à son traitement sans intégrer la logique de transport.
- `commands.*` effectue les opérations de validation en appelant les pilotes existants de LED, RCC, LCD/LTDC et QSPI.
- `serial_adapter.py` envoie les requêtes, associe les réponses aux transactions et gère les timeouts.
- `programmer.py` appelle les cibles Makefile et les outils existants : OpenOCD/ST-LINK ou DFU.
- `board.py` regroupe reset, synchronisation au démarrage et préparation de l’état initial.
- `cases/test_*.py` contient les scénarios, leurs assertions et critères d’acceptation.
- `instruments.py` est utilisé seulement si un équipement de mesure est disponible.

Le Makefile devra permettre de construire l’image depuis `tests/firmware/hil-bench/`, tout en liant les sources du BSP et les modules de `dev/common/`. Les règles actuelles supposent principalement des entrées dans `dev/apps/` : leur généralisation ou l’ajout explicite d’une image HIL sera à traiter dans la branche socle.

## 3. Protocole firmware ↔ PC

Le pilote UART du dépôt est actuellement émetteur seulement. Il faut ajouter la réception des commandes, avec une interface bornée dans le temps. Un protocole texte est recommandé pour commencer : il reste inspectable depuis un terminal et facile à exploiter en Python.

```text
CMD 42 QSPI_READ_ID
RESULT 42 OK id=...
END 42
```

Le numéro identifie la transaction. Chaque commande doit terminer par un résultat explicite, succès ou erreur. La bannière de démarrage indique au minimum le nom et la version du firmware ainsi que ses capacités. Définir les commandes et les formats de réponse avant d’implémenter les deux côtés évite les divergences entre firmware et pytest.

## 4. Périmètre de tests

| Lot | Vérifications principales |
|---|---|
| Démarrage | Programmation, reset, bannière attendue, disponibilité des commandes |
| UART/horloge | Communication, valeurs de configuration et temporisations attendues |
| LED | Commandes et séquence de clignotement ; mesure externe si nécessaire |
| LCD | Activation du rétroéclairage, initialisation LTDC et motifs affichés |
| QSPI | Réponse de la flash, identifiant JEDEC et lecture mémoire mappée |
| Bootloader | Démarrage depuis QSPI et comportement pour image valide/invalide |
| DFU | Entrée dans le bootloader ROM, programmation de la flash interne et redémarrage |

ADC batterie et RTC ne sont pas inclus dans le périmètre initial : ces fonctions ne figurent pas parmi les fonctions logicielles actuellement identifiées dans le dépôt.

## 5. Branches Git et progression

Garder `main` stable et créer les branches au fur et à mesure. Chaque branche doit livrer un incrément intégrable et vérifiable ; ne pas créer toutes les branches d’avance.

```text
main
└── feature/hil-foundation
    └── feature/hil-protocol
        ├── feature/hil-firmware
        └── feature/hil-host-runner
            └── feature/hil-startup-tests
                ├── feature/hil-led-tests
                ├── feature/hil-lcd-tests
                ├── feature/hil-qspi-tests
                └── feature/hil-bootloader-tests
```

| Branche | Incrément attendu |
|---|---|
| `feature/hil-foundation` | Créer l’arborescence et intégrer la cible firmware au Makefile. |
| `feature/hil-protocol` | Définir les commandes, réponses, erreurs et timeouts. |
| `feature/hil-firmware` | Implémenter le firmware, la réception UART et les premières commandes. |
| `feature/hil-host-runner` | Ajouter pytest, configuration, adaptateurs série/programmeur et rapports. |
| `feature/hil-startup-tests` | Valider le parcours complet : programmer, reset, bannière, commande/réponse. |
| `feature/hil-led-tests` | Ajouter les scénarios LED. |
| `feature/hil-lcd-tests` | Ajouter les scénarios LCD et rétroéclairage. |
| `feature/hil-qspi-tests` | Ajouter les contrôles QSPI. |
| `feature/hil-bootloader-tests` | Ajouter les scénarios bootloader, intégrité d’image et DFU. |

Ordre pratique : socle → protocole → firmware et runner → premier test intégré → périphériques → bootloaders/DFU. Fusionner le premier test intégré avant d’étendre la campagne aux autres fonctions.

## 6. Exécution et livrables

Une campagne suit ce cycle : vérifier le banc, compiler l’image, programmer la cible, réinitialiser, attendre la bannière, exécuter les scénarios, collecter les réponses/mesures puis générer le rapport. Chaque test précise prérequis, résultat attendu, timeout et tolérance.

Archiver pour chaque exécution le commit Git, configuration, binaire, journal série, mesures disponibles et rapport JUnit. Les sorties générées vont dans `work/hil-results/` et ne doivent pas être suivies par Git. Les résultats des cas doivent distinguer au minimum les erreurs de programmation, de communication et fonctionnelles.

## 7. Premier incrément recommandé

Commencer par `feature/hil-foundation`, puis réaliser le plus petit parcours bout en bout : construire le firmware de bench, le programmer, le redémarrer, recevoir sa bannière, envoyer `HELLO` et valider sa réponse depuis pytest. Ce parcours validera l’architecture avant l’ajout des tests périphériques.
