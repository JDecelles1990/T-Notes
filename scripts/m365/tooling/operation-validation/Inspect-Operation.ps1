[CmdletBinding()]
param([Parameter(Mandatory)][string]$SourcePath)
$ErrorActionPreference = 'Stop'
# Parse bytes as data. Never dot-source, import, or invoke the inspected operation.
$tokens = $null; $errors = $null
$text = [IO.File]::ReadAllText($SourcePath)
$ast = [Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$errors)
$parameters = @($ast.ParamBlock.Parameters | ForEach-Object {
    $p = $_
    [pscustomobject]@{
        name=$p.Name.VariablePath.UserPath
        type=$p.StaticType.FullName
        generic_arguments=@($p.StaticType.GetGenericArguments() | ForEach-Object { $_.FullName })
        default=($null -ne $p.DefaultValue)
        attributes=@($p.Attributes | ForEach-Object { $_.Extent.Text })
    }
})
$commands = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]}, $true) | ForEach-Object {
    [pscustomobject]@{name=$_.GetCommandName(); invocation=[string]$_.InvocationOperator}
})
$modules = @(Get-Module -ListAvailable Pester | Sort-Object Version -Descending)
[pscustomobject]@{
    powershell=[string]$PSVersionTable.PSVersion
    pester=$(if ($modules.Count) {[string]$modules[0].Version} else {$null})
    parse_errors=$errors.Count
    parameters=$parameters
    commands=$commands
    using_count=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.UsingStatementAst]}, $true)).Count
    requires=($null -ne $ast.ScriptRequirements)
    first_statement=$(if ($ast.EndBlock.Statements.Count) {$ast.EndBlock.Statements[0].Extent.Text} else {''})
} | ConvertTo-Json -Depth 8 -Compress
