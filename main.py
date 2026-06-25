"""Entry point: `python -m portfolio_tracker` style isn't used here since
the project root is flat. Instead, run pieces via the Makefile or directly:

    make digest            # full run
    make accept-pdf        # promote a dropped PDF
    python -m sandbox.try_research OKLO

This file lets `python main.py` run a full digest for convenience.
"""

from pipeline import run_digest

if __name__ == "__main__":
    run_digest()
