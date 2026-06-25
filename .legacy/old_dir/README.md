# Portfolio Tracker

A personal automation that turns forwarded portfolio screenshots into
nicely-rendered PDF summaries. Forward a Revolut, Trading 212, or Bank
of Scotland screenshot to a dedicated Gmail alias; the system reads it
with Claude vision and produces a structured portfolio document.

This is a personal project. Setup is specific to the author's accounts
and not designed to be shared.

---

## Open

Day-to-day usage.

### Common commands

    make help            # list every command
    make receive         # ingest queued Gmail messages → envelopes
    make pipeline        # process pending envelopes (slice 1: archive only)
    make test            # run the test suite
    make test-analysis   # smoke test: produce a PDF from a pending envelope
    make test-claude     # smoke test: verify the Anthropic API works
    make clean-all       # wipe inbox queue and generated outputs

### A typical session

    1. Forward a portfolio screenshot to the dedicated Gmail alias.
       Optionally include text in the body.
    2. Wait a few seconds for Gmail's filter to label it portfolio/queued.
    3. make receive
       — pulls the message from Gmail
       — saves the screenshot and an envelope.json into
         inbox/pending/<id>/
    4. make test-analysis
       — reads the envelope, sends it to Claude, gets HTML back
       — renders to PDF
       — saves to state/outputs/current/ and state/outputs/history/

### Where things live at runtime

    inbox/pending/<id>/        envelopes waiting for the pipeline
                                envelope.json + attachment files
    inbox/processed/<id>/      envelopes after archive

    state/outputs/current/     the latest portfolio (mirror)
    state/outputs/history/     every portfolio ever produced,
                                one folder per run

`state/` is the actual product. `inbox/` is operational plumbing.
Both are gitignored.

---

## Setup

Getting from a fresh machine to a working system.

### Prerequisites

- Python 3.10+
- A Gmail account dedicated to receiving portfolio emails (the "spare")
- A separate Gmail account that will *send* screenshots to the spare
- Homebrew (for native dependencies on macOS)
- An Anthropic API key with billing set up

### 1. Clone and create the venv

    git clone <repo-url> portfolio-tracker
    cd portfolio-tracker
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r REQUIREMENTS.txt

Verify the venv is active any time you work on this — your prompt
should show `(.venv)`. If not: `source .venv/bin/activate`.

### 2. Native dependencies

WeasyPrint (HTML → PDF) needs native graphics libraries.

    brew install pango

This pulls in GObject, GLib, Cairo, and Harfbuzz.

### 3. Google Cloud OAuth (for Gmail)

The receiver authenticates against Gmail with OAuth.

    1. Go to console.cloud.google.com
    2. Create a project (e.g. "portfolio-tracker")
    3. APIs & Services → Library → enable "Gmail API"
    4. APIs & Services → OAuth consent screen:
         - User type: External
         - App name: Portfolio Tracker
         - Support email + developer contact: your spare Gmail
         - Test users: add your spare Gmail address
    5. Add scopes:
         - https://www.googleapis.com/auth/gmail.readonly
         - https://www.googleapis.com/auth/gmail.modify
         - https://www.googleapis.com/auth/gmail.send
    6. APIs & Services → Credentials → Create Credentials → OAuth client ID
         - Type: Desktop app
         - Name: Portfolio Tracker Desktop
    7. Download the JSON, rename to credentials.json, move to
       .secrets/credentials.json

### 4. Anthropic API key

    1. Go to console.anthropic.com
    2. Add a payment method, set a monthly spending limit
       ($5 is plenty for personal use)
    3. API Keys → Create Key → name it portfolio-tracker
    4. Copy the key immediately (Anthropic only shows it once)
    5. Save to .secrets/.env:

           echo "ANTHROPIC_API_KEY=sk-ant-..." > .secrets/.env

`.secrets/` is gitignored.

### 5. Gmail labels and filter

In the spare Gmail account:

    1. Create three labels (left sidebar → + Create new label):
         portfolio/queued
         portfolio/done
         portfolio/failed

       The slash auto-nests them.

    2. Create a filter (search bar → sliders icon):
         From:  the address that will send screenshots
         To:    the spare's +portfolio alias

       Apply the label "portfolio/queued".
       Optionally check "Skip the Inbox".

    3. Update receiver/config.py if your sender or alias differs.

### 6. First-time authentication

    python tests/test_auth.py

A browser opens. Sign in with the spare Gmail.
Click Advanced → "Go to Portfolio Tracker (unsafe)". Click Allow.

The browser closes; the terminal prints success.
A new file .secrets/token.json is created — subsequent runs reuse it.

### 7. End-to-end test

From the sender account, forward a portfolio screenshot to the
`+portfolio` alias. Wait a few seconds, then:

    make receive
    make test-analysis

If a PDF lands in `state/outputs/current/portfolio.pdf`, the system
works.

---

## Architecture

How the pieces fit together.

### Two halves connected by disk

The system splits into a **receiver** (Gmail → disk) and a **pipeline**
(disk → Claude → PDF). They run as separate processes and never share
Python objects in memory. They meet only through files in `inbox/`.

    Gmail
      │
      ▼
    Receiver   →   inbox/pending/<id>/
                     envelope.json + screenshots
                          │
                          ▼
                      Pipeline   →   state/outputs/current/portfolio.pdf
                                      state/outputs/history/<ts>_portfolio/

This decoupling matters: each half can be tested or replaced without
touching the other.

### The shared contract

`inbox/envelope.py` defines the format both halves agree on. The
receiver writes Envelopes; the pipeline reads them. JSON is the wire
format on disk; both halves work with typed `Envelope` objects in
Python.

The contract is deliberately neutral about source. An Envelope from
Gmail looks identical to one from any future receiver. Receivers can
be swapped without the pipeline knowing.

### What the receiver does

For each Gmail message labeled `portfolio/queued`:

    1. Fetch the raw message via Gmail API
    2. Parse it into a ParsedMessage (Gmail-specific intermediate)
    3. Classify by shape:
         - Has visual attachment → SCREENSHOT
         - Has In-Reply-To header → REPLY
         - Otherwise → UNKNOWN
    4. Create inbox/pending/<envelope_id>/
    5. Download attachments into the folder
    6. Write envelope.json into the folder
    7. Relabel the Gmail message from queued to done

Step 7 is intentionally last. If any prior step fails, the message
stays `queued` and gets retried on the next run. Data is never lost.

### What the pipeline does

Currently in slice 2: produce a portfolio PDF from a screenshot envelope.

    1. Read each envelope.json in inbox/pending/
    2. For SCREENSHOT envelopes:
         - Send all attachments to Claude with the example template as
           structural reference
         - Get back HTML matching the template
         - Save HTML, render PDF, copy source screenshots to
           state/outputs/history/<timestamp>_portfolio/
         - Mirror that folder to state/outputs/current/

REPLY and UNKNOWN envelopes are not yet processed. REPLY handling
(corrections to a previous portfolio) is planned for a later slice.

### Storage layout

    inbox/                              receiver's domain (operational)
    ├── pending/<envelope_id>/
    │   ├── envelope.json
    │   └── <attachments>
    └── processed/<envelope_id>/        moved here after pipeline success
        ├── envelope.json
        └── <attachments>

    state/outputs/                      pipeline's domain (the product)
    ├── current/                        always mirrors the latest portfolio
    └── history/<timestamp>_portfolio/
        ├── portfolio.html
        ├── portfolio.pdf
        └── source/                     copies of screenshots used

`inbox/` is the operational record (emails). `state/outputs/` is the
actual product (portfolios). They never mix.

### Module map

    auth/         Google OAuth abstraction (providers, flows, services)
    inbox/        shared envelope schema + storage paths
    receiver/     Gmail → envelope on disk
                  (gmail_client, parser, classifier, gmail_receiver)
    pipeline/     envelope → PDF
                  (intake, analysis, render, storage, archive)
    state/        runtime outputs (gitignored)
    tests/        test suite

Each package has a focused responsibility. Cross-package dependencies
are only allowed downward in this list (e.g. pipeline can import from
inbox, but not vice versa).

---

## Status

What's built and what's not.

### Working

- Receiver: forwards a Gmail message into an envelope folder on disk.
  Tested end-to-end.
- Envelope schema: serialization round-trips, atomic writes.
- Pipeline intake: reads envelope folders from inbox/pending/.
- Pipeline analysis: sends a screenshot envelope to Claude, returns
  HTML.
- Pipeline render: HTML → PDF via WeasyPrint.
- Pipeline storage: writes portfolios to history/ and mirrors to
  current/.
- Test suite: end-to-end smoke tests for analysis and Claude API.

### In progress

- send.py: outbound email (PDF + brief delivery message).
- pipeline.py orchestrator: chains analysis → render → storage → send → archive.

### Not yet built

- Reply-correction flow: when a reply arrives with corrections,
  regenerate the most recent portfolio.
- Scheduled digest: periodic runs that refresh prices and produce
  commentary.

See `todo.txt` for deferred design questions.