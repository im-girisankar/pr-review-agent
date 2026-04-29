from .base import PRFetcher


def get_fetcher(provider: str, settings: object) -> PRFetcher:
    match provider:
        case "github":
            raise NotImplementedError("GitHubFetcher not yet implemented")
        case "azure_devops":
            raise NotImplementedError("AzureDevOpsFetcher not yet implemented")
        case _:
            raise ValueError(f"Unknown provider: {provider}")
