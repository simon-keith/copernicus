"""CDSE authentication: Sentinel Hub OAuth client credentials.

Create the client in the Sentinel Hub dashboard of the Copernicus Data Space
Ecosystem (User settings > OAuth clients > Create), then put its id and secret in
``.env`` as ``CDSE_CLIENT_ID`` and ``CDSE_CLIENT_SECRET``. The secret is shown once.
"""

from collections.abc import Callable
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Final
from typing import override

import httpx
from pydantic import AwareDatetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

IDENTITY_URL: Final = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
EXPIRY_MARGIN: Final = timedelta(seconds=60)


class CdseSettings(BaseSettings):
    """CDSE credentials, read from the environment or ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="CDSE_", env_file=".env", extra="ignore", frozen=True
    )

    client_id: str = Field(description="Sentinel Hub OAuth client id.")
    client_secret: SecretStr = Field(description="Sentinel Hub OAuth client secret.")


class AuthError(Exception):
    """The identity server refused the client credentials."""


class AccessToken(BaseModel):
    """A bearer token and its expiry."""

    model_config = ConfigDict(frozen=True)

    value: SecretStr = Field(description="Bearer token for Sentinel Hub API calls.")
    expires_at: AwareDatetime = Field(description="When the token expires.")

    def is_expired(self, now: datetime) -> bool:
        """Tell whether the token is expired, or about to be.

        Examples
        --------
        >>> t0 = datetime(2026, 1, 1, tzinfo=UTC)
        >>> expires_at = t0 + timedelta(hours=1)
        >>> token = AccessToken(value=SecretStr("t"), expires_at=expires_at)
        >>> token.is_expired(t0), token.is_expired(expires_at - timedelta(seconds=30))
        (False, True)
        """
        return now >= self.expires_at - EXPIRY_MARGIN


class _TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: SecretStr
    expires_in: int


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class ClientCredentialsAuth(httpx.Auth):
    """httpx auth that fetches, caches and renews a client-credentials token.

    The token request goes through the same client as the API call, so tests can
    mock both with one ``httpx.MockTransport``.
    """

    requires_response_body = True

    def __init__(
        self,
        settings: CdseSettings,
        *,
        token_url: str = IDENTITY_URL,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """Wrap the credentials; no request is made until the first API call."""
        self._settings = settings
        self._token_url = token_url
        self._clock = clock
        self._token: AccessToken | None = None

    @override
    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response]:
        if self._token is None or self._token.is_expired(self._clock()):
            self._token = self._parse((yield self._token_request()))
        request.headers["Authorization"] = self._bearer(self._token)
        response = yield request
        if response.status_code == httpx.codes.UNAUTHORIZED:
            # Revoked or expired early: renew once and replay.
            self._token = self._parse((yield self._token_request()))
            request.headers["Authorization"] = self._bearer(self._token)
            yield request

    def _token_request(self) -> httpx.Request:
        return httpx.Request(
            "POST",
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret.get_secret_value(),
            },
        )

    def _parse(self, response: httpx.Response) -> AccessToken:
        if response.is_error:
            msg = f"token request failed: HTTP {response.status_code}"
            raise AuthError(msg)
        body = _TokenResponse.model_validate_json(response.content)
        expires_at = self._clock() + timedelta(seconds=body.expires_in)
        return AccessToken(value=body.access_token, expires_at=expires_at)

    @staticmethod
    def _bearer(token: AccessToken) -> str:
        return f"Bearer {token.value.get_secret_value()}"
