# -*- coding: utf-8 -*-
"""保有ポジションの TP/SL 到達通知のオフラインテスト（ネットワーク不要・通知は送らない）。"""
import os, sys, json, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for k in ("LINE_CHANNEL_ACCESS_TOKEN", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "MAIL_TO", "TEST_NOTIFY"):
    os.environ.pop(k, None)
import carry_signal as C

MXN = {"sym": "MXN_JPY", "entry": 8.40, "lot": 1, "date": "2026-11-01", "tp": 8.60, "sl": 8.30}
T = lambda bid, **kw: dict({"MXN_JPY": {"bid": bid, "ask": bid + 0.003}}, **kw)


class TpSl(unittest.TestCase):
    def test_tp_hit_once(self):
        m, st = C.check_positions([MXN], T(8.612), {}, True, "11-15 10:00")
        self.assertEqual(len(m), 1); self.assertTrue(m[0].startswith("🎯 TP到達 MXN/JPY"))
        self.assertIn("+2,120円", m[0])                      # (8.612-8.40)×1万
        m2, _ = C.check_positions([MXN], T(8.65), st, True, "11-15 11:00")
        self.assertEqual(m2, [], "同じポジションのTP到達を2回送らない")

    def test_sl_hit(self):
        m, _ = C.check_positions([MXN], T(8.29), {}, True, "n")
        self.assertEqual(len(m), 1); self.assertTrue(m[0].startswith("⚠ SL到達")); self.assertIn("-1,100円", m[0])

    def test_between_no_alert(self):
        self.assertEqual(C.check_positions([MXN], T(8.45), {}, True, "n")[0], [])

    def test_market_closed_no_alert(self):
        self.assertEqual(C.check_positions([MXN], T(8.70), {}, False, "n")[0], [])

    def test_edit_tp_rearms(self):
        _, st = C.check_positions([MXN], T(8.62), {}, True, "n")
        m, _ = C.check_positions([dict(MXN, tp=8.61)], T(8.62), st, True, "n")
        self.assertEqual(len(m), 1, "TPを編集したら別の通知として扱う")

    def test_cross_pair_converted_to_yen(self):
        q = {"sym": "AUD_NZD", "entry": 1.2400, "lot": 1, "date": "2026-11-01", "tp": 1.2500, "sl": 1.2300}
        m, _ = C.check_positions([q], {"AUD_NZD": {"bid": 1.2510}, "NZD_JPY": {"bid": 90.0}}, {}, True, "n")
        self.assertIn("+9,900円", m[0])                      # 0.011×1万×90円

    def test_bad_rows_and_missing_tp_skipped(self):
        rows = [{"sym": "MXN_JPY"}, {"sym": "MXN_JPY", "entry": "x"}, dict(MXN, tp=None, sl=None), "junk"]
        self.assertEqual(C.check_positions([r for r in rows if isinstance(r, dict)], T(9.0), {}, True, "n")[0], [])

    def test_load_positions_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"positions": [MXN]}, f); p = f.name
        try:
            self.assertEqual(C.load_positions(p), [MXN])
            self.assertEqual(C.load_positions(p + ".none"), [])
        finally:
            os.unlink(p)

    def test_subject(self):
        self.assertEqual(C.compose_subject(["🎯 TP到達 x"]), "【Carry】TP/SL到達")
        self.assertEqual(C.compose_subject(["🟢 x"]), "【Carry】買いシグナル")
        self.assertEqual(C.compose_subject(["⚠ SL到達 x", "🟢 y"]), "【Carry】買いシグナル・TP/SL到達")


class ExitAlert(unittest.TestCase):
    """保有中のペアが「様子見（下落中）」に転じたら決済検討を1回だけ通知する。"""
    def test_turn_to_wait_alerts_once(self):
        m, st = C.check_positions([MXN], T(8.45), {}, True, "n", {"MXN_JPY": ("wait", -0.31)})
        self.assertEqual(len(m), 1); self.assertTrue(m[0].startswith("📉 決済検討 MXN/JPY"))
        self.assertIn("トレンド-0.31", m[0]); self.assertIn("+500円", m[0])
        m2, st2 = C.check_positions([MXN], T(8.44), st, True, "n", {"MXN_JPY": ("wait", -0.40)})
        self.assertEqual(m2, [], "下落中が続いても再送しない")

    def test_no_alert_while_buy_or_soft(self):
        for v in (("buy", 0.4), ("soft", -0.2)):
            self.assertEqual(C.check_positions([MXN], T(8.45), {}, True, "n", {"MXN_JPY": v})[0], [])

    def test_rearm_only_after_clear_recovery(self):
        _, st = C.check_positions([MXN], T(8.45), {}, True, "n", {"MXN_JPY": ("wait", -0.3)})
        _, st = C.check_positions([MXN], T(8.45), st, True, "n", {"MXN_JPY": ("soft", -0.2)})   # しきい値付近の戻り
        m, st = C.check_positions([MXN], T(8.45), st, True, "n", {"MXN_JPY": ("wait", -0.3)})
        self.assertEqual(m, [], "しきい値付近のチラつきでは再通知しない")
        _, st = C.check_positions([MXN], T(8.45), st, True, "n", {"MXN_JPY": ("soft", -0.1)})   # 十分に回復
        m, _ = C.check_positions([MXN], T(8.45), st, True, "n", {"MXN_JPY": ("wait", -0.3)})
        self.assertEqual(len(m), 1, "十分に回復した後の再下落は再び通知する")

    def test_tp_sl_takes_priority_and_closed_market(self):
        m, st = C.check_positions([MXN], T(8.29), {}, True, "n", {"MXN_JPY": ("wait", -0.5)})
        self.assertEqual(len(m), 1); self.assertTrue(m[0].startswith("⚠ SL到達"))
        m, _ = C.check_positions([MXN], T(8.29), st, True, "n", {"MXN_JPY": ("wait", -0.5)})
        self.assertEqual(m, [], "SL到達を知らせた後に決済検討は重ねない")
        self.assertEqual(C.check_positions([MXN], T(8.45), {}, False, "n", {"MXN_JPY": ("wait", -0.5)})[0], [])

    def test_subject_exit(self):
        self.assertEqual(C.compose_subject(["📉 決済検討 x"]), "【Carry】決済検討")
        self.assertEqual(C.compose_subject(["📉 決済検討 x", "🟢 y"]), "【Carry】買いシグナル・決済検討")


if __name__ == "__main__":
    unittest.main()
