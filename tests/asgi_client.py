"""Small synchronous facade over HTTPX2's async ASGI transport for tests."""
from __future__ import annotations

import asyncio

import httpx2


class ASGITestClient:
    __test__ = False

    def __init__(self, app, base_url: str = "http://testserver"):
        self.app = app
        self.base_url = base_url

    def request(self, method: str, url: str, **kwargs):
        async def send():
            transport = httpx2.ASGITransport(app=self.app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)
