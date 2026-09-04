[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [ValidateSet("loopback", "lan")]
    [string]$Exposure = "lan",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [string]$NetworkInterface,

    [switch]$ConfigureCodex,
    [switch]$InstallSkill,
    [switch]$Start
)

$ErrorActionPreference = "Stop"

$project = (Resolve-Path -LiteralPath $ProjectPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $project "pyproject.toml"))) {
    throw "ProjectPath must contain pyproject.toml: $project"
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/"
}

Push-Location $project
try {
    & $uv.Source sync --extra dev
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE"
    }

    $envFile = Join-Path $project ".env"
    $exampleFile = Join-Path $project ".env.example"
    if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $exampleFile)) {
        Copy-Item -LiteralPath $exampleFile -Destination $envFile
    }

    $bindHost = if ($Exposure -eq "lan") { "0.0.0.0" } else { "127.0.0.1" }
    $urlHost = "127.0.0.1"
    $ipConfigurations = @(
        Get-NetIPConfiguration -ErrorAction SilentlyContinue |
            Where-Object {
                $_.NetAdapter.Status -eq "Up" -and $_.IPv4Address
            }
    )
    if ($NetworkInterface) {
        $ipConfigurations = @(
            $ipConfigurations | Where-Object { $_.InterfaceAlias -eq $NetworkInterface }
        )
    }
    else {
        $wifiConfigurations = @(
            $ipConfigurations | Where-Object {
                $_.InterfaceAlias -match "Wi[- ]?Fi|WLAN|Wireless|无线"
            }
        )
        if ($wifiConfigurations.Count -gt 0) {
            $ipConfigurations = $wifiConfigurations
        }
    }
    $lanAddresses = @(
        $ipConfigurations |
            Where-Object { $_.IPv4DefaultGateway -or $NetworkInterface } |
            ForEach-Object { $_.IPv4Address | Select-Object -ExpandProperty IPAddress }
    )
    if ($lanAddresses.Count -eq 0) {
        $lanAddresses = @(
            Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.IPAddress -notlike "127.*" -and
                    $_.IPAddress -notlike "169.254.*" -and
                    $_.PrefixOrigin -ne "WellKnown"
                } |
                Select-Object -ExpandProperty IPAddress
        )
    }
    if ($Exposure -eq "lan" -and $lanAddresses.Count -gt 0) {
        $urlHost = $lanAddresses[0]
    }

    $mcpUrl = "http://$urlHost`:$Port/mcp"
    $webhookUrl = "http://$urlHost`:$Port/api/v1/providers/smsforwarder/webhook"

    if ($ConfigureCodex) {
        $codex = Get-Command codex -ErrorAction SilentlyContinue
        if (-not $codex) {
            throw "codex was not found; omit -ConfigureCodex or install Codex first"
        }
        & $codex.Source mcp get smsmcphub *> $null
        if ($LASTEXITCODE -ne 0) {
            & $codex.Source mcp add smsmcphub --url $mcpUrl
            if ($LASTEXITCODE -ne 0) {
                throw "codex mcp add failed with exit code $LASTEXITCODE"
            }
        }
    }

    if ($InstallSkill) {
        $skillSource = Join-Path $project "skills\smsmcphub"
        if (-not (Test-Path -LiteralPath (Join-Path $skillSource "SKILL.md"))) {
            throw "Skill source not found: $skillSource"
        }
        $skillTarget = Join-Path $env:USERPROFILE ".codex\skills\smsmcphub"
        New-Item -ItemType Directory -Path (Split-Path -Parent $skillTarget) -Force | Out-Null
        Copy-Item -LiteralPath $skillSource -Destination $skillTarget -Recurse -Force
    }

    if ($Start) {
        $python = Join-Path $project ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $python)) {
            throw "Project virtual environment was not created: $python"
        }
        $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $existing) {
            $logDir = Join-Path $project "logs"
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            Start-Process -WindowStyle Hidden -FilePath $python `
                -ArgumentList "-m", "uvicorn", "smsmcphub.main:app", "--host", $bindHost, "--port", $Port `
                -WorkingDirectory $project `
                -RedirectStandardOutput (Join-Path $logDir "server.out.log") `
                -RedirectStandardError (Join-Path $logDir "server.err.log") | Out-Null
        }
        $healthUrl = "http://127.0.0.1`:$Port/healthz"
        $healthy = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try {
                $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
                if ($health.status -eq "ok") {
                    $healthy = $true
                    break
                }
            }
            catch {
                Start-Sleep -Milliseconds 250
            }
        }
        if (-not $healthy) {
            throw "SmsMCPHub did not become healthy at $healthUrl"
        }
    }

    [ordered]@{
        project_path = $project
        exposure = $Exposure
        network_interface = $NetworkInterface
        bind_host = $bindHost
        lan_ip = if ($Exposure -eq "lan") { $urlHost } else { $null }
        webhook_url = $webhookUrl
        mcp_url = $mcpUrl
        env_file = $envFile
        started = [bool]$Start
        codex_configured = [bool]$ConfigureCodex
        skill_installed = [bool]$InstallSkill
    } | ConvertTo-Json -Depth 4
}
finally {
    Pop-Location
}
