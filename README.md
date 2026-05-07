### The plan for the file

TRIGGERS (any of these starts a run)
  - weekly cron (default: Sundays)
  - manual trigger (a button in GitHub Actions, for testing)
  - new email arrives in the inbox

PIPELINE (runs when triggered)
  1. Check the inbox. Classify what's there:
       a. screenshot email   → go to step 2
       b. reply to a digest  → go to step 6
       c. nothing new        → go to step 3 with last week's data unchanged

  2. Extract positions from the screenshot (Claude vision)
  3. Sanity-check: compare totals to last week. If anything looks wrong,
     flag it in the digest instead of silently trusting bad numbers
  4. Build the new data file:
       - load last week's JSON + investment_philosophy.md + portfolio_context.md
       - send to Claude with the new positions
       - get back: new JSON + a short commentary block
  5. Render and send:
       - save data_YYYY-MM-DD.json (this becomes next week's input)
       - render to PDF using the template
       - email PDF + commentary body to your real inbox

  6. (Reply path) Update portfolio_context.md based on the reply,
     commit it, send a one-line confirmation email