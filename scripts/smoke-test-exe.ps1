[CmdletBinding()]
param(
    [string]$RepoPath = 'C:\Dev\T-Notes',
    [string]$LiveDbPath = '',
    [string]$DbEnvVar = 'TNOTES_DB_PATH',
    [switch]$SkipBuild,
    [switch]$Cleanup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$originalLocation = Get-Location
$smokeRoot = Join-Path -Path $env:TEMP -ChildPath ("TNotes_SmokeTest_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$liveHashBefore = $null

function Invoke-CheckedExe {
    param(
        [Parameter(Mandatory)][string]$ExePath,
        [Parameter(Mandatory)][string]$TargetDb,
        [Parameter(Mandatory)][string]$Label
    )

    Write-Host "`n=== Launching T-Notes.exe ($Label) ===" -ForegroundColor Cyan
    Write-Host "Target DB : $TargetDb" -ForegroundColor DarkGray
    Write-Host "Close the T-Notes window when finished verifying to continue..." -ForegroundColor Yellow

    Set-Item -Path "Env:$DbEnvVar" -Value $TargetDb -ErrorAction Stop
    try {
        $proc = Start-Process -FilePath $ExePath -PassThru -Wait -ErrorAction Stop
        if ($proc.ExitCode -ne 0) {
            throw "T-Notes.exe exited with non-zero code $($proc.ExitCode) during '$Label'."
        }
    }
    finally {
        Remove-Item -Path "Env:$DbEnvVar" -ErrorAction SilentlyContinue
    }
}

try {
    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw "Repository path not found: $RepoPath"
    }

    # Block running while a live T-Notes instance might hold SQLite locks
    $running = Get-Process -Name 'T-Notes' -ErrorAction SilentlyContinue
    if ($running) {
        throw "Close any running T-Notes.exe instance before running the smoke test."
    }

    Set-Location -LiteralPath $RepoPath -ErrorAction Stop
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to determine current Git branch."
    }
    Write-Host "Active branch: $branch" -ForegroundColor Green

    # Resolve venv Python if available, otherwise fall back to PATH python
    $venvPython = Join-Path $RepoPath '.venv\Scripts\python.exe'
    $pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }

    # 1. Run full pytest suite first
    Write-Host "`n[1/5] Running pytest suite..." -ForegroundColor Cyan
    & $pythonExe -m pytest -v
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed (exit code $LASTEXITCODE). Aborting smoke test."
    }

    # 2. Build standalone executable
    if (-not $SkipBuild) {
        $buildScript = Join-Path $RepoPath 'build.ps1'
        if (-not (Test-Path -LiteralPath $buildScript)) {
            throw "build.ps1 not found at $buildScript"
        }
        Write-Host "`n[2/5] Building dist\T-Notes\T-Notes.exe..." -ForegroundColor Cyan
        & $buildScript
        if ($LASTEXITCODE -ne 0) {
            throw "build.ps1 failed (exit code $LASTEXITCODE)."
        }
    }
    else {
        Write-Host "`n[2/5] Skipping build (-SkipBuild)." -ForegroundColor DarkGray
    }

    $exePath = Join-Path $RepoPath 'dist\T-Notes\T-Notes.exe'
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Compiled executable missing: $exePath"
    }

    # Verify taxonomy_seed.json was bundled into the dist directory
    $distRoot = Split-Path -Parent $exePath
    $bundledSeed = Get-ChildItem -Path $distRoot -Filter 'taxonomy_seed.json' -Recurse -ErrorAction Stop
    if (-not $bundledSeed) {
        throw "taxonomy_seed.json was NOT found inside $distRoot. Check PyInstaller --add-data settings."
    }
    Write-Host "Verified bundled asset: $($bundledSeed[0].FullName)" -ForegroundColor Green

    # 3. Prepare isolated temp workspace
    New-Item -ItemType Directory -Path $smokeRoot -Force -ErrorAction Stop | Out-Null

    # 4. Synthetic sandbox test
    $sandboxScript = Join-Path $RepoPath 'scripts\create_synthetic_sandbox.py'
    if (Test-Path -LiteralPath $sandboxScript) {
        Write-Host "`n[3/5] Generating synthetic sandbox DB..." -ForegroundColor Cyan
        $sandboxOutput = & $pythonExe $sandboxScript
        if ($LASTEXITCODE -ne 0) {
            throw "Synthetic sandbox generator failed (exit code $LASTEXITCODE)."
        }

        $sandboxSrc = Join-Path $env:TEMP 'tnotes_synthetic_sandbox.db'
        if (-not (Test-Path -LiteralPath $sandboxSrc)) {
            # Fall back to parsing a .db path printed by the script
            $match = ($sandboxOutput | Out-String) | Select-String -Pattern '([A-Za-z]:\\[^\r\n"]+\.db)'
            if ($match) { $sandboxSrc = $match.Matches[0].Groups[1].Value }
        }
        if (-not (Test-Path -LiteralPath $sandboxSrc)) {
            throw "Could not locate generated synthetic DB. Script output:`n$($sandboxOutput -join "`n")"
        }

        $sandboxCopy = Join-Path $smokeRoot 'synthetic_sandbox.db'
        Copy-Item -LiteralPath $sandboxSrc -Destination $sandboxCopy -Force -ErrorAction Stop
        Invoke-CheckedExe -ExePath $exePath -TargetDb $sandboxCopy -Label 'Synthetic Sandbox (40 EN/FR Tickets)'
    }
    else {
        Write-Host "`n[3/5] scripts\create_synthetic_sandbox.py not found; skipping synthetic run." -ForegroundColor Yellow
    }

    # 5. Live database copy test (never touches source)
    if ($LiveDbPath) {
        if (-not (Test-Path -LiteralPath $LiveDbPath)) {
            throw "Live DB path not found: $LiveDbPath"
        }

        Write-Host "`n[4/5] Copying live DB safely to temp folder..." -ForegroundColor Cyan
        $liveHashBefore = (Get-FileHash -LiteralPath $LiveDbPath -Algorithm SHA256 -ErrorAction Stop).Hash

        $liveCopyDir = Join-Path $smokeRoot 'live_copy'
        New-Item -ItemType Directory -Path $liveCopyDir -Force -ErrorAction Stop | Out-Null
        $liveFileName = Split-Path -Leaf $LiveDbPath
        $liveCopyPath = Join-Path $liveCopyDir $liveFileName

        Copy-Item -LiteralPath $LiveDbPath -Destination $liveCopyPath -Force -ErrorAction Stop
        foreach ($sidecar in @('-wal', '-shm')) {
            $sidecarSrc = "$LiveDbPath$sidecar"
            if (Test-Path -LiteralPath $sidecarSrc) {
                Copy-Item -LiteralPath $sidecarSrc -Destination "$liveCopyPath$sidecar" -Force -ErrorAction Stop
            }
        }

        Invoke-CheckedExe -ExePath $exePath -TargetDb $liveCopyPath -Label 'Live DB Copy (Migration & Search Check)'

        # Verify automatic pre-migration .bak was created inside the temp copy folder
        $bakFiles = Get-ChildItem -Path $liveCopyDir -Filter '*.bak' -ErrorAction SilentlyContinue
        if ($bakFiles) {
            Write-Host "Pre-migration backup confirmed in temp folder: $($bakFiles.Name -join ', ')" -ForegroundColor Green
        }

        # Cryptographically verify original live DB was untouched
        $liveHashAfter = (Get-FileHash -LiteralPath $LiveDbPath -Algorithm SHA256 -ErrorAction Stop).Hash
        if ($liveHashBefore -ne $liveHashAfter) {
            throw "SAFETY ALERT: Live DB SHA-256 changed! Ensure T-Notes respects env var '$DbEnvVar'."
        }
        Write-Host "Verified original live DB SHA-256 unchanged." -ForegroundColor Green
    }
    else {
        Write-Host "`n[4/5] No -LiveDbPath supplied; skipping live DB copy test." -ForegroundColor DarkGray
    }

    Write-Host "`n[5/5] Smoke test finished cleanly." -ForegroundColor Green
}
catch {
    Write-Error "Smoke test failed: $_"
    exit 1
}
finally {
    Remove-Item -Path "Env:$DbEnvVar" -ErrorAction SilentlyContinue
    Set-Location -LiteralPath $originalLocation -ErrorAction SilentlyContinue

    if ($Cleanup -and (Test-Path -LiteralPath $smokeRoot)) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned up temp directory: $smokeRoot" -ForegroundColor DarkGray
    }
    elseif (Test-Path -LiteralPath $smokeRoot) {
        Write-Host "Temp smoke-test artifacts kept at: $smokeRoot" -ForegroundColor DarkGray
    }
}
