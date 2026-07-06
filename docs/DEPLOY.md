# 部署與同步 SOP

> 任何「上線、同步、關站」動作前必讀。照著做，不要即興發揮。

## 0. 先判斷現在是哪個階段

- **過渡期（現在 ～ 2026年7月底收斂完成前）**：開發在 `C:\repo\my-project` 的 `dev` 分支，`linkou-toolbox` 是上線副本，改完要照第 2 節同步。
- **收斂後**：直接在 `linkou-toolbox` 開發，push `main` 即上線，不再有同步這件事。
- **怎麼判斷已收斂**：看本資料夾 `DECISIONS.md` 有沒有「收斂完成」的紀錄；或看獨立站（如 https://s156843217.github.io/linkou-mortgage/ ）是否已變成跳轉頁。

## 1. 部署矩陣

| repo | 線上網址 | 上線方式 |
|---|---|---|
| linkou-toolbox | https://swcasa.com/ （2026-07-06 起自訂網域；舊 github.io 網址永久轉址過來） | push `main` → Pages 約 1 分鐘 |
| linkou-school-zone（=my-project 的 master） | https://s156843217.github.io/linkou-school-zone/ | push `master`（退役中，別再更新內容） |
| linkou-mortgage | https://s156843217.github.io/linkou-mortgage/ | push `main`（退役中） |
| rent-tool | https://s156843217.github.io/rent-tool/ | push `main`（退役中） |
| linkou-bus | https://s156843217.github.io/linkou-bus/ | push `main`（退役中） |
| linkou-crm | https://s156843217.github.io/linkou-crm/ | push `main` |
| linkou-rental-mgmt | https://s156843217.github.io/linkou-rental-mgmt/ | push `main` |
| linkou-line-bot | https://mute-limit-6246linkou-line-bot.s156843217.workers.dev/ | push `main` → Cloudflare 自動 build |

驗證部署完成：
```
gh api repos/s156843217/<repo名>/pages/builds/latest --jq '.status'   # 出現 built 即完成
curl -s <線上網址> | grep "<這次改動的關鍵字>"                        # 確認新內容真的上線了
```

## 2. 過渡期同步 SOP（my-project dev → toolbox）

1. 在 my-project dev 改完、照 `CHECKLIST.md` 驗證、commit。
2. 跑差異報告：`powershell -NoProfile -File C:\repo\my-project\tools\sync-toolbox.ps1`
3. 每一筆 DIFF 都要能說出「這是這次哪個 commit 造成的」；有解釋不了的差異 → 停下來問使用者。
4. 確認後套用：`powershell -NoProfile -File C:\repo\my-project\tools\sync-toolbox.ps1 -Apply`
5. `cd C:\repo\linkou-toolbox` → `git diff` 再肉眼看一次 → `git add -A` → commit（訊息沿用 dev 那則）→ `git push`。
6. 一分鐘後開線上網址驗證這次的改動。

注意：腳本只同步**網站檔白名單**。兩邊的 `CLAUDE.md`、`docs/`、`tools/`、`README.md` 各自獨立，永遠不同步。

## 3. 資料檔有多份複本——誰是真相來源

| 檔案 | 真相來源 | 流向 |
|---|---|---|
| `linkou-data.js`（學區） | 過渡期：my-project dev／收斂後：toolbox | → toolbox（腳本）→ linkou-line-bot（手動複製檔案再 push）|
| `mortgage-data.js` | **toolbox**（2026-07-03 起：每月 1 號本 repo 的 Actions 自動更新地段與三類行情） | Actions 自動 commit 後本機記得 `git pull`。此檔**不在** sync-toolbox.ps1 白名單——要手改（如產品文案）直接改 toolbox 這份，再複製回 my-project。⚠ 腳本遇當月資料量不足會「保留舊值」並在 log 註明，屬正常安全設計 |
| `HOUSE` 門牌庫（在 linkou-data.js 內） | 同 linkou-data.js | toolbox 的 `update_prices.py` 抓 `raw...linkou-toolbox/main/linkou-data.js`（已斷開對學區獨立站的依賴）。⚠ linkou-mortgage 的舊 pipeline 仍抓學區獨立站 master——該獨立站 repo 在 mortgage 關站前不能刪 |

## 4. 收斂 runbook（2026 年 7 月底執行，照順序、做完打勾）

前置：跑 `sync-toolbox.ps1` 確認 my-project 與 toolbox 無未同步差異。

1. **房貸 Actions 遷移** — ✅ **已於 2026-07-03 提前完成**（pipeline 已在 toolbox 跑通、線上驗證過）。
   - [ ] 只剩一步：關站時刪 linkou-mortgage 的 `.github/workflows/update-prices.yml`（關掉舊 cron），再處理該站跳轉。
2. **四個獨立站改跳轉頁**（school-zone 的 master、mortgage、rent-tool、bus）
   - [ ] 各 repo 的 `index.html` 換成跳轉頁：`<meta http-equiv="refresh">` 到 toolbox 對應資料夾頁＋一行手動連結；其餘網站檔可刪。
   - [ ] **不要刪 repo、不要關 Pages**——舊網址已發給客戶，跳轉要永遠活著。
3. **LINE bot**：資料來源說明改為 toolbox（`linkou-line-bot/CLAUDE.md` 同步更新）。
4. **my-project 收尾**：`tools/`（selftest 等）搬到 toolbox；toolbox 建 `.gitignore`（`reference/`、`price_data/`、`tdx-secret.json`、`*.xlsx`）；my-project 的 `CLAUDE.md` 換成「已退役、僅存歷史與本機資料」說明。
5. **更新制度**：`DECISIONS.md` 記收斂完成；全域 `~/.claude/CLAUDE.md` 的 repo 地圖狀態欄更新；memory 更新。
6. **總驗證**：四個舊網址都會跳轉；toolbox 五頁全過 `CHECKLIST.md`；下個月 1 號後確認 Actions 在 toolbox 跑成功。
