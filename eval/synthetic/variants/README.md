# Report layout variants

Everything here is fictional. No real case data, ever.

One small synthetic phone (`base.py`: two chats, two SMS, four calls, three contacts, two owner
accounts) rendered in 25 Cellebrite-style report layouts, so the importers meet the layouts a
real report might use before a pilot does. The layouts come from public descriptions of
Cellebrite Physical Analyzer and Reader reports, not from real exports, so a real report can
still surprise us; the first real sample should become a new variant here (synthetic copy of
its layout only, never its content).

```
python -m eval.synthetic.variants.check        # build all, import, check; exit 1 on a failure
python -m eval.synthetic.variants.check -v     # also print every coverage item
python -m eval.synthetic.variants.check --only x07_ambiguous_dates --out /tmp/variants
```

| File | What it is |
|---|---|
| `base.py` | The phone, and the time formats the variants print |
| `excel.py` | Default Excel layout (the case01 one) and a workbook writer (openpyxl) |
| `pdf.py` | A small PDF report builder (reportlab) |
| `catalog.py` | Every variant: how it is built and what a correct import gives back |
| `check.py` | Imports each variant into a fresh database and checks it |

A variant passes when (1) the imported messages, calls, contacts and attachments equal the
phone's (PDF text compared with whitespace collapsed, since PDF layout reflows it), or the
fields it could not read are empty; (2) the coverage summary flags for review exactly the
problems the variant plants, and its status (`complete` or `needs_review`) is the expected one;
(3) every data row written is imported, skipped with a reason, or inside a sheet listed as not
imported; (4) the summary's own words pass the forbidden-word check.

Files are built in a temporary folder and never committed. tests/test_ingest_variants.py runs
the whole set in `make check`.
