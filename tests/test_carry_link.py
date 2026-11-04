# -*- coding: utf-8 -*-
"""Carry Navi ⇔ FX Navi 連携のオフラインテスト（ネットワーク不要・LINE/メールは送らない）。
実行: python -m unittest discover -s tests -v
"""
import os, sys, json, math, shutil, tempfile, datetime, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for k in ("LINE_CHANNEL_ACCESS_TOKEN", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "MAIL_TO", "TEST_NOTIFY"):
    os.environ.pop(k, None)   # 本番の通知が絶対に飛ばないように

import carry_link as L
import carry_signal as C

JST = L.JST
NOW = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=JST)


def fx_status(h4, h1=None, gen=NOW, positions=()):
    h1 = h4 if h1 is None else h1
    return {"generated_at": gen.strftime("%Y-%m-%d %H:%M JST"), "mode": "mtf",
            "risk": {"open_yen": 0},
            "pairs": [{"symbol": s, "score": 0.0, "mtf": {"1hour": h1, "4hour": h4}}
                      for s in ("USD_JPY", "EUR_JPY", "GBP_JPY", "AUD_JPY")],
            "open_positions": list(positions)}


class YenStrength(unittest.TestCase):
    def test_fx_all_down_is_yen_warn(self):
        y = L.yen_strength(fx_status(-1), [{"symbol": "MXN_JPY", "quote": "JPY", "trend": -0.6}], NOW)
        self.assertEqual(y["level"], "warn")
        self.assertGreater(y["score"], 0.5)

    def test_stale_fx_falls_back_to_carry(self):
        old = NOW - datetime.timedelta(hours=5)
        y = L.yen_strength(fx_status(-1, gen=old), [{"symbol": "MXN_JPY", "quote": "JPY", "trend": 0.4}], NOW)
        self.assertIsNone(y["fx"])
        self.assertAlmostEqual(y["score"], -0.4)
        self.assertEqual(y["level"], "tail")

    def test_non_jpy_carry_pair_ignored(self):
        y = L.yen_strength(None, [{"symbol": "AUD_NZD", "quote": "NZD", "trend": 0.9}], NOW)
        self.assertEqual(y["level"], "unknown")


class News(unittest.TestCase):
    def setUp(self):
        self.news = {"generated_at": NOW.strftime("%Y-%m-%d %H:%M JST"), "events": [
            {"country": "NZD", "time": "2026-11-05 12:20", "title": "RBNZ"},
            {"country": "USD", "time": "2026-11-05 22:30", "title": "NFP"},
            {"country": "GBP", "time": "2026-11-05 12:05", "title": "BOE"},
        ]}

    def test_hold_only_related_country(self):
        ev, warn = L.parse_news(self.news, NOW)
        self.assertIsNone(warn)
        self.assertEqual(L.news_hold("NZD_JPY", ev, NOW)["title"], "RBNZ")
        self.assertEqual(L.news_hold("AUD_NZD", ev, NOW)["title"], "RBNZ")
        self.assertIsNone(L.news_hold("CAD_JPY", ev, NOW))      # GBPは関係なし
        self.assertIsNone(L.news_hold("MXN_JPY", ev, NOW))      # NFPはまだ先

    def test_upcoming_lists_pairs(self):
        ev, _ = L.parse_news(self.news, NOW)
        rows = L.upcoming_news(ev, NOW)
        nfp = [r for r in rows if r["title"] == "NFP"][0]
        self.assertIn("MXN_JPY", nfp["pairs"])
        self.assertFalse([r for r in rows if r["country"] == "GBP"])

    def test_stale_calendar_warns(self):
        self.news["generated_at"] = "2026-10-20 06:00 JST"
        _, warn = L.parse_news(self.news, NOW)
        self.assertIn("日前", warn)

    def test_missing_calendar(self):
        ev, warn = L.parse_news(None, NOW)
        self.assertEqual(ev, [])
        self.assertTrue(warn)


class Overlap(unittest.TestCase):
    def test_overlap(self):
        pos = [{"symbol": "AUD_JPY", "side": "long"}, {"symbol": "EUR_JPY", "side": "short"}]
        self.assertTrue(any("AUD買い" in n for n in L.overlap_notes("AUD_NZD", pos)))
        n = L.overlap_notes("NZD_JPY", pos)
        self.assertEqual(len(n), 1)                       # 売りEUR/JPYは円買い＝重ならない
        self.assertIn("JPY売り", n[0])


def ev(sym, vcls, trend):
    return {"symbol": sym, "vcls": vcls, "trend": trend}


class SelectNotify(unittest.TestCase):
    def test_only_new_buys_and_rearm(self):
        p = [ev("MXN_JPY", "buy", 0.4)]
        out, st = C.select_notify(p, p, {}, [], None, "t1")
        self.assertEqual(len(out), 1)
        out, st = C.select_notify(p, p, st, [], None, "t2")          # 2回目は送らない
        self.assertEqual(out, [])
        p2 = [ev("MXN_JPY", "soft", 0.20)]                           # 0.15以上ならまだ再武装しない
        out, st = C.select_notify(p2, [], st, [], None, "t3")
        self.assertFalse(st["MXN_JPY"]["armed"])
        p3 = [ev("MXN_JPY", "soft", 0.10)]
        out, st = C.select_notify(p3, [], st, [], None, "t4")
        self.assertTrue(st["MXN_JPY"]["armed"])
        out, st = C.select_notify(p, p, st, [], None, "t5")
        self.assertEqual(len(out), 1)

    def test_news_hold_keeps_armed(self):
        events = [("JPY", datetime.datetime.now(JST) + datetime.timedelta(minutes=10), "BOJ")]
        p = [ev("MXN_JPY", "buy", 0.4)]
        out, st = C.select_notify(p, p, {}, events, None, "t1")
        self.assertEqual(out, [])
        self.assertTrue(st["MXN_JPY"]["armed"])
        self.assertEqual(p[0]["news_hold"]["title"], "BOJ")


# ---------- 全体（GMO・FX公開ファイルをモック） ----------
def make_klines(n=400, up=True):
    rows, t0 = [], 1_700_000_000_000
    for i in range(n):
        c = 10 * (1 + (0.0008 if up else -0.0008) * i) + 0.02 * math.sin(i / 3)
        rows.append({"openTime": str(t0 + i * 4 * 3600_000), "open": c, "high": c * 1.002,
                     "low": c * 0.998, "close": c})
    return rows


class Resp:
    def __init__(self, j, code=200):
        self._j, self.status_code = j, code

    def json(self):
        return self._j


def fake_get(fx, news, up=True):
    def _g(url, timeout=None, params=None, **kw):
        if url == L.FX_STATUS_URL:
            return Resp(fx) if fx is not None else Resp({}, 404)
        if url == L.FX_NEWS_URL:
            return Resp(news) if news is not None else Resp({}, 404)
        if url.endswith("/klines"):
            return Resp({"status": 0, "data": make_klines(up=up)})
        if url.endswith("/ticker"):
            return Resp({"data": [{"symbol": s, "bid": "10", "ask": "10.01", "timestamp": "x"}
                                  for s in C.SYMBOLS + ["NZD_JPY"]]})
        if url.endswith("/status"):
            return Resp({"data": {"status": "OPEN"}})
        raise AssertionError("想定外のURL " + url)
    return _g


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        C._OHLC.clear()

    def tearDown(self):
        os.chdir(self.cwd); shutil.rmtree(self.d)

    def run_main(self, fx, news, up=True):
        C._OHLC.clear()
        sent = []
        with mock.patch("requests.get", side_effect=fake_get(fx, news, up)), \
             mock.patch.object(C, "notify_line", side_effect=lambda t, force=False: sent.append(t)), \
             mock.patch.object(C, "notify_mail", side_effect=lambda s, b, force=False: None):
            C.main()
        return sent, json.load(open(C.STATUS_FILE, encoding="utf-8"))

    def test_link_and_dedupe(self):
        fx = fx_status(-1, gen=datetime.datetime.now(JST),
                       positions=[{"symbol": "AUD_JPY", "side": "long", "lot": 10000, "current": 100}])
        news = {"generated_at": datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"), "events": []}
        sent, st = self.run_main(fx, news)
        self.assertEqual(len(sent), 1)
        self.assertIn("FX Navi", sent[0])
        self.assertIn("AUD買い", sent[0])                 # AUD/NZD 買い × FX の AUD/JPY 買い
        self.assertTrue(st["link"]["fx_ok"])
        self.assertEqual(len(st["link"]["fx_positions"]), 1)
        self.assertTrue(all(p["vcls"] == "buy" for p in st["pairs"]))
        sent2, _ = self.run_main(fx, news)
        self.assertEqual(sent2, [])                        # 同じ買いは2回送らない

    def test_fx_down_still_works(self):
        sent, st = self.run_main(None, None)
        self.assertEqual(len(sent), 1)                     # 連携が無くても従来どおり通知
        self.assertFalse(st["link"]["fx_ok"])
        self.assertTrue(st["link"]["news_warn"])

    def test_verdicts_unchanged_by_link(self):
        """連携の有無でCarryの判定値が変わらないこと（既存性能の維持）。"""
        _, a = self.run_main(None, None, up=False)
        os.remove(C.STATUS_FILE)
        _, b = self.run_main(fx_status(1, gen=datetime.datetime.now(JST)), None, up=False)
        keys = ("verdict", "trend", "ctr", "tp_price", "sl_price", "tp_winrate")
        self.assertEqual([[p.get(k) for k in keys] for p in a["pairs"]],
                         [[p.get(k) for k in keys] for p in b["pairs"]])


if __name__ == "__main__":
    unittest.main()
