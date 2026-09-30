# 簡易POSアプリ

修正後の要件定義書・設計仕様書に基づく、レジ担当者向けの実装です。Next.jsの画面、BFF、FastAPI、SQLAlchemyのDBモデル、QR読取、Jest・pytestのテストを含みます。購買履歴表示とおすすめ表示は含みません。会計中の購入リストと確定後の取引記録は扱います。

## 最初にやること

1. ZIPファイルを展開し、`pos-app` フォルダーを開きます。
2. バックエンドを起動して、担当者のパスワードと練習用データを作ります。
3. 別のPowerShellでフロントエンドを起動します。
4. ブラウザで `http://localhost:3000` を開きます。

画面では商品ごとに税抜単価を表示し、購入リストの下に税抜合計・消費税・税込合計を表示します。まだAzureへの配置はしていないため、まずは自分のPC上で操作を確認できます。

## Visual Studio / VS Codeで開く

- **VS Code**：`pos-app.code-workspace` を開きます。PythonとTypeScriptの拡張機能を入れると編集しやすくなります。
- **Visual Studio**：`ファイル → 開く → フォルダー` で `pos-app` を選びます。実行にはPython・Node.jsの開発環境と、下記のターミナル操作が必要です。

Python 3.11以降、Node.js 20以降、npmを用意してください。以下はWindows PowerShellで、`pos-app` フォルダーを開いた後の操作です。

### 1. バックエンド

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

初回の `app.seed` で `cashier01` のパスワードを設定します。開発用会員 `M001`、商品 `P101`（税抜101円）、`P250`（250円）、`P000`（0円）、税率10%を作ります。QR画像は `backend/dev_qr` に作られます。**担当者QRはログイン用の秘密情報**なので、共有・Gitへの追加を避けてください。

### 2. フロントエンド（別のPowerShell）

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm ci
npm run dev
```

ブラウザで `http://localhost:3000` を開き、担当者ID `cashier01` と設定したパスワードでログインします。会員 `M001` または「会員IDなしで購入」を選び、商品 `P101` を検索して購入リストに追加します。101円の税は10円、税込合計は111円です。

PowerShellの場所が不明な場合は、エクスプローラーで `pos-app` フォルダーを開き、アドレス欄に `powershell` と入力してください。バックエンドとフロントエンドはそれぞれ別のウィンドウで動かしたままにします。

## QRコード

初期実装はブラウザのカメラで読みます。`localhost` またはHTTPSで開き、カメラ使用を許可してください。読めない場合はID・商品コードを手入力できます。会員QRは会員ID、商品QRは商品コード、担当者QRはランダムな資格トークンを含みます。外付けUSBリーダーは、キーボード入力として動く機種なら入力欄と併用できますが、機種別の動作確認は未実施です。

## テスト

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

```powershell
cd frontend
npm test
npm run build
```

pytestは隔離したSQLiteのテストDBを使い、ログイン、QR資格、会員・商品照会、金額再計算、重複保存防止などを検証します。Jestは画面の暫定税計算を検証します。テスト仕様書の全69件を自動化したものではありません。実機QR、障害復旧、ユーザーテストは別途実施します。

## 実装上の初期値と未確定事項

- 商品単価は**税抜の整数円**とし、0～9,999,999円を許容します。DBの型は `DECIMAL(10,2)` ですが小数円は拒否します。購入確定APIの金額が整数型であるための暫定判断です。
- 税率はDBの有効日付から選び、取引全体の税抜合計に掛けて1円未満を切り捨てます。現時点では全商品に共通の税率です。
- 購入リストは100行まで。1回の読み取りを1行とし、同じ商品も集約しません。空のリストは確定できません。
- QRの機器、コード発行・失効運用、入力形式は実環境で確定してください。担当者QRの失効はDBの `staff_qr_credential.revoked_at` で管理する初期設計です。
- Azure MySQLへの接続は `backend/.env` の `DATABASE_URL` を `mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME?charset=utf8mb4` の形式で設定します。Azureのリソース作成、ネットワーク、TLS証明書、バックアップ、DBマイグレーションと本番デプロイは別工程です。`app.seed` の `create_all` は開発用の初期化です。
- 本番時は `ENVIRONMENT=production` と十分長いランダムな `JWT_SECRET` を設定し、Next.jsとFastAPIの間を非公開ネットワーク／TLSで接続してください。JWTとリフレッシュトークンはHttpOnly Cookie、CSRFトークンは別Cookieとヘッダーで扱います。

## 主な構成

| 場所 | 内容 |
| --- | --- |
| `frontend/src/app/page.tsx` | ログイン・会員・商品・購入リスト・購入確定画面 |
| `frontend/src/components/QrScanner.tsx` | カメラによるQR読取 |
| `frontend/src/app/api/[...path]/route.ts` | Next.js BFF、Cookie、CSRF、API代理送信 |
| `backend/app/main.py` | FastAPIの認証・照会・購入確定API |
| `backend/app/models.py` | DBの担当者、会員、商品、税率、取引モデル |
| `backend/app/security.py` | JWT、Argon2id、QRトークン、更新・失効 |
