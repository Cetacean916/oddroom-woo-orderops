[CmdletBinding()]
param(
    [ValidateSet('Hub', 'Preflight', 'Start', 'Status', 'Stop', 'Restart', 'Recover', 'Diagnostics', 'Evidence')]
    [string]$Action = 'Hub'
)

$ErrorActionPreference = 'Stop'
$PackageRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot 'packaging\common\action-contract.json'))) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        'The PF07 package is incomplete. Extract the complete ZIP into one folder and try again.',
        'OFFSET OrderOps',
        'OK',
        'Error'
    ) | Out-Null
    exit 13
}

$StateDirectory = Join-Path $PackageRoot '.pf07'
New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
$ResumePath = Join-Path $StateDirectory 'prerequisite-resume.json'

function Show-PF07Message {
    param([string]$Text, [string]$Kind = 'Information', [string]$Buttons = 'OK')
    Add-Type -AssemblyName System.Windows.Forms
    return [System.Windows.Forms.MessageBox]::Show($Text, 'OFFSET OrderOps', $Buttons, $Kind)
}

function Save-PF07Resume {
    param([string]$State, [string]$NextAction)
    @{
        schema = 'pf07.prerequisite-resume.v1'
        state = $State
        next_action = $NextAction
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $ResumePath -Encoding UTF8
}

function Find-PF07Python {
    $Py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $Py) { return @{ File = $Py.Source; Prefix = @('-3') } }
    $Python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $Python) { return @{ File = $Python.Source; Prefix = @() } }
    return $null
}

function Open-PF07Prerequisite {
    param([string]$State)
    if ($State -eq 'MISSING_PYTHON') {
        $answer = Show-PF07Message -Buttons 'YesNo' -Kind 'Warning' -Text @'
Python 3.10 or newer is required.

1. Select Yes to open the official Python download page.
2. Install Python and enable its launcher/PATH option.
3. Open PF07-Launcher.exe again. PF07 will recheck and resume.
'@
        if ($answer -eq 'Yes') { Start-Process 'https://www.python.org/downloads/windows/' }
        Save-PF07Resume -State $State -NextAction 'Hub'
        return
    }
    $answer = Show-PF07Message -Buttons 'YesNo' -Kind 'Warning' -Text @'
A ready Docker-compatible runtime with Compose is required.

0-KRW maintained path for this portfolio package:
1. Select Yes to open the official Rancher Desktop site.
2. Install Rancher Desktop and select the Moby container engine.
3. Start Rancher Desktop and wait until it reports Ready.
4. Open PF07-Launcher.exe again. PF07 will recheck and resume.

Docker Desktop is only an optional alternative when your use is eligible under its current terms.
'@
    if ($answer -eq 'Yes') { Start-Process 'https://rancherdesktop.io/' }
    Save-PF07Resume -State $State -NextAction 'Hub'
}

$Python = Find-PF07Python
if ($null -eq $Python) {
    Open-PF07Prerequisite -State 'MISSING_PYTHON'
    exit 20
}

$env:PYTHONPATH = (Join-Path $PackageRoot 'launcher')
$env:PYTHONDONTWRITEBYTECODE = '1'
$PythonArguments = @() + $Python.Prefix + @('-B')

if ($Action -eq 'Preflight' -or $Action -eq 'Hub') {
    $PreflightJson = & $Python.File @PythonArguments -m pf07_launcher.cli preflight 2>&1
    if ($LASTEXITCODE -ne 0) {
        Show-PF07Message -Kind 'Error' -Text ($PreflightJson -join [Environment]::NewLine) | Out-Null
        exit $LASTEXITCODE
    }
    $Preflight = ($PreflightJson -join [Environment]::NewLine) | ConvertFrom-Json
    if (-not $Preflight.ready) {
        Open-PF07Prerequisite -State $Preflight.state
        exit 21
    }
    if (Test-Path -LiteralPath $ResumePath) { Remove-Item -LiteralPath $ResumePath -Force }
    if ($Action -eq 'Preflight') {
        Show-PF07Message -Text 'Python, the container runtime, and Docker Compose are ready.' | Out-Null
        exit 0
    }
}

if ($Action -eq 'Hub') {
    $arguments = @() + $PythonArguments + @('-m', 'pf07_launcher.hub')
    Start-Process -FilePath $Python.File -ArgumentList $arguments -WorkingDirectory $PackageRoot -WindowStyle Hidden
    exit 0
}

$Command = switch ($Action) {
    'Start' { 'start' }
    'Status' { 'status' }
    'Stop' { 'stop' }
    'Restart' { 'restart' }
    'Recover' { 'recover' }
    'Diagnostics' { 'diagnostics' }
    'Evidence' { 'evidence-export' }
}
$Result = & $Python.File @PythonArguments -m pf07_launcher.cli $Command 2>&1
if ($LASTEXITCODE -ne 0) {
    Show-PF07Message -Kind 'Error' -Text ($Result -join [Environment]::NewLine) | Out-Null
    exit $LASTEXITCODE
}
Show-PF07Message -Text ($Result -join [Environment]::NewLine) | Out-Null
exit 0
