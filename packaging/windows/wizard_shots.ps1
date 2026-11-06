<#
Walks Mabillon's Setup wizard the way a person would (not silently), clicks Next, Install and
Finish, and saves a picture of every page, so the wizard's look and wording can be checked
without a Windows PC. CI runs it on a fresh runner (.github/workflows/windows-installer.yml).
No model is downloaded: the download box is unticked (/MERGETASKS=!downloadmodel).

    powershell -ExecutionPolicy Bypass -File wizard_shots.ps1 -Installer <Setup.exe> -Out <folder>

Runs in Windows PowerShell 5.1 (it uses .NET Framework's UI Automation). Exits non-zero when
Setup does not finish, a page has no button to go on, or Mabillon is not installed afterwards.
#>
param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$Out,
    [int]$TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$log = Join-Path $Out 'setup.log'
$A = [System.Windows.Automation.AutomationElement]
$tree = [System.Windows.Automation.TreeScope]

function Save-Shot([System.Windows.Automation.AutomationElement]$window, [string]$name) {
    $r = $window.Current.BoundingRectangle
    $bmp = New-Object System.Drawing.Bitmap ([int]$r.Width), ([int]$r.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen([int]$r.X, [int]$r.Y, 0, 0, $bmp.Size)
    $bmp.Save((Join-Path $Out "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "saved $name.png"
}

function Get-Wizard([int]$processId) {
    $cond = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $processId)
    foreach ($w in $A::RootElement.FindAll($tree::Children, $cond)) {
        if ($w.Current.ControlType -eq [System.Windows.Automation.ControlType]::Window -and
            -not $w.Current.IsOffscreen -and $w.Current.BoundingRectangle.Width -gt 200) { return $w }
    }
    return $null
}

function Get-Text([System.Windows.Automation.AutomationElement]$window) {
    # Every visible label on the page, so the log records the wording beside each picture.
    $cond = New-Object System.Windows.Automation.PropertyCondition($A::IsOffscreenProperty, $false)
    ($window.FindAll($tree::Descendants, $cond) | ForEach-Object { $_.Current.Name } |
        Where-Object { $_ } | Select-Object -Unique) -join ' | '
}

function Get-Button([System.Windows.Automation.AutomationElement]$window) {
    # Next, Install or Finish, enabled: the button a person presses to go on.
    $cond = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button)
    foreach ($b in $window.FindAll($tree::Descendants, $cond)) {
        $label = $b.Current.Name -replace '&', ''
        if ($label -match '^(Next|Install|Finish)\b' -and $b.Current.IsEnabled -and -not $b.Current.IsOffscreen) {
            return $b
        }
    }
    return $null
}

# The Setup process Start-Process returns is the one that shows the wizard (Inno Setup 6 runs
# the wizard in a second, temporary process it starts from %TEMP%): watch for both.
$setupArgs = '/RUNTIME=cpu', '/MERGETASKS=addtopath,!downloadmodel', "/LOG=$log"
$first = Start-Process $Installer -ArgumentList $setupArgs -PassThru
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$page = 0
$lastText = ''
$shotInstalling = $false
$finished = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1500
    $procs = @(Get-Process | Where-Object { $_.Id -eq $first.Id -or $_.Path -like '*\is-*\*.tmp' })
    if (-not $procs) { break }
    $window = $null
    foreach ($p in $procs) { if (-not $window) { $window = Get-Wizard $p.Id } }
    if (-not $window) { continue }
    $text = Get-Text $window
    $button = Get-Button $window
    # While files are copied the progress text changes every moment: one picture of that page.
    $installing = (-not $button) -and $text -match 'Installing'
    if ($text -ne $lastText -and -not ($installing -and $shotInstalling)) {
        if ($installing) { $shotInstalling = $true }
        $page++
        $name = '{0:D2}-page' -f $page
        Save-Shot $window $name
        "$name : $text" | Out-File (Join-Path $Out 'pages.txt') -Append -Encoding utf8
        $lastText = $text
    }
    if (-not $button) { continue }  # the install itself, or a page still drawing
    $label = $button.Current.Name -replace '&', ''
    Write-Host "page $page : pressing $label"
    $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    if ($label -like 'Finish*') { $finished = $true }
}
if (-not $finished) { throw "Setup did not reach Finish within $TimeoutSeconds s (pages seen: $page; see $log)" }
$first.WaitForExit(60000) | Out-Null
$app = Join-Path $env:LOCALAPPDATA 'Programs\Mabillon'
if (-not (Test-Path (Join-Path $app 'mabillon.cmd'))) { throw "Mabillon is not installed at $app" }
Write-Host "Setup finished after $page pages; Mabillon is installed at $app"
