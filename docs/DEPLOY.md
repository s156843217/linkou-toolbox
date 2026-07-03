# 部署與同步 SOP

> 任何「上線、同步、關站」動作前必讀。照著做，不要即興發揮。

## 0. 先判斷現在是哪個階段

- **過渡期（現在 ～ 2026年7月底收斂完成前）**：開發在 `C:\repo\my-project` 的 `dev` 分支，`linkou-toolbox` 是上線副本，改完要照第 2 節同步。
- **收斂後**：直接在 `linkou-toolbox` 開發，push `main` 即上線，不再有同步這件事。
- **怎麼判斷已收斂**：看本資料夾 `DECISIONS.md` 有沒有「收斂完成」的紀錄；或看獨立站（如 https://s156843217.github.io/linkou-mortgage/ ）是否已變成跳轉頁。

## 1. 部署矩陣

| repo | 線上網址 | 上線方式 |
|---|---|---|
| linkou-toolbox | https://s156843217.github.io/linkou-toolbox/ | push `main` → Pages 約 1 分鐘 |
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
| `mortgage-data.js` 的 LINKOU_ZONES 段 | **linkou-mortgage**（每月 1 號 Actions 自動更新，方向跟其他檔相反！） | 每月更新後：`cd C:\repo\linkou-mortgage; git pull`，把 `<<AUTO-ZONES-START>>`～`END` 段的數字人工帶回 my-project 與 toolbox 的 `mortgage-data.js`（兩邊格式不同，比對數字搬，不要整檔覆蓋）|
| `HOUSE` 門牌庫（在 linkou-data.js 內） | 同 linkou-data.js | ⚠ `linkou-mortgage/update_prices.py` 會線上抓 `raw.githubusercontent.com/s156843217/linkou-school-zone/master/linkou-data.js`——學區獨立站關掉前**必須**先改這個 URL（見第 4 節步驟 1）|

## 4. 收斂 runbook（2026 年 7 月底執行，照順序、做完打勾）

前置：跑 `sync-toolbox.ps1` 確認 my-project 與 toolbox 無未同步差異。

1. **房貸 Actions 遷移（最優先，有跨 repo 依賴）**
   - [ ] 複製 linkou-mortgage 的 `update_prices.py`、`road_zone_map.csv`、`林口價格地圖.geojson`、`.github/workflows/update-prices.yml` 到 toolbox。
   - [ ] 改 `update_prices.py` 內 HOUSE 來源 URL：`linkou-school-zone/master` → `linkou-toolbox/main`。
   - [ ] toolbox 的 `mortgage-data.js` 先照 linkou-mortgage 的格式加上 `<<AUTO-ZONES-START>>`／`END` 標記（腳本只覆寫標記之間）。
   - [ ] push 後 `gh workflow run update-prices.yml` 手動跑一次，確認成功、線上房貸頁數字正常。
   - [ ] 成功後刪 linkou-mortgage 的 workflow 檔（關掉舊 cron），再處理該站跳轉。
2. **四個獨立站改跳轉頁**（school-zone 的 master、mortgage、rent-tool、bus）
   - [ ] 各 repo 的 `index.html` 換成跳轉頁：`<meta http-equiv="refresh">` 到 toolbox 對應資料夾頁＋一行手動連結；其餘網站檔可刪。
   - [ ] **不要刪 repo、不要關 Pages**——舊網址已發給客戶，跳轉要永遠活著。
3. **LINE bot**：資料來源說明改為 toolbox（`linkou-line-bot/CLAUDE.md` 同步更新）。
4. **my-project 收尾**：`tools/`（selftest 等）搬到 toolbox；toolbox 建 `.gitignore`（`reference/`、`price_data/`、`tdx-secret.json`、`*.xlsx`）；my-project 的 `CLAUDE.md` 換成「已退役、僅存歷史與本機資料」說明。
5. **更新制度**：`DECISIONS.md` 記收斂完成；全域 `~/.claude/CLAUDE.md` 的 repo 地圖狀態欄更新；memory 更新。
6. **總驗證**：四個舊網址都會跳轉；toolbox 五頁全過 `CHECKLIST.md`；下個月 1 號後確認 Actions 在 toolbox 跑成功。
