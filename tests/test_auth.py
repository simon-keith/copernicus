from datetime import UTC
from datetime import datetime
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from copernicus.auth import IDENTITY_URL
from copernicus.auth import AuthError
from copernicus.auth import ClientCredentialsAuth
from tests.conftest import mock_client

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
API = "https://sh.dataspace.copernicus.eu/api/v1/process"


class FakeIdentity:
    """Token endpoint plus an API endpoint that checks the bearer token."""

    def __init__(self) -> None:
        self.issued = 0
        self.revoked: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == IDENTITY_URL:
            form = parse_qs(request.content.decode())
            if form["client_secret"] != ["secret"]:
                return httpx.Response(401, json={"error": "unauthorized_client"})
            self.issued += 1
            return httpx.Response(
                200, json={"access_token": f"t{self.issued}", "expires_in": 600}
            )
        token = request.headers["Authorization"].removeprefix("Bearer ")
        if token in self.revoked:
            return httpx.Response(401)
        return httpx.Response(200, text=token)


class TestClientCredentialsAuth:
    def test_reuses_the_token_until_it_expires(self, settings):
        now = [T0]
        identity = FakeIdentity()
        auth = ClientCredentialsAuth(settings, clock=lambda: now[0])
        with mock_client(identity, auth) as http:
            first = http.get(API).text
            now[0] += timedelta(minutes=5)
            second = http.get(API).text
            now[0] += timedelta(minutes=5)
            third = http.get(API).text
        assert (first, second, third) == ("t1", "t1", "t2")

    def test_renews_a_revoked_token_once(self, settings):
        identity = FakeIdentity()
        auth = ClientCredentialsAuth(settings, clock=lambda: T0)
        with mock_client(identity, auth) as http:
            http.get(API)
            identity.revoked.add("t1")
            assert http.get(API).text == "t2"

    def test_bad_secret_raises_without_leaking_it(self, settings):
        bad = settings.model_copy(update={"client_secret": SecretStr("wrong")})
        auth = ClientCredentialsAuth(bad, clock=lambda: T0)
        with mock_client(FakeIdentity(), auth) as http, pytest.raises(AuthError) as err:
            http.get(API)
        assert "wrong" not in str(err.value)
