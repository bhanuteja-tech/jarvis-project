"""Catalog and resolvers for popular web services and platforms.

Maps natural-language service requests (e.g. 'github', 'youtube', 'linkedin')
to structured URLs, taking account-level credentials and search queries into consideration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from app.desktop.vault import CredentialVault, default_vault


@dataclass
class ServiceSpec:
    name: str
    display_name: str
    base_url: str
    account_url_template: str | None = None
    search_url_template: str | None = None
    credential_field: str = "username"
    credential_prompt: str = "What is your username for this service?"
    aliases: tuple[str, ...] = ()


WEB_SERVICES: dict[str, ServiceSpec] = {
    "github": ServiceSpec(
        name="github",
        display_name="GitHub",
        base_url="https://github.com",
        account_url_template="https://github.com/{username}",
        search_url_template="https://github.com/search?q={query}",
        credential_field="username",
        credential_prompt="What is your GitHub username or handle?",
        aliases=("gh", "git hub"),
    ),
    "youtube": ServiceSpec(
        name="youtube",
        display_name="YouTube",
        base_url="https://youtube.com",
        account_url_template="https://youtube.com/@{username}",
        search_url_template="https://www.youtube.com/results?search_query={query}",
        credential_field="username",
        credential_prompt="What is your YouTube channel handle or username?",
        aliases=("yt", "you tube"),
    ),
    "linkedin": ServiceSpec(
        name="linkedin",
        display_name="LinkedIn",
        base_url="https://www.linkedin.com",
        account_url_template="https://www.linkedin.com/in/{username}",
        search_url_template="https://www.linkedin.com/search/results/all/?keywords={query}",
        credential_field="username",
        credential_prompt="What is your LinkedIn profile handle or username?",
        aliases=("linked in",),
    ),
    "twitter": ServiceSpec(
        name="twitter",
        display_name="X (Twitter)",
        base_url="https://x.com",
        account_url_template="https://x.com/{username}",
        search_url_template="https://x.com/search?q={query}",
        credential_field="username",
        credential_prompt="What is your X (Twitter) username?",
        aliases=("x", "x.com", "tweets"),
    ),
    "gmail": ServiceSpec(
        name="gmail",
        display_name="Gmail",
        base_url="https://mail.google.com",
        aliases=("mail", "email", "google mail"),
    ),
    "google": ServiceSpec(
        name="google",
        display_name="Google",
        base_url="https://www.google.com",
        search_url_template="https://www.google.com/search?q={query}",
        aliases=("google search",),
    ),
    "chatgpt": ServiceSpec(
        name="chatgpt",
        display_name="ChatGPT",
        base_url="https://chatgpt.com",
        aliases=("chat gpt", "openai chat"),
    ),
    "reddit": ServiceSpec(
        name="reddit",
        display_name="Reddit",
        base_url="https://www.reddit.com",
        account_url_template="https://www.reddit.com/user/{username}",
        search_url_template="https://www.reddit.com/search/?q={query}",
        credential_field="username",
        credential_prompt="What is your Reddit username?",
    ),
    "leetcode": ServiceSpec(
        name="leetcode",
        display_name="LeetCode",
        base_url="https://leetcode.com",
        account_url_template="https://leetcode.com/u/{username}",
        credential_field="username",
        credential_prompt="What is your LeetCode username?",
        aliases=("leet code",),
    ),
    "amazon": ServiceSpec(
        name="amazon",
        display_name="Amazon",
        base_url="https://www.amazon.com",
        search_url_template="https://www.amazon.com/s?k={query}",
    ),
    "spotify": ServiceSpec(
        name="spotify",
        display_name="Spotify",
        base_url="https://open.spotify.com",
        search_url_template="https://open.spotify.com/search/{query}",
    ),
    "netflix": ServiceSpec(
        name="netflix",
        display_name="Netflix",
        base_url="https://www.netflix.com",
    ),
    "hackernews": ServiceSpec(
        name="hackernews",
        display_name="Hacker News",
        base_url="https://news.ycombinator.com",
        search_url_template="https://hn.algolia.com/?q={query}",
        aliases=("hacker news", "hn", "ycombinator"),
    ),
    "wikipedia": ServiceSpec(
        name="wikipedia",
        display_name="Wikipedia",
        base_url="https://www.wikipedia.org",
        search_url_template="https://en.wikipedia.org/wiki/Special:Search?search={query}",
        aliases=("wiki",),
    ),
    "stackoverflow": ServiceSpec(
        name="stackoverflow",
        display_name="Stack Overflow",
        base_url="https://stackoverflow.com",
        search_url_template="https://stackoverflow.com/search?q={query}",
        aliases=("stack overflow",),
    ),
}


def find_service(name: str) -> ServiceSpec | None:
    """Find a ServiceSpec by name or alias."""
    norm = (name or "").strip().lower()
    if not norm:
        return None
    if norm in WEB_SERVICES:
        return WEB_SERVICES[norm]
    for spec in WEB_SERVICES.values():
        if norm in spec.aliases:
            return spec
    return None


def parse_service_account_query(text: str) -> tuple[ServiceSpec | None, str | None]:
    """Extract a service spec and target username from text like 'open lohith122 github account'."""
    import re

    norm = (text or "").strip().lower()
    if not norm:
        return None, None
    for s_name, spec in WEB_SERVICES.items():
        aliases = (s_name,) + spec.aliases
        for alias in aliases:
            # Check for '<username> <alias> account/profile'
            m1 = re.search(
                rf"\b([a-zA-Z0-9_-]+)\s+{re.escape(alias)}\s*(?:account|profile|page)?\b",
                norm,
            )
            if m1:
                uname = m1.group(1)
                if uname not in {"open", "view", "launch", "go", "to", "the", "my"}:
                    return spec, uname
            # Check for '<alias> account/profile for/of <username>'
            m2 = re.search(
                rf"\b{re.escape(alias)}\s+(?:account|profile|page)?\s*(?:for|of)?\s+([a-zA-Z0-9_-]+)\b",
                norm,
            )
            if m2:
                uname = m2.group(1)
                if uname not in {"open", "view", "launch", "go", "to", "the", "my"}:
                    return spec, uname
    return None, None


@dataclass
class ServiceResolution:
    success: bool
    url: str | None = None
    needs_credential: bool = False
    service: str = ""
    field: str | None = None
    prompt: str | None = None
    message: str = ""
    details: dict[str, Any] | None = None


def resolve_service_request(
    service_name: str,
    *,
    account: bool = False,
    username: str | None = None,
    query: str | None = None,
    vault: CredentialVault | None = None,
) -> ServiceResolution:
    """Resolve a user's web service request.

    If `username` is provided, constructs the personalized URL directly for that user.
    If `account` is True and the service needs a credential (e.g. username),
    it checks the vault. If found, constructs the personalized URL.
    If missing, sets `needs_credential=True` so JARVIS can prompt the user.
    """
    spec = find_service(service_name)
    if spec is None:
        return ServiceResolution(
            success=False,
            service=service_name,
            message=f"Unknown service '{service_name}'.",
        )

    v = vault or default_vault

    # If explicit username provided and service has account template
    if username and spec.account_url_template:
        url = spec.account_url_template.format(
            **{spec.credential_field: quote_plus(str(username))}
        )
        return ServiceResolution(
            success=True,
            url=url,
            service=spec.name,
            message=f"👤 Opening {spec.display_name} account (@{username}).",
            details={"service": spec.name, "url": url, "username": username},
        )

    # If query is provided and service supports search
    if query and spec.search_url_template:
        url = spec.search_url_template.format(query=quote_plus(query))
        return ServiceResolution(
            success=True,
            url=url,
            service=spec.name,
            message=f"🔍 Searching {spec.display_name} for '{query}'.",
            details={"service": spec.name, "url": url, "query": query},
        )

    # If user explicitly asked for their account/profile or github account
    if account:
        if spec.account_url_template:
            cred_val = v.get_field(spec.name, spec.credential_field)
            if cred_val:
                url = spec.account_url_template.format(
                    **{spec.credential_field: quote_plus(str(cred_val))}
                )
                return ServiceResolution(
                    success=True,
                    url=url,
                    service=spec.name,
                    message=f"👤 Opening your {spec.display_name} account (@{cred_val}).",
                    details={"service": spec.name, "url": url, "username": cred_val},
                )
            else:
                prompt_msg = (
                    f"I don't have your {spec.display_name} {spec.credential_field} yet. "
                    f"{spec.credential_prompt}"
                )
                return ServiceResolution(
                    success=False,
                    needs_credential=True,
                    service=spec.name,
                    field=spec.credential_field,
                    prompt=prompt_msg,
                    message=prompt_msg,
                    details={"service": spec.name, "field": spec.credential_field},
                )

    # Check if we already have account credentials anyway for github/linkedin/twitter
    # If so and no query, opening their profile/dashboard is preferred if requested
    cred_val = v.get_field(spec.name, spec.credential_field) if spec.account_url_template else None
    if spec.name in {"github"}:
        if cred_val:
            url = spec.account_url_template.format(  # type: ignore[union-attr]
                **{spec.credential_field: quote_plus(str(cred_val))}
            )
            return ServiceResolution(
                success=True,
                url=url,
                service=spec.name,
                message=f"👤 Opening your {spec.display_name} account (@{cred_val}).",
                details={"service": spec.name, "url": url, "username": cred_val},
            )
        prompt_msg = (
            f"I don't have your {spec.display_name} {spec.credential_field} yet. "
            f"{spec.credential_prompt}"
        )
        return ServiceResolution(
            success=False,
            needs_credential=True,
            service=spec.name,
            field=spec.credential_field,
            prompt=prompt_msg,
            message=prompt_msg,
            details={"service": spec.name, "field": spec.credential_field},
        )

    # Default to base URL
    return ServiceResolution(
        success=True,
        url=spec.base_url,
        service=spec.name,
        message=f"🌐 Opening {spec.display_name}.",
        details={"service": spec.name, "url": spec.base_url},
    )


__all__ = [
    "ServiceSpec",
    "ServiceResolution",
    "WEB_SERVICES",
    "find_service",
    "parse_service_account_query",
    "resolve_service_request",
]
