param([string]$ProjectFile = '', [switch]$SmokeTest, [switch]$Shortcut)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
# Try the project environment first, then the local scientific environment and PATH.
# Probe imports because finding a Python executable alone does not verify native DLLs.
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
    $taskMessage = 'No Python environment with all dependencies was found. See README.md / README_RU.md.'
    if ($Shortcut) {
        $taskShell = New-Object -ComObject WScript.Shell
        [void]$taskShell.Popup($taskMessage, 0, 'SoLoData', 16)
    } else {
        Write-Host $taskMessage
        Read-Host 'Press Enter to exit / Нажмите Enter для выхода'
    }
    exit 1
}
# Keep startup paths predictable when launched by double-click or from another folder.
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
if ($taskExitCode -ne 0 -and -not $Shortcut) {
    Read-Host 'Application error. Press Enter / Ошибка приложения. Нажмите Enter'
}
exit $taskExitCode
