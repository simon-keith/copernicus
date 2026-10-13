from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from copernicus.auth import CdseSettings

type Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def settings() -> CdseSettings:
    return CdseSettings(client_id="client", client_secret=SecretStr("secret"))


def mock_client(handler: Handler, auth: httpx.Auth | None = None) -> httpx.Client:
    """An httpx client that never touches the network."""
    return httpx.Client(transport=httpx.MockTransport(handler), auth=auth)


def stac_feature(product: str, when: str, cloud: float) -> dict[str, object]:
    """A CDSE STAC item, trimmed to the fields the client reads (2026-10)."""
    return {
        "type": "Feature",
        "id": product,
        "properties": {
            "datetime": when,
            "platform": "sentinel-2b",
            "grid:code": "MGRS-32TLP",
            "eo:cloud_cover": cloud,
        },
        "assets": {},
    }
