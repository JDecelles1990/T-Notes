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
    [switch]$SkipZip,
    [switch]$InstallPyInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ProjectRoot
try {
    # 1. Resolve Python interpreter (explicitly require project .venv unless -PythonExe is supplied)
    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        $venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $venvPy -PathType Leaf)) {
            throw "Project virtual environment not found at '$venvPy'. Create it and install dependencies first, or pass -PythonExe <path>."
        }
        $PythonExe = $venvPy
    }
    elseif (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Specified Python interpreter not found: '$PythonExe'"
    }
    Write-Host "[1/7] Using Python: $PythonExe" -ForegroundColor Cyan

    # 2. Verify required packages + PyInstaller
    & $PythonExe -c "import PySide6, PIL, jsonschema, referencing"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing required Python dependencies in '$PythonExe'. Run: `"$PythonExe`" -m pip install -r requirements.txt"
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

    $appVersion = (& $PythonExe -c "from src.core.constants import APP_VERSION; print(APP_VERSION)").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($appVersion)) {
        throw "Unable to read APP_VERSION from src.core.constants."
    }

    # 3. Clean stale build / dist directories
    if (-not $SkipClean) {
        Write-Host "[2/7] Cleaning build/ and dist/ directories..." -ForegroundColor Cyan
        foreach ($dirName in @("build", "dist")) {
            $dirPath = Join-Path $ProjectRoot $dirName
            if (Test-Path -LiteralPath $dirPath) {
                Remove-Item -LiteralPath $dirPath -Recurse -Force
            }
        }
    } else {
        Write-Host "[2/7] Skipping clean (-SkipClean)" -ForegroundColor DarkGray
    }

    # 4. Run packaging & path sanity tests before compiling
    if (-not $SkipTests) {
        Write-Host "[3/7] Running packaging & path tests..." -ForegroundColor Cyan
        & $PythonExe -m pytest -q tests\test_packaging_and_paths.py
        if ($LASTEXITCODE -ne 0) {
            throw "Pre-build pytest check failed."
        }
    } else {
        Write-Host "[3/7] Skipping pre-build tests (-SkipTests)" -ForegroundColor DarkGray
    }

    # 5. Build standalone --onedir executable via PyInstaller
    Write-Host "[4/7] Running PyInstaller --clean --noconfirm T-Notes.spec..." -ForegroundColor Cyan
    & $PythonExe -m PyInstaller --clean --noconfirm (Join-Path $ProjectRoot "T-Notes.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    # 6. Post-build bundle verification
    Write-Host "[5/7] Verifying bundled runtime artifacts..." -ForegroundColor Cyan
    $DistRoot = Join-Path $ProjectRoot "dist\T-Notes"
    $InternalRoot = Join-Path $DistRoot "_internal"
    $ExePath = Join-Path $DistRoot "T-Notes.exe"

    $requiredFiles = @(
        $ExePath,
        (Join-Path $InternalRoot "src\database\schema.sql"),
        (Join-Path $InternalRoot "src\database\taxonomy_seed.json"),
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
        (Join-Path $InternalRoot "PySide6\plugins\imageformats\qjpeg.dll"),
        (Join-Path $InternalRoot "PySide6\plugins\platforms\qwindows.dll")
    )

    foreach ($req in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $req -PathType Leaf)) {
            throw "Missing expected bundled file: $req"
        }
    }

    # Verify unused heavy Qt binaries were excluded
    $forbiddenBinaries = @("Qt6WebEngineCore.dll", "Qt6Pdf.dll", "qpdf.dll", "Qt6Multimedia.dll")
    foreach ($forbidden in $forbiddenBinaries) {
        $leaked = Get-ChildItem -LiteralPath $DistRoot -Filter $forbidden -Recurse -ErrorAction SilentlyContinue
        if ($leaked) {
            throw "Unexpected bloated Qt binary found in dist: $($leaked[0].FullName)"
        }
    }

    $ps1Count = @(Get-ChildItem -LiteralPath (Join-Path $InternalRoot "scripts\m365") -Filter "*.ps1" -Recurse).Count
    if ($ps1Count -lt 28) {
        throw "Expected at least 28 bundled PowerShell scripts under _internal\scripts\m365, found $ps1Count."
    }

    $imgPlugins = @(Get-ChildItem -LiteralPath (Join-Path $InternalRoot "PySide6\plugins\imageformats") -Filter "*.dll").Name -join ", "
    $totalBytes = (Get-ChildItem -LiteralPath $DistRoot -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $totalMb = [math]::Round($totalBytes / 1MB, 1)

    # 7. Package portable ZIP archive
    $zipPath = Join-Path $ProjectRoot ("dist\T-Notes-v{0}-win64.zip" -f $appVersion)
    $zipInfo = "Skipped (-SkipZip)"
    if (-not $SkipZip) {
        Write-Host "[6/7] Creating portable release archive..." -ForegroundColor Cyan
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        Compress-Archive -Path $DistRoot -DestinationPath $zipPath -CompressionLevel Optimal
        $zipBytes = (Get-Item -LiteralPath $zipPath).Length
        $zipMb = [math]::Round($zipBytes / 1MB, 1)
        $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
        $zipInfo = "$zipPath ($zipMb MB, SHA256: $zipHash)"
    }
    else {
        Write-Host "[6/7] Skipping ZIP creation (-SkipZip)" -ForegroundColor DarkGray
    }

    Write-Host "[7/7] Build verified successfully!" -ForegroundColor Green
    Write-Host "  Version         : v$appVersion"
    Write-Host "  Executable      : $ExePath"
    Write-Host "  Bundle Size     : $totalMb MB (--onedir)"
    Write-Host "  Portable ZIP    : $zipInfo"
    Write-Host "  Bundled .ps1    : $ps1Count scripts"
    Write-Host "  Image Plugins   : $imgPlugins"
}
finally {
    Pop-Location
}