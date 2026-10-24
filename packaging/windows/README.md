# Windows packaging

| File | What it does |
|---|---|
| `pins.json` | Every download the build uses (embeddable Python, llama-cpp-python source, CUDA toolkit, model), pinned by SHA-256 |
| `build_llama.ps1` | Builds the llama-cpp-python wheel from the pinned PyPI source: `cpu` (AVX2, no OpenMP) or `cuda` |
| `install_cuda.ps1` | CUDA toolkit on the build machine only (checks NVIDIA's signature) |
| `stage.py` | Lays out what the installer ships: Python, Mabillon's git-tracked source (in a folder still named `baker`) (no case02, no cloud benchmark), both runtimes, `BUILD_INFO.json` with every file's SHA-256 |
| `baker.iss` | Inno Setup script: per-user install, picks the runtime, places and verifies the model, writes `~/.mabillon/model.json`. An update over an install made under the name Baker keeps its folder, model and own model setting, and replaces its Start-menu shortcuts |
| `baker.cmd` | The `mabillon` command (`python -X utf8 -m cli`), staged as both `mabillon.cmd` and `baker.cmd` |
| `speedtest.ps1` | Install, model download and check, probe and timed case01 audit, then `RESULTS.md` to paste back |

CI (`.github/workflows/windows-installer.yml`) runs on every push to `main`, on pull requests
that touch this folder, and on demand. It checks the pins, builds both runtimes (cached), builds
the installer, installs it on a fresh runner and runs the case01 merge gate from the installed
copy, then uninstalls it. The installer, its `.sha256`, `BUILD_INFO.json` and `speedtest.ps1`
are the `mabillon-installer` artifact of the run.

CPU timing: **Actions > windows-installer > Run workflow** with "Time the 14B model" ticked, or
on a pull request add the `cpu-timing` label (or push a commit to `main` whose message contains
`[cpu-timing]`). Results are in the run summary and the
`cpu-timing` artifact.

## Decisions

- Setup keeps the AppId it had under the name Baker, so it updates such an install in place
  (in `%LOCALAPPDATA%\Programs\Baker`) rather than installing a second copy. The pip package
  and the source folder keep the name `baker`, like the file format ids (CLAUDE.md).
- The model runtime is chosen at install time, not at run time: a CUDA build of llama.cpp does
  not load at all on a PC without the NVIDIA driver.
- The CUDA build carries `cudart64_12.dll`, `cublas64_12.dll` and `cublasLt64_12.dll`, which the
  CUDA license lets applications redistribute, so an expert never installs the CUDA toolkit. It
  needs an NVIDIA driver that supports CUDA 12.4 (R550 or later is safe; minor-version
  compatibility allows older 12.x drivers).
- llama-cpp-python is 0.3.36, the version Arsh's Mac ran, so Mac and Windows run the same
  llama.cpp.
- The MSVC runtime DLLs ship next to the llama runtime, so a PC without the Visual C++
  redistributable still loads it.
- Builds of main are signed with Microsoft Artifact Signing (docs/code-signing.md); a main
  build whose signing settings are missing fails instead of shipping unsigned. Pull request
  builds are unsigned and the run warns. The installer's SHA-256 is published with every build.
