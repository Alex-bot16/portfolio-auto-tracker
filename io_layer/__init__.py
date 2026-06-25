"""io_layer — input/output plumbing.

The parts that move bytes around, with no opinions about portfolios:
  - intake  : accept a PDF from portfolio_inbox/ -> state/current/
  - storage : write a digest to state/outputs/history/, version the PDF
  - render  : markdown -> PDF
  - send    : deliver the digest (stubbed; swap the backend to email)

Nothing here reasons about holdings or research — that's core.
"""
