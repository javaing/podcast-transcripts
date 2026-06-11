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

## 新增一集（概要）

```bash
# 1. 下載音檔到 transcripts/<slug>/episode.mp3
# 2. 轉錄與翻譯
python transcripts/<slug>/process_episode.py
# 3. 套用術語修正
python scripts/fix_episode.py transcripts/<slug>
# 4. 產生網頁
python scripts/build_site.py
```
