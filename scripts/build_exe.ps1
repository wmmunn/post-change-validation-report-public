param(
    [switch]$SkipTests,
    [switch]$SkipInstall,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecFile = Join-Path $ProjectRoot "post_change_validation_reviewer.spec"
$DistExe = Join-Path $ProjectRoot "dist\post_change_validation_reviewer.exe"
$WarnFile = Join-Path $ProjectRoot "build\post_change_validation_reviewer\warn-post_change_validation_reviewer.txt"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Args
    )

    & $FilePath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Args -join ' ')"
    }
}

function New-ProjectVenv {
    if (Test-Path -LiteralPath $VenvPython) {
        return
    }

    Write-Step "Creating project virtual environment"

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        Invoke-Checked $pyLauncher.Source -3 -m venv (Join-Path $ProjectRoot ".venv")
        return
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        Invoke-Checked $python.Source -m venv (Join-Path $ProjectRoot ".venv")
        return
    }

    throw "No Python launcher was found. Install Python 3.11+, then rerun build_exe.ps1."
}

function Invoke-VenvPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    Invoke-Checked $VenvPython @Args
}

Set-Location -LiteralPath $ProjectRoot

New-ProjectVenv

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python was not created at $VenvPython"
}

Write-Step "Using project Python"
Invoke-VenvPython -c "import sys; print(sys.executable); print(sys.version)"

if (-not $SkipInstall) {
    Write-Step "Installing runtime and build dependencies"
    Invoke-VenvPython -m pip install --upgrade pip
    Invoke-VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements-build.txt")
}

Write-Step "Verifying required imports"
$ImportCheck = @'
from importlib.metadata import version
import PyInstaller
import customtkinter
import reportlab
import post_change_validation_reviewer
from src.port_mapping.profiles.generic import discover_public_profiles
profiles = discover_public_profiles()
assert profiles, "No public port-mapping profiles discovered"
print("customtkinter=" + customtkinter.__version__)
print("reportlab=" + version("reportlab"))
print("pyinstaller=" + PyInstaller.__version__)
print("public_profiles=" + str(len(profiles)))
'@
Invoke-VenvPython -c $ImportCheck

if (-not $SkipTests) {
    Write-Step "Running unit tests"
    Invoke-VenvPython -m unittest discover -s tests -v
}

Write-Step "Building windowed executable (one-file)"
Invoke-VenvPython -m PyInstaller --noconfirm --clean $SpecFile

if (-not (Test-Path -LiteralPath $DistExe)) {
    throw "Expected executable was not created: $DistExe"
}

Write-Step "Checking PyInstaller warnings for missing required packages"
if (Test-Path -LiteralPath $WarnFile) {
    $requiredMissing = Select-String `
        -LiteralPath $WarnFile `
        -Pattern "missing module named ['""]?(customtkinter|reportlab|tkinter)(?![\.\w])['""]?" `
        -CaseSensitive:$false

    if ($requiredMissing) {
        $requiredMissing | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
        throw "The executable build is missing a required dependency. See $WarnFile"
    }
}
else {
    Write-Warning "PyInstaller warning file was not found: $WarnFile"
}

$exeInfo = Get-Item -LiteralPath $DistExe
Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "  $($exeInfo.FullName)"
Write-Host "  $([math]::Round($exeInfo.Length / 1MB, 2)) MB"

if ($SmokeTest) {
    Write-Step "Smoke test: launch GUI for 5 seconds"
    $proc = Start-Process -FilePath $DistExe -PassThru
    Start-Sleep -Seconds 5
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
        Write-Host "Smoke test passed (process stayed running)." -ForegroundColor Green
    }
    else {
        throw "Executable exited early with code $($proc.ExitCode)."
    }
}
