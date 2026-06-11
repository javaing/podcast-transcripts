# podcast-transcripts

英文 podcast 中文逐字稿文集，以 GitHub Pages 發布。

## 線上閱讀

https://javaing.github.io/podcast-transcripts/

## 目錄結構

- `index.html` — 文集首頁
- `episodes/` — 各集 HTML 頁面
- `transcripts/` — 原始轉錄檔（txt / md / json）
- `glossary.json` — 翻譯術語表（不翻譯詞彙 + 修正對照）
- `scripts/` — 轉錄、修正、建站腳本

## 術語規則

翻譯時保留英文原文：

- 節目名（如 Waiting To Be Signed）
- 平台名（如 fxhash、Tezos、Art Blocks）
- 人名

詳見 `glossary.json`。

## 一鍵處理（推薦）

```bash
python scripts/process_url.py "https://creators.spotify.com/pod/profile/.../episodes/..." --push
```

流程：解析 RSS → 下載 MP3 → Whisper 轉錄 → 術語保護翻譯 → 產生網頁 →（可選）推送到 GitHub Pages。

## 手動步驟（進階）

```bash
python scripts/fix_episode.py transcripts/<slug>
python scripts/build_site.py
```
