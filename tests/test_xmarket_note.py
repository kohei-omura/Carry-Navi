# -*- coding: utf-8 -*-
"""通知に添える「株×FX地合い」（carry_signal.xmarket_note）のテスト。ネットワーク不要・通知は送らない。
姉妹アプリのファイルが読めなくても通知の本文は従来どおり、読めた時だけ2行足すことを確認する。"""
import datetime, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carry_signal as C
import xmarket

JST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda fmt: datetime.datetime.now(JST).strftime(fmt)


class XmarketNoteTest(unittest.TestCase):
    def setUp(self):
        self._file, self._get = C.STATUS_FILE, xmarket._get_json
        self.tmp = os.path.join(tempfile.mkdtemp(), "carry_status.json")
        C.STATUS_FILE = self.tmp
        self.addCleanup(setattr, C, "STATUS_FILE", self._file)
        self.addCleanup(setattr, xmarket, "_get_json", self._get)

    def _status(self, score=0.6, level="warn"):
        with open(self.tmp, "w", encoding="utf-8") as f:
            json.dump({"generated_at": now("%Y-%m-%d %H:%M JST"), "link": {"yen": {"score": score, "level": level}}}, f)

    def test_empty_when_others_unreadable(self):
        self._status()
        xmarket._get_json = lambda u: None
        self.assertEqual(C.xmarket_note(), "")

    def test_empty_when_fetch_raises_or_status_missing(self):
        def boom(u):
            raise ConnectionError("down")
        xmarket._get_json = boom
        self.assertEqual(C.xmarket_note(), "")       # status ファイル無し
        self._status()
        self.assertEqual(C.xmarket_note(), "")       # 取得が例外

    def test_two_lines_with_stock_data(self):
        self._status(score=0.6, level="warn")         # FX Navi が読めない時は自分の「円の強さ」で代用
        seen = []

        def fake(u):
            seen.append(u)
            if "kabu-oracle" in u:
                return {"generated": now("%Y.%m.%d %H:%M"), "regime": {"label": "下落基調", "chg20": -5.0}}
            return None
        xmarket._get_json = fake
        t = C.xmarket_note()
        self.assertTrue(t.startswith("\n\n🌐 株×FX地合い: ☔ リスクオフ（株:弱い／円:円高）"), t)
        self.assertIn("巻き戻し", t)
        self.assertFalse(any("Carry-Navi" in u for u in seen))   # 自分の分は取りに行かない


if __name__ == "__main__":
    unittest.main()
