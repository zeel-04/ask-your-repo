import os
import threading
from abc import ABC, abstractmethod
from typing import Any

from dotenv import load_dotenv
from github import Auth, Github


class BaseAuth(ABC):
    """One shared instance per subclass. Subclasses implement login()."""

    client: Any
    _lock = threading.Lock()

    def __new__(cls):
        # Sync tools run in threads: lock so concurrent first calls log in once.
        with cls._lock:
            # Check cls's own dict so each subclass gets its own instance.
            if "_instance" not in cls.__dict__:
                instance = super().__new__(cls)
                instance.client = instance.login()
                # Cache only after login succeeds, so a failed login is retried next call.
                cls._instance = instance
        return cls._instance

    @abstractmethod
    def login(self) -> Any:
        """Return an authenticated client."""


class GitHubAuth(BaseAuth):
    client: Github

    def login(self) -> Github:
        return Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))


if __name__ == "__main__":
    load_dotenv()
    assert GitHubAuth() is GitHubAuth()
    print("ok")
