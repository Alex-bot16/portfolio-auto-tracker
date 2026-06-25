"""Smoke test: prove we can call Claude and get a response back."""

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(".secrets/.env")

client = Anthropic()  # auto-picks up ANTHROPIC_API_KEY from environment

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=200,
    messages=[
        {"role": "user", "content": "Reply with exactly: 'Pipeline ready.'"}
    ],
)

print(response.content[0].text)