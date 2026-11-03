[CmdletBinding()]
param([Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$backupRoot = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $backupRoot) { throw 'Backup destination must be new.' }
if (-not $backupRoot.StartsWith('C:\Dev\TNotes-ReviewBackups\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected backup root.' }
$entry = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'entry-state.json') -Raw | ConvertFrom-Json -AsHashtable
# Prove all sources still match before copying anything.
foreach ($relative in $entry.files.Keys) {
    $source = Join-Path $root $relative
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.files[$relative]) { throw "Source drift: $relative" }
}
New-Item -ItemType Directory -Path $backupRoot | Out-Null
foreach ($relative in $entry.files.Keys) {
    $source = Join-Path $root $relative
    $target = [IO.Path]::GetFullPath((Join-Path $backupRoot $relative))
    if (-not $target.StartsWith($backupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup path escape.' }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    [IO.File]::Copy($source, $target, $false)
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.files[$relative]) { throw "Backup mismatch: $relative" }
}
[IO.File]::Copy((Join-Path $root '.git/index'), (Join-Path $backupRoot 'git-index.bin'), $false)
if ((Get-FileHash -LiteralPath (Join-Path $backupRoot 'git-index.bin')).Hash.ToLowerInvariant() -cne $entry.index_sha256) { throw 'Index drift.' }
[IO.File]::Copy((Join-Path $PSScriptRoot 'entry-state.json'), (Join-Path $backupRoot 'entry-state.json'), $false)
[ordered]@{status='PASS'; backup=$backupRoot; files=$entry.files.Count; index_sha256=$entry.index_sha256} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'backup-verification.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'backup-verification.json')
