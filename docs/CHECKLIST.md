# 驗證清單（改完之後、回報之前）

> 「完成」的三級定義見全域 `~/.claude/CLAUDE.md` 第 4 節：L0 已修改 → L1 已自檢 → L2 已實測。
> 回報時標明等級，並給使用者具體步驟＋預期結果。本檔的路徑以開發主場為準（過渡期 = `C:/repo/my-project`）。

## 判斷表：改了什麼 → 跑哪些清單

| 改動的檔案 | 必跑 |
|---|---|
| `linkou-data.js` | selftest ＋ A 學區 ＋ D 公車（兩頁都吃這份資料） |
| `style.css` | A～E **全部**開一遍（共用樣式，一處改壞五頁遭殃） |
| `school/index.html` | A |
| `mortgage/index.html`、`mortgage-data.js` | B |
| `rent/index.html`、`rent/rent-data.js` | C |
| `bus/index.html`、`bus-data.js` | D |
| 根 `index.html`（首頁）或導覽列 | E |

## selftest：學區資料一致性自檢

開 `file:///C:/repo/my-project/tools/selftest.html` → 必須**全綠**。有紅字先修資料再往下。

AI 可以不勞煩使用者、自己用 headless Edge 跑：
```powershell
& "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --virtual-time-budget=5000 --dump-dom "file:///C:/repo/my-project/tools/selftest.html" | Out-File "$env:TEMP\st.html" -Encoding utf8
Select-String -Path "$env:TEMP\st.html" -Pattern 'id="summary"[^<]*'   # 看到「全數通過」才算過；有錯誤時 grep class="fail" 的列
```
同一招（dump-dom 或 `--screenshot`）也可用來驗證其他頁面有沒有算出結果、版面有沒有爆。

## A. 學區頁

開 `file:///C:/repo/my-project/school/index.html`：
1. 輸入這次改動的社區名（沒有就用「世紀長虹」）→ 顯示里＋鄰＋國小/國中，地圖 pin 落在**林口**（pin 飛到外縣市＝門牌座標壞了）。
2. 輸入門牌地址（例：`文化三路一段356號`）→ 能解析出里鄰與學區。
3. 輸入額滿學校（頭湖/南勢/新林/東湖國小）學區內的地址 → 出現紅字額滿警示與最後設籍日。
4. 幼兒園區塊有資料、免責提醒（`.disc` 區塊）還在。

## B. 房貸頁

開 `mortgage/index.html`：
1. 輸入月收入（例 8 萬）→ 月付金、可購總價、可購坪數都有數字、**沒有 NaN**。
2. 地段卡（三井/南勢/家樂福等）每張都有單價與筆數。
3. 記得：可購坪數預設含 1 車位 200 萬（已拍板，勿改）。

## C. 租約頁

開 `rent/index.html`：
1. 「載入範例」→「產生合約」→ 合約全文出現，範例資料是**假資料**（看到疑似真實身分證字號＝出大事，立刻回報）。
2. 「列印 / 存 PDF」預覽：分頁正常、浮動 toast 沒被印出來。
3. 「匯出 Word」下載的 .doc 開得起來、中文正常。

## D. 公車頁

開 `bus/index.html`：
1. 輸入社區名 → 列出附近站牌與路線。
2. 點一條路線 → 地圖聚焦到住家附近的上車站。

## E. 首頁與導覽

開根 `index.html`：五張工具卡／導覽列連結全部點得通；手機寬度（DevTools 切 375px）導覽列橫向滑動、不撐寬頁面。

## 通用（每次都要）

- F12 開 Console：**沒有紅色錯誤**。
- 只有使用者親自操作過才算 L2；你自己開檔檢查算 L1。
- 上線後（push 完）用 `curl -s <線上網址> | grep <關鍵字>` 確認改動真的到了線上。
