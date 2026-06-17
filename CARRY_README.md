# FX Carry Navi（キャリーナビ）— 金利差特化アプリ

元の **FX Navi（USD/EUR/GBP/AUD 円・スキャル/デイ）では扱わない**、金利差が大きいクロス円7種に特化した
スイング/ポジション向けアプリです。GMOコイン外国為替FX Public API + GitHub Actions + LINE/メール + ダッシュボード。

## 対象ペアと金利差（2026-06-15時点・要確認）
高金利通貨を買って円を売る＝**買いで正スワップ**になる「キャリー」候補です。

| ペア | 高金利側 政策金利 | 対円 金利差 |
|---|---|---|
| TRY/JPY | トルコ 40.00% | **+39.25%** |
| ZAR/JPY | 南アフリカ 7.00% | +6.25% |
| MXN/JPY | メキシコ 6.75% | +6.00% |
| HUF/JPY | ハンガリー 6.25% | +5.50% |
| NZD/JPY | NZ 2.25% | +1.50% |
| CAD/JPY | カナダ 2.25% | +1.50% |
| SEK/JPY | スウェーデン 1.75% | +1.00% |

（日本 BoJ 0.75%）。金利は変動します。`carry_signal.py` の `POLICY_RATES` を編集して更新してください。
出典: 各中央銀行発表および金利集計（BoJ/CBRT/SARB 2026-05-28/Banxico 2026-03-26/MNB/RBNZ/BoC/Riksbank, 2026-06）。

## 判定ロジック
- **トレンド**（4時間足のテクニカル）：EMA(21/55)・MACD・RSI・ボリンジャー、ADXで強度調整 → -1〜+1
- **キャリー**：金利差（スワップ方向）。全ペア対円プラス＝買いで正スワップ
- **総合判定**：
  - トレンド ≥ +0.25 → **買い（順張り）**（金利差を取りつつ価格も上向き）
  - −0.25〜+0.25 → **買い寄り（押し目検討）**
  - ≤ −0.25 → **様子見（下落中）**（スワップが値下がりで相殺される懸念）
- **キャリー対リスク C/R＝金利差 ÷ 年率ボラ**：高いほど「金利差のわりに値動きが穏やか」。これで全ペアをランキング。

## TP/SL（ATR基準・価格と%で表示）
ペアごとに価格スケールが大きく違う（TRY 3.4 / HUF 0.53 / CAD 114…）ため、**pipsではなく価格と%**で表示します。
- SL = 現在値 − **2.0×ATR(4h)**
- TP = 現在値 + **3.0×ATR(4h)**（リスクリワード 1:1.5）
- 倍率は `SL_ATR` / `TP_ATR` で調整可

## ⚠️ リスク（重要）
- キャリー取引は、**急落（アンワインド）や新興国通貨の減価**で、スワップ益を一気に失う尾部リスクがあります。
- 特に **TRY は超高金利＝高インフレ・減価リスク特大**。少額・長期前提で。
- TRY/ZAR/MXN/HUF は新興国通貨として警告バッジを表示します。
- C/R は過去ボラ基準で、**ギャップ・急落は測りきれません**。表示は判断補助で、利益も最適値も保証しません。自己責任で。

## セットアップ
元のFX Naviと同じリポジトリに追加してOK（別ページとして共存します）。
1. 次を配置：`carry_signal.py`／`carry.html`／`carry-sw.js`／`carry.webmanifest`／`carry-icon-180.png`／`carry-icon-192.png`／`carry-icon-512.png`／`carry_status.json`／`.github/workflows/carry-signal.yml`
2. 依存は `requests` のみ（既存の `requirements.txt` でOK）
3. **Secrets はFX Naviと共用**：`LINE_CHANNEL_ACCESS_TOKEN`／`GMAIL_ADDRESS`／`GMAIL_APP_PASSWORD`／`MAIL_TO`（同じrepoなら設定済み）
4. GitHub Pagesで開く：`https://ユーザー名.github.io/リポジトリ名/carry.html`
5. iPhoneのSafariで「ホーム画面に追加」→ PWAとして全画面表示
6. （任意）ライブ価格：`carry.html` の `LIVE_PRICE_URL` に**FX Naviと同じWorker URL**を入れると、現在値が15秒ごとに更新されます（Workerの改修は不要）

## 動作
- ワークフローは**毎時5分**に実行（スイング=4時間足なので1時間ごとで十分）
- `買い（順張り）` が出たペアをLINE/メール通知（金利差・スワップ方向・トレンド・C/R・TP/SL）
- 市場クローズ中（週末）は通知しません
- 手動実行の `test` を true にするとテスト通知

## ファイル
| ファイル | 役割 |
|---|---|
| carry_signal.py | エンジン（金利差×トレンド×ボラ、C/Rランキング、通知、carry_status.json生成）|
| carry.html | ダッシュボード（ランキング＋ペア別カード、PWA）|
| carry-sw.js | Service Worker（オフライン/インストール対応）|
| carry-icon-180/192/512.png | 専用アプリアイコン（金コイン＋¥＋上昇アロー）|
| carry.webmanifest | PWA設定 |
| carry_status.json | 画面が読む状態ファイル（Actionが毎時更新）|
| .github/workflows/carry-signal.yml | 毎時実行のワークフロー |
| worker.js | （FX Naviと共用。ライブ価格を使う場合のみ）|


---

## アプリ化（最高品質・FX Naviと同等のライブ機能）
このダッシュボードは完全なPWA＋ライブ計算に対応しています。

### Service Worker（インストール対応）
`carry-sw.js` を同じ場所に置くと、シェルをキャッシュしてオフラインでも起動でき、
「ホーム画面に追加」で**ネイティブアプリのように全画面起動**します。データ（carry_status.json・Worker）は常に最新取得（network-first）。

### ライブ計算（画面側で4時間足を再計算）
`LIVE_PRICE_URL` に **FX Naviと同じWorker URL** を入れると：
- **現在値**：15秒ごとに更新
- **トレンド・C/R・判定・ランキング・TP/SL**：約3分ごとに画面側で再計算（毎時のAction待ち不要）
- 計算式はPython版と**完全一致を検証済み**
- ヘッダに「● LIVE計算 時刻」を表示

### ライブLINE通知
`買い（順張り）`に転じたペアを、Worker経由でLINE送信（**FX NaviのWorker・LINE_TOKEN・NOTIFY_KEYをそのまま共用**）。
- `NOTIFY_KEY` をWorkerに設定しているなら、`carry.html` の `const NOTIFY_KEY = "";` にも同じ値を入れる
- 同じ通貨は30分間は再送しない（連投防止）。文面は「⚡ライブ」始まり
- **画面（PWA）を開いている間のみ**動作。閉じている時は毎時のActionが通知を担当

※Worker・LINE_TOKEN・NOTIFY_KEYはFX Naviと共用でOK（追加設定不要）。`LIVE_PRICE_URL` が空ならライブ機能はオフで、毎時のAction更新のみになります。


---

## 専用アイコン・デザイン
ホーム画面用に**専用アイコン**を同梱（`carry-icon-180/192/512.png`）。
金のコインリング＋¥＋グローする緑の上昇アローで「クロス円のキャリー（右肩上がりの利回り）」を表現。
- iOS：`carry-icon-180.png`（apple-touch-icon、角丸は自動）
- Android/Chrome：`carry-icon-192/512.png`（maskable対応、`theme_color #0a0c10`）
- ヘッダーにも同じエンブレム（SVG）を表示し統一感

iPhoneでは Safari で `carry.html` を開き「ホーム画面に追加」→ アイコンから全画面のアプリとして起動できます。
