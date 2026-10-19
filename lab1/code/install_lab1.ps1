<#
.SYNOPSIS
    Installe l'environnement Python du laboratoire 6MIG841.

.DESCRIPTION
    Cree le .venv a la racine du depot, y installe les librairies figees de
    requirements.txt, installe le socle ihr_ros en mode editable, puis lance la
    verification. Aucun droit administrateur n'est requis : tout reste dans le
    repertoire du depot et dans le profil de l'utilisateur.

    Le script est idempotent. Relance sur un environnement deja installe, il ne
    reinstalle que ce qui manque.

.PARAMETER PythonVersion
    Version passee au lanceur `py`. Defaut 3.13, mesuree fonctionnelle le
    2026-09-18. Une version 3.12 cassee sur cette machine (venvlauncher.exe absent)
    est la raison pour laquelle ce parametre existe.

.PARAMETER Recreate
    Supprime le .venv existant avant de le recreer.

.PARAMETER DryRun
    Affiche ce qui serait fait, sans rien ecrire.

.PARAMETER Cuda
    Installe en plus Lab1/code/requirements-cuda.txt (nvidia-cublas-cu12,
    nvidia-cudnn-cu12, nvidia-cuda-nvrtc-cu12). PAS installe par defaut : poids mesure
    sur disque le 2026-09-19, 2,0 Go, plus que toutes les autres librairies du Lab 1
    reunies. Necessaire uniquement si Lab1/code/ihr_config.json (section "devoir2",
    cle "speech_device") vaut "cuda" ET que la machine a un GPU NVIDIA ; sans ce
    commutateur, une machine sans GPU n'a rien a en faire. `check_env.py` rapporte
    l'ecart si "cuda" est configure sans ces paquets.

.EXAMPLE
    .\Lab1\code\install_lab1.ps1
    .\Lab1\code\install_lab1.ps1 -PythonVersion 3.11 -Recreate
    .\Lab1\code\install_lab1.ps1 -DryRun
    .\Lab1\code\install_lab1.ps1 -Cuda
#>
[CmdletBinding()]
param(
    [string]$PythonVersion = "3.13",
    [switch]$Recreate,
    [switch]$DryRun,
    [switch]$Cuda
)

$ErrorActionPreference = "Stop"

$CodeDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $CodeDir)
$VenvDir  = Join-Path $RepoRoot ".venv"
$VenvPy   = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $CodeDir "requirements.txt"
$RequirementsCuda = Join-Path $CodeDir "requirements-cuda.txt"
$ConfigPath   = Join-Path $CodeDir "ihr_config.json"

# Nom de l'environnement conda ROS2, lu dans la configuration comme le fait
# Lab1/code/ros2_env.ps1 (R7 : jamais ecrit en dur ici). Reste $null si la
# configuration est absente ou muette : -Cuda se rabattra alors sur .venv seul,
# en le DISANT (R8).
$CondaEnvName = $null
if (Test-Path $ConfigPath) {
    try {
        $cfgInstall = Get-Content -Raw -Path $ConfigPath -Encoding UTF8 | ConvertFrom-Json
        if ($cfgInstall.ros2 -and $cfgInstall.ros2.conda_env_name) {
            $CondaEnvName = [string]$cfgInstall.ros2.conda_env_name
        }
    } catch {
        $CondaEnvName = $null
    }
}

function Get-CondaPython {
    # Meme derivation que ros2_env.ps1, depuis USERPROFILE (R1).
    if (-not $CondaEnvName) { return $null }
    $chemin = Join-Path $env:USERPROFILE 'scoop\apps\miniforge3\current\envs'
    $chemin = Join-Path $chemin $CondaEnvName
    $chemin = Join-Path $chemin 'python.exe'
    if (Test-Path $chemin) { return $chemin }
    return $null
}

function Write-Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Write-Info($text) { Write-Host "   $text" }
function Write-Warn($text) { Write-Host "   $text" -ForegroundColor Yellow }
function Write-Bad ($text) { Write-Host "   $text" -ForegroundColor Red }

Write-Host "6MIG841 - installation de l'environnement" -ForegroundColor Green
Write-Info "Depot   : $RepoRoot"
Write-Info "Venv    : $VenvDir"
Write-Info "Python  : py -$PythonVersion"
if ($DryRun) { Write-Warn "MODE DRY-RUN : rien ne sera ecrit." }

# --- 1. Le lanceur Python existe-t-il dans la version demandee -----------------
Write-Step "1/6  Verification de l'interpreteur"
$probe = & py "-$PythonVersion" --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Bad "py -$PythonVersion indisponible. Versions installees :"
    & py --list
    Write-Bad "Relancer avec -PythonVersion <une de ces versions>."
    exit 1
}
Write-Info "Trouve : $probe"

if (-not (Test-Path $Requirements)) {
    Write-Bad "requirements.txt introuvable : $Requirements"
    exit 1
}

# --- 2. Creation du .venv ------------------------------------------------------
Write-Step "2/6  Environnement virtuel"
if ($Recreate -and (Test-Path $VenvDir)) {
    if ($DryRun) { Write-Warn "supprimerait $VenvDir" }
    else { Write-Info "suppression de l'ancien .venv"; Remove-Item -Recurse -Force $VenvDir }
}

if (Test-Path $VenvPy) {
    Write-Info "deja present, reutilise : $VenvPy"
} elseif ($DryRun) {
    Write-Warn "creerait le venv : py -$PythonVersion -m venv `"$VenvDir`""
} else {
    & py "-$PythonVersion" -m venv $VenvDir
    if (-not (Test-Path $VenvPy)) {
        Write-Bad "Creation du venv echouee : $VenvPy absent."
        Write-Bad "Cause deja rencontree le 2026-09-18 : une installation Python 3.12"
        Write-Bad "amputee de venvlauncher.exe. Essayer -PythonVersion 3.13 ou 3.11."
        exit 1
    }
    Write-Info "cree : $VenvPy"
}

if ($DryRun) {
    Write-Step "3-6/6  (dry-run) installerait pip, requirements.txt, ihr_ros, puis verifierait"
    if ($Cuda) {
        $CondaPyDry = Get-CondaPython
        if ($CondaPyDry) {
            Write-Warn "-Cuda : poserait requirements-cuda.txt dans .venv ET dans conda '$CondaEnvName'."
        } else {
            Write-Warn "-Cuda : poserait requirements-cuda.txt dans .venv seul (conda introuvable)."
        }
    }
    Write-Host "`nDry-run termine, rien n'a ete ecrit." -ForegroundColor Green
    exit 0
}

# --- 3. pip a jour -------------------------------------------------------------
Write-Step "3/6  Mise a jour de pip"
& $VenvPy -m pip install --upgrade pip --quiet
Write-Info (& $VenvPy -m pip --version)

# --- 4. Librairies -------------------------------------------------------------
# pip retourne 0 meme quand une epingle n'existe pas (mesure le 2026-09-18 :
# `pyttsx3==2.100` et `ollama==0.6.3` ont echoue avec un code de retour nul). Le
# code de retour ne prouve donc rien : la verification porte sur l'EFFET, plus bas.
Write-Step "4/6  Installation des librairies"
& $VenvPy -m pip install -r $Requirements
Write-Info "pip a rendu $LASTEXITCODE (non concluant, verifie a l'etape 6)"

# --- 5. Socle ihr_ros ----------------------------------------------------------
Write-Step "5/6  Installation du socle ihr_ros (editable)"
& $VenvPy -m pip install -e $CodeDir --quiet
Write-Info "ihr_ros installe depuis $CodeDir"

# --- 5b. Paquets CUDA optionnels ------------------------------------------------
# Corrige le 2026-09-20. DEUX defauts superposes, tous deux mesures ce jour-la en
# salle, sur la panne `RuntimeError: Library cublas64_12.dll is not found or
# cannot be loaded` du noeud voice_input :
#
#   1. -Cuda etait DECLARE en parametre et documente dans l'aide, mais n'etait
#      utilise NULLE PART dans le corps de ce script, et requirements-cuda.txt n'y
#      etait nomme que dans un commentaire. `install_lab1.ps1 -Cuda` n'installait
#      donc aucun paquet CUDA et rendait 0 (R14 : un drapeau documente qui n'existe
#      pas dans le comportement ; R8 : jamais de succes silencieux).
#
#   2. Ce script n'installe que dans .venv. Or le noeud vocal du Devoir 2 tourne
#      dans l'environnement conda ROS2 (.claude/rules/ros2.md), PAS dans .venv.
#      Meme repare, le drapeau aurait pose les 2 Go de CUDA dans l'environnement
#      qui n'en a pas besoin et jamais dans celui qui en a besoin.
#
# Les DEUX interpreteurs sont donc servis ici : .venv pour les essais hors ligne,
# conda pour l'execution reelle des noeuds.
if ($Cuda) {
    Write-Step "5b/6  Paquets CUDA (option -Cuda)"
    if (-not (Test-Path $RequirementsCuda)) {
        Write-Bad "requirements-cuda.txt introuvable : $RequirementsCuda"
        exit 1
    }

    $CiblesCuda = @(@{ Nom = ".venv"; Python = $VenvPy })
    $CondaPy = Get-CondaPython
    if ($CondaPy) {
        $CiblesCuda += @{ Nom = "conda '$CondaEnvName'"; Python = $CondaPy }
    } else {
        Write-Warn "environnement conda introuvable : CUDA ne sera pose que dans .venv."
        Write-Warn "Le noeud vocal du Devoir 2 tourne dans conda (Lab1/tutoriel.md etape 6),"
        Write-Warn "donc la voix restera en echec tant que conda n'aura pas ces paquets."
    }

    foreach ($cible in $CiblesCuda) {
        Write-Info "installation dans $($cible.Nom)"
        & $cible.Python -m pip install -r $RequirementsCuda

        # R9 : pip rend 0 meme quand rien n'a ete pose (mesure le 2026-09-18 sur
        # d'autres epingles de ce depot). La preuve est donc la DLL sur le disque,
        # pas le code de retour. Verifiee ici SANS invoquer python -c : PowerShell
        # mutile les guillemets d'un argument passe a un executable natif (mesure
        # le 2026-09-20), donc le chemin est derive de l'interpreteur lui-meme.
        $racineInterp = Split-Path -Parent $cible.Python
        $relatif = 'Lib\site-packages\nvidia\cublas\bin\cublas64_12.dll'
        $candidats = @(
            (Join-Path (Split-Path -Parent $racineInterp) $relatif),
            (Join-Path $racineInterp $relatif)
        )
        $dll = $candidats | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($dll -and (Test-Path $dll)) {
            Write-Info "verifie : $dll"
        } else {
            Write-Bad "cublas64_12.dll absente de $($cible.Nom) apres installation."
            Write-Bad "Sans elle, devoir2.speech_device vaut cuda et la voix plante au PREMIER calcul reel."
            exit 1
        }
    }
}

# --- 6. Verification par l'effet ----------------------------------------------
Write-Step "6/6  Verification"
& $VenvPy (Join-Path $CodeDir "check_env.py")
$checkCode = $LASTEXITCODE

Write-Host ""
if ($checkCode -eq 0) {
    Write-Host "Installation terminee. Environnement pret." -ForegroundColor Green
    Write-Host "Activer :  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
} else {
    Write-Bad "Installation incomplete, voir le rapport ci-dessus."
}
exit $checkCode
