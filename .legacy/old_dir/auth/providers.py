from abc import ABC, abstractmethod
import json
import os

class CredentialsProvider(ABC):
    """A generalised abstract class to provide credentials."""

    @abstractmethod
    def load_client_secrets(self) -> dict: ...

    @abstractmethod
    def load_token(self) -> dict | None: ...

    @abstractmethod
    def save_token(self, token_data: dict) -> None: ...


class FileCredentialsProvider(CredentialsProvider):
    """A class to give out credentials from a file."""

    def __init__(self, secrets_path: str, token_path: str):
        self.secrets_path = secrets_path
        self.token_path = token_path

    def load_client_secrets(self) -> dict:
        with open(self.secrets_path, "r") as f:
            return json.load(f)

    def load_token(self) -> dict | None:
        if not os.path.exists(self.token_path):
            return None
        with open(self.token_path, "r") as f:
            return json.load(f)

    def save_token(self, token_data: dict) -> None:
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(token_data, f, indent=2)