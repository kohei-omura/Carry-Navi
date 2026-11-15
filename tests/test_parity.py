# -*- coding: utf-8 -*-
"""画面(JS)とエンジン(Python)の判定が一致するかの検証。
同じ4時間足を両方に通し、トレンド・判定・TP/SL・C/R などが一致することを確かめる。
Node と Playwright が無い環境ではスキップ。 実行: python -m unittest tests.test_parity -v
"""
import os, sys, json, random, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import carry_signal as C

JS = os.path.join(ROOT, "tests", "ui", "eval_js.js")
KEYS_EXACT = ["verdict", "vcls", "risk", "risk_note", "carry_dir", "swap_sign", "reasons", "base", "quote"]
KEYS_NUM = ["trend", "ctr", "vol", "rsi", "adx", "diff", "tp_price", "sl_price", "tp_pct", "sl_pct", "atr_pct"]


def walk(seed, start, n=300, vol=0.004, drift=0.0):
    r = random.Random(seed); px = start; out = []
    for _ in range(n):
        c = px * (1 + drift + r.gauss(0, vol))
        h = max(px, c) * (1 + abs(r.gauss(0, vol / 2))); l = min(px, c) * (1 - abs(r.gauss(0, vol / 2)))
        out.append((round(h, 5), round(l, 5), round(c, 5))); px = c
    return out


def have_node():
    if not shutil.which("node"): return False
    return subprocess.run(["node", "-e", "require('playwright')"], cwd=ROOT, capture_output=True).returncode == 0


@unittest.skipUnless(have_node(), "node/playwright が無いためスキップ")
class JsPythonParity(unittest.TestCase):
    def test_same_verdict_and_levels(self):
        cases = []
        for i, (sym, px) in enumerate([("TRY_JPY", 3.16), ("MXN_JPY", 8.47), ("NZD_JPY", 89.3),
                                        ("CAD_JPY", 113.5), ("AUD_NZD", 1.2449), ("HUF_JPY", 0.489)]):
            for drift in (0.0015, -0.0015, 0.0):          # 上昇・下落・横ばい
                cases.append({"symbol": sym, "ohlc": walk(100 * i + int(drift * 1e4), px, drift=drift)})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"rates": C.POLICY_RATES, "cases": cases}, f); path = f.name
        try:
            js = json.loads(subprocess.run(["node", JS, path], cwd=ROOT, capture_output=True, text=True,
                                           check=True, timeout=120).stdout)
        finally:
            os.unlink(path)
        verdicts = set()
        for c, j in zip(cases, js):
            py = C.evaluate(c["symbol"], [tuple(x) for x in c["ohlc"]])
            self.assertIsNotNone(py); self.assertIsNotNone(j)
            verdicts.add(py["vcls"])
            for k in KEYS_EXACT:
                self.assertEqual(py[k], j[k], f"{c['symbol']} {k}")
            for k in KEYS_NUM:
                tol = 2e-5 * max(1.0, abs(py[k])) if k.endswith("price") else 0.011
                self.assertAlmostEqual(py[k], j[k], delta=tol, msg=f"{c['symbol']} {k}: py={py[k]} js={j[k]}")
        self.assertGreaterEqual(len(verdicts), 2, "上昇・下落の両方の判定を検証できていない")


if __name__ == "__main__":
    unittest.main()
