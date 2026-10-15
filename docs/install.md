# Installing Baker on Windows

Baker runs on one Windows PC, offline by default. Nothing leaves the computer and Baker sends no
telemetry, unless you opt a case in to cloud AI at case setup (only if its protective order
allows it). Then, for that case only, one stance question at a time goes to Anthropic under your
own key. The only download is the AI model, once, during setup, and you
can skip it and copy the model from a USB drive instead.

## What you need

| | Minimum | Recommended |
|---|---|---|
| Windows | Windows 10 or 11, 64-bit | Windows 11 |
| Processor | x64 with AVX2 (Intel 2013 or later, AMD 2015 or later) | 8 cores or more |
| Memory | 16 GB | 32 GB |
| Graphics | none (runs on the processor, but see the speed table) | NVIDIA with 12 GB or more of video memory |
| Disk | 15 GB free (Baker 1 GB, model 9 GB, room for cases) | SSD |

How long a case takes depends almost entirely on the graphics card. Measured on the synthetic
test case (case01, 20 claims, about 500 model calls):

| Machine | Seconds per model call | Whole case | Measured |
|---|---|---|---|
| Apple M4 Mac, 24 GB (for comparison) | 56 | 7.75 h; about 6.2 h with flash attention, Baker's default since 2026-10-12 (estimated) | 2026-10-12, full case01 run |
| Windows, no GPU (4 cores, 16 GB) | more than 270 (estimated) | more than 1.5 days (estimated) | 2026-10-12, GitHub Windows runner: 3 claims, an estimated 75 calls, did not finish in 5 h 46 min |
| Windows, NVIDIA GPU | not yet measured | | rented-machine speed test, pending |

Without an NVIDIA card, a 4-core PC is too slow for real cases: use an NVIDIA PC or an Apple
silicon Mac with 24 GB. Until the NVIDIA numbers are in, plan on running a case overnight. A run
can stop and resume: finished claims are kept.

The 12 GB figure is an estimate, not a measurement: the model is 9.0 GB and its working memory
at Baker's context size about 1.3 GB more. On a card with less, the model may fail to load; the
run then stops with an error and nothing is decided from it. Reinstall with
`Baker-Setup-<version>.exe /RUNTIME=cpu` to run on the processor instead.

## Install

1. Download `Baker-Setup-<version>.exe` and `Baker-Setup-<version>.exe.sha256`.
2. Check the file before running it. In PowerShell:

       Get-FileHash .\Baker-Setup-<version>.exe -Algorithm SHA256

   The hash must match the one in the `.sha256` file and the one published with the release.
   Do not run the installer if they differ.
3. Run the installer. It installs for your Windows user only and needs no administrator rights.
   A signed installer names its publisher (right-click > **Properties** > **Digital
   Signatures**). An unsigned one makes Windows warn that the publisher is unknown: choose
   **More info**, then **Run anyway**, only after the hash check in step 2 matched. Signing
   is described in docs/code-signing.md.
4. Setup picks the model runtime for you: the NVIDIA (CUDA) build if the PC has an NVIDIA
   driver, otherwise the processor build. If you add an NVIDIA card later, run Setup again.
5. Leave **Download the AI model** ticked to download it now (9 GB, from Hugging Face), or untick
   it for an offline computer (next section).

Baker installs to `%LOCALAPPDATA%\Programs\Baker`, the model to `%LOCALAPPDATA%\Baker\models`,
and the model setting to `%USERPROFILE%\.baker\model.json`. Setup adds the `baker` command to
your PATH and a **Baker command prompt** shortcut to the Start menu.

## Offline computer (no internet)

On a computer with internet, download the installer, its `.sha256` file and the model file
`Qwen3-14B-Q4_K_M.gguf` from
<https://huggingface.co/Qwen/Qwen3-14B-GGUF> (Apache-2.0 license). Copy all three to a USB
drive and put them in one folder on the offline PC, then run Setup from that folder. Setup
copies the model and checks its SHA-256:

    500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0

A file with any other hash is refused, and Baker runs everything except the model steps until
a correct file is in place.

## Install the model later

Put `Qwen3-14B-Q4_K_M.gguf` next to the installer and run the installer again. Your cases are
not touched.

## Uninstall

**Settings > Apps > Baker > Uninstall** removes the program. Your case databases, the model
file and `%USERPROFILE%\.baker` stay, because they are your files. Delete them by hand if you
no longer need them.

## Check the install

Open **Baker command prompt** from the Start menu and run:

    baker --help

## For builders

The installer is built by `.github/workflows/windows-installer.yml` from `packaging/windows/`
(see the README there). Every download the build uses is pinned by SHA-256 in
`packaging/windows/pins.json`.
