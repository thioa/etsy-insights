import socket

import pytest

from etsy_insights.printify_api import (MissingScope, PrintifyBusy, PrintifyClient, PrintifyUnreachable,
                                        TokenRejected, UnexpectedResponse)
from tests import printify_data as data
from tests.printify_fake import FakePrintify


@pytest.fixture
def fake():
    with FakePrintify() as server:
        yield server.load_default()


@pytest.fixture
def timing():
    t, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        t[0] += seconds
    return t, sleeps, sleep


def make(fake_url, timing, token="tok"):
    t, sleeps, sleep = timing
    return PrintifyClient(token, base_url=fake_url, clock=lambda: t[0], sleep=sleep, no_proxy=True)


def retries(sleeps):
    return [s for s in sleeps if s != 1.0]


def test_sends_auth_and_user_agent(fake, timing):
    assert make(fake.url, timing).shops() == data.SHOPS
    method, path, query, headers = fake.requests[-1]
    assert (method, path) == ("GET", "/v1/shops.json")
    assert headers["Authorization"] == "Bearer tok" and headers["User-Agent"] == "EtsyInsights/4.0"


def test_products_reads_all_pages(fake, timing):
    products = make(fake.url, timing).products(111)
    assert [p["id"] for p in products] == ["p-sweat", "p-mug", "p-off"]
    queries = [q for _, path, q, _ in fake.requests if path == "/v1/shops/111/products.json"]
    assert queries == [{"page": "1", "limit": "50"}, {"page": "2", "limit": "50"}]


def test_waits_between_requests(fake, timing):
    client = make(fake.url, timing)
    client.shops()
    client.shops()
    assert timing[1] == [1.0]


def test_429_uses_retry_after(fake, timing):
    fake.queue("/v1/shops.json", (429, {"error": "slow down"}, {"Retry-After": "7"}), (200, data.SHOPS, None))
    assert make(fake.url, timing).shops() == data.SHOPS
    assert 7 in timing[1]


def test_429_gives_up_after_three_retries(fake, timing):
    fake.queue("/v1/shops.json", *[(429, {}, None)] * 4)
    with pytest.raises(PrintifyBusy) as err:
        make(fake.url, timing).shops()
    assert timing[1].count(60) == 3
    assert err.value.message == "Printify is busy. Try Sync again in a few minutes."


def test_server_errors_back_off(fake, timing):
    fake.queue("/v1/shops.json", *[(500, {}, None)] * 4)
    with pytest.raises(PrintifyUnreachable) as err:
        make(fake.url, timing).shops()
    assert retries(timing[1]) == [5, 15, 45]
    assert err.value.message == "Could not reach Printify. Check your internet connection and try again."


def test_401_and_403(fake, timing):
    fake.set("/v1/shops.json", {"error": "Unauthenticated"}, status=401)
    with pytest.raises(TokenRejected) as err:
        make(fake.url, timing).shops()
    assert err.value.message == "Printify rejected the token. Create a new token in Printify and paste it here."
    fake.set("/v1/shops/111/products.json?page=1", {}, status=403)
    with pytest.raises(MissingScope) as err:
        make(fake.url, timing).products(111)
    assert err.value.scope == "products.read"
    assert err.value.message == ("The token needs the products.read permission. Create a new token with "
                                 "shops.read, products.read and catalog.read.")
    fake.set("/v1/catalog/blueprints.json", {}, status=403)
    with pytest.raises(MissingScope) as err:
        make(fake.url, timing).blueprints()
    assert err.value.scope == "catalog.read"
    fake.set("/v1/shops.json", {}, status=403)
    with pytest.raises(MissingScope) as err:
        make(fake.url, timing).shops()
    assert err.value.scope == "shops.read"


def test_not_json_is_unexpected(fake, timing):
    fake.set("/v1/catalog/blueprints.json", "oops")
    with pytest.raises(UnexpectedResponse) as err:
        make(fake.url, timing).blueprints()
    assert err.value.path == "/v1/catalog/blueprints.json" and err.value.body == "oops"


def test_connection_refused_is_unreachable(timing):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(PrintifyUnreachable):
        make(f"http://127.0.0.1:{port}", timing).shops()
    assert retries(timing[1]) == [5, 15, 45]


def test_truncated_body_is_retried(fake, timing):
    from tests.printify_fake import TRUNCATE
    fake.queue("/v1/shops.json", (200, TRUNCATE, None), (200, data.SHOPS, None))
    assert make(fake.url, timing).shops() == data.SHOPS
    assert retries(timing[1]) == [5]


def test_timeout_is_retried(fake, timing):
    from tests.printify_fake import SLOW
    t, sleeps, sleep = timing
    client = PrintifyClient("tok", base_url=fake.url, timeout=0.2, clock=lambda: t[0], sleep=sleep, no_proxy=True)
    fake.queue("/v1/shops.json", (200, SLOW, None), (200, data.SHOPS, None))
    assert client.shops() == data.SHOPS
    assert retries(sleeps) == [5]


def test_redirect_never_forwards_the_token(fake, timing):
    with FakePrintify() as other:
        fake.set("/v1/shops.json", {}, status=302, headers={"Location": other.url + "/steal"})
        with pytest.raises(UnexpectedResponse):
            make(fake.url, timing, token="SECRET-TOKEN").shops()
        assert other.requests == []


@pytest.fixture
def tls_files(tmp_path):
    import subprocess
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "2", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    return cert, key


def test_untrusted_certificate_fails_fast_with_clear_message(tls_files, timing):
    """Seperti Python dari python.org di Mac tanpa daftar sertifikat: jangan coba ulang, jelaskan masalahnya."""
    from etsy_insights.printify_api import CertificateProblem
    with FakePrintify(tls=tls_files) as fake:
        fake.load_default()
        with pytest.raises(CertificateProblem) as err:
            make(fake.url, timing).shops()
    assert retries(timing[1]) == []
    assert err.value.message.startswith("Etsy Insights could not verify Printify's security certificate")


def test_trusted_certificate_works(tls_files, timing):
    import ssl
    t, sleeps, sleep = timing
    with FakePrintify(tls=tls_files) as fake:
        fake.load_default()
        client = PrintifyClient("tok", base_url=fake.url, clock=lambda: t[0], sleep=sleep, no_proxy=True,
                                ssl_context=ssl.create_default_context(cafile=str(tls_files[0])))
        assert client.shops() == data.SHOPS


def test_default_context_uses_the_system_certificate_store():
    import truststore
    from etsy_insights.printify_api import default_ssl_context
    assert isinstance(default_ssl_context(), truststore.SSLContext)


def test_requirements_include_certificate_packages():
    from pathlib import Path
    names = {line.split(">")[0].split("=")[0].strip()
             for line in (Path(__file__).parent.parent / "requirements.txt").read_text().splitlines()}
    assert {"truststore", "certifi"} <= names
