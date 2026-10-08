# Baker

Local-first audit of government claims about phone evidence, for the criminal defense.
Baker reads the government's document, splits it into claims, and marks each one supported,
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

## Expert review screen

```
baker serve --db case.db --expert "Your Name" --open
```

Opens the review screen at `http://127.0.0.1:8765/`, served from this computer only, with no
internet access and no scripts. See [docs/review-screen.md](docs/review-screen.md).
