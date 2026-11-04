# -*- coding: utf-8 -*-
"""
Carry Navi ⇔ FX Navi(FX-Signal-Notifier) 連携モジュール
---------------------------------------------------------------------
FX Navi が5分ごとに公開している2つのファイルを読み、キャリー判断の補助情報を作る。
  data/status.json        … USD/EUR/GBP/AUD円の上位足トレンド・保有ポジション
  data/news_blackout.json … 重要経済指標カレンダー（High のみ / NZD・CAD も取得済み）

作るもの（carry_status.json の "link" に入る）
  1) 円の強さ指数   … FX 4ペアの上位足(1h/4h) と Carry の円クロスの4hトレンドから。円高＝キャリーの逆風
  2) 指標カレンダー … キャリー各ペアに関係する直近の重要指標。発表前後は新規の買い通知を保留する
  3) FX保有の要約   … 両アプリ合計のリスク（通貨別エクスポージャー）を画面で計算するための材料

※ここで作る情報はすべて「補助」。Carry の判定（verdict / trend / C/R / TP・SL）は一切変えない。
※取得に失敗しても Carry 単体の動作は従来どおり（連携欄が「未取得」になるだけ）。
"""
import sys, datetime
from zoneinfo import ZoneInfo
import requests

JST = ZoneInfo("Asia/Tokyo")

FX_RAW = "https://raw.githubusercontent.com/kohei-omura/FX-Signal-Notifier/main/data/"
FX_STATUS_URL = FX_RAW + "status.json"
FX_NEWS_URL = FX_RAW + "news_blackout.json"
FX_APP_URL = "https://kohei-omura.github.io/FX-Signal-Notifier/"
TIMEOUT = 15

FX_STALE_MIN = 90        # FXの status.json がこれより古ければ円の強さに使わない（FX停止中の誤判定防止）
NEWS_STALE_DAYS = 3      # カレンダーがこれより古ければ警告
NEWS_HOLD_MIN = 30       # 発表の前後この分数は、新規の買い通知を保留（次の毎時実行で再判定）
NEWS_SHOW_H = 48         # 画面に出す指標の範囲（これから何時間先まで）

# 円の強さ（+1=円高 / −1=円安）。FXの上位足は 4h を重く見る（Carryは4時間足のスイング）
YEN_W_H4, YEN_W_H1 = 0.6, 0.4
YEN_W_FX = 0.5           # FX(主要4ペア)とCarry(円クロス)の配分。FXが使えない時はCarryのみ
YEN_WARN = 0.5           # これ以上 → 円高警戒（リスクオフ）
YEN_SOFT = 0.25          # これ以上 → やや円高 / −これ以下 → 円安（キャリー追い風）

# キャリー各ペアに効く国。新興国(TRY/ZAR/MXN/HUF)はカレンダー対象外のため、
# 新興国通貨を大きく動かす米国(USD)の重要指標（FOMC・雇用統計など）で代用する。
PAIR_COUNTRIES = {
    "TRY_JPY": {"JPY", "USD"},
    "ZAR_JPY": {"JPY", "USD"},
    "MXN_JPY": {"JPY", "USD"},
    "HUF_JPY": {"JPY", "USD"},
    "NZD_JPY": {"JPY", "NZD"},
    "CAD_JPY": {"JPY", "CAD"},
    "AUD_NZD": {"AUD", "NZD", "CNY"},
}


def _get_json(url):
    try:
        r = requests.get(url, timeout=TIMEOUT, params={"t": int(datetime.datetime.now().timestamp())})
        if r.status_code != 200:
            print(f"[WARN] 連携取得 {url} HTTP {r.status_code}", file=sys.stderr)
            return None
        return r.json()
    except Exception as e:
        print(f"[WARN] 連携取得失敗 {url}: {e}", file=sys.stderr)
        return None


def _parse_gen(s):
    """'2026-11-05 00:30 JST' → aware datetime"""
    try:
        return datetime.datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    except Exception:
        return None


def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------- 1) 円の強さ ----------
def yen_strength(fx_status, carry_pairs, now=None):
    """FX 4ペアの上位足と、Carry の円クロスの4hトレンドから円の強さ(-1〜+1)を出す。
       +なら円高（＝円クロスが下がる＝キャリーの逆風）。"""
    now = now or datetime.datetime.now(JST)
    detail, fx_vals = [], []
    fx_fresh = False
    if fx_status:
        gen = _parse_gen(fx_status.get("generated_at"))
        fx_fresh = bool(gen and (now - gen).total_seconds() <= FX_STALE_MIN * 60)
        for p in fx_status.get("pairs", []) or []:
            sym = p.get("symbol", "")
            if not sym.endswith("_JPY"):
                continue
            m = p.get("mtf") or {}
            h1, h4 = m.get("1hour"), m.get("4hour")
            if isinstance(h1, (int, float)) and isinstance(h4, (int, float)):
                v = YEN_W_H4 * h4 + YEN_W_H1 * h1
            elif isinstance(p.get("score"), (int, float)):
                v = clamp(p["score"])        # 上位足が無い版の status.json でも動くように
            else:
                continue
            fx_vals.append(v)
            detail.append({"symbol": sym, "src": "FX", "h1": h1, "h4": h4, "v": round(v, 2)})
    cr_vals = []
    for p in carry_pairs:
        if p.get("quote") == "JPY" and isinstance(p.get("trend"), (int, float)):
            cr_vals.append(p["trend"])
            detail.append({"symbol": p["symbol"], "src": "Carry", "v": round(p["trend"], 2)})
    fx_y = -sum(fx_vals) / len(fx_vals) if (fx_vals and fx_fresh) else None
    cr_y = -sum(cr_vals) / len(cr_vals) if cr_vals else None
    if fx_y is not None and cr_y is not None:
        score = YEN_W_FX * fx_y + (1 - YEN_W_FX) * cr_y
    else:
        score = fx_y if fx_y is not None else cr_y
    if score is None:
        return {"score": None, "level": "unknown", "label": "判定不可", "fx": None, "carry": None,
                "fx_fresh": fx_fresh, "detail": detail}
    score = clamp(score)
    if score >= YEN_WARN:
        level, label = "warn", "円高警戒（リスクオフ）"
    elif score >= YEN_SOFT:
        level, label = "soft", "やや円高"
    elif score <= -YEN_SOFT:
        level, label = "tail", "円安（キャリー追い風）"
    else:
        level, label = "neutral", "中立"
    return {"score": round(score, 2), "level": level, "label": label,
            "fx": None if fx_y is None else round(fx_y, 2),
            "carry": None if cr_y is None else round(cr_y, 2),
            "fx_fresh": fx_fresh, "detail": detail}


# ---------- 2) 指標カレンダー ----------
def parse_news(news, now=None):
    """news_blackout.json → [(country, dt, title)]。古さの警告文も返す。"""
    now = now or datetime.datetime.now(JST)
    out, warn = [], None
    if not news:
        return out, "指標カレンダーを取得できませんでした（通知の保留は働きません）"
    gen = str(news.get("generated_at", ""))[:10]
    try:
        age = (now.date() - datetime.datetime.strptime(gen, "%Y-%m-%d").date()).days
        if age > NEWS_STALE_DAYS:
            warn = f"指標カレンダーが{age}日前のままです（FX Navi の news-calendar を確認）"
    except ValueError:
        warn = "指標カレンダーの更新日時を読めません"
    for e in news.get("events", []) or []:
        try:
            t = datetime.datetime.strptime(e["time"], "%Y-%m-%d %H:%M").replace(tzinfo=JST)
            out.append((e.get("country"), t, e.get("title", "")))
        except Exception:
            continue
    return out, warn


def news_hold(symbol, events, now=None):
    """発表の前後 NEWS_HOLD_MIN 分に入っていれば、その指標(dict)を返す。"""
    now = now or datetime.datetime.now(JST)
    cs = PAIR_COUNTRIES.get(symbol, {"JPY"})
    best = None
    for c, t, title in events:
        if c not in cs:
            continue
        d = (t - now).total_seconds() / 60.0
        if -NEWS_HOLD_MIN <= d <= NEWS_HOLD_MIN and (best is None or abs(d) < abs(best[0])):
            best = (d, c, t, title)
    if not best:
        return None
    d, c, t, title = best
    return {"country": c, "time": t.strftime("%m/%d %H:%M"), "title": title, "min": round(d)}


def upcoming_news(events, now=None):
    """これから NEWS_SHOW_H 時間の指標（発表後 NEWS_HOLD_MIN 分までは残す）と、影響するキャリーペア。"""
    now = now or datetime.datetime.now(JST)
    rows = []
    for c, t, title in sorted(events, key=lambda x: x[1]):
        d = (t - now).total_seconds() / 60.0
        if -NEWS_HOLD_MIN <= d <= NEWS_SHOW_H * 60:
            pairs = [s for s, cs in PAIR_COUNTRIES.items() if c in cs]
            if pairs:
                rows.append({"country": c, "time": t.strftime("%Y-%m-%d %H:%M"), "title": title,
                             "min": round(d), "pairs": pairs})
    return rows[:20]


# ---------- 3) FX保有の要約 ----------
def fx_positions(fx_status):
    out = []
    for p in (fx_status or {}).get("open_positions", []) or []:
        try:
            out.append({"symbol": p["symbol"], "side": p.get("side", "long"),
                        "lot": float(p.get("lot") or 0), "entry": p.get("entry"),
                        "current": p.get("current"), "yen": p.get("yen"), "mode": p.get("mode")})
        except Exception:
            continue
    return out


def overlap_notes(symbol, fx_pos):
    """このキャリーペアを買った時に、FX Naviの保有と同じ向きに重なる通貨の注記。"""
    base, quote = symbol.split("_")
    notes = []
    for p in fx_pos:
        b, q = p["symbol"].split("_")
        long_c, short_c = (b, q) if p["side"] == "long" else (q, b)
        same = []
        if long_c == base:
            same.append(f"{base}買い")
        if short_c == quote:
            same.append(f"{quote}売り")
        if same:
            notes.append(f"{p['symbol'].replace('_', '/')} {'買い' if p['side'] == 'long' else '売り'}"
                         f"（{'・'.join(same)}が重なる）")
    return notes


# ---------- まとめ ----------
def build_link(carry_pairs, now=None):
    """FXの公開ファイルを読み、carry_status.json の "link" を作る。失敗しても例外は出さない。"""
    now = now or datetime.datetime.now(JST)
    fx = _get_json(FX_STATUS_URL)
    news = _get_json(FX_NEWS_URL)
    events, news_warn = parse_news(news, now)
    fx_gen = _parse_gen((fx or {}).get("generated_at"))
    fx_age = round((now - fx_gen).total_seconds() / 60) if fx_gen else None
    pos = fx_positions(fx)
    link = {
        "fx_ok": fx is not None,
        "fx_generated_at": (fx or {}).get("generated_at"),
        "fx_age_min": fx_age,
        "fx_stale": fx_age is None or fx_age > FX_STALE_MIN,
        "fx_mode": (fx or {}).get("mode"),
        "fx_url": FX_APP_URL,
        "yen": yen_strength(fx, carry_pairs, now),
        "news_ok": news is not None,
        "news_generated_at": (news or {}).get("generated_at"),
        "news_warn": news_warn,
        "news": upcoming_news(events, now),
        "news_hold_min": NEWS_HOLD_MIN,
        "fx_positions": pos,
        "fx_risk": (fx or {}).get("risk"),
    }
    return link, events
