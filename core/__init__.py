"""Core domain logic — what the system thinks.

This package holds the parts that reason about a portfolio:
  - holdings    : the Position model + extracting positions from a PDF
  - prices      : fetching current market prices (swappable backend)
  - research    : the sandbox — links, quotes, numbers, sentiment per name
  - digest      : composing the final digest document
  - claude_client : thin wrapper around the Anthropic API

Nothing here knows about email, folders, or rendering — that's io_layer.
"""
