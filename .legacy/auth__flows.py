from abc import ABC, abstractmethod
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import json

# The . in front of .providers means the import is from the same package (auth/)
from .providers import CredentialsProvider

class AuthFlow(ABC):
    """Generalised class to get any sort of credentials object to use an API."""
    @abstractmethod
    def get_credentials(self) -> Any: ...

class GoogleOAuthFlow(AuthFlow):
    """Retrieves GoogleOAuth Credentials to use a given API."""

    def __init__(self, provider: CredentialsProvider, scopes: list[str]):
        self.provider = provider
        self.scopes = scopes

    def _persist(self, creds: Credentials) -> None:
        """Saves a token to a json file"""
        
        self.provider.save_token(json.loads(creds.to_json()))

    def _run_interactive_flow(self) -> Credentials:
        """Runs the browser-based OAuth server, which asks for google authentication, then returns credentials.""" 

        # Gets client information
        client_config = self.provider.load_client_secrets()

        # Builds an InstallAppFlow object (OAuth Flow)
        # We tell it who the client is (client_config), and what the client wants access to (self.scopes)
        flow = InstalledAppFlow.from_client_config(client_config, self.scopes)

        # Run the server
        return flow.run_local_server(port=0)

    def get_credentials(self) -> Credentials:
        creds = None

        # State 1: try to load existing token
        token_data = self.provider.load_token()
        if token_data:
            creds = Credentials.from_authorized_user_info(token_data, self.scopes)

        # State 2: token is valid → use as-is
        if creds and creds.valid:
            return creds

        # State 3: token is expired but refreshable → refresh
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._persist(creds)
                return creds
            except Exception:
                # Refresh failed (revoked, network, etc.) → fall through
                creds = None

        # State 4: no valid token → run interactive flow
        creds = self._run_interactive_flow()
        self._persist(creds)
        return creds

