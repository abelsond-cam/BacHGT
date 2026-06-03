import pdfplumber # Install with pip install pdfplumber
import csv  #built-in module for CSV files
import re  #built-in module for regular expressions
from pathlib import Path  #built-in module for pathlib

pdf_path = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata/"
    "study_level_metadata/ENA_projects/PRJEB29143/supplement_revision.pdf"
)
out_path = pdf_path.with_suffix(".csv")

headers = ["Isolate","Species","Phylo-group","ST","Country","Site","Isolation year","Accession Number"]
rows = []

def is_isolate(tok):
    return tok.startswith("SB") and tok[2:].isdigit()

def is_phylo(tok):
    return tok in {"Kp1","Kp2","Kp3","Kp4","Kp5"}

def is_accession(tok):
    return tok.startswith(("ERS","ERR","SRR"))

with pdfplumber.open(pdf_path) as pdf:
    tokens = []
    for page in pdf.pages:
        t = page.extract_text()
        if not t:
            continue
        tokens.extend(t.split())

i = 0
while i < len(tokens):
    if not is_isolate(tokens[i]):
        i += 1
        continue

    isolate = tokens[i]
    i += 1

    # Species: up to phylo-group
    species_tokens = []
    while i < len(tokens) and not is_phylo(tokens[i]):
        species_tokens.append(tokens[i])
        i += 1
    if i >= len(tokens):
        break
    phylo = tokens[i]; i += 1

    if i >= len(tokens):
        break
    st = tokens[i]; i += 1

    if i + 2 > len(tokens):
        break
    country = tokens[i]; site = tokens[i+1]; i += 2

    if i >= len(tokens):
        break
    isolation_year = tokens[i]; i += 1

    # Scan forward until next isolate; keep last accession-like token
    acc = ""
    j = i
    while j < len(tokens) and not is_isolate(tokens[j]):
        if is_accession(tokens[j]):
            acc = tokens[j]
        j += 1

    species = " ".join(species_tokens)
    rows.append([isolate, species, phylo, st, country, site, isolation_year, acc])

    i = j  # move to next isolate

# Write CSV
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(headers)
    w.writerows(rows)

print(f"Wrote {len(rows)} rows to {out_path}")
