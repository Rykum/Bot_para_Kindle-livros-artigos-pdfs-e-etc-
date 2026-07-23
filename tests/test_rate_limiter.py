from scrapers.base_scraper import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds  # o sono avança o relógio


def test_token_bucket_throttles_after_cap():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    # zera o delay fixo para isolar o token-bucket
    rl.delays = {"default": 0.0}
    url = "https://api.mangadex.org/manga"
    # 5 req/s: a 6ª deve forçar um sleep
    for _ in range(5):
        rl.wait(url)
    rl.wait(url)
    assert clock.slept, "a 6ª requisição no mesmo segundo deveria aguardar"


def test_different_hosts_have_independent_budgets():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    rl.delays = {"default": 0.0}
    for _ in range(5):
        rl.wait("https://api.mangadex.org/manga")
    # outro host não deve ter sido afetado (nenhum sleep ainda p/ 1ª dele)
    before = len(clock.slept)
    rl.wait("https://cmdxd98.mangadex.network/data/abc/1.jpg")
    assert len(clock.slept) == before
