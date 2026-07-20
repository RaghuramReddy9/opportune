$ErrorActionPreference = "Stop"

$version = if ($env:OPPORTUNE_VERSION) { $env:OPPORTUNE_VERSION } else { "0.1.1" }
$repository = if ($env:OPPORTUNE_REPOSITORY) { $env:OPPORTUNE_REPOSITORY } else { "RaghuramReddy9/opportune" }
$baseUrl = if ($env:OPPORTUNE_RELEASE_BASE_URL) { $env:OPPORTUNE_RELEASE_BASE_URL } else { "https://github.com/$repository/releases/download/v$version" }
$wheel = "opportune-$version-py3-none-any.whl"
$workDir = Join-Path ([IO.Path]::GetTempPath()) ("opportune-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $workDir | Out-Null

try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "uv was not found; installing it with the official installer..."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = "$HOME\.local\bin;$HOME\.cargo\bin;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is unavailable. Restart PowerShell and try again." }

    $wheelPath = Join-Path $workDir $wheel
    $sumsPath = Join-Path $workDir "SHA256SUMS"
    Invoke-WebRequest -UseBasicParsing "$baseUrl/$wheel" -OutFile $wheelPath
    Invoke-WebRequest -UseBasicParsing "$baseUrl/SHA256SUMS" -OutFile $sumsPath
    $escapedWheel = [regex]::Escape($wheel)
    $sumLine = Get-Content $sumsPath | Where-Object { $_ -match "^([0-9a-fA-F]{64})\s+\*?$escapedWheel$" } | Select-Object -First 1
    if (-not $sumLine) { throw "Checksum for $wheel is missing." }
    $expected = ($sumLine -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 $wheelPath).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Checksum verification failed." }

    & uv tool install --force --link-mode copy $wheelPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Installed Opportune v$version. Start it with: opportune run"
    if ($env:OPPORTUNE_NO_RUN -ne "1") { & opportune run @args }
} finally {
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
}
