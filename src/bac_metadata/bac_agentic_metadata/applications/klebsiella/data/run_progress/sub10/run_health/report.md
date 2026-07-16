# Run-health report (sub10 / sub10)

## ⚠️ **60 ACTIONABLE + 0 BLOCKED outstanding — supplement & rerun**

5008 (study × field) cells over 1252 studies — **FILLED 3402 · ACTIONABLE 60 · BLOCKED 0 · EXHAUSTED 1546**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 431/1252 studies have a resolvable paper (820 none-found) |
| Manual papers picked up & used | 0 study(ies) filled from a hand-added PDF |
| Meaningless values dropped (preclean) | **47** cells blanked pre-fill (isolation_source 47) so the agent can recover a real value |
| Per-sample added from supplementary tables | 0 study(ies), **0** fills from a per-isolate table (0 tables read) |
| Meaning of words improved (overwrites) | 0 — no deposited ENA value was overwritten (fidelity guard kept every one) |
| Escalation fired (close calls + big papers) | 0 decision(s) / 0 studies — close-call 0, big-decision 0, residual 0, sticky 0 |
| Extra manual tables requested | **none required** ✅ |

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 0 decision(s) queued |
| 2 | answer | answer / answer_note | 0 answered · 0 skip (0 auto) |
| 3 | apply | escalation_applied | 0 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 53 rows · 41 answered |
| 5 | fill | filled_metadata_provenance | 0 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch papers (35)

| study | fields short | already have (per-sample) | paper |
|---|---|---|---|
| PRJDB18280 | isolation_source | isolation_source:0,host:0,collection_date:0 | [In vitro activity of aztreonam in combination with relebacta](https://doi.org/10.1016/j.jgar.2025.02.008) |
| PRJDB5117 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Nosocomial transmission of carbapenem-resistant Klebsiella p](https://doi.org/10.1007/s15010-017-0986-3) |
| PRJDB9614 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic features of plasmids coding for KPC-2, NDM-5 or OXA-](https://doi.org/10.1093/jac/dkaa387) |
| PRJEB14232 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic sequence investigation Streptococcus pyogenes cluste](https://doi.org/10.1016/j.cmi.2018.04.011) |
| PRJEB2581 | collection_date,country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Identification of enterotoxigenic Escherichia coli (ETEC) cl](https://doi.org/10.1038/ng.3145) |
| PRJEB2968 | collection_date,country,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Global dissemination of a multidrug resistant Escherichia co](https://doi.org/10.1073/pnas.1322678111) |
| PRJEB32700 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [A link between the newly described colistin resistance gene ](https://doi.org/10.1016/j.jgar.2019.08.007) |
| PRJEB3353 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Rapid bacterial whole-genome sequencing to enhance diagnosti](https://doi.org/10.1001/jamainternmed.2013.7734) |
| PRJEB33694 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Phenotypic, biochemical and genetic analysis of KPC-41, a KP](https://doi.org/10.1128/aac.01111-19) |
| PRJEB41009 | collection_date,country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Distinguishing <i>bla</i><sub>KPC</sub> Gene-Containing IncF](https://doi.org/10.1128/aac.00147-21) |
| PRJNA1020811 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Do we still need Illumina sequencing data? Evaluating Oxford](https://doi.org/10.1139/cjm-2023-0175) |
| PRJNA1106484 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Community-associated Carbapenem-Resistant Organism Case Inve](https://doi.org/10.1093/ofid/ofaf622) |
| PRJNA184888 | collection_date,country,isolation_source | isolation_source:0,host:0,collection_date:0 | [A genomic day in the life of a clinical microbiology laborat](https://doi.org/10.1128/jcm.03237-12) |
| PRJNA187285 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187287 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187305 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187315 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA193165 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA198783 | host | isolation_source:0,host:0,collection_date:0 | [Single-molecule sequencing to track plasmid diversity of hos](https://doi.org/10.1126/scitranslmed.3009845) |
| PRJNA202047 | country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Carbapenem Resistance Caused by High-Level Expression of OXA](https://doi.org/10.1128/aac.01281-18) |
| PRJNA202895 | host | isolation_source:0,host:0,collection_date:0 | [Single-molecule sequencing to track plasmid diversity of hos](https://doi.org/10.1126/scitranslmed.3009845) |
| PRJNA279655 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Horizontal Transfer of Carbapenemase-Encoding Plasmids and C](https://doi.org/10.1128/aac.00014-16) |
| PRJNA279656 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Horizontal Transfer of Carbapenemase-Encoding Plasmids and C](https://doi.org/10.1128/aac.00014-16) |
| PRJNA542320 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Preventing dysbiosis of the neonatal mouse intestinal microb](https://doi.org/10.1038/s41591-019-0640-y) |
| PRJNA612645 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Proteomic Changes of Klebsiella pneumoniae in Response to Co](https://doi.org/10.1128/aac.02200-19) |
| PRJNA707347 | country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Core Antibiotic-Induced Transcriptional Signatures Reflect S](https://doi.org/10.1128/aac.02296-20) |
| PRJNA728680 | collection_date | isolation_source:0,host:0,collection_date:0 | [Fecal microbiota transplantation promotes reduction of antim](https://doi.org/10.1126/scitranslmed.abo2750) |
| PRJNA73843 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Tracking a hospital outbreak of carbapenem-resistant Klebsie](https://doi.org/10.1126/scitranslmed.3004129) |
| PRJNA746575 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Spread of hypervirulent multidrug-resistant ST147 Klebsiella](https://doi.org/10.1093/jac/dkab495) |
| PRJNA749600 | collection_date,country,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Functional attractors in microbial community assembly.](https://doi.org/10.1016/j.cels.2021.09.011) |
| PRJNA762607 | collection_date | isolation_source:0,host:0,collection_date:0 | [Pharmacodynamics of Piperacillin-Tazobactam/Amikacin Combina](https://doi.org/10.1128/aac.00162-22) |
| PRJNA786472 | collection_date | isolation_source:0,host:0,collection_date:0 | [Differences in antimicrobial susceptibility testing complica](https://doi.org/10.1016/j.jgar.2021.09.010) |
| PRJNA793828 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Enterobacterales high-risk clones and plasmids spreading bla](https://doi.org/10.1093/jac/dkac268) |
| PRJNA868191 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Antibiotic resistance and virulence characteristics of four ](https://doi.org/10.1016/j.micpath.2023.105969) |
| PRJNA981541 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Real-time genomic epidemiologic investigation of a multispec](https://doi.org/10.1016/j.ijid.2024.02.014) |

## No paper could be found — validated, won't be recovered
590 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB10890, PRJDB11111, PRJDB11476, PRJDB11627, PRJDB11634, PRJDB12737, PRJDB1836, PRJDB2133, PRJDB2159, PRJDB2238, PRJDB2655, PRJDB4694, PRJDB5948, PRJDB7330, PRJDB9124, PRJEB10263, PRJEB11503, PRJEB12145, PRJEB12887, PRJEB13482, PRJEB14648, PRJEB15430, PRJEB17631, PRJEB18525, PRJEB19657, PRJEB20557, PRJEB20997, PRJEB21131, PRJEB21201, PRJEB21566, PRJEB21765, PRJEB23879, PRJEB25425, PRJEB25904, PRJEB26081, PRJEB27400, PRJEB29743, PRJEB30066, PRJEB3184, PRJEB32059, PRJEB32402, PRJEB33365, PRJEB34174, PRJEB34232, PRJEB35084, PRJEB36448, PRJEB38602, PRJEB38951, PRJEB38960, PRJEB39709, PRJEB39816, PRJEB41279, PRJEB43940, PRJEB43975, PRJEB44490, PRJEB4649, PRJEB50806, PRJEB54871, PRJEB58069, PRJEB60446, PRJEB61017, PRJEB6416, PRJEB66292, PRJEB6657, PRJEB6921, PRJEB70870, PRJEB74142, PRJEB75744, PRJEB7689, PRJEB76944, PRJEB8302, PRJEB8303, PRJEB8721, PRJEB8768, PRJEB9173, PRJEB9644, PRJEB9824, PRJNA1003529, PRJNA1021015, PRJNA1029537, PRJNA1029809, PRJNA1031676, PRJNA1037605, PRJNA1037744, PRJNA1040118, PRJNA1044623, PRJNA1058963, PRJNA1066419, PRJNA1067287, PRJNA1075815, PRJNA1088746, PRJNA1099652, PRJNA1100205, PRJNA1101017, PRJNA1101420, PRJNA1122522, PRJNA1123194, PRJNA1134078, PRJNA1138264, PRJNA161277, PRJNA164933, PRJNA165913, PRJNA168337, PRJNA169453, PRJNA169454, PRJNA169455, PRJNA169456, PRJNA181050, PRJNA181051, PRJNA181052, PRJNA187279, PRJNA187280, PRJNA187281, PRJNA187283, PRJNA187284, PRJNA187286, PRJNA187288, PRJNA187289, PRJNA187290, PRJNA187291, PRJNA187292, PRJNA187293, PRJNA187294, PRJNA187295, PRJNA187296, PRJNA187297, PRJNA187298, PRJNA187299, PRJNA187300, PRJNA187301, PRJNA187302, PRJNA187303, PRJNA187304, PRJNA187306, PRJNA187307, PRJNA187308, PRJNA187309, PRJNA187310, PRJNA187311, PRJNA187312, PRJNA187313, PRJNA187314, PRJNA187316, PRJNA187317, PRJNA187318, PRJNA187319, PRJNA187320, PRJNA187321, PRJNA187322, PRJNA187323, PRJNA187324, PRJNA187325, PRJNA187326, PRJNA193160, PRJNA193161, PRJNA193162, PRJNA193163, PRJNA193164, PRJNA193167, PRJNA193168, PRJNA193169, PRJNA195754, PRJNA197002, PRJNA201932, PRJNA201933, PRJNA201934, PRJNA201935, PRJNA201936, PRJNA201942, PRJNA201943, PRJNA201944, PRJNA201945, PRJNA201946, PRJNA201947, PRJNA201950, PRJNA201951, PRJNA201955, PRJNA201956, PRJNA201957, PRJNA201958,PRJNA201967, PRJNA201959, PRJNA201960, PRJNA201961, PRJNA201962, PRJNA201963, PRJNA201964, PRJNA201965, PRJNA201966, PRJNA201967,PRJNA201954, PRJNA201968, PRJNA201970, PRJNA201974, PRJNA201978, PRJNA201981, PRJNA201984, PRJNA201985, PRJNA201987, PRJNA201989, PRJNA201990, PRJNA201991, PRJNA201994, PRJNA201999, PRJNA202000, PRJNA202001, PRJNA202002, PRJNA202005, PRJNA202006, PRJNA202008, PRJNA202009, PRJNA202012, PRJNA202013, PRJNA202014, PRJNA202015, PRJNA202016, PRJNA202017, PRJNA202018, PRJNA202020, PRJNA202023, PRJNA202024, PRJNA202025, PRJNA202026, PRJNA202032, PRJNA202033, PRJNA202034, PRJNA202035, PRJNA202036, PRJNA202042, PRJNA202043, PRJNA202045, PRJNA202046, PRJNA202048, PRJNA202052, PRJNA202053, PRJNA212643, PRJNA212649, PRJNA213341, PRJNA219247, PRJNA219248, PRJNA219252, PRJNA219253, PRJNA219254, PRJNA219255, PRJNA219259, PRJNA219260, PRJNA219261, PRJNA219262, PRJNA219265, PRJNA219266, PRJNA219267, PRJNA219268, PRJNA219269, PRJNA219270, PRJNA219271, PRJNA219272, PRJNA219275, PRJNA219276, PRJNA219277, PRJNA219278, PRJNA219283, PRJNA219284, PRJNA219287, PRJNA219289, PRJNA219292, PRJNA219293, PRJNA219294, PRJNA219295, PRJNA219296, PRJNA219297, PRJNA219298, PRJNA219299, PRJNA219300, PRJNA223655, PRJNA230968, PRJNA233696, PRJNA233724, PRJNA234107, PRJNA234108, PRJNA234109, PRJNA234110, PRJNA234111, PRJNA234112, PRJNA234113, PRJNA234114, PRJNA234115, PRJNA234116, PRJNA234117,PRJNA201967, PRJNA234118, PRJNA234119, PRJNA234120, PRJNA234122, PRJNA234123, PRJNA234128, PRJNA234129, PRJNA234132, PRJNA234134, PRJNA234135, PRJNA234136, PRJNA234137, PRJNA234140, PRJNA234141, PRJNA234142, PRJNA234143, PRJNA234144, PRJNA234148, PRJNA234149, PRJNA234157, PRJNA234168, PRJNA234169, PRJNA234170, PRJNA234171, PRJNA234172, PRJNA234173, PRJNA234174, PRJNA234175, PRJNA234176, PRJNA234177, PRJNA234178, PRJNA234179, PRJNA234180, PRJNA234181, PRJNA234182, PRJNA234183, PRJNA234184, PRJNA234185, PRJNA234186, PRJNA234187, PRJNA234188, PRJNA234189, PRJNA234190, PRJNA234191, PRJNA234192, PRJNA234193, PRJNA234194, PRJNA234195, PRJNA234196, PRJNA234197, PRJNA234198, PRJNA234199, PRJNA234200, PRJNA234201, PRJNA234202, PRJNA234203, PRJNA234204, PRJNA234205, PRJNA234206, PRJNA234207, PRJNA234208, PRJNA234209, PRJNA234210, PRJNA234211, PRJNA234212, PRJNA234213, PRJNA234215, PRJNA234216, PRJNA234217, PRJNA234218, PRJNA234219, PRJNA234220, PRJNA234221, PRJNA234222, PRJNA234223, PRJNA234224, PRJNA234225, PRJNA234226, PRJNA234227, PRJNA234228, PRJNA234229, PRJNA234230, PRJNA234231, PRJNA234232, PRJNA234233, PRJNA234234, PRJNA234235, PRJNA234236, PRJNA234239, PRJNA234240, PRJNA234241, PRJNA234242, PRJNA234243, PRJNA234244, PRJNA234245, PRJNA234249, PRJNA234250, PRJNA234251, PRJNA234258, PRJNA234259, PRJNA234260, PRJNA234261, PRJNA234262, PRJNA234263, PRJNA234264, PRJNA234265, PRJNA243331, PRJNA244068, PRJNA244547, PRJNA244567, PRJNA263062, PRJNA265231, PRJNA265232, PRJNA265233, PRJNA265234, PRJNA265235, PRJNA265236, PRJNA265237, PRJNA265240, PRJNA265241, PRJNA265242, PRJNA265243, PRJNA265244, PRJNA265245, PRJNA265246, PRJNA265247, PRJNA265248, PRJNA265254, PRJNA265255, PRJNA265256, PRJNA265257, PRJNA265258, PRJNA265259, PRJNA265260, PRJNA265261, PRJNA265262, PRJNA265263, PRJNA265264, PRJNA265265, PRJNA265266, PRJNA265267, PRJNA265268, PRJNA265269, PRJNA265270, PRJNA265275, PRJNA265347, PRJNA269826, PRJNA269833, PRJNA269877, PRJNA269879, PRJNA269915, PRJNA272089, PRJNA275974, PRJNA279650, PRJNA279657, PRJNA279669, PRJNA292403, PRJNA293225, PRJNA296147, PRJNA303003, PRJNA312972, PRJNA316321, PRJNA318591, PRJNA344449, PRJNA350242, PRJNA353361, PRJNA354234, PRJNA360179, PRJNA391510, PRJNA393721, PRJNA40025, PRJNA40049, PRJNA429995, PRJNA450215, PRJNA456216, PRJNA456219, PRJNA463112, PRJNA47211,PRJNA47257,PRJNA47225,PRJNA47209,PRJNA47275,PRJNA47263,PRJNA47223,PRJNA47217,PRJNA47267,PRJNA47259,PRJNA47271,PRJNA47229, PRJNA480281, PRJNA481356, PRJNA482007, PRJNA485367, PRJNA491527, PRJNA493667, PRJNA499494, PRJNA500331, PRJNA501401, PRJNA501405, PRJNA501406, PRJNA501409, PRJNA501412, PRJNA503785, PRJNA508495, PRJNA508509, PRJNA512885, PRJNA513350, PRJNA516562, PRJNA52135, PRJNA52137, PRJNA52139, PRJNA52141, PRJNA52143, PRJNA52145, PRJNA52151, PRJNA52153, PRJNA523427, PRJNA523730, PRJNA523732, PRJNA528367, PRJNA530250, PRJNA531724, PRJNA543187, PRJNA544642, PRJNA547184, PRJNA549563, PRJNA552311, PRJNA555823, PRJNA561052, PRJNA593956, PRJNA601835, PRJNA604394, PRJNA607307, PRJNA610191, PRJNA612869, PRJNA613320, PRJNA613629, PRJNA614986, PRJNA628847, PRJNA631981, PRJNA634081, PRJNA641130, PRJNA641131, PRJNA642369, PRJNA646204, PRJNA647060, PRJNA655785, PRJNA660205, PRJNA673369, PRJNA680857, PRJNA681360, PRJNA687988, PRJNA689691, PRJNA690982, PRJNA716436, PRJNA719009, PRJNA721588, PRJNA731002, PRJNA736853, PRJNA739632, PRJNA739637, PRJNA739732, PRJNA754800, PRJNA754801, PRJNA754802, PRJNA754804, PRJNA754806, PRJNA754809, PRJNA754810, PRJNA754811, PRJNA754812, PRJNA754813, PRJNA754819, PRJNA754822, PRJNA754824, PRJNA754827, PRJNA754831, PRJNA754832, PRJNA756309, PRJNA760944, PRJNA763348, PRJNA773853, PRJNA774259, PRJNA78565, PRJNA78567, PRJNA793126, PRJNA803341, PRJNA807502, PRJNA809128, PRJNA811351, PRJNA811370, PRJNA824073, PRJNA824074, PRJNA825843, PRJNA839526, PRJNA853708, PRJNA855340, PRJNA861272, PRJNA861987, PRJNA872534, PRJNA886974, PRJNA887375, PRJNA896194, PRJNA930879, PRJNA931810, PRJNA942340, PRJNA946148, PRJNA947381, PRJNA966930, PRJNA970235, PRJNA981489, PRJNA983061, PRJNA985548, PRJNA985853, PRJNA986296

## Escalation status
- queue generated: 0 rows; answered: 0; applied fills: 0.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 1363
- abstained_other: 243


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ⛔ INCOMPLETE

⛔ **35 studies have a real paper but NO usable full text** — download each to `find_papers/manual_download/<acc>.pdf`, then rerun:

| study | paper |
|---|---|
| PRJDB18280 | [In vitro activity of aztreonam in combination with relebacta](https://doi.org/10.1016/j.jgar.2025.02.008) |
| PRJDB5117 | [Nosocomial transmission of carbapenem-resistant Klebsiella p](https://doi.org/10.1007/s15010-017-0986-3) |
| PRJDB9614 | [Genomic features of plasmids coding for KPC-2, NDM-5 or OXA-](https://doi.org/10.1093/jac/dkaa387) |
| PRJEB14232 | [Genomic sequence investigation Streptococcus pyogenes cluste](https://doi.org/10.1016/j.cmi.2018.04.011) |
| PRJEB2581 | [Identification of enterotoxigenic Escherichia coli (ETEC) cl](https://doi.org/10.1038/ng.3145) |
| PRJEB2968 | [Global dissemination of a multidrug resistant Escherichia co](https://doi.org/10.1073/pnas.1322678111) |
| PRJEB32700 | [A link between the newly described colistin resistance gene ](https://doi.org/10.1016/j.jgar.2019.08.007) |
| PRJEB3353 | [Rapid bacterial whole-genome sequencing to enhance diagnosti](https://doi.org/10.1001/jamainternmed.2013.7734) |
| PRJEB33694 | [Phenotypic, biochemical and genetic analysis of KPC-41, a KP](https://doi.org/10.1128/aac.01111-19) |
| PRJEB41009 | [Distinguishing <i>bla</i><sub>KPC</sub> Gene-Containing IncF](https://doi.org/10.1128/aac.00147-21) |
| PRJNA1020811 | [Do we still need Illumina sequencing data? Evaluating Oxford](https://doi.org/10.1139/cjm-2023-0175) |
| PRJNA1106484 | [Community-associated Carbapenem-Resistant Organism Case Inve](https://doi.org/10.1093/ofid/ofaf622) |
| PRJNA184888 | [A genomic day in the life of a clinical microbiology laborat](https://doi.org/10.1128/jcm.03237-12) |
| PRJNA187285 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187287 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187305 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA187315 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA193165 | [Population structure of KPC-producing Klebsiella pneumoniae ](https://doi.org/10.1128/aac.00125-14) |
| PRJNA198783 | [Single-molecule sequencing to track plasmid diversity of hos](https://doi.org/10.1126/scitranslmed.3009845) |
| PRJNA202047 | [Carbapenem Resistance Caused by High-Level Expression of OXA](https://doi.org/10.1128/aac.01281-18) |
| PRJNA202895 | [Single-molecule sequencing to track plasmid diversity of hos](https://doi.org/10.1126/scitranslmed.3009845) |
| PRJNA279655 | [Horizontal Transfer of Carbapenemase-Encoding Plasmids and C](https://doi.org/10.1128/aac.00014-16) |
| PRJNA279656 | [Horizontal Transfer of Carbapenemase-Encoding Plasmids and C](https://doi.org/10.1128/aac.00014-16) |
| PRJNA542320 | [Preventing dysbiosis of the neonatal mouse intestinal microb](https://doi.org/10.1038/s41591-019-0640-y) |
| PRJNA612645 | [Proteomic Changes of Klebsiella pneumoniae in Response to Co](https://doi.org/10.1128/aac.02200-19) |
| PRJNA707347 | [Core Antibiotic-Induced Transcriptional Signatures Reflect S](https://doi.org/10.1128/aac.02296-20) |
| PRJNA728680 | [Fecal microbiota transplantation promotes reduction of antim](https://doi.org/10.1126/scitranslmed.abo2750) |
| PRJNA73843 | [Tracking a hospital outbreak of carbapenem-resistant Klebsie](https://doi.org/10.1126/scitranslmed.3004129) |
| PRJNA746575 | [Spread of hypervirulent multidrug-resistant ST147 Klebsiella](https://doi.org/10.1093/jac/dkab495) |
| PRJNA749600 | [Functional attractors in microbial community assembly.](https://doi.org/10.1016/j.cels.2021.09.011) |
| PRJNA762607 | [Pharmacodynamics of Piperacillin-Tazobactam/Amikacin Combina](https://doi.org/10.1128/aac.00162-22) |
| PRJNA786472 | [Differences in antimicrobial susceptibility testing complica](https://doi.org/10.1016/j.jgar.2021.09.010) |
| PRJNA793828 | [Enterobacterales high-risk clones and plasmids spreading bla](https://doi.org/10.1093/jac/dkac268) |
| PRJNA868191 | [Antibiotic resistance and virulence characteristics of four ](https://doi.org/10.1016/j.micpath.2023.105969) |
| PRJNA981541 | [Real-time genomic epidemiologic investigation of a multispec](https://doi.org/10.1016/j.ijid.2024.02.014) |

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/sub10/escalation/decisions_needed.tsv`: **0 generated · 0 answered · 0 PENDING** (0 fills applied).

✅ No tight-grading escalations were raised.

# → ⛔ CURATOR ACTION OUTSTANDING — 35 paper(s) to add, 0 escalation(s) to answer

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 0 answered decision(s) → 0 applied (study×field), 0 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 53 ⊇ HEAD 53 rows; 0 committed decisions dropped.
- **INV3 fill** — 0 escalation fill(s) → 0 non-blank in filled_metadata_sub10. 0 lost to a blank final cell.
