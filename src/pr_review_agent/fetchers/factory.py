from pr_review_agent.core.settings import Settings

from .base import PRFetcher
from .github import GitHubFetcher


def get_fetcher(provider: str, settings: Settings) -> PRFetcher:
    match provider:
        case "github":
            return GitHubFetcher(pat=settings.github_pat)
        case "azure_devops":
            from .azure_devops import AzureDevOpsFetcher
            return AzureDevOpsFetcher(org=settings.azure_org, pat=settings.azure_pat)
        case _:
            raise ValueError(f"Unknown provider: {provider}")
