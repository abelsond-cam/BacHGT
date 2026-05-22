import re
import pandas as pd
from dateutil.parser import parse
from dateutil.parser._parser import ParserError


def normalize_date_str(val):
    """Normalize raw collection_date values for consistent matching."""
    if isinstance(val, (pd.Series, pd.Index, list, tuple)):
        if len(val) == 0:
            return None
        val = next(iter(val))
    try:
        if pd.isna(val):
            return None
    except TypeError:
        pass
    s = str(val).strip()
    if s.lower() in {"nan", "none"}:
        return None
    # Normalize dash/slash variants to simplify matching
    s = re.sub(r"[–—−]", "-", s)  # en dash, em dash, minus to hyphen
    s = re.sub(r"[／]", "/", s)    # fullwidth slash to slash
    # Collapse repeated whitespace
    s = re.sub(r"\s+", " ", s)
    # Convert floats that are really integers (e.g., 2023.0)
    float_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)", s)
    if float_match:
        try:
            num = float(float_match.group(1))
            if num.is_integer():
                s = str(int(num))
        except ValueError:
            pass
    return s


def step0_clean(df):
    """Step 0 cleaning: replace known non-date strings and report counts."""
    not_collected_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['not collected', 'notcollected'])
    not_provided_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['not provided', 'notprovided'])
    not_applicable_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['not applicable', 'notapplicable'])
    not_available_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['not available', 'notavailable'])
    missing_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['missing', 'missing'])
    not_determined_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['not determined', 'notdetermined'])
    unknown_mask = df['collection_date'].astype(str).str.lower().str.strip().isin(['unknown'])

    not_collected_count = not_collected_mask.sum()
    not_provided_count = not_provided_mask.sum()
    not_applicable_count = not_applicable_mask.sum()
    not_available_count = not_available_mask.sum()
    missing_count = missing_mask.sum()
    not_determined_count = not_determined_mask.sum()
    unknown_count = unknown_mask.sum()

    df.loc[not_collected_mask, 'collection_date'] = None
    df.loc[not_provided_mask, 'collection_date'] = None
    df.loc[not_applicable_mask, 'collection_date'] = None
    df.loc[not_available_mask, 'collection_date'] = None
    df.loc[missing_mask, 'collection_date'] = None
    df.loc[not_determined_mask, 'collection_date'] = None
    df.loc[unknown_mask, 'collection_date'] = None

    print(f"  Replaced 'not collected' with None: {not_collected_count} values")
    print(f"  Replaced 'not provided' with None: {not_provided_count} values")
    print(f"  Replaced 'not applicable' with None: {not_applicable_count} values")
    print(f"  Replaced 'not available' with None: {not_available_count} values")
    print(f"  Replaced 'missing' with None: {missing_count} values")
    print(f"  Replaced 'not determined' with None: {not_determined_count} values")
    print(f"  Replaced 'unknown' with None: {unknown_count} values")

    # Step 0.2: Identify and remove strings with no integers
    non_null_mask = df['collection_date'].notna()
    strings_without_digits = []
    strings_without_digits_counts = {}

    for idx in df[non_null_mask].index:
        date_val = str(df.at[idx, 'collection_date']).strip()
        # Check if string contains any digit
        if not re.search(r'\d', date_val):
            strings_without_digits.append(date_val)
            if date_val in strings_without_digits_counts:
                strings_without_digits_counts[date_val] += 1
            else:
                strings_without_digits_counts[date_val] = 1
            df.at[idx, 'collection_date'] = None

    no_digits_count = len(strings_without_digits)
    print(f"  Replaced strings with no integers with None: {no_digits_count} values")

    if strings_without_digits_counts:
        print("  Unique values removed (with counts):")
        sorted_items = sorted(strings_without_digits_counts.items(), key=lambda x: (-x[1], x[0]))
        for val, count in sorted_items[:20]:  # Show top 20
            print(f"    - '{val}': {count}")
        if len(sorted_items) > 20:
            print(f"    ... and {len(sorted_items) - 20} more unique values")


def parse_with_pandas_and_dateutil(df, stage_label):
    """Pandas then dateutil parsing with reporting."""
    print("\n" + "-"*60)
    print(stage_label)
    print("-"*60)

    # pandas parsing
    try:
        parsed_dates_pandas = pd.to_datetime(df['collection_date'], errors='coerce', format='mixed', utc=True)
    except (TypeError, ValueError):
        parsed_dates_pandas = pd.to_datetime(df['collection_date'], errors='coerce', utc=True)

    if not pd.api.types.is_datetime64_any_dtype(parsed_dates_pandas):
        parsed_dates_pandas = pd.to_datetime(parsed_dates_pandas, errors='coerce')

    pandas_success_mask = parsed_dates_pandas.notna()
    pandas_success_count = pandas_success_mask.sum()

    if pandas_success_count > 0:
        years_all = parsed_dates_pandas.dt.year
        formatted_dates_all = parsed_dates_pandas.dt.strftime('%Y/%m/%d')
        df.loc[pandas_success_mask, 'year_parsed'] = years_all.loc[pandas_success_mask].astype('Int64')
        df.loc[pandas_success_mask, 'collection_date_parsed'] = formatted_dates_all.loc[pandas_success_mask]

    # dateutil fallback
    failed_mask = ~pandas_success_mask
    failed_and_not_null = failed_mask & df['collection_date'].notna()
    dateutil_success_count = 0
    if failed_and_not_null.any():
        for idx in df[failed_and_not_null].index:
            try:
                date_str = str(df.at[idx, 'collection_date'])
                parsed_date = parse(date_str, fuzzy=True)
                df.at[idx, 'year_parsed'] = parsed_date.year
                df.at[idx, 'collection_date_parsed'] = parsed_date.strftime('%Y/%m/%d')
                dateutil_success_count += 1
            except (ParserError, ValueError, TypeError, KeyError):
                pass

    total_parsed = df['collection_date_parsed'].notna().sum()
    total_unparsed = (df['collection_date'].notna() & df['collection_date_parsed'].isna()).sum()

    print(f"  Parsed by pandas: {pandas_success_count}")
    print(f"  Parsed by dateutil: {dateutil_success_count}")
    print(f"  Total parsed this stage: {total_parsed}")
    print(f"  Still unparseable: {total_unparsed}")

    return {
        "pandas": pandas_success_count,
        "dateutil": dateutil_success_count,
        "total_parsed": total_parsed,
        "unparsed": total_unparsed,
    }


def apply_targeted_fixes(df):
    """Step 2 targeted fixes with mini reports and debug output."""
    def mini_report(label, changed):
        filled = df['collection_date_parsed'].notna().sum()
        missing = df['collection_date_parsed'].isna().sum()
        print(f"  {label}: {changed} rows updated")
        print(f"    collection_date_parsed filled: {filled}, missing: {missing}")

    # Work only on rows still unparsable after initial parsing
    unparsable_mask_stage2 = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())

    # 2.a Year ranges like 2015-17 -> midpoint year
    year_range_count = 0
    for idx in df[unparsable_mask_stage2].index:
        val = normalize_date_str(df.at[idx, 'collection_date'])
        if not val:
            continue
        # Specific hard-code: 2015-17 -> 2016/06/30
        val_compact = val.replace(" ", "")
        if val_compact in {"2015-17", "2015/17"} or re.search(r"\b2015[-/]?17\b", val):
            df.at[idx, 'collection_date_parsed'] = "2016/06/30"
            df.at[idx, 'year_parsed'] = 2016
            year_range_count += 1
            continue
        m = re.match(r'^(20\d{2})[-/](\d{2})$', val)
        if m:
            start_year = int(m.group(1))
            end_year = 2000 + int(m.group(2))
            midpoint_year = (start_year + end_year) // 2
            df.at[idx, 'collection_date_parsed'] = f"{midpoint_year}/06/30"
            df.at[idx, 'year_parsed'] = midpoint_year
            year_range_count += 1
    mini_report("Year ranges (20yy-yy -> midpoint)", year_range_count)

    # Recompute mask after modifications
    unparsable_mask_stage2 = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())

    # 2.b Dual year 1800/2014 -> use 2014
    dual_year_count = 0
    for idx in df[unparsable_mask_stage2].index:
        val = normalize_date_str(df.at[idx, 'collection_date'])
        if not val:
            continue
        if val == "1800/2014":
            df.at[idx, 'collection_date_parsed'] = "2014/06/30"
            df.at[idx, 'year_parsed'] = 2014
            dual_year_count += 1
    mini_report("Dual year '1800/2014' -> 2014/06/30", dual_year_count)

    # Recompute mask
    unparsable_mask_stage2 = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())

    # 2.c Span 2019-10/2020-09 -> 2020/01/01 (or similar spans -> later year Jan 1)
    span_count = 0
    for idx in df[unparsable_mask_stage2].index:
        val = normalize_date_str(df.at[idx, 'collection_date'])
        if not val:
            continue
        # Specific known span
        if val == "2019-10/2020-09":
            df.at[idx, 'collection_date_parsed'] = "2020/01/01"
            df.at[idx, 'year_parsed'] = 2020
            span_count += 1
            continue
        if val.replace(" ", "") in {"2015-01-01/2015-08-31"} or re.search(r"2015[-/]01[-/]01[-/]\s*2015[-/]08[-/]31", val.replace(" ", "")):
            df.at[idx, 'collection_date_parsed'] = "2015/01/01"
            df.at[idx, 'year_parsed'] = 2015
            span_count += 1
            continue
        # Generic span like 2014-11/2016-01 or 2016/2018
        m = re.match(r'^(20\d{2})(?:[-/]\d{2})?[-/](20\d{2})(?:[-/]\d{2})?$', val)
        if m:
            later_year = int(m.group(2))
            df.at[idx, 'collection_date_parsed'] = f"{later_year}/01/01"
            df.at[idx, 'year_parsed'] = later_year
            span_count += 1
    mini_report("Spans (e.g., 2019-10/2020-09) -> later year 01/01", span_count)

    # Recompute mask
    unparsable_mask_stage2 = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())

    # 2.d Year-only (4 digits, 18xx/19xx/20xx)
    year_only_count = 0
    year_only_candidates = df[unparsable_mask_stage2]['collection_date'].apply(normalize_date_str)
    year_only_matches = year_only_candidates[year_only_candidates.notna() & year_only_candidates.str.match(r'^(18|19|20)\d{2}$')]
    print(f"  Debug: year-only candidates total={len(year_only_candidates.dropna())}, matching pattern={len(year_only_matches)}")
    print(f"  Debug: top year-only values:\n{year_only_matches.value_counts().head(10)}")
    for idx in df[unparsable_mask_stage2].index:
        val = normalize_date_str(df.at[idx, 'collection_date'])
        if not val:
            continue
        if re.match(r'^(18|19|20)\d{2}$', val):
            year_val = int(val)
            df.at[idx, 'collection_date_parsed'] = f"{year_val}/06/30"
            df.at[idx, 'year_parsed'] = year_val
            year_only_count += 1
    mini_report("Year-only (18xx/19xx/20xx) -> yyyy/06/30", year_only_count)

    # Recompute mask
    unparsable_mask_stage2 = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())

    # 2.e ISO-like 20yy-mm-dd where collection_date_parsed is missing
    iso_like_count = 0
    for idx in df[unparsable_mask_stage2].index:
        val = normalize_date_str(df.at[idx, 'collection_date'])
        if not val:
            continue
        m = re.match(r'^(20\d{2})[-/](\d{2})[-/](\d{2})$', val)
        if m:
            year_val = int(m.group(1))
            month = m.group(2)
            day = m.group(3)
            df.at[idx, 'collection_date_parsed'] = f"{year_val}/{month}/{day}"
            df.at[idx, 'year_parsed'] = year_val
            iso_like_count += 1
    mini_report("ISO-like 20yy-mm-dd -> yyyy/mm/dd", iso_like_count)

    return df


def apply_manual_hand_fixes(df, unparsable_df, manual_map):
    """Apply manual map to remaining unparsable values and report results."""
    manual_updates = 0
    for raw_val, (cur_date, yr) in manual_map.items():
        mask = unparsable_df['collection_date'] == raw_val
        if mask.any():
            idxs = unparsable_df[mask].index
            matches_count = len(idxs)
            df.loc[idxs, 'collection_date_parsed'] = cur_date
            df.loc[idxs, 'year_parsed'] = yr
            manual_updates += matches_count

            preview = df.loc[idxs, ['sample_accession', 'secondary_study_accession']].head(5).copy()
            preview.insert(0, 'row_index', preview.index)
            print(f"\nManual map '{raw_val}' -> {cur_date} ({yr}) matched {matches_count} rows. First five:")
            print(preview.to_string(index=False))
    if manual_updates:
        print(f"\nHand-fixed unparsable collections: {manual_updates} rows updated.")
    else:
        print("\nHand-fixed unparsable collections: 0 rows matched.")

    # Recompute after hand-fix
    unparsable_mask = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())
    unparsable_df = df.loc[unparsable_mask, ['collection_date', 'collection_date_parsed', 'year_parsed']]
    if not unparsable_df.empty:
        top_unparsable_after = unparsable_df['collection_date'].value_counts().head(10)
        print("\nTop 10 unparsable collection_date values (after hand-fix):")
        for val, count in top_unparsable_after.items():
            print(f"  '{val}': {count}")
    else:
        print("\nNo unparsable collection_date values remain after hand-fix.")

    return df
