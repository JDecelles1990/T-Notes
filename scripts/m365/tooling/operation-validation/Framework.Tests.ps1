# Pester 3.4 compatible; only synthetic source text is parsed, never executed.
Describe 'Portable operation AST inspection' {
    It 'accepts immutable contract ABI types as AST data' {
        $path = Join-Path ([IO.Path]::GetTempPath()) ('abi-' + [guid]::NewGuid() + '.txt')
        try {
            @'
[CmdletBinding()]
param(
[Parameter(Mandatory)][System.Collections.Generic.IReadOnlyDictionary[string,object]]$Context,
[Parameter(Mandatory)][System.Collections.Generic.IReadOnlyDictionary[string,object]]$Parameters,
[Parameter(Mandatory)][System.Threading.CancellationToken]$CancellationToken)
throw 'THIS_SOURCE_MUST_NEVER_EXECUTE'
'@ | Set-Content -LiteralPath $path -Encoding utf8
            $result = & (Join-Path $PSScriptRoot 'Inspect-Operation.ps1') -SourcePath $path | ConvertFrom-Json
            if ($result.parse_errors -ne 0 -or $result.parameters.Count -ne 3) { throw 'ABI AST failure' }
            if ($result.parameters[0].name -cne 'Context') { throw 'ABI name failure' }
        } finally { Remove-Item -LiteralPath $path -ErrorAction SilentlyContinue }
    }
    It 'reports malformed syntax without invoking it' {
        $path = Join-Path ([IO.Path]::GetTempPath()) ('invalid-' + [guid]::NewGuid() + '.txt')
        try {
            'param(' | Set-Content -LiteralPath $path -Encoding utf8
            $result = & (Join-Path $PSScriptRoot 'Inspect-Operation.ps1') -SourcePath $path | ConvertFrom-Json
            if ($result.parse_errors -eq 0) { throw 'Malformed syntax accepted' }
        } finally { Remove-Item -LiteralPath $path -ErrorAction SilentlyContinue }
    }
}
