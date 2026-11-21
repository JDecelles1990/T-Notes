<#
.SYNOPSIS
    Clean reproducible --onedir Windows release builder for T-Notes.
.DESCRIPTION
    Synchronizes synthetic M365 metadata, cleans previous build/dist artifacts,
    verifies PyInstaller + Qt image format plugins, builds dist\T-Notes\T-Notes.exe
    from T-Notes.spec, and validates every required runtime asset and PowerShell script.
#>
[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [switch]$SkipClean,
    [switch]$SkipTests,
    [switch]$InstallPyInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ProjectRoot
try {
    # 1. Resolve Python interpreter
    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        $venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $venvPy -PathType Leaf) {
            & $venvPy -c "import PySide6" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonExe = $venvPy
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $cmd) {
            throw "Python interpreter not found on PATH. Pass -PythonExe <path>."
        }
        $PythonExe = $cmd.Source
    }
    Write-Host "[1/6] Using Python: $PythonExe" -ForegroundColor Cyan

    # 2. Verify required packages + PyInstaller
    & $PythonExe -c "import PySide6, PIL, jsonschema, referencing"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing required Python dependencies. Run: `"$PythonExe`" -m pip install -r requirements.txt"
    }

    & $PythonExe -m PyInstaller --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if ($InstallPyInstaller) {
            Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
            & $PythonExe -m pip install pyinstaller
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install PyInstaller."
            }
        } else {
            throw "PyInstaller is not installed for '$PythonExe'. Install it via `"$PythonExe`" -m pip install pyinstaller, or re-run build.ps1 -InstallPyInstaller."
        }
    }

    # 3. Clean stale build / dist directories
    if (-not $SkipClean) {
        Write-Host "[2/6] Cleaning build/ and dist/ directories..." -ForegroundColor Cyan
        foreach ($dirName in @("build", "dist")) {
            $dirPath = Join-Path $ProjectRoot $dirName
            if (Test-Path -LiteralPath $dirPath) {
                Remove-Item -LiteralPath $dirPath -Recurse -Force
            }
        }
    } else {
        Write-Host "[2/6] Skipping clean (-SkipClean)" -ForegroundColor DarkGray
    }

    # 4. Run optional packaging & path sanity tests before compiling
    if (-not $SkipTests) {
        Write-Host "[3/6] Running packaging & path tests..." -ForegroundColor Cyan
        & $PythonExe -m pytest -q tests\test_packaging_and_paths.py
        if ($LASTEXITCODE -ne 0) {
            throw "Pre-build pytest check failed."
        }
    } else {
        Write-Host "[3/6] Skipping pre-build tests (-SkipTests)" -ForegroundColor DarkGray
    }

    # 5. Build standalone --onedir executable via PyInstaller
    Write-Host "[4/6] Running PyInstaller --clean --noconfirm T-Notes.spec..." -ForegroundColor Cyan
    & $PythonExe -m PyInstaller --clean --noconfirm (Join-Path $ProjectRoot "T-Notes.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    # 6. Post-build bundle verification
    Write-Host "[5/6] Verifying bundled runtime artifacts..." -ForegroundColor Cyan
    $DistRoot = Join-Path $ProjectRoot "dist\T-Notes"
    $InternalRoot = Join-Path $DistRoot "_internal"
    $ExePath = Join-Path $DistRoot "T-Notes.exe"

    $requiredFiles = @(
        $ExePath,
        (Join-Path $InternalRoot "src\database\schema.sql"),
        (Join-Path $InternalRoot "assets\styles\dark_theme.qss"),
        (Join-Path $InternalRoot "assets\icons\app_icon.png"),
        (Join-Path $InternalRoot "assets\m365\categories.json"),
        (Join-Path $InternalRoot "assets\m365\contract-review-pins.json"),
        (Join-Path $InternalRoot "assets\m365\synthetic-catalog.json"),
        (Join-Path $InternalRoot "assets\m365_synthetic\catalog.json"),
        (Join-Path $InternalRoot "docs\contracts\m365\schemas\script-manifest.schema.json"),
        (Join-Path $InternalRoot "prototypes\m365_official_engine\protocol.ps1"),
        (Join-Path $InternalRoot "scripts\m365\_host\M365WorkerHost.ps1"),
        (Join-Path $InternalRoot "scripts\m365\_host\M365SyntheticRunner.ps1"),
        (Join-Path $InternalRoot "scripts\m365\_host\M365PreflightProbe.ps1"),
        (Join-Path $InternalRoot "PySide6\plugins\imageformats\qjpeg.dll")
    )

    foreach ($req in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $req -PathType Leaf)) {
            throw "Missing expected bundled file: $req"
        }
    }

    $ps1Count = @(Get-ChildItem -LiteralPath (Join-Path $InternalRoot "scripts\m365") -Filter "*.ps1" -Recurse).Count
    if ($ps1Count -lt 28) {
        throw "Expected at least 28 bundled PowerShell scripts under _internal\scripts\m365, found $ps1Count."
    }

    $imgPlugins = @(Get-ChildItem -LiteralPath (Join-Path $InternalRoot "PySide6\plugins\imageformats") -Filter "*.dll").Name -join ", "
    $totalBytes = (Get-ChildItem -LiteralPath $DistRoot -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $totalMb = [math]::Round($totalBytes / 1MB, 1)

    Write-Host "[6/6] Build verified successfully!" -ForegroundColor Green
    Write-Host "  Executable      : $ExePath"
    Write-Host "  Bundle Size     : $totalMb MB (--onedir)"
    Write-Host "  Bundled .ps1    : $ps1Count scripts"
    Write-Host "  Image Plugins   : $imgPlugins"
}
finally {
    Pop-Location
}
finally {
    if ($tempWorkDir -and (Test-Path -Path $tempWorkDir)) {
        Remove-Item -Path $tempWorkDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Set-Location -Path $origLocation.Path
    if ($Host.Name -eq "ConsoleHost" -and -not $env:CI) {
        Read-Host "`nPress Enter to close"
    }
}