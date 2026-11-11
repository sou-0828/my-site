# note自動販売カンパニー

AI社員6人で「リサーチ → 企画 → 執筆 → 検品 → デザイン → 営業」を毎朝自動で回し、noteを売る仕組みです。

| 担当 | ファイル | 仕事 | 使うデータ |
|---|---|---|---|
| リサーチ | `company/research.py` | 毎朝 X・Threads から伸びているポストを集め、Web検索で売れ筋テーマも補完し、「売れるテーマ」と「勝ちフック」を抽出 | X API / Threads API / Web検索 |
| 企画 | `company/planner.py` | 過去の売上と今日のリサーチを照らし合わせ、次に出すnoteを3案出して1つに決める（価格・目次・無料ラインまで） | `data/sales.csv`, `state/published.json` |
| 執筆 | `company/writer.py` | 売れたnoteとセールスレターの型を学び、無料部分/有料部分つきで本文を書く | `data/notes/`, `data/letters/` |
| 検品 | `company/reviewer.py` | **執筆とは別のAI（Sonnet）** が「AIっぽい言い回し」だけを直す。AIには置換リストしか返させず、適用はプログラム側で行うため、内容・数字・構成・有料ライン・見出しは変わらない | 下書き |
| デザイン | `company/designer.py` | 表紙（1280×670）と記事内の図解をHTMLでデザインし、PNGに書き出して本文に差し込む | 本文 |
| 営業 | `company/sales.py`, `publisher.py` | X/Threads用の集客ポストを作り、予約投稿キューに登録。時刻になったら自動投稿 | 本文の無料部分・勝ちフック |

## 1日の流れ

```
06:00  GitHub Actions が起動（自動）
       リサーチ → 企画 → 執筆 → 検品 → デザイン → 営業（下書き）
       ↓ 成果物は Actions の Artifacts に保存（article.md + images/）
あなた  article.md と画像を note に貼って公開（※noteに公式APIが無いため、ここだけ手動）
       ↓ 公開URLを渡す
       Actions「note会社 / 予約投稿」を手動実行し launch_day と note_url を入力
       → 営業ポストが次の投稿枠（config.toml の slots）に自動で予約される
15分毎 時刻が来たポストを X / Threads に自動投稿
```

公開ボタンだけ人が押すのは、note に公式の投稿APIが無いことに加えて、有料記事を中身を見ずに出さないための最終チェックも兼ねています。

## セットアップ

### 1. データを入れる（ここが売上を左右します）

- `data/sales.csv` … noteのダッシュボードの数字を転記（今入っているのはサンプルなので消してください）
- `data/notes/` … 売れた自分のnoteの本文を 1本 = 1ファイル で
- `data/letters/` … 成約したセールスレター・LP・販売文を 1本 = 1ファイル で
- `config.toml` … ジャンル、読者、書き手のキャラ、検索キーワード、投稿時刻

### 2. APIキーを用意する

| キー | 用途 | 無いとどうなる |
|---|---|---|
| `ANTHROPIC_API_KEY` | 全担当 | 動きません（必須） |
| `X_BEARER_TOKEN` | X検索（リサーチ） | Web検索だけでリサーチ |
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | Xへの投稿 | X投稿が `failed` になる |
| `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` | Threads検索・投稿（`threads_keyword_search`, `threads_content_publish` 権限） | 同上 |

X の検索・投稿には X API の有料プランが必要です。

### 3-a. GitHub Actions で毎朝動かす

1. リポジトリの Settings → Secrets and variables → Actions に上のキーを登録
2. `.github/workflows/note-company-daily.yml` と `note-company-publish.yml` がデフォルトブランチ（main）に入れば、スケジュール実行が始まります

> ⚠ **公開リポジトリでは使わないでください。** Artifacts（有料部分を含む原稿）は、公開リポジトリだと誰でもダウンロードできます。private リポジトリにこの `note-company/` フォルダごと移すのがおすすめです。

### 3-b. 自分のPCで動かす

```bash
cd note-company
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # 中身を埋めて
set -a; source .env; set +a

python -m company daily                      # 制作ライン一式
python -m company launch --day 2026-11-11 --url https://note.com/xxx/n/yyy
python -m company queue                      # 予約状況を確認
python -m company publish-due --dry-run      # 投稿せずに確認
```

cron 例: `*/15 * * * * cd /path/note-company && python -m company publish-due`

途中で失敗したら、その担当から再開できます: `python -m company daily --from review`

## 出力（`output/YYYY-MM-DD/`）

| ファイル | 中身 |
|---|---|
| `research.json` / `research_raw.json` / `research_web.md` | リサーチ結果と生データ |
| `plan.json` | 売上から読み取った法則、3案、採用理由 |
| `draft.md` → `reviewed.md` → **`article.md`** | 執筆 → 検品後 → 画像差し込み済みの完成原稿 |
| `review_log.json` | 検品担当が直した箇所の before/after（適用されなかった提案も理由つき） |
| `images/cover.png`, `images/fig-*.png` | 表紙と図解（`.html` も残るので手直し可能） |
| `sales.json` | 集客ポストと戦略 |

## 運用メモ

- モデルは `config.toml` の `[models]` で変更できます（標準は執筆系が Claude Opus 5.5、検品が Claude Sonnet 5.5）。安全上の理由で応答が拒否された場合は、APIのサーバー側フォールバックで別モデルに自動で切り替わります。
- 執筆担当は材料にない数字を作らず `〇〇` と書くようにしてあります。公開前に必ず自分の実数で埋めてください。
- 集客ポストは誇大表現・実績の捏造を禁じていますが、最終責任は投稿者にあります。`python -m company queue` で予約内容を確認し、問題があれば `state/queue.json` を直接編集してください（`status` を `draft` に戻せば投稿されません）。
