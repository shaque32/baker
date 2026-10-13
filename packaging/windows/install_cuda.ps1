# Installs the parts of the CUDA toolkit the CUDA build needs (compiler, runtime, cuBLAS), from
# NVIDIA's network installer pinned in pins.json, and sets CUDA_PATH for later CI steps.
# Build machines only: an expert's PC gets the runtime DLLs inside the installer, never this.
$ErrorActionPreference = 'Stop'
$cuda = (Get-Content (Join-Path $PSScriptRoot 'pins.json') -Raw | ConvertFrom-Json).cuda
$short = ($cuda.version -split '\.')[0..1] -join '.'
$exe = Join-Path $env:RUNNER_TEMP 'cuda_network.exe'
Invoke-WebRequest $cuda.url -OutFile $exe
$sig = Get-AuthenticodeSignature $exe
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'NVIDIA') {
    throw "CUDA installer signature: $($sig.Status) $($sig.SignerCertificate.Subject)"
}
$parts = $cuda.components | ForEach-Object { "${_}_$short" }
Write-Host "installing CUDA $short components: $parts"
$p = Start-Process $exe -ArgumentList (@('-s') + $parts) -Wait -PassThru
if ($p.ExitCode) { throw "CUDA installer exit code $($p.ExitCode)" }
$root = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v$short"
if (-not (Test-Path "$root\bin\nvcc.exe")) { throw "nvcc not found under $root" }
# Visual Studio's CUDA build rules look for CUDA_PATH_V<major>_<minor>, not CUDA_PATH.
$versioned = 'CUDA_PATH_V' + ($short -replace '\.', '_')
"CUDA_PATH=$root", "$versioned=$root", "CudaToolkitDir=$root\" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
"$root\bin" | Out-File $env:GITHUB_PATH -Append -Encoding utf8
& "$root\bin\nvcc.exe" --version
