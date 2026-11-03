# Fixed, pinned offline schema helper; stdin is an internal validation batch.
try {
    . "$PSScriptRoot/protocol.ps1"
    $raw = [Console]::In.ReadToEnd()
    if ([Text.Encoding]::UTF8.GetByteCount($raw) -gt 2097152) { throw 'Batch too large' }
    $batch = ConvertFrom-Json -InputObject $raw -AsHashtable -Depth 100
    $options = New-SchemaOptions $batch.schemas
    foreach ($case in $batch.cases) { Assert-Schema $case.instance $case.reference $options }
    [Console]::Out.WriteLine('{"valid":true}')
} catch {
    [Console]::Out.WriteLine('{"valid":false}')
}
