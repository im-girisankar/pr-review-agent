from .base import PRFetcher
from .github import GitHubFetcher


def get_fetcher(provider: str, settings: object) -> PRFetcher:
    match provider:
        case "github":
            from pr_review_agent.core.settings import Settings
            assert isinstance(settings, Settings)
            return GitHubFetcher(pat=settings.github_pat)
        case "azure_devops":
            raise NotImplementedError("AzureDevOpsFetcher not yet implemented")
        case _:
            raise ValueError(f"Unknown provider: {provider}")
