import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.intake import load_pending
from pipeline.analysis import build_portfolio_html
from pipeline.storage import save_portfolio
from inbox.envelope import EnvelopeKind


envelopes = load_pending()
if not envelopes:
    print("No envelopes in pending. Forward a screenshot and run receiver first.")
    exit()

# Find the first SCREENSHOT envelope (skip replies/unknowns)
screenshot = None
for env, p in envelopes:
    if env.kind == EnvelopeKind.SCREENSHOT:
        screenshot = (env, p)
        break

if not screenshot:
    print(f"No SCREENSHOT envelopes among {len(envelopes)} pending. Found:")
    for env, _ in envelopes:
        print(f"  {env.id}: {env.kind.value}")
    exit()

envelope, path = screenshot
print(f"processing {envelope.id}")
print(f"  body: {envelope.body_text[:100]!r}")
print(f"  attachments: {[a.filename for a in envelope.attachments]}")

print("calling Claude...")
html = build_portfolio_html(envelope)
print(f"got {len(html)} chars of HTML")

# Save to state/outputs/history/<timestamp>_portfolio/ and mirror to current/
source_paths = [a.path for a in envelope.attachments]
folder = save_portfolio(html, source_paths)
print(f"saved portfolio to {folder}")