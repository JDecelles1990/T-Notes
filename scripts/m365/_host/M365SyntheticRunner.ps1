<#
.SYNOPSIS
    One-shot isolated PowerShell 7 runner for T-Notes M365 operations.
.DESCRIPTION
    Reads a single UTF-8 JSON request line from stdin containing protocol_path,
    script_path, context, parameters, and already_cancelled, invokes the target
    operation script with frozen inputs and native return validation, and emits
    a single-line compressed JSON result on stdout.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Force UTF-8 (no BOM) so Unicode characters survive stdin/stdout piping on Windows.
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$raw = [Console]::In.ReadLine()
$payload = ConvertFrom-Json -InputObject $raw -AsHashtable -Depth 25
. $payload['protocol_path']
Initialize-NativeReturnValidation
$frozenContext = Freeze-Value $payload['context']
$rawParams = if ($null -ne $payload['parameters']) { $payload['parameters'] } else { @{} }
$frozenParams = Freeze-Value $rawParams
$cts = [System.Threading.CancellationTokenSource]::new()
if ([bool]$payload['already_cancelled']) { $cts.Cancel() }
$ret = & $payload['script_path'] -Context $frozenContext -Parameters $frozenParams -CancellationToken $cts.Token
Assert-NativeOperationReturn $ret
$json = ConvertTo-Json -InputObject $ret -Depth 20 -Compress
[Console]::Out.WriteLine($json)
