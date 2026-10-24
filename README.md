# Mabillon

Local-first audit of government claims about phone evidence, for the criminal defense.
Mabillon reads the government's document, splits it into claims, and marks each one supported,
contradicted or unproven against the extraction data, with cited evidence.

Synthetic data only. Never put real discovery material in this repo.

- Rules for contributors and agents: [CLAUDE.md](CLAUDE.md)
- Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

```
make install   # editable install with dev tools
make check     # lint, tests, eval
```

Scanned government documents need OCR, which uses a local Tesseract install
(`apt install tesseract-ocr`, or the Windows installer from UB Mannheim). Without it, text-layer
PDFs still import, scanned pages fail with a clear error, and the OCR test is skipped.
`make fixtures` regenerates the synthetic PDFs in `eval/fixtures/govdoc/`.

## Working in the browser

```
mabillon serve --open                                  # cases in ~/Mabillon/cases (or --cases DIR)
mabillon serve --db case.db --expert "Your Name" --open  # one existing case database
mabillon model-check                                   # is the local model there, pinned, and does it fit?
mabillon demo                                          # reset and open the synthetic demo case (port 8766)
mabillon encrypt --db CASE/case.db --by "expert:Your Name"  # encrypt a case made before encryption
```

Giving a demo: [docs/demo.md](docs/demo.md) (the 10-minute flow and the planted traps' answer
key). Installing on an expert's computer: [docs/install-mac.md](docs/install-mac.md) (one
script, Apple silicon) or [docs/install.md](docs/install.md) (Windows installer).

Opens Mabillon at `http://127.0.0.1:8765/`, served from this computer only, with no internet
access and no scripts. The expert makes a case, imports the government document and the
phone reports (Cellebrite Excel, PDF or UFDR; Magnet AXIOM XML or Excel, unverified), copied
into the case folder, read-only, SHA-256 hashed, then settles the claims, confirms who used
each phone, runs the audit in the background with progress, and reviews each claim as soon as
it is labeled. See [docs/review-screen.md](docs/review-screen.md).
New cases are encrypted with a passphrase by default; older cases stay as they are until the
expert encrypts them. See [docs/encryption.md](docs/encryption.md).
