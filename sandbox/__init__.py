"""Sandbox — standalone scripts for iterating on one piece at a time.

Each script exercises a single capability in isolation, so you can tune
prompts and check output without running the whole pipeline:

    python -m sandbox.try_research OKLO      # research one ticker
    python -m sandbox.try_prices             # price every mapped ticker
    python -m sandbox.try_extract            # extract holdings from current PDF

These are for development, not production. Print freely, experiment freely.
"""
