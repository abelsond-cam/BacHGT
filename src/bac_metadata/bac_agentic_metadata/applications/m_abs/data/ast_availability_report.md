# M. abscessus — AST availability (scoping only)

**133 graded studies** across tags `mabs_top20, mabs_21_40, mabs_all`. Detection grades + a keyword scan of the read paper for the backbone panel. **No per-drug MIC / S-I-R value is parsed or integrated** — this decides whether a per-drug *paper*-extraction round is worth running.

Backbone panel (7): cefoxitin, amikacin, tigecycline, clarithromycin, linezolid, imipenem, tobramycin.

## 1. Detection grades

- **reports_AST** (paper reports phenotypic AST for ≥1 isolate): — 61, true 39, false 33
- **per_sample_AST** (per-isolate AST table obtainable): — 63, none 43, possible 17, retrievable 10
- studies with reports_AST = true: **39**; of those, per_sample_AST retrievable/possible: **27**

## 2. Backbone-drug mentions in the read papers

Whole-word, case-insensitive match of the full drug name in the cached full text (abbreviations are **not** matched — a floor, not a ceiling).

| drug | studies mentioning | among reports_AST=true | among per_sample follow-up |
|---|---|---|---|
| cefoxitin | 15 | 13 | 12 |
| amikacin | 27 | 20 | 18 |
| tigecycline | 7 | 6 | 6 |
| clarithromycin | 26 | 19 | 17 |
| linezolid | 14 | 13 | 12 |
| imipenem | 12 | 11 | 10 |
| tobramycin | 10 | 9 | 9 |

## 3. Priority studies for a possible per-drug round

| study | reports_AST | per_sample_AST | backbone drugs found | paper |
|---|---|---|---|---|
| PRJNA1177655 | true | retrievable | cefoxitin; amikacin; tigecycline; clarithromycin; linezolid; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12291787/) |
| PRJNA347845 | true | retrievable | cefoxitin; amikacin; clarithromycin; linezolid; imipenem; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6433289/) |
| PRJNA672126 | true | retrievable | cefoxitin; amikacin; clarithromycin; linezolid; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8280865/) |
| PRJNA523365 | true | retrievable | cefoxitin; amikacin; clarithromycin; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8390669/) |
| PRJNA566387 | true | retrievable | amikacin; tigecycline; linezolid; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC7778363/) |
| PRJNA1051626 | true | retrievable | amikacin; clarithromycin; linezolid | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC11619595/) |
| PRJNA65163 | true | retrievable | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA203564 | true | retrievable | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA1013065 | true | retrievable | cefoxitin; amikacin; imipenem *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC11620514/) |
| PRJNA65167 | true | retrievable | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA734660 | true | possible | cefoxitin; amikacin; tigecycline; clarithromycin; linezolid; imipenem; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8743566/) |
| PRJNA832057 | true | possible | cefoxitin; amikacin; tigecycline; clarithromycin; linezolid; imipenem; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC9430165/) |
| PRJEB1520 | true | possible | cefoxitin; amikacin; tigecycline; clarithromycin; linezolid; imipenem; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC3655965/) |
| PRJEB57933 | true | possible | cefoxitin; amikacin; clarithromycin; linezolid; imipenem; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC10606986/) |
| PRJEB39129 | true | possible | cefoxitin; amikacin; clarithromycin; linezolid; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8526041/) |
| PRJEB28875 | true | possible | cefoxitin; amikacin; clarithromycin; linezolid; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6821159/) |
| PRJNA756101 | true | possible | cefoxitin; amikacin; tigecycline; clarithromycin; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8535176/) |
| PRJNA323571 | true | possible | cefoxitin; amikacin; clarithromycin; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC5420552/) |
| PRJEB14002 | true | possible | amikacin; clarithromycin; tobramycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC3664974/) |
| PRJNA1209868 | true | possible | amikacin; clarithromycin; linezolid | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12057340/) |
| PRJDB10333 | true | possible | amikacin; clarithromycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC7910664/) |
| PRJDB12235 | true | possible | amikacin; clarithromycin | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC9241747/) |
| PRJNA1165220 | true | possible | clarithromycin *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12128065/) |
| PRJNA882917 | true | possible | amikacin; clarithromycin *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC10420398/) |
| PRJNA941035 | true | possible | clarithromycin *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12091025/) |
| PRJNA1080355 | true | possible | clarithromycin *(quote)* | [link](https://pubmed.ncbi.nlm.nih.gov/38810940/) |
| PRJEB38893 | true | possible | linezolid *(quote)* | [link](https://pubmed.ncbi.nlm.nih.gov/36802272/) |
| PRJNA865308 | true | none | cefoxitin; amikacin; clarithromycin; linezolid | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC10786304/) |
| PRJDB15290 | true | none | amikacin; clarithromycin; imipenem | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC11099050/) |
| PRJNA420644 | true | none | clarithromycin *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6325232/) |
| PRJEB9515 | true | none | clarithromycin *(quote)* | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6325232/) |
| PRJNA1211657 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4982176/) |
| PRJNA1169404 | true | — | amikacin; clarithromycin; linezolid *(quote)* | [link](https://doi.org/10.26502/fjhs.350) |
| PRJNA65171 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA65159 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA65165 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA65195 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJNA65211 | true | none | — | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4187745/) |
| PRJDB14511 | true | — | — | — |

## 4. Scan coverage & limitations

- full text scanned: **49/133** studies (quote-only: 26; no text: 58).
- Full drug-name match only; abbreviations (AMK, CLR, FOX…) and class terms are not counted.
- A mention is not a result: presence of a drug name ≠ a reported MIC/S-I-R for it. This report scopes availability; it does not extract values.

