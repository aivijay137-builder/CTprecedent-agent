"""Bring your own key (BYOK). The visitor's provider URL, model and key arrive as request headers (X-LLM-Base-URL, X-LLM-Model, X-LLM-Key).
They live only in memory for the length of the request or run: never written to the database, never logged (llmsvc scrubs them from errors).
The provider URL must be https and a public address, otherwise a visitor could aim the server at its own internal network."""
import ipaddress
import os
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from fastapi import HTTPException, Request


@dataclass
class Creds:
    base_url: str
    api_key: str
    model: str
    rejected: bool = field(default=False)  # set when the provider refuses the key: later calls in the run stop trying


def check_url(url: str):
    """Raises ValueError (message safe to show) unless the URL is https and points at a public address."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("The provider address must be a plain https:// URL.")
    if os.environ.get("BYOK_ALLOW_PRIVATE") == "1":  # local development only (e.g. a model running on this machine)
        return
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or 443)}
    except OSError:
        raise ValueError("Could not look up the provider address.")
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("The provider address must be a public one.")
    # ponytail: the address is checked now, not pinned for the call itself (DNS rebinding); pin it if this ever handles more than a demo


def from_request(request: Request) -> "Creds | None":
    """None when the visitor sent no key (the app then uses its own settings or the free reader)."""
    h = request.headers
    key, base, model = h.get("x-llm-key"), h.get("x-llm-base-url"), h.get("x-llm-model")
    if not key:
        return None
    if not (base and model):
        raise HTTPException(400, "Your AI settings are incomplete: provider address, model and key are all needed.")
    try:
        check_url(base.strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Creds(base.strip(), key.strip(), model.strip())
