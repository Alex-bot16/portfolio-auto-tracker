# Gmail Setup

For the service to correctly extract emails, you need to configure a label and filter.

## 1. Create three labels

Gmail → left sidebar → "+ Create new label". Create exactly:

  - portfolio/queued
  - portfolio/done
  - portfolio/failed

The slash creates a nested label automatically.

## 2. Create one filter

Gmail → search bar → sliders icon → fill in:

  - From:  alexandre.bommensath@gmail.com
  - To:    yourspare+portfolio@gmail.com

Click "Create filter" → check "Apply the label: portfolio/queued"
→ optionally check "Skip the Inbox" → "Create filter".

## 3. Test it

Send any email from alexandre.bommensath@gmail.com to
yourspare+portfolio@gmail.com. Within seconds it should appear
labeled `portfolio/queued` and skipping the inbox.

## Reproducing on a new account

Repeat steps 1-3. Update receiver/config.py if you change the
sender or alias.