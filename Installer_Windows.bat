@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==============================================
echo  TrailMaster Pro - construction de l'application
echo ==============================================
echo.
echo Ce script doit etre execute directement sur le PC Windows ou tu
echo veux installer l'appli (il ne peut pas etre fabrique a distance :
echo une vraie appli Windows doit etre construite sur un PC Windows).
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=python
) else (
    where py >nul 2>nul
    if !errorlevel!==0 (
        set PYTHON_CMD=py -3
    ) else (
        echo ATTENTION : Python n'est pas installe sur ce PC.
        echo   Installe-le d'abord depuis https://www.python.org/downloads/windows/
        echo   ^(coche bien la case "Add python.exe to PATH" pendant l'installation^),
        echo   puis relance ce fichier.
        pause
        exit /b 1
    )
)

echo 1/6 - Preparation d'un environnement Python dedie ^(.venv^)...
if not exist ".venv" (
    %PYTHON_CMD% -m venv .venv
)
call .venv\Scripts\activate.bat

echo 2/6 - Installation des dependances ^(peut prendre quelques minutes^)...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

echo 3/6 - Construction de TrailMaster Pro.exe...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller ^
    --windowed ^
    --name "TrailMaster Pro" ^
    --add-data "interface/assets;interface/assets" ^
    --hidden-import "PySide6.QtWebEngineWidgets" ^
    --hidden-import "PySide6.QtWebEngineCore" ^
    --hidden-import "PySide6.QtWebChannel" ^
    --collect-all "PySide6" ^
    --noconfirm ^
    --log-level WARN ^
    main.py

call .venv\Scripts\deactivate.bat

echo 4/6 - Installation dans %%LOCALAPPDATA%%\Programs\TrailMaster Pro...
set "DOSSIER_INSTALL=%LOCALAPPDATA%\Programs\TrailMaster Pro"
if exist "%DOSSIER_INSTALL%" rmdir /s /q "%DOSSIER_INSTALL%"
mkdir "%DOSSIER_INSTALL%"
xcopy "dist\TrailMaster Pro\*" "%DOSSIER_INSTALL%\" /e /i /q /y >nul

echo 5/6 - Reprise de tes donnees existantes...
set "DOSSIER_DONNEES=%APPDATA%\TrailMaster Pro"
if not exist "%DOSSIER_DONNEES%" mkdir "%DOSSIER_DONNEES%"
if exist "data\trailmaster.db" if not exist "%DOSSIER_DONNEES%\trailmaster.db" (
    copy "data\trailmaster.db" "%DOSSIER_DONNEES%\trailmaster.db" >nul
    echo     Base de donnees reprise.
)
if exist "data\photos" if not exist "%DOSSIER_DONNEES%\photos" (
    xcopy "data\photos" "%DOSSIER_DONNEES%\photos\" /e /i /q /y >nul
    echo     Photos des athletes reprises.
)

echo 6/6 - Creation des raccourcis ^(Bureau + menu Demarrer^)...
powershell -NoProfile -Command ^
    "$s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\TrailMaster Pro.lnk'); $s.TargetPath='%DOSSIER_INSTALL%\TrailMaster Pro.exe'; $s.WorkingDirectory='%DOSSIER_INSTALL%'; $s.Save()"
powershell -NoProfile -Command ^
    "$s=(New-Object -COM WScript.Shell).CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\TrailMaster Pro.lnk'); $s.TargetPath='%DOSSIER_INSTALL%\TrailMaster Pro.exe'; $s.WorkingDirectory='%DOSSIER_INSTALL%'; $s.Save()"

echo.
echo ==============================================
echo  Installation terminee !
echo ==============================================
echo.
echo TrailMaster Pro est maintenant installe. Tu peux le lancer :
echo   - depuis le raccourci sur le Bureau
echo   - ou depuis le menu Demarrer ^(tape "TrailMaster")
echo.
echo ATTENTION : au tout premier lancement, Windows SmartScreen peut
echo afficher "Windows a protege votre ordinateur" ^(l'appli n'est pas
echo signee par un editeur reconnu, normal pour une appli maison^) :
echo clique sur "Informations complementaires" puis "Executer quand
echo meme". Les fois suivantes, un double-clic normal suffira.
echo.
echo Tes donnees existantes ont ete reprises automatiquement dans :
echo   %%APPDATA%%\TrailMaster Pro\
echo.
echo ^(Relancer ce script plus tard, pour une future mise a jour, ne
echo  touchera plus a tes donnees : il ne copie que si rien n'existe
echo  encore a cet emplacement.^)
echo.
pause
