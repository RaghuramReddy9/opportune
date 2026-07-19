# One-command source installer for Windows PowerShell.
# Optional environment variables:
#   $env:OPPORTUNE_REF = "main"
#   $env:OPPORTUNE_DIR = "$HOME\opportune"
#   $env:OPPORTUNE_NO_RUN = "1"

$ErrorActionPreference = "Stop"

$repoUrl = if ($env:OPPORTUNE_REPO_URL) { $env:OPPORTUNE_REPO_URL } else { "https://github.com/RaghuramReddy9/opportune.git" }
$repoRef = if ($env:OPPORTUNE_REF) { $env:OPPORTUNE_REF } else { "main" }
$installDir = if ($env:OPPORTUNE_DIR) { $env:OPPORTUNE_DIR } else { Join-Path $HOME "opportune" }

function Stop-Install([string]$Message) {
    Write-Error "Opportune installation stopped: $Message"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Stop-Install "Git is required. Install Git and run this command again."
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv was not found; installing it with the official installer..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$HOME\.local\bin;$HOME\.cargo\bin;$env:Path"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Stop-Install "uv was installed but is not available in this PowerShell session. Restart PowerShell and try again."
}

$gitDir = Join-Path $installDir ".git"
if (Test-Path $gitDir) {
    $status = (& git -C $installDir status --porcelain)
    if ($status) {
        Stop-Install "$installDir has local changes. Save them before running the updater."
    }
    $currentRef = (& git -C $installDir branch --show-current).Trim()
    if ($currentRef -ne $repoRef) {
        Stop-Install "$installDir is on '$currentRef'. Switch it to '$repoRef' before updating."
    }
    Write-Host "Updating Opportune in $installDir..."
    & git -C $installDir pull --ff-only origin $repoRef
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} elseif (Test-Path $installDir) {
    Stop-Install "$installDir exists but is not an Opportune Git checkout."
} else {
    Write-Host "Downloading Opportune into $installDir..."
    & git clone --branch $repoRef --depth 1 $repoUrl $installDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Installing Python dependencies..."
Push-Location $installDir
try {
    # Copy mode avoids Windows cloud-sync hardlink errors such as OS error 396.
    & uv sync --frozen --link-mode copy
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($env:OPPORTUNE_NO_RUN -eq "1") {
        Write-Host "Opportune is installed in $installDir"
        Write-Host "Start it with: cd $installDir; uv run opportune run"
    } else {
        & uv run opportune run
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
