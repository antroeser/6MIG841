# Lab 1, Préparer l'environnement du cours 6MIG841

Ce laboratoire ne produit pas de robot. Il produit **la machine** sur laquelle les deux
devoirs et le projet vont tourner. Vous en sortez avec un environnement Python vérifié,
les modèles de vision téléchargés, un LLM local qui répond, et une idée claire de ce que
ROS2 apporte et de ce qu'il coûte.

Comptez 45 à 60 minutes, dont une bonne part en téléchargement.

---

## Ce que vous aurez à la fin

| Élément | Où | Vérification |
| --- | --- | --- |
| Environnement Python isolé | `.venv/` à la racine | `check_env.py` dit `PRET` |
| Neuf librairies, versions figées | `Lab1/code/requirements.txt` | `check_env.py` les liste avec leur version |
| Socle commun `ihr_ros` | `Lab1/code/ihr_ros/` | `import ihr_ros` fonctionne |
| Modèle de main MediaPipe | `Lab1/code/models/hand_landmarker.task` | 7 819 105 octets |
| Modèle d'objets YOLO | `Lab1/code/models/yolo11n.pt` | 80 classes chargées |
| LLM local | démon Ollama | `ollama list` montre `llama3.2` |
| 65 tests verts | `Lab1/test/` | `pytest Lab1/test -q` |

---

## Étape 0, Ce que vous devez déjà avoir

Ouvrez un terminal PowerShell à la racine du dépôt (`6MIG841-Lab`) et vérifiez :

```powershell
py --list
ollama --version
```

Résultat attendu : au moins une version de Python 3.11, 3.12 ou 3.13, et une version
d'Ollama.

**Diagnostic.** Pas de `py` : installez Python depuis python.org, en cochant
« Add python.exe to PATH ». Pas d'`ollama` : installez-le depuis ollama.com, l'installation
ne demande pas de droits administrateur.

---

## Étape 1, Créer l'environnement virtuel

Un environnement virtuel isole les librairies du cours du reste de votre machine. Sans lui,
une mise à jour faite pour un autre cours casse celui-ci.

```powershell
powershell -ExecutionPolicy Bypass -File .\Lab1\code\install_lab1.ps1
```

Le script enchaîne six étapes et les annonce. Il est **idempotent** : relancé, il ne
réinstalle que ce qui manque. Pour voir ce qu'il ferait sans rien écrire :

```powershell
powershell -ExecutionPolicy Bypass -File .\Lab1\code\install_lab1.ps1 -DryRun
```

Résultat attendu, à la fin :

```text
Installation terminee. Environnement pret.
Activer :  .\.venv\Scripts\Activate.ps1
```

### Diagnostic, les deux pannes rencontrées le 2026-09-18

**Panne 1 : `py -3.12 -m venv` échoue.**

```text
Unable to copy 'C:\...\Python312\venvlauncher.exe'
Error: [WinError 2] Le fichier spécifié est introuvable
```

L'installation de Python 3.12 de cette machine est amputée de `venvlauncher.exe`. Le
Python lui-même fonctionne, mais il ne sait plus fabriquer d'environnement virtuel.
Solution : prenez une autre version.

```powershell
powershell -ExecutionPolicy Bypass -File .\Lab1\code\install_lab1.ps1 -PythonVersion 3.13
```

**Panne 2 : `pip` rend 0 alors qu'il a échoué.**

```text
ERROR: Could not find a version that satisfies the requirement pyttsx3==2.100
ERROR: No matching distribution found for pyttsx3==2.100
[exited with code 0]
```

Lisez bien la dernière ligne. `pip` a signalé deux erreurs et s'est terminé avec le code
de sortie **0**, qui veut dire succès. Un script qui teste le code de retour conclurait
donc que l'installation a réussi, alors qu'aucune librairie n'a été installée.

C'est pour cela que `install_lab1.ps1` ne juge pas `pip` sur son code de retour. Il lance
`check_env.py`, qui **importe réellement chaque librairie**. On vérifie l'effet, jamais
l'annonce. Retenez ce réflexe, il resservira tout le trimestre.

La cause de cette panne-là : les versions `pyttsx3==2.100` et `ollama==0.6.3` avaient été
écrites de mémoire et n'existent pas. Les dernières sont `2.99` et `0.6.2`. Les versions
de `requirements.txt` sont maintenant **mesurées**, pas devinées : elles proviennent d'une
résolution `pip` réelle sur cette machine, puis figées.

---

## Étape 2, Vérifier l'environnement

C'est la commande à relancer chaque fois que quelque chose refuse de démarrer.

```powershell
.\.venv\Scripts\python.exe .\Lab1\code\check_env.py
```

Sortie attendue, abrégée :

```text
OK   Python 3.13.3
     C:\...\6MIG841-Lab\.venv\Scripts\python.exe

-- Librairies indispensables ---------------------------------------------
OK   cv2                  5.0.0
OK   mediapipe            1.0.1
OK   numpy                2.5.3
OK   ihr_ros              1.0.0

-- ROS2 et dorsale -------------------------------------------------------
abs  ROS2 importable : False
     dorsale retenue : sim

==========================================================================
 PRET : les librairies indispensables sont en place.
==========================================================================
```

Deux options utiles :

```powershell
.\.venv\Scripts\python.exe .\Lab1\code\check_env.py --camera   # ouvre vraiment la webcam
.\.venv\Scripts\python.exe .\Lab1\code\check_env.py --json     # sortie lisible par machine
```

**Diagnostic.** La ligne `Python` marquée `ATT` au lieu de `OK` signifie que vous avez
lancé `python` au lieu du Python du `.venv`. C'est la panne la plus fréquente du cours :
l'installation s'est bien passée, mais vous parlez au mauvais interpréteur. Utilisez le
chemin complet `.\.venv\Scripts\python.exe`, ou activez l'environnement une fois pour
toutes :

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## Étape 3, D'où viennent ces librairies

Elles ne sont pas choisies au hasard : elles sont **extraites des rapports** des
étudiants des années précédentes. Le script qui fait ce travail est réutilisable.

```powershell
.\.venv\Scripts\python.exe .\Lab1\code\extract_libs.py
```

Il lit les 19 PDF et les 11 fichiers source de `*/rapport_etudiants/`, relève chaque
`import`, croise avec les mentions en prose (« nous avons utilisé OpenCV et Yolo »), et
écrit `Lab1/code/libraries.json`.

Résultat mesuré le 2026-09-18 : **30 documents lus, 0 illisible, 0 module inconnu**.

```text
module               pypi                 role     preuve         travaux
----------------------------------------------------------------------------
cv2                  opencv-python        vision   import,prose   Devoir1,Projet
mediapipe            mediapipe            vision   import,prose   Devoir1,Projet
ultralytics          ultralytics          objets   import,prose   Projet
rclpy                -                    ros2     import,prose   Devoir2,Projet
ollama               ollama               llm      import,prose   Devoir2
speech_recognition   SpeechRecognition    voix     import,prose   Devoir2
...
```

La colonne `preuve` distingue `import` (le module apparaît dans du code) de `prose` (il
est cité dans le texte du rapport). Un module cité mais jamais importé est un signal :
soit le code n'a pas été joint, soit la librairie a été mentionnée sans être utilisée.

La correspondance module → paquet PyPI vit dans `Lab1/code/library_markers.json`, en
**donnée**. Ajouter une librairie n'exige donc pas de modifier le script.

### Diagnostic, un piège d'expression régulière

La première version du script rapportait treize « modules inconnus », dont `client`,
`yolo`, `node`, `pose` et `twist`. Aucun n'est un module. Le motif `import\s+(\w+)`
appliqué au texte entier capture aussi ce qui suit le mot `import` dans un
`from ollama import Client`, c'est-à-dire le nom **importé** et non le module.

Le correctif est dans `extract_libs.py` : les formes `from X import` sont relevées
**puis retirées** du texte, de sorte que le second motif ne puisse plus les voir. Le test
`Lab1/test/test_extract_libs.py` vérifie les deux directions, `{"ollama"}` présent et
`"client"` absent.

---

## Étape 4, Les modèles de vision

Deux modèles sont nécessaires. Ils se téléchargent tout seuls au premier usage, mais
autant le faire maintenant, en salle, plutôt que pendant une démonstration.

```powershell
.\.venv\Scripts\python.exe -c "from ihr_ros.hands import ensure_model; print(ensure_model())"
cd Lab1\code\models
..\..\..\.venv\Scripts\python.exe -c "from ultralytics import YOLO; m=YOLO('yolo11n.pt'); print(len(m.names), 'classes')"
cd ..\..\..
```

Résultat attendu : le chemin du fichier `hand_landmarker.task`, puis `80 classes`.

| Fichier | Taille | Sert à |
| --- | --- | --- |
| `hand_landmarker.task` | 7 819 105 o | Devoir 1 et Projet : 21 points de la main |
| `yolo11n.pt` | 5 613 764 o | Projet : détection de 80 classes d'objets |

### Le piège MediaPipe, à connaître avant d'ouvrir un code d'étudiant

Les quatre programmes rendus en 2025 commencent tous par :

```python
import mediapipe as mp
mp_hands = mp.solutions.hands          # <-- n'existe plus
```

Sur MediaPipe 1.0.1, installé ici, cette ligne lève :

```text
AttributeError: module 'mediapipe' has no attribute 'solutions'
```

Ce n'est pas une faute de leur part. L'ancienne API, dite « Solutions », a été retirée
depuis leur remise. Le paquet n'expose plus que `Image`, `ImageFormat` et `tasks`, et
`import mediapipe.python.solutions` lève `ModuleNotFoundError`.

La nouvelle API s'appelle **Tasks**. Deux différences pratiques :

1. Le modèle n'est plus embarqué dans la roue Python, d'où le fichier `.task` ci-dessus.
2. Le mode vidéo exige un **horodatage strictement croissant** à chaque appel. Un
   horodatage qui recule fait lever MediaPipe.

Vous n'avez pas à gérer cela vous-même : `ihr_ros.hands.HandTracker` enveloppe l'API et
s'occupe de l'horodatage. C'est d'ailleurs sa principale raison d'être.

---

## Étape 5, Le LLM local

Le Devoir 2 fait traduire des commandes vocales par un modèle de langue qui tourne **sur
votre machine**. Rien ne part sur Internet, et il n'y a pas de clé d'API à obtenir.

```powershell
ollama pull llama3.2
ollama list
```

Résultat attendu : une ligne `llama3.2:latest` d'environ 2,0 Go.

Vérifiez que le démon répond :

```powershell
.\.venv\Scripts\python.exe .\Lab1\code\check_env.py
```

La section `-- Ollama --` doit afficher `demon joignable` et la liste des modèles.

**Diagnostic.** `demon injoignable` : lancez `ollama serve` dans un terminal séparé et
laissez-le ouvert.

---

## Étape 6 - ROS2, installé, vérifié, et `colcon build` prouvé

Les trois travaux qui suivent commandent une tortue `turtlesim` par des messages ROS2. ROS2 est
un intergiciel né sous Linux, et la voie habituelle sous Windows passe par WSL2 ou Docker.

**Aucune des deux ne fonctionne sur les machines gérées de l'UQAC.** Mais une troisième voie
existe, et c'est celle que ce laboratoire emploie.

### Ce qui est bloqué, et ce qui ne l'est pas

Mesuré le 2026-09-18 sur la machine de l'enseignant :

```powershell
wsl -d docker-desktop -- echo ok
```

```text
Échec d'ouverture de session : l'utilisateur ne bénéficie pas du type d'ouverture
de session demandé sur cet ordinateur.
Code d'erreur : Wsl/Service/CreateInstance/CreateVm/HCS/0x80070569
```

La distribution `docker-desktop` était **déjà installée**, et elle échoue aussi. Donc ce n'est
pas Ubuntu : **aucune machine virtuelle WSL2 ne démarre pour ce compte.** Le compte appartient
au groupe `BUILTIN\Utilisateurs` et n'est pas membre de `Hyper-V Administrators`. Docker
Desktop passant par la même machine virtuelle, il est bloqué pour la même raison.

| Voie | Verdict |
| --- | --- |
| WSL2 | bloquée, politique machine |
| Docker | bloquée, même machine virtuelle |
| archive binaire ROS2 officielle | bloquée : Chocolatey, OpenSSL et un `setx /m` réclament l'administrateur |
| **conda et le canal RoboStack** | **passe**, tout reste dans le profil utilisateur |

Retenez le raisonnement autant que la conclusion. Trois voies fermées ne prouvent pas que la
chose est impossible ; elles disent qu'il faut chercher ailleurs.

### L'installation

Rien de tout cela ne demande de droits administrateur.

```powershell
scoop install miniforge3
$conda = "$env:USERPROFILE\scoop\apps\miniforge3\current"
& "$conda\Scripts\conda.exe" create -n ihr -y -c conda-forge -c robostack-humble `
    python=3.12 ros-humble-ros-base ros-humble-turtlesim
& "$conda\envs\ihr\python.exe" -m pip install -r Lab1\code\requirements.txt
& "$conda\envs\ihr\python.exe" -m pip install -e Lab1\code
```

Résultat mesuré : **13 imports sans échec dans un seul interpréteur**, Python 3.12.14, avec
`rclpy`, `geometry_msgs.msg`, `turtlesim.msg`, `cv2` et `mediapipe` ensemble.

Vous avez donc **deux** interpréteurs, et c'est voulu.

| | `.venv` | environnement conda `ihr` |
| --- | --- | --- |
| Python | 3.13.3 | 3.12.14 |
| ROS2 | absent | Humble |
| Sert à | Lab 1, Devoir 1, tests hors ligne | Devoir 2, Projet, tout ce qui touche ROS2 |

### Deux variables obligatoires, et le script qui les pose

Ce ne sont pas des astuces. Sans elles, deux problèmes arrivent.

```powershell
$env:ROS_LOCALHOST_ONLY = "1"
$env:ROS_DOMAIN_ID = "7"
```

**Le pare-feu.** Fast DDS émet en multicast sur les interfaces réseau, et Windows réclame alors
les droits administrateur pour `turtlesim_node.exe` et `python.exe`. Vous pouvez **refuser**
l'invite : le trafic loopback échappe au filtrage, et la première preuve ROS2 a réussi malgré un
refus. Mais `ROS_LOCALHOST_ONLY` supprime la demande à la source.

**Le voisin.** Sans cette variable, DDS découvre tout le monde sur le sous-réseau. En salle de
classe, la commande d'un étudiant pilote la tortue d'un autre. Le symptôme est une tortue qui
bouge toute seule, et le coupable est à trois rangs de là. Ce piège coûte une séance entière,
parce que personne ne soupçonne le voisin. Donnez-vous un `ROS_DOMAIN_ID` distinct.

Depuis plan01, vous ne posez plus ces variables (ni `AMENT_PREFIX_PATH`, ni le `PATH`) à la
main : `Lab1/code/ros2_env.ps1` s'en charge et rend le chemin de l'interpréteur conda sur sa
sortie standard.

```powershell
$py = & .\Lab1\code\ros2_env.ps1
& $py -c "import rclpy; print('ok')"
```

Le domaine ROS2 par défaut (7) vient de `Lab1/code/ihr_config.json`, section `ros2` (R7,
aucune valeur numérique en dur) : `-RosDomainId` le remplace au besoin. Un environnement conda
absent est un refus explicite, code de sortie **2**, jamais un repli silencieux sur le `.venv`.

### Vérifier que ça marche

Deux terminaux. Dans le premier, la tortue :

```powershell
$py = & .\Lab1\code\ros2_env.ps1
& "$env:USERPROFILE\scoop\apps\miniforge3\current\envs\ihr\Library\lib\turtlesim\turtlesim_node.exe"
```

Dans le second, le Devoir 2 sur la vraie tortue :

```powershell
$py = & .\Lab1\code\ros2_env.ps1
$env:IHR_BACKEND = "ros2"
& $py Devoir2\code\voice_turtle.py --input clavier
```

La bannière doit dire `[ROS2] dorsale = ROS2 (rclpy + turtlesim)`. Si elle dit `[SUBSTITUT]`,
l'interpréteur n'est pas le bon.

Preuve relevée le 2026-09-18 : `recue=True`, et la pose passée de `x=5.544` à `x=6.826`. Le
`recue=True` est la ligne qui compte : la pose vient du vrai topic, pas d'une valeur supposée.

### Cinq frictions, toutes mesurées

| Symptôme | Cause | Remède |
| --- | --- | --- |
| le pare-feu réclame l'administrateur | Fast DDS émet en multicast | `ROS_LOCALHOST_ONLY`, et refuser l'invite |
| la tortue bouge toute seule | DDS a découvert un autre étudiant | `ROS_LOCALHOST_ONLY` et un `ROS_DOMAIN_ID` propre |
| `ros2 ...` échoue mais `import rclpy` marche | `AMENT_PREFIX_PATH` absent | passer par `ros2_env.ps1` |
| `turtlesim_node.exe` introuvable dans `Library\bin` | il vit dans `Library\lib\turtlesim\` | convention ROS2 |
| `conda run` plante sur un greffon | commande trop longue | appeler `envs\ihr\python.exe` directement |

### Le substitut de tortue, et à quoi il sert maintenant

`ihr_ros.backends.sim` reproduit le modèle cinématique de turtlesim en Python pur. Il a été
écrit quand ROS2 semblait inaccessible, et il reste utile pour une seule chose : les **tests
hors ligne**. Les 200 tests du dépôt tournent sans ROS2 grâce à lui, donc sans rien installer,
et rendent le même résultat sous l'environnement conda (plan01, étape 9).

Ce n'est pas la solution livrée. Il annonce toujours `[SUBSTITUT]` dans sa sortie, parce qu'un
étudiant qui croit piloter turtlesim alors qu'il pilote un substitut passerait la séance à
déboguer une installation qui n'a jamais été active.

### Le paquet d'interfaces, et `colcon build` prouvé le 2026-09-18

`ros2_ws/src/ihr_6mig841_interfaces/` déclare trois interfaces, en `ament_cmake` (un paquet
`ament_python` ne peut pas générer de messages) :

| Type | Nom | Contenu |
| --- | --- | --- |
| message | `Step` | `nom_action`, `distance_m`, `angle_deg`, `is_forward`, `is_clockwise` |
| service | `Interpret` | requête : commande, historique. réponse : succès, tableau de `Step`, justification, erreur |
| action | `ExecutePlan` | but : tableau de `Step`. résultat : succès, messages publiés, raison d'arrêt. retour : étape courante, total, progression |

`distance_m` et `angle_deg` sont des grandeurs **non signées** : le sens passe par
`is_forward` et `is_clockwise`. Motif mesuré le 2026-09-18 : un modèle de langue rendait `+90`
pour « à droite » comme pour « à gauche ». Un booléen ne peut pas avoir le mauvais signe.

Précondition : le compilateur MSVC actif dans ce terminal (`vcvarsall.bat x64`, voir la
note sous le tableau de frictions ci-dessous). Sans les deux options `-DPYTHON_EXECUTABLE`
et `-DPython3_EXECUTABLE`, CMake trouve un autre Python que celui de conda et la
configuration meurt sur `ModuleNotFoundError: ament_package` (voir la première friction du
tableau) : c'est la commande **réellement exécutée** le 2026-09-18, copiable telle quelle.

```powershell
$py = & .\Lab1\code\ros2_env.ps1
$pyBarres = $py -replace '\\', '/'
Set-Location ros2_ws
colcon build --merge-install --cmake-args "-DPYTHON_EXECUTABLE=$pyBarres" "-DPython3_EXECUTABLE=$pyBarres"
Set-Location ..
```

Vérifié le 2026-09-18, **par l'effet et non par le code de retour** (R9) : les trois types
s'importent depuis l'interpréteur conda (`from ihr_6mig841_interfaces.msg import Step`, etc.),
et `ros2 interface show ihr_6mig841_interfaces/msg/Step` les affiche depuis la CLI.

**Insuffisant pour un paquet qui crée un service ou une action, mesuré le 2026-09-18
(plan02).** La commande ci-dessus suffit pour l'**import** des messages, mais pas pour la
création réelle d'un service ROS2 : `LlmNode.create_service(Interpret, ...)` échouait sur
`rosidl_generator_py.import_type_support_impl.UnsupportedTypeSupport`, sans lien avec le
code Python du Devoir 2. `dumpbin /dependents` sur
`ihr_6mig841_interfaces_s__rosidl_typesupport_c.pyd` montrait un lien vers
`python314.dll` (l'installation par utilisateur de `AppData\Local\Python\pythoncore-3.14-64`,
la même fautive que la première friction du tableau ci-dessous), alors que le `.pyd` doit
être lié à `python312.dll` (l'environnement conda `ihr`). Cause : `rosidl_generator_py`
résout Python par **deux mécanismes CMake différents** dans le même paquet
(`rosidl_generator_py_generate_interfaces.cmake`, lignes 21-34) : `find_package(PythonExtra
REQUIRED)` (legacy `FindPythonInterp`/`FindPythonLibs`, correctement pointé par
`-DPYTHON_EXECUTABLE`/`-DPython3_EXECUTABLE`), **puis** `find_package(Python REQUIRED
COMPONENTS Interpreter Development NumPy)` (le module moderne `FindPython`, préfixe
`Python_*` **sans numéro**, jamais visé par ces deux options) pour construire l'extension
Python compilée (`_s__rosidl_typesupport_c.pyd`) elle-même. Sans indice, ce second appel
redécouvre `pythoncore-3.14-64` tout seul. Remède : ajouter les variables du préfixe
`Python_*` (et `Python3_*` par prudence) à la commande, puis reconfigurer proprement
(`--cmake-clean-cache`, sans quoi CMake garde le cache existant) :

```powershell
$py = & .\Lab1\code\ros2_env.ps1
$pyBarres = $py -replace '\\', '/'
$condaEnvDir = Split-Path -Parent $py
$condaEnvBarres = $condaEnvDir -replace '\\', '/'
Set-Location ros2_ws
colcon build --merge-install --cmake-args `
  "-DPYTHON_EXECUTABLE=$pyBarres" "-DPython3_EXECUTABLE=$pyBarres" `
  "-DPython_EXECUTABLE=$pyBarres" `
  "-DPython_ROOT_DIR=$condaEnvBarres" "-DPython3_ROOT_DIR=$condaEnvBarres" `
  "-DPython_FIND_STRATEGY=LOCATION" "-DPython3_FIND_STRATEGY=LOCATION"
Set-Location ..
```

Vérifié par l'effet (R9), pas par le code de retour (`--cmake-clean-cache` seul rendait déjà
0 en gardant `python314.dll`) : `dumpbin /dependents` sur le `.pyd` reconstruit montre
`python312.dll`, et les deux tests `LlmNode` qui créent un vrai service ROS2
(`test_llm_node_le_service_rend_des_etapes`, `test_llm_node_rapporte_l_erreur_sans_lever`)
passent sous conda. Si `colcon build` est relancé un jour sans `--cmake-clean-cache` après un
premier essai fautif, le cache CMake garde `python314.dll` malgré ces options : la case
`build/ihr_6mig841_interfaces` doit être reconfigurée, pas seulement recompilée.

### Cinq frictions du `colcon build`, mesurées le 2026-09-18

`colcon build` n'avait jamais été exécuté avant plan01. Cinq pannes, dans l'ordre où elles
sont apparues (la cinquième, sous plan02, n'est apparue qu'en exerçant un vrai service
ROS2, ce que plan01 ne faisait pas) :

| Symptôme | Cause | Remède |
| --- | --- | --- |
| `ModuleNotFoundError: ament_package` pendant la configuration CMake | CMake trouvait un Python du registre Windows (`pythoncore-3.14-64`), pas celui de conda | `-DPYTHON_EXECUTABLE=... -DPython3_EXECUTABLE=...` vers l'interpréteur conda |
| `Invalid character escape '\U'` dans `cmake_install.cmake` | le chemin `C:\Users\...` contient `\U`, une séquence d'échappement invalide pour CMake | passer ce chemin en barres obliques (`-replace '\\', '/'`) |
| `AttributeError: module 'em' has no attribute 'BUFFERED_OPT'` dans `rosidl_adapter` | `colcon-common-extensions` installe `empy` 4.x, incompatible avec le générateur `rosidl` de Humble | `pip install empy==3.3.4` (version réelle, résolue via `pip index versions empy`, R14) |
| `PluginValidationError` sur `launch_testing` puis `launch_ros` au lancement de `pytest` sous conda | ces deux greffons `pytest11` de ROS2 Humble ne suivent pas le hookspec de `pytest` 9.1.1 (installé par `colcon-common-extensions`) | `pytest -p no:launch_testing -p no:launch_ros` |
| `UnsupportedTypeSupport` à la création d'un service ROS2 réel (`create_service`), le `.pyd` lié à `python314.dll` au lieu de `python312.dll` | `rosidl_generator_py` appelle `find_package(Python ...)` (préfixe moderne, sans numéro) en plus de `find_package(PythonExtra ...)` (legacy) ; seul ce second appel est visé par `-DPYTHON_EXECUTABLE`/`-DPython3_EXECUTABLE` | ajouter `-DPython_EXECUTABLE=... -DPython_ROOT_DIR=... -DPython3_ROOT_DIR=... -DPython_FIND_STRATEGY=LOCATION -DPython3_FIND_STRATEGY=LOCATION`, puis `--cmake-clean-cache` (voir détail ci-dessus) |

Le compilateur MSVC (Visual Studio Build Tools, `vcvarsall.bat x64`) doit être actif dans le
terminal avant `colcon build` : `ament_cmake` et `rosidl` compilent du C et du C++ pour le
typesupport des messages.

### `check_env.py` reconnaît deux interprètes légitimes

Avant plan01, `check_env.py` levait une alerte dès que l'interpréteur n'était pas celui du
`.venv`, un jugement faux la moitié du temps puisque l'environnement conda est le second
interprète légitime du laboratoire. Il porte maintenant un rôle à trois valeurs, `venv`,
`conda` ou `inconnu`, et n'avertit que sur la troisième. Il rapporte aussi les deux variables
ROS2 obligatoires, dont l'absence est la cause la plus probable d'un problème de pare-feu.

```powershell
.\.venv\Scripts\python.exe .\Lab1\code\check_env.py            # role : venv
$py = & .\Lab1\code\ros2_env.ps1; & $py .\Lab1\code\check_env.py   # role : conda
```

### Le paquet ROS2 du solutionnaire

Les trois travaux sont aussi publiés comme paquet `ament_python`, dans `ros2_ws/src/`, avec
trois points d'entrée, et dépendent maintenant de `ihr_6mig841_interfaces`. `colcon build` est
**vérifié depuis le 2026-09-18** (voir ci-dessus) : les deux paquets se construisent, et les
200 tests hors ligne du dépôt passent à l'identique sous le `.venv` et sous l'environnement
conda.

### Ce qui vient ensuite

Le Devoir 2 deviendra un **système ROS2** à six nœuds indépendants et parallèles, avec les trois
modes de communication : topic, service et action. Voir `enonce.md` à la racine et `plan02.md`.
Aujourd'hui le Devoir 2 est encore un programme unique qui publie dans ROS2, ce qui fonctionne
mais n'enseigne pas ROS2 ; le paquet d'interfaces de plan01 est le socle dont `plan02` a besoin
pour le service `Interpret` et l'action `ExecutePlan`.

## Étape 7, Le harnais Aider, pour coder localement

Aider est un outil de programmation assistée qui s'appuie sur un modèle **local** via
Ollama. Il est déjà installé et configuré sur les machines du laboratoire.

**Son manuel complet est `C:\Users\m3otis\.config\aider\MANUAL.md`.** Ne recopiez pas ses
instructions ici : lisez-le à la source, il est tenu à jour.

Repères pour vous y retrouver :

| Vous voulez | Section du `MANUAL.md` |
| --- | --- |
| Comprendre ce que le harnais construit | « What this builds » |
| Voir le processus complet en une figure | « The whole process, in one figure » |
| Installer les outils | « Step 1, Install the tools » |
| Vérifier que la machine suit | « Step 3, Test the computer » |
| Régler Ollama et fabriquer le tag à exécuter | « Step 4, Tune Ollama... » |
| Créer un projet | « Step 5, Create a project » |
| Lancer une nuit de travail | « Step 7, Run it » |
| Lire le résultat | « Step 8, Read the result » |
| Comprendre une panne | « Measured failure modes » |
| Savoir ce qui n'est délibérément pas automatisé | « What is deliberately not automated » |

Deux règles qui valent pour ce cours comme pour le harnais : le modèle local ne voit que
ce que vous mettez dans le prompt, il n'a ni votre dépôt ni votre conversation ; et une
réponse d'un modèle local est **relue**, jamais recopiée sans vérification.

---

## Étape 8, Lancer les tests du socle

```powershell
.\.venv\Scripts\python.exe -m pytest Lab1\test -q
```

Résultat attendu :

```text
65 passed in 0.40s
```

Ces 65 tests ne touchent ni la caméra, ni le micro, ni Ollama, ni ROS2. Ils couvrent la
configuration, la géométrie, le simulateur de tortue, le choix de dorsale, l'extracteur
de librairies, et depuis plan01 le contenu de `ros2_env.ps1`. Chaque fichier vérifie au moins
un **chemin d'échec** : une clé de configuration absente, une image de largeur nulle, une
dorsale ROS2 exigée mais indisponible, un environnement conda absent.

**Diagnostic.** `ModuleNotFoundError: No module named 'ihr_ros'` : le socle n'est pas
installé. Relancez `install_lab1.ps1`, ou seulement :

```powershell
.\.venv\Scripts\python.exe -m pip install -e .\Lab1\code
```

---

## L'évitement de collision

Les étapes 0 à 8 préparaient **la machine**. Le sujet réel du Lab 1, celui que l'énoncé donne,
est l'évitement de collision : une grille, un obstacle, un départ, un but, et un planificateur
qui rend une suite de points de passage. Aucune caméra, aucun micro, aucun ROS2 ici, un seul
processus matplotlib.

Ce sujet n'est pas livré par un seul planificateur, mais par **trois**, dans cet ordre, chacun
motivé par une limite du précédent, mesurée et non seulement affirmée.

| Palier | Planificateur | Ce qu'il apporte | La limite qu'il laisse |
| --- | --- | --- | --- |
| 1 | **A\*** | le chemin le plus court sur la grille | un escalier : le chemin suit les arêtes des cellules, donc multiplie les changements de direction |
| 2 | **Theta\*** | un test de ligne de vue, donc des segments à angle libre et bien moins de points de passage | il replanifie tout dès qu'un obstacle apparaît |
| 3 | **D\*-Lite** | la replanification **incrémentale**, qui réutilise le calcul précédent | aucune, c'est le dernier palier |

Le palier 2 est celui qui compte pour la suite du cours. Chaque changement de direction est
une rotation, et sur un vrai robot chaque rotation ajoute de la dérive d'odométrie. Un chemin
en escalier coûte donc plus qu'il n'en a l'air, et c'est au Projet que le prix se paie.

### Fichiers

| Fichier | Rôle |
| --- | --- |
| `Lab1/code/planif_config.json` | grille, départ, but, deux obstacles, couleurs : toutes les valeurs, avec provenance datée |
| `Lab1/code/planif/world.py` | grille, géométrie de cellule, occupation, ligne de vue |
| `Lab1/code/planif/astar.py` | palier 1 |
| `Lab1/code/planif/thetastar.py` | palier 2 |
| `Lab1/code/planif/dstarlite.py` | palier 3, expose `cellules_reexaminees` |
| `Lab1/code/planif/compare.py` | le banc comparé, rapport JSON |
| `Lab1/code/planif/app.py` | la vue matplotlib, le triangle qui se téléporte |

### Le tableau mesuré

Relancé le 2026-09-20 avec le banc de comparaison, sur la grille de `planif_config.json`
alignée sur la référence `solution_robot_dimension` (**64x64 cellules, départ `(1, 1)`, but
`(62, 62)`**, obstacle 3x3 centré sur `(32, 32)`) : la grille 12x10 du 2026-09-18 est retirée,
et le tableau ci-dessous la remplace. Voir aussi la section « Régression du 2026-09-20 et son
correctif » plus bas : ce tableau est mesuré **après** le correctif de `ligne_de_vue_libre`,
pas avant.

```powershell
cd Lab1\code
..\..\.venv\Scripts\python.exe -m planif.compare
```

```text
planificateur  longueur  points_de_passage  cellules_reexaminees
astar          88.024    65                 190
thetastar      86.375    4                  174
dstarlite      88.024    65                 107
```

Le rapport JSON complet est écrit dans `Lab1/code/planif/rapport_comparaison.json`.

Trois lectures de ce tableau, chacune la preuve mesurée d'un palier :

**A\* vers Theta\*.** Même grille, même départ, même but : A\* rend 65 points de passage,
Theta\* seulement 4, pour une longueur légèrement plus courte (86,375 contre 88,024). C'est la
ligne de vue du palier 2 qui supprime l'escalier. Une grille seize fois plus grande rend cet
écart bien plus visible qu'à 12x10 (18 contre 4).

**Theta\* et D\*-Lite face à une replanification.** La colonne `cellules_reexaminees` mesure,
pour A\* et Theta\*, le coût d'une replanification **complète** après l'ajout de l'obstacle de
replanification (colonnes 1-2, ligne 2, choisi pour ce point précis, voir la provenance de
`planif_config.json`) ; pour D\*-Lite, le coût d'une mise à jour **incrémentale** du même
changement. D\*-Lite réexamine 107 cellules là où A\* en réexamine 190 : près de deux fois
moins de travail pour retrouver un chemin tout aussi valide. C'est la raison d'être du palier 3,
et c'est exactement ce que
`Lab1/test/test_dstarlite.py::test_moins_de_cellules_reexaminees_qu_une_replanification_complete`
prouve à chaque exécution de la suite, pas seulement le 2026-09-20.

**Le chemin de D\*-Lite égale celui d'A\*.** Sans changement, D\*-Lite ne recalcule pas un
autre chemin : même longueur (88,024) et même nombre de points de passage (65) qu'A\*, avec un
ordre de points de passage différent puisque D\*-Lite part du but plutôt que du départ. C'est la
garantie que le palier 3 ne sacrifie rien à la qualité du chemin pour gagner en vitesse de
replanification.

### Régression du 2026-09-20 et son correctif

Signalée par l'enseignant : Theta\* traçait un chemin qui traverse l'obstacle. Diagnostic
complet dans `.sdd/6mig841-ameliorations/planificateurs-regression-report.md` ; résumé ici
par R1 (workflow.md), la faute n'est pas effacée.

**Cause racine, mesurée et non supposée.** `World.ligne_de_vue_libre` (world.py) marchait au
pas de Bresenham : sur un pas diagonal, elle ne bloquait que si les DEUX cellules voisines du
coin franchi étaient occupées, la même règle que `voisins()`. Cette règle est correcte pour un
pas de grille exactement à 45 degrés (le segment passe alors réellement par le coin, un point
de mesure nulle), mais fausse pour un pas diagonal de Bresenham a l'INTÉRIEUR d'un segment de
pente quelconque : mesuré sur le segment (0,0)-(4,7), Bresenham saute de (3,6) à (4,7) sans
jamais tester (4,6), alors que le segment réel (centres de cellule à centres de cellule)
traverse effectivement l'intérieur de (4,6) sur un intervalle non nul (t entre 0,875 et 0,929).
Corrigée par un parcours de grille exact (DDA / Amanatides-Woo, comparaison de fractions
entières, aucune division flottante) qui ne relâche la règle « deux côtés occupés » que pour un
vrai croisement de coin (les deux frontières franchies exactement ensemble).

**Un test circulaire l'a laissée passer.** Le seul test qui prouvait « Theta\* ne traverse pas
l'obstacle » rappelait `ligne_de_vue_libre` elle-même pour se juger : une version cassée de la
fonction validait donc son propre résultat. Remplacé par un contrôle indépendant
(`segments_traversant_une_cellule_occupee`, `Lab1/test/conftest.py`) qui échantillonne chaque
segment en coordonnées réelles et teste `est_occupee` directement, sans jamais appeler
`ligne_de_vue_libre` — appliqué aux trois planificateurs, pas seulement Theta\*.

**A\* et D\*-Lite : pas de défaut.** Le "1 segment traversant" mesuré pour A\* était un artefact
d'arrondi flottant dans un contrôle ad hoc moins prudent (une comparaison de frontière trop
stricte) ; le contrôle indépendant, avec une tolérance de frontière explicite, mesure 0 segment
traversant pour A\* avant comme après le correctif. L'`IndexError` rapporté pour D\*-Lite n'a
pas été reproduit malgré une mesure étendue (appels directs sur la grille de production, avant
et après son passage à 64x64, et 3000 configurations aléatoires avec mises à jour
incrémentales) : aucun code de D\*-Lite n'a été changé pour un défaut qui ne s'est jamais
manifesté (R14). Voir les réserves du rapport de régression pour le détail de cette mesure.

### Pourquoi le triangle se téléporte

Dans `app.py`, le triangle saute d'un point de passage au suivant, sans aucune interpolation
entre les deux. Aucune cinématique, aucune dynamique : ni vitesse, ni accélération, ni rayon de
virage n'existent ici.

C'est délibéré, pas une simplification oubliée. Un chemin correct et un mouvement correct sont
deux problèmes distincts, et les mêler rend l'échec illisible : si le triangle heurtait un
obstacle en le contournant mal, serait-ce le planificateur qui a mal calculé le chemin, ou
l'asservissement qui l'a mal suivi ? Le Lab 1 tranche la question en retirant le second
problème. La cinématique arrive au Devoir 2, dans turtlesim, sous forme de profils de vitesse,
avec sa propre conséquence à découvrir par l'expérience : commander la vitesse linéaire et la
vitesse angulaire à la fois décrit un arc, et un arc peut entrer dans un obstacle qu'un segment
évitait.

### Lancer l'application

```powershell
cd Lab1\code
..\..\.venv\Scripts\python.exe -m planif.app
```

Trois boutons, un par palier (`A*`, `Theta*`, `D*-Lite`), retracent le chemin dans sa propre
couleur et relancent la téléportation du triangle depuis le départ. C'est ce qui rend le
tableau ci-dessus visible, et pas seulement tabulé.

### Les tests

```powershell
.\.venv\Scripts\python.exe -m pytest Lab1\test\test_world.py Lab1\test\test_astar.py Lab1\test\test_thetastar.py Lab1\test\test_dstarlite.py Lab1\test\test_compare.py -q
```

Chaque suite couvre le chemin heureux de son module et au moins un chemin d'échec (départ hors
grille, but enfermé, ou configuration incomplète). Les deux tests qui prouvent la progression
d'un palier à l'autre, et non seulement trois implémentations sans hiérarchie, sont
`test_thetastar.py::test_thetastar_a_moins_de_points_de_passage_qu_astar_sur_la_meme_grille` et
`test_dstarlite.py::test_moins_de_cellules_reexaminees_qu_une_replanification_complete` : les
deux importent réellement les deux planificateurs comparés et mesurent la différence sur le
même monde, plutôt que de supposer le résultat.

---

## Ce qui est prêt pour la suite

| Travail | Lancement | Ce qu'il exige en plus |
| --- | --- | --- |
| Devoir 1 | `.\stDev1.bat` | une webcam |
| Devoir 2 | `.\stDev2.bat` | un micro, et le démon Ollama lancé |
| Projet | `python Projet\code\projet_turtle.py` | webcam, micro, Ollama |

---

## Journal du solutionnaire

Conformément à `workflow.md` (règle R1), voici ce qui s'est réellement passé pendant la
construction de ce laboratoire. Les échecs y figurent, parce qu'ils enseignent plus que
les commandes qui ont fini par marcher.

### 2026-09-18

| Étape | Résultat |
| --- | --- |
| Inventaire du dépôt | 19 PDF, 11 sources, 4 travaux |
| `wsl --install -d Ubuntu-24.04` | **ÉCHEC** `HCS/0x80070569`, code de sortie 0 |
| `wsl -d docker-desktop -- echo ok` | **ÉCHEC** identique, le blocage est machine, pas distro |
| Recherche ROS2 binaire Windows | Humble et Lyrical existent, mais admin requis |
| **Décision d'architecture** | Vrai code ROS2 + dorsale de substitution, basculement annoncé |
| `py -3.12 -m venv` | **ÉCHEC** `venvlauncher.exe` absent |
| `py -3.13 -m venv` | Succès, Python 3.13.3 |
| `pip install` avec versions devinées | **ÉCHEC** sur `pyttsx3==2.100` et `ollama==0.6.3`, code 0 |
| `pip install` sans épingle, puis figeage | Succès, 9 librairies, versions mesurées |
| `extract_libs.py`, première version | 13 faux modules inconnus, défaut d'expression régulière |
| `extract_libs.py`, corrigé | 30 documents, 0 inconnu, code de sortie 0 |
| Test caméra | 640x480, trame lue |
| `ollama pull llama3.2` | 2,0 Go |
| Modèles de vision | `hand_landmarker.task` 7,8 Mo, `yolo11n.pt` 5,6 Mo |
| Découverte MediaPipe | `mp.solutions` supprimé en 1.0.1, les 4 rendus 2025 sont morts |
| Migration vers l'API Tasks | `ihr_ros.hands`, `ihr_ros.overlay` |
| Tests du socle | 61 verts en 0,39 s |
| **plan01, `colcon build`, 1re tentative** | **ÉCHEC** `ModuleNotFoundError: ament_package`, CMake utilisait le Python du registre Windows |
| `colcon build`, Python conda forcé | **ÉCHEC** `Invalid character escape '\U'`, chemin Windows non converti en barres obliques |
| `colcon build`, chemin en barres obliques | **ÉCHEC** `em.BUFFERED_OPT` absent, `empy` 4.2.1 incompatible avec `rosidl` Humble |
| `pip install empy==3.3.4` (résolu via `pip index versions`) | Succès |
| `colcon build --merge-install`, 4e tentative | **Succès**, code 0, 2 paquets (`ihr_6mig841_interfaces`, `ihr_6mig841`) |
| Vérification par l'effet (R9) | 3 types importés depuis l'interpréteur conda, `ros2 interface show` les affiche |
| `pytest` sous conda, 1re tentative | **ÉCHEC** `PluginValidationError` sur `launch_testing` puis `launch_ros`, incompatibles avec `pytest` 9.1.1 |
| `pytest -p no:launch_testing -p no:launch_ros` sous conda | 5 échecs dans `test_backend_selection.py` : le test supposait ROS2 absent au lieu de le simuler (R5) |
| `test_backend_selection.py`, ROS2 simulé par monkeypatch | **Succès**, 200 verts sous `.venv` ET sous conda |
| `check_env.py`, rôle à trois valeurs | `venv` et `conda` tous deux `OK`, conseil vide dans les deux cas |

### 2026-09-19 - plan08 : dictée trouée et énoncés de laboratoire

Le solutionnaire porte désormais 16 marqueurs `# TROU debut ... / # TROU fin`, un par
fonction de décision des quatre travaux (plan04 à plan07 réécrivaient ces fonctions,
plan08 les troue en dernier, voir `docs/superpowers/plans/6mig841-ameliorations/plan08.md`).
`etudiant/` et `distribution/` sont **générés**, jamais maintenus à la main : deux copies
qui divergent est la seule raison pour laquelle ce générateur existe.

| Étape | Commande | Résultat attendu |
| --- | --- | --- |
| Générer la dictée, à blanc | `.\.venv\Scripts\python.exe dictee\code\generer_etudiant.py --dry-run` | rapport JSON, `total_trous: 16`, rien écrit |
| Générer la dictée | `.\.venv\Scripts\python.exe dictee\code\generer_etudiant.py` | `etudiant\{Lab1,Devoir1,Devoir2,Projet}\{code,test}` créés |
| Prouver que les trous mordent | `.\.venv\Scripts\python.exe -m pytest etudiant\Lab1\test etudiant\Devoir1\test etudiant\Devoir2\test etudiant\Projet\test -q` | rouge, 117 échecs, tous `NotImplementedError`, 16 fonctions distinctes en échec |
| Solutionnaire inchangé | `.\.venv\Scripts\python.exe -m pytest Lab1\test Devoir1\test Devoir2\test Projet\test evaluation\test dictee\test -q` | vert, inchangé (les marqueurs sont des commentaires) |
| Générer les énoncés | `.\.venv\Scripts\python.exe dictee\code\generer_enonces.py` | un `etudiant\<travail>\enonce.md` par travail, barème totalisant 100 |
| Balayage anti-divulgation | `.\.venv\Scripts\python.exe dictee\code\anti_divulgation.py` | code de sortie 0, aucune fuite sur les 16 trous |
| Zips de distribution | `.\.venv\Scripts\python.exe dictee\code\generer_zips.py` | `distribution\{lab1,dev1,dev2,projet}.zip`, version étudiante seule |

Défaut mesuré et corrigé pendant la construction du générateur : deux trous
(`arcs.echantillonner_arc`, `Regleur.regler`) étaient inatteignables depuis les tests,
masqués par un AUTRE trou exécuté plus tôt dans le même appel (`calculer_profil` avant
`echantillonner_arc` dans tous les tests de `test_arcs.py` ; `construire_schema` appelé
dès `Regleur.__init__`, avant que `.regler()` ne soit jamais atteint). Corrigé en
déplaçant le trou "profil de vitesse" vers `trajectory.evaluer` et en retirant le trou
`Regleur.regler` : 17 trous prévus, 16 posés, chacun atteignable. Détail complet dans
`.sdd/6mig841-ameliorations/plan08-report.md`.

### 2026-09-20 - régression des trois planificateurs, et alignement de la grille sur la référence

Signalement de l'enseignant : Theta\* traçait un chemin traversant l'obstacle. Rapport complet
dans `.sdd/6mig841-ameliorations/planificateurs-regression-report.md`.

| Étape | Résultat |
| --- | --- |
| Contrôle indépendant (avant correctif) sur la grille 64x64 | astar 0 segment traversant, thetastar **1 segment traversant**, dstarlite 0 |
| Cause racine | `World.ligne_de_vue_libre` (world.py) : règle « coin coupé, deux côtés occupés » du pas de Bresenham appliquée à tort à un pas diagonal qui n'est pas un vrai croisement de coin (segment de pente 4:7, pas seulement 45 degrés) |
| Test circulaire trouvé | `test_thetastar.py::test_chemin_theta_reste_libre_de_collision` jugeait `ligne_de_vue_libre` avec elle-même |
| **Alignement de grille (consigne de l'enseignant, reçue en cours de tâche)** | `planif_config.json` : 12x10 → **64x64**, obstacle colonnes 4-7/lignes 0-6 → **3x3 centré (31-33, 31-33)**, départ (0,0) → **(1,1)**, but (11,0) → **(62,62)**, alignés sur `C:\Users\m3otis\solution_robot_dimension\config.json` (lecture seule) |
| Correctif `ligne_de_vue_libre` | parcours de grille exact (DDA, fractions entières) ; corner-cut réservé au vrai croisement de coin |
| Test circulaire remplacé | par `segments_traversant_une_cellule_occupee` (`conftest.py`, fixture pytest), qui échantillonne le segment en coordonnées réelles sans jamais appeler `ligne_de_vue_libre`, appliqué aux trois planificateurs |
| Contrôle indépendant (après correctif) sur la grille 64x64 | astar 0, thetastar **0**, dstarlite 0 |
| `IndexError` de D\*-Lite | **non reproduit** malgré une mesure étendue (grille 12x10 ET 64x64, appels directs, 3000 configurations aléatoires avec mises à jour incrémentales) ; aucun code de D\*-Lite changé (R14) ; six tests de couverture ajoutés pour cette classe de défaut |
| Conséquence hors périmètre, signalée et non corrigée | `Devoir2/test/test_quadrillage_config.py` : 2 échecs attendus (24 → 130 segments turtlesim, la grille du Devoir 2 dérive de `planif_config.json`) |
| `pytest Lab1\test Devoir1\test Devoir2\test Projet\test evaluation\test dictee\test -q` | 438 passed, 2 failed (attendus, hors périmètre), 3 skipped |
| Dictée régénérée (`world.py` touché, marqueurs TROU inchangés) | 16 trous, 16 distincts, `World.ligne_de_vue_libre` toujours présent ; `etudiant/Lab1` rouge avec seulement `NotImplementedError` sur les 4 trous du Lab 1 |
| Tableau `compare.py` du 2026-09-18 (12x10) | **remplacé** par la mesure du 2026-09-20 (64x64), voir plus haut |
