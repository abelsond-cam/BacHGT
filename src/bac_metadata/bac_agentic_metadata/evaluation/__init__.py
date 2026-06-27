"""Fold + gold/manual-data validation harness for the agentic-metadata engine.

These scripts evaluate an engine run against a curated ground truth (the Klebsiella frozen gold) and
produce the splits, frozen sidecars, validation/adjudication reports and the agent-vs-manual scorecard.
They are the *evaluation* layer — separate from the application-agnostic ``engine/`` (the production run)
and the thin ``applications/<app>/`` glue.

Today only Klebsiella carries a gold standard, so each script roots its data tree + spec at the Klebsiella
application directory (``parents[1] / "applications" / "klebsiella"``). TODO(multi-app): accept
``--data-dir`` / ``--spec`` so a second gold-bearing application can reuse them without code changes.
"""
