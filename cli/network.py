"""Enterprise network utilities — proxy and CA certificate support."""

from typing import Optional

import httpx

from .config import NetworkConfig, load_config


def build_httpx_kwargs(config: Optional[NetworkConfig] = None) -> dict:
    """Build httpx client kwargs from NetworkConfig.

    Returns a dict that can be unpacked into httpx.Client() or httpx.AsyncClient().
    Proxy and CA settings are read from NetworkConfig (which itself reads env vars).
    """
    if config is None:
        config = load_config().network

    kwargs: dict = {}

    # Proxy settings — use mounts/HTTPTransport (proxies= removed in httpx 0.28)
    mounts: dict = {}
    if config.http_proxy:
        mounts["http://"] = httpx.HTTPTransport(proxy=config.http_proxy)
    if config.https_proxy:
        mounts["https://"] = httpx.HTTPTransport(proxy=config.https_proxy)
    if mounts:
        kwargs["mounts"] = mounts

    # SSL / CA bundle
    if not config.ssl_verify:
        kwargs["verify"] = False
    elif config.ca_bundle:
        kwargs["verify"] = config.ca_bundle
    # else: use default verify=True (system CA)

    # Note: timeout is intentionally NOT set here so callers can supply their own
    # without a duplicate-keyword TypeError. Use build_httpx_client() for a default.

    return kwargs


def build_httpx_client(
    config: Optional[NetworkConfig] = None,
    **extra_kwargs,
) -> httpx.Client:
    """Create an httpx.Client with proxy/CA/timeout settings applied.

    timeout defaults to NetworkConfig.request_timeout; callers can override via extra_kwargs.
    """
    if config is None:
        config = load_config().network
    kwargs = build_httpx_kwargs(config)
    kwargs.setdefault("timeout", config.request_timeout)
    kwargs.update(extra_kwargs)
    return httpx.Client(**kwargs)
