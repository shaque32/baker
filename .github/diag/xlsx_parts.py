"""Temporary diagnostic: regenerate case01 into a temp dir and print each xlsx part's SHA-256."""
import hashlib, sys, tempfile, zipfile
from pathlib import Path
from eval.synthetic.generate import generate

out = Path(tempfile.mkdtemp())
generate(out, None)
for x in sorted(out.glob("*.xlsx")):
    print(x.name, hashlib.sha256(x.read_bytes()).hexdigest())
    with zipfile.ZipFile(x) as z:
        for i in z.infolist():
            data = z.read(i)
            print("  ", i.filename, i.date_time, len(data), hashlib.sha256(data).hexdigest()[:16])
for f in sorted(out.iterdir()):
    if f.suffix != ".xlsx":
        b = f.read_bytes()
        print(f.name, len(b), b.count(b"\r\n"), hashlib.sha256(b).hexdigest()[:16])
