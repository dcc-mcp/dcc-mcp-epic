$ErrorActionPreference = "Stop"

$stdout = [IO.Path]::GetTempFileName()
$stderr = [IO.Path]::GetTempFileName()
$server = (Get-Command dcc-mcp-server).Source
$arguments = @(
    "translate",
    "--stdio", '"uv run dcc-mcp-epic"',
    "--app-type", "epic",
    "--host", "127.0.0.1",
    "--port", "39876",
    "--gateway-port", "0",
    "--no-register",
    "--server-name", "dcc-mcp-epic-smoke"
)
$process = Start-Process -FilePath $server -ArgumentList $arguments `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
    -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds 5
    $tcp = Get-NetTCPConnection -LocalPort 39876 -State Listen -ErrorAction SilentlyContinue
    [pscustomobject]@{
        pid = $process.Id
        running = -not $process.HasExited
        listening = ($null -ne $tcp)
        stdout = Get-Content $stdout -Raw
        stderr = Get-Content $stderr -Raw
    } | ConvertTo-Json -Depth 4
}
finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    Start-Sleep -Milliseconds 500
    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
}
