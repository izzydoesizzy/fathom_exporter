import os
import socket
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest


def _network_tests_enabled() -> bool:
    return os.environ.get("FATHOM_RUN_NETWORK_TESTS", "0") == "1"


@pytest.mark.skipif(
    not _network_tests_enabled(),
    reason="Set FATHOM_RUN_NETWORK_TESTS=1 to run live network connectivity diagnostics.",
)
def test_fathom_base_url_dns_and_https_connectivity():
    """Optional live diagnostic test for DNS + HTTPS connectivity.

    This test is intentionally opt-in because it depends on external network access
    and can fail in CI/proxied environments even when code is correct.
    """
    base_url = os.environ.get("FATHOM_API_BASE_URL", "https://api.fathom.ai")
    host = base_url.replace("https://", "").replace("http://", "").split("/")[0]

    print("\n[NETWORK TEST] Starting live connectivity diagnostics")
    print(f"[NETWORK TEST] Base URL under test: {base_url}")
    print(f"[NETWORK TEST] Host extracted for DNS lookup: {host}")

    dns_records = socket.getaddrinfo(host, 443)
    first_ip = dns_records[0][4][0]
    print(f"[NETWORK TEST] DNS lookup succeeded. Example resolved IP: {first_ip}")

    request = Request(base_url, method="GET", headers={"User-Agent": "fathom-exporter-test/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            print(f"[NETWORK TEST] HTTPS connection succeeded. HTTP status: {response.status}")
            assert response.status >= 200
    except URLError as exc:
        message = str(exc)
        if "Tunnel connection failed" in message or "403 Forbidden" in message:
            pytest.skip(
                "HTTPS connectivity blocked by proxy/tunnel policy in this environment. "
                f"Host: {host}. Error: {exc}"
            )
        pytest.fail(
            "HTTPS connectivity failed after successful DNS lookup. "
            f"Host: {host}. Error: {exc}"
        )
