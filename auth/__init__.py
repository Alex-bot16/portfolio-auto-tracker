"""

Public API for the auth package.

Provides authenticated API service clients via three composable abstractions:

  - CredentialsProvider — where credentials live (file, env var, ...)
  - AuthFlow            — how credentials are obtained (OAuth, API key, ...)
  - ServiceFactory      — what service is built (Gmail, Drive, ...)

The `get_service(flow, factory)` helper wires a flow and a factory together
and returns a ready-to-use service client.

Example:
    from auth import (
        FileCredentialsProvider,
        GoogleOAuthFlow,
        GmailServiceFactory,
        get_service,
    )
    from auth.config import CLIENT_SECRETS_PATH, TOKEN_PATH, SCOPES

    provider = FileCredentialsProvider(CLIENT_SECRETS_PATH, TOKEN_PATH)
    flow     = GoogleOAuthFlow(provider, SCOPES)
    factory  = GmailServiceFactory()
    service  = get_service(flow, factory)

Currently only Google OAuth and Gmail are implemented, but the abstractions
are vendor-neutral — additional flows and factories can be added without
touching callers.

"""

from .flows import GoogleOAuthFlow, AuthFlow
from .providers import FileCredentialsProvider, CredentialsProvider
from .services import GmailServiceFactory, ServiceFactory


def get_service(flow, factory):
    return factory.build_service(flow.get_credentials())