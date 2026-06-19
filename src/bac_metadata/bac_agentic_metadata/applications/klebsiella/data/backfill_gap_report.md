# Per-study date/source completeness gap vs metadata_v2 (train, val)

Total residual gap (samples v2 has & we don't): **collection_date 3742**, **isolation_source 5689**, over 21 studies with any gap.

Top gap studies (residual = v2 has a value and we don't):

| study | n | date gap | source gap | method-b | curator src tables | src date col | src source col | src accession |
|---|---|---|---|---|---|---|---|---|
| PRJEB42462 | 1278 | 1110 | 1167 | abstained | 3 | Y | · | Y |
| PRJEB28400 | 827 | 692 | 667 | abstained | 2 | Y | Y | Y |
| PRJEB29742 | 555 | 423 | 404 | abstained | 4 | Y | Y | Y |
| PRJEB6891 | 513 | 386 | 378 | abstained | 9 | Y | Y | Y |
| PRJNA845975 | 567 | 0 | 551 | abstained | 0 | · | · | · |
| PRJDB5929 | 631 | 1 | 523 | abstained | 1 | Y | Y | Y |
| PRJEB29143 | 498 | 496 | 0 | abstained | 1 | Y | Y | Y |
| PRJNA603790 | 462 | 0 | 445 | abstained | 0 | · | · | · |
| PRJEB33565 | 400 | 0 | 373 | abstained | 1 | · | Y | Y |
| PRJEB24082 | 200 | 163 | 158 | abstained | 1 | Y | Y | Y |
| PRJEB46513 | 281 | 0 | 258 | abstained | 1 | Y | Y | Y |
| PRJNA341927 | 244 | 0 | 243 | abstained | 1 | · | · | · |
| PRJEB36486 | 221 | 200 | 0 | abstained | 1 | · | · | Y |
| PRJEB24085 | 104 | 96 | 94 | abstained | 0 | · | · | · |
| PRJEB1563 | 198 | 0 | 170 | abstained | 1 | · | Y | Y |
| PRJNA804332 | 138 | 0 | 135 | abstained | 1 | · | Y | · |
| PRJEB12699 | 141 | 126 | 0 | abstained | 0 | · | · | · |
| PRJEB20799 | 46 | 37 | 37 | abstained | 1 | Y | Y | Y |
| PRJNA271899 | 258 | 1 | 66 | abstained | 1 | · | Y | Y |
| PRJEB27256 | 989 | 11 | 11 | no_outcome | 2 | · | Y | Y |
| PRJDB12075 | 184 | 0 | 9 | abstained | 0 | · | · | · |

- **src date/source col** = a curator source table has a date/source-like column; **src accession** = it carries an ENA accession (directly joinable) vs isolate-keyed only.
