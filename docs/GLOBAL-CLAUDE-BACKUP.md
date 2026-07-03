# 全域規範（這台電腦所有專案共用）

> 每個 Claude session 的固定守則。專案細節看各 repo 自己的 CLAUDE.md；
> 跨 repo 的 SOP 集中在 `C:\repo\linkou-toolbox\docs\`（DEPLOY / CHECKLIST / DATA-UPDATE / DECISIONS）。
> 本檔不在 git 內，備份副本在 `C:\repo\linkou-toolbox\docs\GLOBAL-CLAUDE-BACKUP.md`，兩份要一起改。

## 0. 使用者是誰

- 房仲（太平洋房屋・林口捷運加盟店），**不是職業工程師**。解釋技術決定時用一句話講清楚「為什麼」，少用術語。
- 所有回應、程式註解、commit 訊息一律**繁體中文**，絕不混入日文、簡體字（連串場語也不行）。
- 他的專案都是自用小工具：純前端、零建置、重視「簡單可靠、開檔即用」，不追求工程完美。未經他要求，不重構、不引入框架或建置工具。

## 1. 環境事實（永遠成立，不要浪費時間重試）

- Windows 11 + PowerShell 5.1（沒有 `&&`，鏈接用 `;` 或 `if ($?)`）。
- **本機沒有 Node**；`python` 是 WindowsApps 空殼，**執行不了**。不要嘗試 npm / node / pip。
  需要 Python 的工作（如房貸實價登錄更新）只能在 GitHub Actions 雲端跑，用 `gh workflow run` 觸發。
- 測試網頁 = 瀏覽器開 `file:///C:/repo/.../xxx.html`（所有工具都設計成 file:// 可完整運作）。
- **沒有 Node 但有 headless Edge**——你可以自己執行網頁 JS 來驗證，不必每次都請使用者開頁面：
  ```powershell
  # 取「JS 執行完之後」的 DOM（驗證頁面真的算出東西）
  & "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --virtual-time-budget=5000 --dump-dom "file:///C:/repo/....html" | Out-File "$env:TEMP\dom.html" -Encoding utf8
  # 截圖後用 Read 工具親眼看版面
  & "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --screenshot="$env:TEMP\shot.png" --window-size=1280,900 "file:///C:/repo/....html"
  ```
- `git`、`gh`（GitHub CLI）可用。所有部署靠 GitHub Pages 或 Cloudflare，**push 即上線**（見下表）。

## 2. Repo 地圖（動手前先確認自己在哪）

| 本機目錄 C:\repo\ | 是什麼 | push 會發生什麼 | 狀態 |
|---|---|---|---|
| `my-project` | 網站**開發主場（過渡期）**。⚠ remote 名叫 `linkou-school-zone` | push `dev`：無部署效果。push `master`：更新學區獨立站（退役中，勿隨意動） | 開發中，7月底後主場移往 toolbox |
| `linkou-toolbox` | **整合站＝正式站**（首頁+school/mortgage/rent/bus）。未來開發主場 | push `main` → Pages 自動上線 | 上線中 |
| `linkou-mortgage` | 房貸獨立測試站。⚠ 掛**每月自動更新 Actions**（每月1號） | push `main` → Pages 上線 | 退役中（7月底關，關前 Actions 要先遷移） |
| `rent-tool` | 租約獨立測試站 | push `main` → Pages 上線 | 退役中（7月底關） |
| `linkou-bus` | 公車獨立測試站 | push `main` → Pages 上線 | 退役中（7月底關） |
| `linkou-crm` | 買方追蹤 CRM（兩人用，Supabase） | push `main` → Pages 自動上線 | 使用中 |
| `rental-mgmt` | 套房代管記帳。⚠ remote 名叫 `linkou-rental-mgmt` | push `main` → Pages 自動上線 | 使用中 |
| `linkou-line-bot` | LINE 官方帳號學區 bot（Cloudflare Worker） | push `main` → Cloudflare 自動 build+deploy | 使用中 |

**最容易搞錯的一件事**：`my-project` 的 remote 叫 `linkou-school-zone`，但它是整個網站的開發主場；它的 `master` 反而是「學區獨立站」部署版（結構跟 dev 不同）。日常一律待在 `dev`。

## 3. 開工儀式（每個 session 改任何檔案之前，照順序做）

1. 跑 `git branch --show-current`、`git status -sb`、`git remote get-url origin`，對照上表確認 repo 與分支。
2. 讀該 repo 的 `CLAUDE.md`。
3. 任務涉及「上線 / 同步 / 資料更新 / 關站」→ 先讀 `C:\repo\linkou-toolbox\docs\DEPLOY.md` 或 `DATA-UPDATE.md`。
4. 使用者的要求若與過去決定相衝（查 `C:\repo\linkou-toolbox\docs\DECISIONS.md` 與 memory）→ **把衝突說出來請他確認**，不要默默照做、也不要默默拒絕。已列在 DECISIONS.md 的事**不要重新問**。

## 4. 「完成」的定義（回報時必須誠實標明等級）

改完 ≠ 完成。三個等級：

- **L0 已修改**：檔案改好，尚未任何驗證。
- **L1 已自檢**：重讀過自己的 diff；若動到學區資料，用 headless Edge 跑過 `tools/selftest.html` 全綠。
- **L2 已實測**：在瀏覽器實際操作過對應功能，看到預期結果。用 headless Edge 的 dump-dom／截圖看到預期結果可算 L2；**使用者親測仍是最終標準**，牽涉列印、匯出 Word、手機版面時一定要請他測。

規則：
- 回報一律標明等級，並給使用者**具體的驗證步驟＋預期結果**。範例：
  「已改好並自檢（L1）。請開 `file:///C:/repo/my-project/school/index.html`，輸入『世紀長虹』，應顯示南勢里19鄰、南勢國小。確認 OK 我再 commit。」
- **禁止**：沒開過頁面卻說「測試通過」；改了共用檔（`style.css`、`linkou-data.js`）卻只檢查一個工具頁。
- 每類改動要驗證什麼 → `C:\repo\linkou-toolbox\docs\CHECKLIST.md`。

## 5. 紅線（違反＝造成真實傷害，沒有例外）

1. **真實個資**：`rent/reference/`（租約含身分證號）、`reference/`、`price_data/`、`tdx-secret.json` 已 gitignore——永遠不准 commit、不准把內容貼進任何會公開的檔案。範例／測試資料一律用假資料。
2. 頁尾**營業員姓名/電話/LINE/證照字號**、rental-mgmt 的**屋主匯款帳戶**是真實資料：未經指示不改動、不在範例亂填。
3. **法定契約條文**（租約產生器 `CLAUSES`）與**學區免責提醒**（`.disc` 區塊）：不准刪、不准「順手潤飾」。
4. **Nominatim** 線上地理編碼有流量限制：呼叫它的程式必須保留 350–900ms 節流。
5. 不改沒被點名的檔案；順手重構＝踩線。

## 6. Commit 慣例

- 訊息格式照既有風格：`範圍:做了什麼`（繁中一行為主）。例：`學區資料:新增社區「世紀長虹」(南勢里19鄰)`。
- 告一段落就提醒 commit，並附一句判斷：「commit 即存檔，diff 已完整記錄」——只有「多步驟做到一半的計畫、決策理由、踩過的雷」才值得寫進 HANDOFF/md，小改動不用。
- `my-project` 的改動 commit 到 `dev`；上線另有 SOP（`docs/DEPLOY.md`），**不要自行 push master 或自行 cherry-pick**。
- 新的重大決定拍板時：追記到 `C:\repo\linkou-toolbox\docs\DECISIONS.md`（一行：日期｜決定｜原因）。
