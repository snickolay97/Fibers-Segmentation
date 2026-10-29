param([string]$ProjectFile = '', [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskCandidates = @(
    (Join-Path $taskRoot '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE 'anaconda3\envs\bm-336546\python.exe'),
    'python'
)
$taskPython = $null
foreach ($taskCandidate in $taskCandidates) {
    if ($taskCandidate -ne 'python' -and -not (Test-Path -LiteralPath $taskCandidate)) { continue }
    try {
        & $taskCandidate -c "import importlib.util; import cv2, numpy, skimage, scipy, pandas, tifffile, PIL; assert importlib.util.find_spec('PySide6') or importlib.util.find_spec('PyQt6')" 2>$null
        if ($LASTEXITCODE -eq 0) { $taskPython = $taskCandidate; break }
    } catch { continue }
}
if (-not $taskPython) {
    Write-Host 'No Python environment with all dependencies was found. See README.md / README_RU.md.'
    Read-Host 'Press Enter to exit / Нажмите Enter для выхода'
    exit 1
}
Push-Location -LiteralPath $taskRoot
try {
    $taskArguments = @()
    if ($ProjectFile) { $taskArguments += @('--project', $ProjectFile) }
    if ($SmokeTest) { $taskArguments += '--smoke-test' }
    & $taskPython -B (Join-Path $taskRoot 'app.py') @taskArguments
    $taskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($taskExitCode -ne 0) { Read-Host 'Application error. Press Enter / Ошибка приложения. Нажмите Enter' }
exit $taskExitCode
