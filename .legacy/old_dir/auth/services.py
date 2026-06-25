from abc import ABC, abstractmethod
from typing import Any

from googleapiclient.discovery import build


class ServiceFactory(ABC):
    """Builds an API client given credentials."""

    @abstractmethod
    def build_service(self, credentials: Any) -> Any: ...


class GmailServiceFactory(ServiceFactory):
    """Builds a Gmail v1 service client."""

    def build_service(self, credentials: Any) -> Any:
        return build("gmail", "v1", credentials=credentials)