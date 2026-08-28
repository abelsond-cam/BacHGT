# cf_status review register

## A. Whole-project cf calls (applied to blank cells; known values never overwritten)

**non-CF first** — scrutinise the *non-CF-by-absence* inference: the argument must describe the patient cohort (ages/comorbidities) AND note no CF mention. Flag any weak argument to revert.

| tag | study | proposed | blanks filled | argument (agent's basis) |
|---|---|---|---|---|
| mabs_top20 | PRJDB10566 | **non-CF** | 217 | Molecular Epidemiological Characteristics of Mycobacterium abscessus Complex Derived from Non-Cystic Fibrosis Patients in Japan and Taiwan... our sample set did not include clinical isolates derived from patients with CF in Japan and Taiwan |
| mabs_top20 | PRJNA734660 | **non-CF** | 203 | Only two isolates were from patients with cystic fibrosis. |
| mabs_top20 | PRJDB10333 | **non-CF** | 148 | A total of 147 MABC clinical isolates and one environmental isolate obtained for differential diagnosis at 20 hospitals in Japan were considered. Of the clinical isolates, 138 originated in the respiratory system, 8 were isolated from skin lesions, and 1 strain was isolated from  |
| mabs_top20 | PRJEB7058 | **non-CF** | 0 | The 188 sequenced isolates are from post-surgical skin and soft tissue wound infections in Brazilian patients (video-assisted surgeries). The paper fully characterises its patient cohort clinically but never mentions cystic fibrosis for the Brazilian cases. CF is referenced only  |
| mabs_top20 | PRJNA319839 | **CF** | 423 | WGS was performed on 558 M. abscessus isolates from 266 patients with CF attending 48 CF Care Centers in 28 U.S. states as part of a nationwide surveillance program. |
| mabs_top20 | PRJEB14002 | **CF** | 162 | whole genome sequencing on 168 consecutive isolates from 31 infected patients attending the Cambridge Centre for Lung Infection at Papworth Hospital, UK, a large adult cystic fibrosis centre... acquisition of this NTM by cystic fibrosis patients is frequently through cross-infect |
| mabs_top20 | PRJEB44160 | **CF** | 122 | EBI study title: 'WGS of M. abscessus strains from german CF patients'; ENA has 122 samples closely matching 123 CF patients described in the paper; the 14 non-CF control isolates appear not deposited under this accession or are a negligible minority. |
| mabs_top20 | PRJEB39129 | **CF** | 86 | Mycobacterium abscessus was isolated from patients with Cystic Fibrosis in a treatment center in Germany. The genomes of 87 M. abscessus isolates from serial samples from 11 patients were compared to describe relationship between strains. |
| mabs_top20 | PRJNA1119444 | **CF** | 68 | we collected isolates from 26 MAB-positive pwCF over a three-year period from a previous uninvestigated population of MAB colonized individuals at the CF@tlanta Cystic Fibrosis centers |

9 whole-project calls (4 non-CF, 5 CF).

## B. Big studies (>= 1% of the cohort) — cf composition + decision, ALWAYS reviewed

The large studies drive the phenotype and have caused problems before (PRJEB2779). Check each cf split + how it was decided, regardless of whether it carried a whole-project call.

| tag | study | n | CF | non-CF | blank | other | decision | argument |
|---|---|---|---|---|---|---|---|---|
| mabs_top20 | PRJEB2779 | 2143 | 824 | 115 | 1201 | 3 | curator-skip (answer=''; curator skip: 88% CF (<95% whole-project rule) — genuinely wide, leave cf blank) | Lung infections with Mycobacterium abscessus...are emerging as an important global threat to individuals with cystic fibrosis (CF)...1080 clinical isolates of M. abscessus from 517 |
| mabs_top20 | PRJNA319839 | 619 | 619 | 0 | 0 | 0 | whole-project CF | WGS was performed on 558 M. abscessus isolates from 266 patients with CF attending 48 CF Care Centers in 28 U.S. states as part of a nationwide surveillance program. |
| mabs_top20 | PRJNA1036625 | 219 | 0 | 0 | 219 | 0 | known-only (no whole-project fill) | With respect to CF status, 48.6% (n = 34/70) had CF. |
| mabs_top20 | PRJDB10566 | 217 | 0 | 217 | 0 | 0 | whole-project non-CF | Molecular Epidemiological Characteristics of Mycobacterium abscessus Complex Derived from Non-Cystic Fibrosis Patients in Japan and Taiwan... our sample set did not include clinica |
| mabs_top20 | PRJNA734660 | 203 | 0 | 203 | 0 | 0 | whole-project non-CF | Only two isolates were from patients with cystic fibrosis. |
| mabs_top20 | PRJEB7058 | 189 | 0 | 189 | 0 | 0 | whole-project non-CF | The 188 sequenced isolates are from post-surgical skin and soft tissue wound infections in Brazilian patients (video-assisted surgeries). The paper fully characterises its patient  |
| mabs_top20 | PRJNA1165220 | 182 | 0 | 0 | 182 | 0 | known-only (no whole-project fill) | MAB is responsible for an increasing number of severe pulmonary and extrapulmonary infections, especially in patients with cystic fibrosis. |
| mabs_top20 | PRJNA778024 | 175 | 0 | 0 | 175 | 0 | known-only (no whole-project fill) | 27 adult patients with CF receiving routine clinical care... We included a convenience sample of isolates from seven non-CF patients obtained between 2013 and 2018 |
| mabs_top20 | PRJNA882917 | 175 | 0 | 0 | 175 | 0 | known-only (no whole-project fill) | MABC disproportionately colonize and infect the lungs of individuals with cystic fibrosis (CF)... The patient was on azithromycin therapy for CF at earlier time points (MAB_18_01 t |
| mabs_top20 | PRJEB14002 | 162 | 162 | 0 | 0 | 0 | whole-project CF | whole genome sequencing on 168 consecutive isolates from 31 infected patients attending the Cambridge Centre for Lung Infection at Papworth Hospital, UK, a large adult cystic fibro |
| mabs_top20 | PRJNA989271 | 153 | 0 | 0 | 153 | 0 | known-only (no whole-project fill) | Molecular Epidemiology of Mycobacterium abscessus complex in Cystic Fibrosis and Non-Cystic Fibrosis patients in New South Wales |
| mabs_top20 | PRJDB10333 | 148 | 0 | 148 | 0 | 0 | whole-project non-CF | A total of 147 MABC clinical isolates and one environmental isolate obtained for differential diagnosis at 20 hospitals in Japan were considered. Of the clinical isolates, 138 orig |
| mabs_top20 | PRJEB31559 | 145 | 111 | 31 | 3 | 0 | known-only (no whole-project fill) | Table 1 lists Underlying Condition as 'Cystic fibrosis' for 41/62 patients (all GOSH CF patients plus bcn_hvh_030–040 and bcn_hcl_002); remaining 21 patients have bronchiectasis, N |
| mabs_top20 | PRJEB44160 | 122 | 122 | 0 | 0 | 0 | whole-project CF | EBI study title: 'WGS of M. abscessus strains from german CF patients'; ENA has 122 samples closely matching 123 CF patients described in the paper; the 14 non-CF control isolates  |
| mabs_top20 | PRJNA401515 | 118 | 0 | 0 | 118 | 0 | known-only (no whole-project fill) |  |
| mabs_top20 | PRJEB39129 | 86 | 86 | 0 | 0 | 0 | whole-project CF | Mycobacterium abscessus was isolated from patients with Cystic Fibrosis in a treatment center in Germany. The genomes of 87 M. abscessus isolates from serial samples from 11 patien |
| mabs_top20 | PRJNA420644 | 85 | 0 | 0 | 85 | 0 | known-only (no whole-project fill) | M. abscessus poses a significant problem, particularly in patients with cystic fibrosis (CF)... no prior selection according to the site of isolation or whether M. abscessus comple |
| mabs_top20 | PRJNA1119444 | 68 | 68 | 0 | 0 | 0 | whole-project CF | we collected isolates from 26 MAB-positive pwCF over a three-year period from a previous uninvestigated population of MAB colonized individuals at the CF@tlanta Cystic Fibrosis cen |
| mabs_top20 | PRJEB37730 | 67 | 49 | 15 | 3 | 0 | known-only (no whole-project fill) | The MABC isolates comprised 52 isolates from 27 CF patients and 18 isolates from 10 non-CF patients. |
