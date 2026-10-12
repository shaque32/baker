# Builds the llama-cpp-python wheel the installer ships, from the PyPI source release pinned in
# pins.json (the version Arsh's Mac runs), on a Windows runner with Visual Studio.
#
#   pwsh packaging/windows/build_llama.ps1 -Variant cpu  -OutDir build/wheels/cpu
#   pwsh packaging/windows/build_llama.ps1 -Variant cuda -OutDir build/wheels/cuda
#
# cpu:  AVX2 baseline (every Intel CPU since 2013 and AMD since 2015), not the build machine's
#       own CPU, so the wheel runs on an expert's laptop. No OpenMP, so no extra runtime DLL.
# cuda: the same plus CUDA kernels for Turing (RTX 20, T4), Ampere (RTX 30, A10) and Ada
#       (RTX 40, L4); newer cards (RTX 50) run the Ada code through the driver. Needs the CUDA
#       toolkit (install_cuda.ps1) and copies its runtime DLLs to <OutDir>\cuda-dlls.
param(
    [Parameter(Mandatory)][ValidateSet('cpu', 'cuda')][string]$Variant,
    [Parameter(Mandatory)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
$pins = Get-Content (Join-Path $PSScriptRoot 'pins.json') -Raw | ConvertFrom-Json
$llama = $pins.llama_cpp_python
New-Item -ItemType Directory -Force $OutDir | Out-Null
$sdistDir = Join-Path $OutDir 'sdist'

python -m pip download --no-deps --no-binary ':all:' "llama-cpp-python==$($llama.version)" -d $sdistDir
if ($LASTEXITCODE) { throw 'pip download failed' }
$sdist = Get-ChildItem $sdistDir -Filter 'llama_cpp_python-*.tar.gz' | Select-Object -First 1
$sha = (Get-FileHash $sdist.FullName -Algorithm SHA256).Hash.ToLower()
if ($sha -ne $llama.sdist_sha256) { throw "$($sdist.Name): SHA-256 $sha is not the pinned $($llama.sdist_sha256)" }
Write-Host "source $($sdist.Name) sha256 $sha"

$cmake = $llama.cpu_cmake_args
if ($Variant -eq 'cuda') {
    if (-not $env:CUDA_PATH) { throw 'CUDA_PATH is not set; run install_cuda.ps1 first' }
    # Newer Visual Studio releases than the CUDA toolkit knows about still build these kernels.
    $cmake = "$cmake $($llama.cuda_cmake_args) -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler"
}
$env:CMAKE_ARGS = $cmake
$env:CMAKE_BUILD_PARALLEL_LEVEL = [string][Environment]::ProcessorCount
Write-Host "CMAKE_ARGS=$cmake"
python -m pip wheel --no-deps -w $OutDir $sdist.FullName
if ($LASTEXITCODE) { throw 'wheel build failed' }

if ($Variant -eq 'cuda') {
    $dlls = Join-Path $OutDir 'cuda-dlls'
    New-Item -ItemType Directory -Force $dlls | Out-Null
    foreach ($name in $pins.cuda.runtime_dlls) {
        $src = Join-Path $env:CUDA_PATH "bin\$name"
        if (-not (Test-Path $src)) { throw "missing CUDA runtime DLL $src" }
        Copy-Item $src $dlls
    }
}
Get-ChildItem $OutDir -Recurse -File | Where-Object { $_.Extension -in '.whl', '.dll' } |
    ForEach-Object { '{0}  {1:N0} bytes' -f $_.FullName, $_.Length }
