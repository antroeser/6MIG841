<#
.SYNOPSIS
    Pose l'environnement ROS2 (conda, canal robostack-humble) pour ce depot, et rend
    le chemin de l'interpreteur conda sur la sortie standard.

.DESCRIPTION
    Ce script ne source PAS les scripts d'activation conda ni les `local_setup.ps1`
    generes par colcon : il pose lui-meme les variables necessaires, pour eviter
    `conda activate` (plante avec les greffons PowerShell installes ici) et
    `conda run` (plante des que la commande depasse quelques lignes, mesure le
    2026-09-18).

    DEUX VARIABLES SONT OBLIGATOIRES, pas facultatives, mesure le 2026-09-18 :

      - ROS_LOCALHOST_ONLY=1 : sans elle, deux choses arrivent. Le pare-feu Windows
        reclame les droits administrateur pour turtlesim_node.exe et python.exe,
        parce que Fast DDS emet en multicast sur les interfaces reseau. Et surtout,
        DANS UNE SALLE DE CLASSE, DDS decouvre tout le monde sur le sous-reseau : la
        commande d'un etudiant pilote la tortue d'un autre, le coupable etant a
        trois rangs de la.

      - ROS_DOMAIN_ID : cloisonne le graphe ROS2 d'un poste a l'autre. Sans un
        domaine distinct, deux postes sur le meme reseau partagent le meme graphe
        ROS2 meme avec ROS_LOCALHOST_ONLY actif l'un envers l'autre via le reseau
        physique partage.

    Les autres variables (ROS_DISTRO, ROS_VERSION, RMW_IMPLEMENTATION) reproduisent
    ce que le paquet conda `ros_environment` de robostack-humble pose lui-meme :
    verifie le 2026-09-18 dans
    envs\ihr\Library\share\ros_environment\environment\*.dsv (ROS_DISTRO=humble,
    ROS_VERSION=2) et par la presence de envs\ihr\Library\bin\rmw_fastrtps_cpp.dll
    (implementation par defaut de ROS2 Humble).

    AMENT_PREFIX_PATH est pose sur `envs\<env>\Library`. Si l'espace de travail
    `ros2_ws\install` existe (colcon build --merge-install deja passe), son chemin
    est prepend a AMENT_PREFIX_PATH ET son dossier Python (`Lib\site-packages`) est
    prepend a PYTHONPATH, sinon les types generes (Step, Interpret, ExecutePlan) ne
    s'importent pas meme si `colcon build` a rendu 0 (R9 : verifier l'effet).

.PARAMETER RosDomainId
    Domaine ROS2. Defaut lu dans ihr_config.json, section "ros2", cle
    "ros_domain_id_default" (R7 : aucune valeur numerique en dur ici).

.PARAMETER CondaEnvName
    Nom de l'environnement conda ROS2. Defaut lu dans ihr_config.json, section
    "ros2", cle "conda_env_name".

.EXAMPLE
    $py = & .\Lab1\code\ros2_env.ps1
    & $py -c "import rclpy; print('ok')"

.EXAMPLE
    $py = & .\Lab1\code\ros2_env.ps1 -RosDomainId 12
#>
[CmdletBinding()]
param(
    [System.Nullable[int]]$RosDomainId = $null,
    [string]$CondaEnvName = $null
)

$CodeDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent (Split-Path -Parent $CodeDir)
$ConfigPath = Join-Path $CodeDir "ihr_config.json"

function Write-Bad($text) { Write-Host "ERREUR ros2_env.ps1 : $text" -ForegroundColor Red }

# --- 1. Configuration : domaine ROS2 par defaut et nom de l'environnement (R7) --
if (-not (Test-Path $ConfigPath)) {
    Write-Bad "configuration introuvable : $ConfigPath."
    exit 2
}
try {
    $config = Get-Content -Raw -Path $ConfigPath -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Bad "configuration illisible ($ConfigPath) : $($_.Exception.Message)"
    exit 2
}
if (-not $config.ros2) {
    Write-Bad "section 'ros2' absente de $ConfigPath."
    exit 2
}
if ($null -eq $RosDomainId) {
    $RosDomainId = [int]$config.ros2.ros_domain_id_default
}
if (-not $CondaEnvName) {
    $CondaEnvName = [string]$config.ros2.conda_env_name
}

# --- 2. Chemin de l'environnement conda, derive de USERPROFILE (R1, jamais un --
#        nom de compte ecrit en dur) ---------------------------------------------
$CondaRoot = Join-Path $env:USERPROFILE "scoop\apps\miniforge3\current"
$CondaEnv  = Join-Path $CondaRoot "envs\$CondaEnvName"
$CondaPy   = Join-Path $CondaEnv "python.exe"

if (-not (Test-Path $CondaPy)) {
    Write-Bad "environnement conda ROS2 introuvable : $CondaPy attendu."
    Write-Bad "Installer avec : scoop install miniforge3, puis"
    Write-Bad "  conda create -n $CondaEnvName -c conda-forge -c robostack-humble ``"
    Write-Bad "    python=3.12 ros-humble-ros-base ros-humble-turtlesim"
    Write-Bad "Voir Lab1/tutoriel.md, etape 6."
    exit 2
}

# --- 3. Variables obligatoires, mesurees le 2026-09-18 --------------------------
$env:ROS_LOCALHOST_ONLY = [string][int]$config.ros2.ros_localhost_only
$env:ROS_DOMAIN_ID      = "$RosDomainId"

# --- 4. Variables ROS2 de base, reproduisant le paquet conda ros_environment ----
$env:ROS_DISTRO        = [string]$config.ros2.ros_distro
$env:ROS_VERSION       = [string][int]$config.ros2.ros_version
$env:RMW_IMPLEMENTATION = [string]$config.ros2.rmw_implementation
$env:PYTHONHOME        = ""

# --- 5. AMENT_PREFIX_PATH, espace de travail construit prepend s'il existe ------
$LibraryDir = Join-Path $CondaEnv "Library"
$AmentPaths = @($LibraryDir)

$WorkspaceInstall = Join-Path $RepoRoot "ros2_ws\install"
if (Test-Path $WorkspaceInstall) {
    $AmentPaths = @($WorkspaceInstall) + $AmentPaths

    $SitePackages = Join-Path $WorkspaceInstall "Lib\site-packages"
    if (Test-Path $SitePackages) {
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = "$SitePackages;$env:PYTHONPATH"
        } else {
            $env:PYTHONPATH = "$SitePackages"
        }
    }
}
$env:AMENT_PREFIX_PATH = ($AmentPaths -join ";")

# --- 6. PATH : Scripts (ros2, colcon), Library\bin (DLL ROS2), et l'espace de --
#        travail construit en tete s'il existe ------------------------------------
$PathAdditions = @(
    (Join-Path $CondaEnv "Scripts"),
    (Join-Path $LibraryDir "bin"),
    $CondaEnv
)
if (Test-Path $WorkspaceInstall) {
    $PathAdditions = @(
        (Join-Path $WorkspaceInstall "Library\bin"),
        (Join-Path $WorkspaceInstall "bin")
    ) + $PathAdditions
}
$PathAdditions = $PathAdditions | Where-Object { Test-Path $_ }
$env:PATH = ($PathAdditions -join ";") + ";" + $env:PATH

# --- 7. Sortie : le chemin de l'interpreteur, pour qu'un lanceur le capture -----
Write-Output $CondaPy
