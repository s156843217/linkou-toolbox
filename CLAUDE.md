# CLAUDE.md — 林口置產工具箱（整合站／正式站）

> 這是**正式上線的整合站**：https://s156843217.github.io/linkou-toolbox/
> push `main` 即自動部署（GitHub Pages，約 1 分鐘）。改壞就是線上壞。
> 通用守則（開工儀式、完成定義、紅線）在全域 `~/.claude/CLAUDE.md`，先讀它。

## ⚠ 現在是過渡期還是收斂後？（動手前先判斷）

- **過渡期（～2026 年 7 月底）**：開發主場在 `C:\repo\my-project`（dev 分支），本 repo 是上線副本。
  **不要直接在這裡改網站檔**——改了會被下次同步蓋掉。應該去 my-project 改，再照 `docs/DEPLOY.md` 第 2 節同步過來。
- **收斂後**：本 repo 就是開發主場，直接在這裡改、驗證、push。
- 怎麼判斷：看 `docs/DECISIONS.md` 有沒有「收斂完成」紀錄。

## 站台結構

```
index.html        首頁（工具卡＋導覽）
school/index.html 林口學區快查（吃 ../linkou-data.js）
mortgage/index.html 房貸試算（吃 ../mortgage-data.js）
rent/index.html   租約產生器（吃 rent-data.js）
bus/index.html    公車路線（吃 ../bus-data.js 與 ../linkou-data.js）
style.css         全站共用樣式（CSS 變數＝設計系統）
img/              圖片
docs/             SOP 文件（不是網站內容，是給 AI/接手者的制度）
```

## 路由表：做某類事之前，先讀對應文件

| 任務 | 先讀 |
|---|---|
| 上線、同步、關獨立站 | `docs/DEPLOY.md` |
| 改學區/社區/幼兒園/門牌資料 | `docs/DATA-UPDATE.md` |
| 任何改動後的驗證 | `docs/CHECKLIST.md` |
| 不確定某件事是否已有定論 | `docs/DECISIONS.md` |
| 115 學年度學區切換 | `docs/DATA-UPDATE.md` 第 4 節 ＋ memory `linkou-115-switch-plan` |

## 核心原則

1. **資料與邏輯分離**：改資料只動 `*-data.js`，改功能才動 `index.html`。
2. **純前端、零建置、無框架**：直接開檔即可執行。不引入 npm/打包工具（本機也沒有 Node）。
3. **設計系統**：色彩字型都在 `style.css` 的 `:root` CSS 變數（陶土橘 `--clay`、墨綠 `--teal`、米色 `--bg`；標題 Noto Serif TC、內文 Noto Sans TC）。新 UI 重用 `.panel`、`.btn` 等既有 class，不要硬寫色碼、不要另起爐灶。
4. 外部服務：Leaflet + OpenStreetMap（地圖）、Nominatim（地理編碼，**必須保留 350–900ms 節流**）、Google Fonts。全部 CDN。

## 本 repo 專屬紅線

- 頁尾營業員姓名/電話/LINE/證照字號是**真實資料**，未經指示不動。
- 學區頁免責提醒（`.disc`，含 115 學年里鄰重編警語）不准刪。
- 租約條文（`CLAUSES`）是法定範本文字，不准「順手潤飾」。
- `mortgage-data.js` 的地段數字由 linkou-mortgage 的 Actions 每月自動更新（見 `docs/DEPLOY.md` 第 3 節），不要手改成舊數字。
- 這是公開 repo：任何含金鑰、個資的檔案（`tdx-secret.json`、`reference/`）永遠不進來。
