from __future__ import annotations

from datetime import datetime, timedelta
import logging
import asyncio
from typing import Any, Awaitable, Callable

import aiohttp

from app.services.log_context import get_request_context


class MarzbanService:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        notify_admin: Callable[[str], Awaitable[None]] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._token: str | None = None
        self._logger = logging.getLogger(__name__)
        self._session: aiohttp.ClientSession | None = None
        self._notify_admin = notify_admin

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        context = get_request_context()
        context_str = f"context={context}" if context else "context=none"
        retries = 3
        for attempt in range(retries):
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            session = await self._get_session()
            try:
                async with session.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    timeout=15,
                    headers=headers,
                ) as resp:
                    if resp.status == 401:
                        if self._can_refresh_token() and attempt == 0:
                            self._token = None
                            continue
                        self._logger.error(
                            "Marzban auth error %s %s: status=%s %s",
                            method,
                            path,
                            resp.status,
                            context_str,
                        )
                        if self._notify_admin:
                            await self._notify_admin(
                                f"⚠️ Marzban auth error ({resp.status}) on {path}."
                            )
                        resp.raise_for_status()
                    if resp.status == 404:
                        body = await resp.text()
                        self._logger.error(
                            "Marzban API route not found %s %s: status=%s body=%s %s",
                            method,
                            path,
                            resp.status,
                            body,
                            context_str,
                        )
                        if self._notify_admin:
                            await self._notify_admin(
                                f"⚠️ Marzban API route not found ({path})."
                            )
                        resp.raise_for_status()
                    if resp.status in {502, 503, 504} and attempt < retries - 1:
                        await asyncio.sleep(2**attempt)
                        continue
                    if resp.status >= 400:
                        body = await resp.text()
                        self._logger.error(
                            "Marzban API error %s %s: status=%s body=%s %s",
                            method,
                            path,
                            resp.status,
                            body,
                            context_str,
                        )
                        resp.raise_for_status()
                    if resp.status == 204:
                        return {}
                    try:
                        return await resp.json(content_type=None)
                    except aiohttp.ContentTypeError:
                        return {}
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
                if attempt < retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                self._logger.error(
                    "Marzban API connection error %s %s: error=%s %s",
                    method,
                    path,
                    exc,
                    context_str,
                )
                raise
        return {}

    async def _get_token(self) -> str:
        if not self.api_key:
            return ""
        if ":" not in self.api_key:
            return self.api_key
        if self._token is not None:
            return self._token
        username, password = [part.strip() for part in self.api_key.split(":", maxsplit=1)]
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/admin/token",
                data={"username": username, "password": password},
                timeout=15,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        self._token = data.get("access_token") or data.get("token") or ""
        return self._token

    def _can_refresh_token(self) -> bool:
        return ":" in self.api_key

    async def create_user(
        self,
        username: str,
        expire_at: datetime,
        traffic_gb: float | None = None,
        traffic_reset_period: str | None = None,
        proxy: str | None = None,
        flow: str | None = None,
        inbounds: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "username": username,
            "expire": int(expire_at.timestamp()),
        }
        if traffic_gb:
            payload["data_limit"] = int(traffic_gb * 1024**3)
        if traffic_reset_period:
            payload["data_limit_reset"] = traffic_reset_period
        if proxy:
            proxy_settings: dict[str, Any] = {}
            if flow:
                proxy_settings["flow"] = flow
            if proxy_settings:
                payload["proxies"] = {proxy: proxy_settings}
            if inbounds:
                payload["inbounds"] = {proxy: inbounds}
        return await self._request("POST", "/api/user", json=payload)

    async def renew_user(self, username: str, add_days: timedelta) -> dict[str, Any]:
        payload = {"add_days": add_days.days}
        return await self._request("POST", f"/api/user/{username}/renew", json=payload)

    async def update_user_expire(self, username: str, expire_at: datetime) -> dict[str, Any]:
        payload = {"expire": int(expire_at.timestamp())}
        return await self._request("PUT", f"/api/user/{username}", json=payload)

    async def update_user_traffic_policy(
        self,
        username: str,
        traffic_gb: float | None = None,
        traffic_reset_period: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if traffic_gb is not None:
            payload["data_limit"] = int(traffic_gb * 1024**3)
        if traffic_reset_period:
            payload["data_limit_reset"] = traffic_reset_period
        if not payload:
            return {}
        return await self._request("PUT", f"/api/user/{username}", json=payload)

    async def get_user(self, username: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/user/{username}")

    async def delete_user(self, username: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/api/user/{username}")

    async def get_subscription_link(self, username: str) -> str:
        data = await self._request("GET", f"/api/user/{username}/subscription")
        return (
            data.get("url")
            or data.get("subscription_url")
            or data.get("subscription_link")
            or ""
        )
