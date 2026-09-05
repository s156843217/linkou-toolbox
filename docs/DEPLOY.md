# 部署與上線 SOP

> 任何「上線、關站」動作前必讀。照著做，不要即興發揮。

## 0. 現況（2026-09-05 已收斂）

開發**直接在 `linkou-toolbox` 進行**，push `main` 即上線，**不再有 my-project↔toolbox 同步這件事**。`my-project` 已退役為歷史檔庫（詳見該 repo 的 `CLAUDE.md`）。四個獨立站（學區/房貸/租約/公車）已改為跳轉頁，導向本站對應資料夾，repo 與 Pages 保留不關閉。

## 1. 部署矩陣

| repo | 線上網址 | 上線方式 |
|---|---|---|
| linkou-toolbox | https://swcasa.com/ （2026-07-06 起自訂網域；舊 github.io 網址永久轉址過來） | push `main` → Pages 約 1 分鐘 |
| linkou-school-zone（=my-project 的 master） | https://s156843217.github.io/linkou-school-zone/ | **已退役＝跳轉頁**（2026-09-05 起，導向 swcasa.com/school/）；不要再更新內容 |
| linkou-mortgage | https://s156843217.github.io/linkou-mortgage/ | **已退役＝跳轉頁**（同上，導向 /mortgage/）；舊自動更新 cron 已刪除 |
| rent-tool | https://s156843217.github.io/rent-tool/ | **已退役＝跳轉頁**（同上，導向 /rent/） |
| linkou-bus | https://s156843217.github.io/linkou-bus/ | **已退役＝跳轉頁**（同上，導向 /bus/） |
| linkou-crm | https://s156843217.github.io/linkou-crm/ | push `main` |
| linkou-rental-mgmt | https://s156843217.github.io/linkou-rental-mgmt/ | push `main` |
| linkou-line-bot | https://mute-limit-6246linkou-line-bot.s156843217.workers.dev/ | push `main` → Cloudflare 自動 build |

驗證部署完成：
```
gh api repos/s156843217/<repo名>/pages/builds/latest --jq '.status'   # 出現 built 即完成
curl -s <線上網址> | grep "<這次改動的關鍵字>"                        # 確認新內容真的上線了
```

## 2. 資料檔有多份複本——誰是真相來源

| 檔案 | 真相來源 | 流向 |
|---|---|---|
| `linkou-data.js`（學區） | **toolbox** | 改完手動複製到 linkou-line-bot 再 push（見該 repo CLAUDE.md） |
| `mortgage-data.js` | **toolbox**（每月 1 號 Actions 自動更新地段與三類行情） | Actions 自動 commit 後本機記得 `git pull`；要手改（如產品文案）直接改這份 |
| `HOUSE` 門牌庫（在 linkou-data.js 內） | 同 linkou-data.js | toolbox 的 `update_prices.py` 抓本 repo 的 `linkou-data.js` |

開發工具（selftest、資料解析腳本等）都在本 repo 的 `tools/`。

## 3. 收斂紀錄（已於 2026-09-05 完成，過程存查）

過渡期（my-project dev 開發、同步到 toolbox 上線）已結束，以下六項全部完成：

1. **房貸 Actions 遷移** — 2026-07-03 提前完成；2026-09-05 補刪 linkou-mortgage 的 `.github/workflows/update-prices.yml`（關掉舊 cron）。
2. **四個獨立站改跳轉頁**（school-zone 的 master、mortgage、rent-tool、bus）— index.html 換成跳轉頁（2秒自動跳轉＋手動連結），repo 與 Pages 保留不關閉。
3. **LINE bot** 資料來源說明改為 toolbox（`linkou-line-bot/CLAUDE.md` 已更新）。
4. **my-project 收尾** — `tools/`（selftest 等）已搬到 toolbox；toolbox 已建 `.gitignore`；my-project 的 `CLAUDE.md` 已換成退役說明。
5. **制度更新** — `DECISIONS.md` 已記收斂完成；全域 `~/.claude/CLAUDE.md` 的 repo 地圖狀態欄已更新；memory 已更新。
6. **總驗證** — 四個舊網址皆已確認顯示跳轉頁（curl 驗證）；selftest.html 於新位置重跑全綠。下個月 1 號後應再確認 Actions 在 toolbox 跑成功。
