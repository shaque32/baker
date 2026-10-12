<#
Baker speed test on a Windows PC: installs Baker from the installer, downloads and checks the
model, runs the stance probe and a timed case01 audit, and writes RESULTS.md to paste back.
Everything it runs is synthetic (case01 and the signed probe set). It also proves the
installer works on a clean PC.

On an NVIDIA machine (rented or a friendly examiner's), in PowerShell:

    powershell -ExecutionPolicy Bypass -File .\speedtest.ps1 -Installer .\Baker-Setup-<version>.exe

Options:
    -InstallerSha256 <hex>  check the installer against the SHA-256 published with it
    -Claims C02,C05,C12     time only these case01 claims and project the whole case
                            (default: the whole case on an NVIDIA GPU, C02,C05,C12 on CPU)
    -SkipProbe              skip the 88-item probe (CI's CPU run does; it adds hours on a CPU)
    -NCtx 8192              model context (8192 is what accuracy was measured with)
    -Out <folder>           where results go (default: Documents\baker-speedtest)

Needs about 25 GB free disk (model 9 GB, Baker 1 GB, a copy during install) and an internet
connection for the model download only. Baker itself never connects to the internet.
#>
param(
    [Parameter(Mandatory)][string]$Installer,
    [string]$InstallerSha256 = '',
    [string]$Claims = '',
    [switch]$SkipProbe,
    [int]$NCtx = 8192,
    [string]$Out = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'baker-speedtest')
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
Start-Transcript (Join-Path $Out 'transcript.txt') -Force | Out-Null
$started = Get-Date
$app = Join-Path $env:LOCALAPPDATA 'Programs\Baker'

function Step([string]$text) { Write-Host "`n== $text ($((Get-Date).ToString('HH:mm:ss')))" -ForegroundColor Cyan }

function Install-Baker([string]$exe, [string]$log) {
    $setupArgs = '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/MERGETASKS=!downloadmodel', "/LOG=$log"
    $p = Start-Process $exe -ArgumentList $setupArgs -Wait -PassThru
    if ($p.ExitCode) { throw "Setup exit code $($p.ExitCode); see $log" }
}

function Run-Py([string[]]$pyArgs) {
    Push-Location (Join-Path $app 'baker')
    try {
        & (Join-Path $app 'python\python.exe') -X utf8 @pyArgs
        if ($LASTEXITCODE) { throw "python $($pyArgs -join ' ') exited $LASTEXITCODE" }
    } finally { Pop-Location }
}

# ------------------------------------------------------------------ the machine
Step 'Machine'
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$os = Get-CimInstance Win32_OperatingSystem
$gpu = 'none (no nvidia-smi)'
$smi = Join-Path $env:WINDIR 'System32\nvidia-smi.exe'
if (Test-Path $smi) {
    $gpu = (& $smi --query-gpu=name,driver_version,memory.total --format=csv,noheader) -join '; '
}
$machine = "$($cpu.Name.Trim()), $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads, $ram GB RAM; GPU: $gpu; $($os.Caption) $($os.Version)"
Write-Host $machine
if (-not $Claims -and -not (Test-Path $smi)) { $Claims = 'C02,C05,C12' }

# ------------------------------------------------------------------ install
Step 'Installer'
if ($Installer -match '^https://') {
    $local = Join-Path $Out (Split-Path $Installer -Leaf)
    Invoke-WebRequest $Installer -OutFile $local
    $Installer = $local
}
$Installer = (Resolve-Path $Installer).Path
$installerSha = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLower()
Write-Host "$Installer sha256 $installerSha"
if ($InstallerSha256 -and $installerSha -ne $InstallerSha256.ToLower()) {
    throw "Installer SHA-256 $installerSha is not the published $InstallerSha256"
}
$sig = (Get-AuthenticodeSignature $Installer).Status
Write-Host "Code signature: $sig (unsigned until Baker has a code-signing certificate)"
Install-Baker $Installer (Join-Path $Out 'setup-1.log')
$runtime = (Select-String -Path (Join-Path $Out 'setup-1.log') -Pattern 'Model runtime installed: (\w+)').Matches |
    ForEach-Object { $_.Groups[1].Value } | Select-Object -Last 1
Write-Host "Model runtime: $runtime"
$build = Get-Content (Join-Path $app 'BUILD_INFO.json') -Raw | ConvertFrom-Json
$model = $build.model
Run-Py @('-c', "import llama_cpp; print('llama-cpp-python', llama_cpp.__version__, 'gpu offload:', llama_cpp.llama_supports_gpu_offload())")

# ------------------------------------------------------------------ model
Step "Model $($model.file)"
$modelDir = Join-Path $env:LOCALAPPDATA 'Baker\models'
New-Item -ItemType Directory -Force $modelDir | Out-Null
$modelPath = Join-Path $modelDir $model.file
$have = (Test-Path $modelPath) -and ((Get-FileHash $modelPath -Algorithm SHA256).Hash.ToLower() -eq $model.sha256)
if (-not $have) {
    $curl = Join-Path $env:WINDIR 'System32\curl.exe'
    Write-Host "Downloading $($model.url) (about 9 GB; resumes if interrupted)"
    $t = Measure-Command { & $curl -fL --retry 5 -C - -o $modelPath $model.url }
    if ($LASTEXITCODE) { throw "model download failed (curl exit $LASTEXITCODE)" }
    Write-Host ("Downloaded in {0:N0} s" -f $t.TotalSeconds)
    $sha = (Get-FileHash $modelPath -Algorithm SHA256).Hash.ToLower()
    if ($sha -ne $model.sha256) { Remove-Item $modelPath; throw "model SHA-256 $sha is not the pinned $($model.sha256)" }
}
Write-Host 'Model SHA-256 matches the pin.'
# Reinstall: Setup finds the verified model and points Baker at it (~/.baker/model.json).
Install-Baker $Installer (Join-Path $Out 'setup-2.log')
$config = Join-Path $env:USERPROFILE '.baker\model.json'
if (-not (Test-Path $config)) { throw "Setup did not write $config; see setup-2.log" }
Get-Content $config

$models = Join-Path $Out 'models.json'
$entry = @{ name = $model.name; path = $modelPath.Replace('\', '/'); sha256 = $model.sha256; license = $model.license }
# UTF-8 without a byte-order mark (Windows PowerShell's Out-File adds one, which JSON readers reject).
[IO.File]::WriteAllText($models, "[$($entry | ConvertTo-Json)]")

# ------------------------------------------------------------------ probe and timed audit
if (-not $SkipProbe) {
    Step 'Stance probe on the signed set (P001-P088)'
    Run-Py @('-m', 'eval.probe.run_probe', '--models', $models, '--probe-set', 'eval/gold/probe/probe.jsonl',
        '--stance-only', '--repeat', '1', '--n-ctx', "$NCtx", '--out', (Join-Path $Out 'probe'))
}
Step "Timed case01 audit ($(if ($Claims) { "claims $Claims, projected to the whole case" } else { 'whole case' }))"
$timeArgs = @('-m', 'eval.probe.time_case', '--models', $models, '--n-ctx', "$NCtx", '--out', (Join-Path $Out 'speed'))
if ($Claims) { $timeArgs += @('--claims', $Claims) }
Run-Py $timeArgs

# ------------------------------------------------------------------ results
Step 'Results'
$results = Join-Path $Out 'RESULTS.md'
$lines = @(
    "# Baker Windows speed test ($((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mmZ')))",
    '',
    "Machine: $machine",
    "Model runtime: $runtime; n_ctx $NCtx; model $($model.file) sha256 $($model.sha256)",
    "Installer: $(Split-Path $Installer -Leaf) sha256 $installerSha (signature: $sig); Baker commit $($build.git_commit)",
    "Wall time of this script: $([math]::Round(((Get-Date) - $started).TotalMinutes)) min",
    ''
)
if (Test-Path $smi) { $lines += @('```', (& $smi) , '```', '') }
foreach ($part in @('probe\summary.md', 'speed\summary.md')) {
    $f = Join-Path $Out $part
    if (Test-Path $f) { $lines += (Get-Content $f); $lines += '' }
}
[IO.File]::WriteAllText($results, ($lines -join "`r`n") + "`r`n")
Stop-Transcript | Out-Null
Write-Host "`nDone. Paste back the contents of $results :`n"
Get-Content $results
