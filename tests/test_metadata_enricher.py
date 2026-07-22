import tempfile

from cache_manager import CacheManager
from app.metadata_enricher import MetadataEnricher


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, get_map=None, post_result=None):
        self.get_map = get_map or {}
        self.post_result = post_result
        self.get_calls = []
        self.post_calls = []

    def get(self, url, params=None, timeout=None):
        self.get_calls.append((url, params))
        return self.get_map.get("default", FakeResponse({"data": []}))

    def post(self, url, json=None, timeout=None):
        self.post_calls.append((url, json))
        return self.post_result


JIKAN_OK = {
    "data": [{
        "title": "Dandadan",
        "titles": [{"title": "ダンダダン"}],
        "status": "Publishing",
        "chapters": 120,
        "volumes": 12,
        "score": 8.6,
        "synopsis": "Uma história sobre fantasmas e aliens.",
        "images": {"jpg": {"large_image_url": "http://img/dandadan.jpg"}},
    }]
}


def test_enrich_uses_jikan_first():
    session = FakeSession(get_map={"default": FakeResponse(JIKAN_OK)})
    with tempfile.TemporaryDirectory() as tmp:
        enricher = MetadataEnricher(cache=CacheManager(tmp), session=session)
        result = enricher.enrich("Dandadan")
    assert result is not None
    assert result["title"] == "Dandadan"
    assert result["chapters"] == 120
    assert result["cover_image"] == "http://img/dandadan.jpg"


def test_enrich_caches_result():
    session = FakeSession(get_map={"default": FakeResponse(JIKAN_OK)})
    with tempfile.TemporaryDirectory() as tmp:
        cache = CacheManager(tmp)
        enricher = MetadataEnricher(cache=cache, session=session)
        enricher.enrich("Dandadan")
        first_calls = len(session.get_calls)
        enricher.enrich("Dandadan")  # deve vir do cache
        assert len(session.get_calls) == first_calls


ANILIST_OK = {
    "data": {
        "Media": {
            "title": {"romaji": "Dandadan", "english": "Dandadan", "native": "ダンダダン"},
            "status": "RELEASING",
            "chapters": 120,
            "volumes": 12,
            "averageScore": 86,
            "description": "desc",
            "coverImage": {"large": "http://img/anilist.jpg"},
        }
    }
}


def test_enrich_falls_back_to_anilist():
    session = FakeSession(
        get_map={"default": FakeResponse({"data": []})},
        post_result=FakeResponse(ANILIST_OK),
    )
    with tempfile.TemporaryDirectory() as tmp:
        enricher = MetadataEnricher(cache=CacheManager(tmp), session=session)
        result = enricher.enrich("Dandadan")
    assert result is not None
    assert len(session.post_calls) == 1
    assert result["title"] == "Dandadan"
    assert result["chapters"] == 120
    assert result["volumes"] == 12
    assert result["score"] == 86
    assert result["status"] == "RELEASING"
    assert result["synopsis"] == "desc"
    assert result["cover_image"] == "http://img/anilist.jpg"


def test_enrich_returns_none_on_network_error():
    class BrokenSession:
        def get(self, *a, **k):
            raise ConnectionError("sem rede")

        def post(self, *a, **k):
            raise ConnectionError("sem rede")

    with tempfile.TemporaryDirectory() as tmp:
        enricher = MetadataEnricher(cache=CacheManager(tmp), session=BrokenSession())
        assert enricher.enrich("Qualquer") is None
