"""Online smoke test — verifies the Claude API key works.

Run from the project root:   python -m tests.test_online   (or `make test-online`)

Unlike test_all, this DOES need network and a valid ANTHROPIC_API_KEY in
.secrets/.env. It's a fast, cheap check that the key is wired up before
you spend time on a full digest run.
"""

import sys


def main():
    try:
        from core import claude_client
    except Exception as e:
        print(f"FAIL  could not import claude_client: {e}")
        sys.exit(1)

    print("Pinging Claude...")
    try:
        reply = claude_client.ask_text(
            "Reply with exactly: Pipeline ready.",
            max_tokens=50,
        )
    except Exception as e:
        print(f"FAIL  API call failed: {type(e).__name__}: {e}")
        print("      Check ANTHROPIC_API_KEY in .secrets/.env")
        sys.exit(1)

    print(f"  reply: {reply!r}")
    if "Pipeline ready" in reply:
        print("ok    Claude API works.")
        sys.exit(0)
    else:
        print("WARN  API responded but not as expected — key works, though.")
        sys.exit(0)


if __name__ == "__main__":
    main()
