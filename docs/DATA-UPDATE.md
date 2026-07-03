# 資料更新 SOP（學區為主，含房貸/公車資料）

> 原則：**要改資料只改 data 檔，不動各頁 index.html 的邏輯。**能在 data 檔解決的，就不要碰邏輯。

## 1. linkou-data.js 內的物件對照（改資料前先找對物件）

| 物件 | 內容 | 常見改動 |
|---|---|---|
| `COMMUNITY` | 社區 → 里鄰對照（900+ 筆，最大宗） | 新增社區、改里鄰 |
| `ALIASES` | 社區俗稱字典（別名 → 官方報備名） | 客戶慣稱查不到時新增 |
| `LI` | 各里 → 國小/國中學區規則 | ⚠ 學年度調整才動，動前讀第 4 節 |
| `SCHOOLS` | 各校地址/電話/網站 | 電話網址變更 |
| `INFO` | 各校亮點/介紹話術 | 話術更新 |
| `FULL_ES` / `CITY_FREE_ES` | 額滿國小 / 全市自由學區國小 | 每年公告後更新 |
| `FULL_DATA` | 額滿學校歷年最後設籍日 | 每年公告後更新 |
| `KG_PUBLIC` / `KG_PRIVATE` | 公立(非營利)/私立幼兒園 | 每年名額公告後更新 |
| `LK_GEO` | 各里界線 GeoJSON（`properties.li`＝里名） | 里界重劃才動 |
| `HOUSE` | 門牌 → 里鄰＋座標索引 | 只能整批重建，見第 5 節 |

`COMMUNITY` 一筆的格式：
```js
"世紀長虹":{"addr":"林口區忠孝三路61號","li":"南勢里","lin":19}
// 特例：{"addr":"...","unk":1} = 里鄰不明；{"addr":"...","cands":["仁愛里","湖南里"]} = 跨里候選
```
`ALIASES` 的值必須是 `COMMUNITY` 裡存在的正式名稱，否則查詢會斷。

## 2. 標準流程（新增/修改一筆社區為例）

1. 在開發主場（過渡期＝`my-project` dev）改 `linkou-data.js` 對應物件。
2. 開 `file:///C:/repo/my-project/tools/selftest.html` → 全綠。
3. 開學區頁實測**改的那一筆**（照 CHECKLIST.md 的 A）。
4. commit，格式：`學區資料:新增社區「世紀長虹」(南勢里19鄰)`。
5. **傳播到所有複本**（少一步就會有一份過期）：
   - toolbox：跑 `sync-toolbox.ps1 -Apply` → commit → push（見 DEPLOY.md 第 2 節）。
   - LINE bot：複製整份 `linkou-data.js` 到 `C:\repo\linkou-line-bot\` → commit → push → 用手機對官方 LINE 打該社區名，應秒回學區。
   - 學區獨立站（master）：**不再更新**（退役中，7 月底改跳轉）。

## 3. 房貸與公車資料

- `mortgage-data.js`：`LINKOU_ZONES` 各地段數字由 linkou-mortgage repo 的 Actions **每月自動更新**，真相來源在那邊（流向見 DEPLOY.md 第 3 節）；`LINKOU_PRODUCTS` 等其餘部分才是手改。
- `bus-data.js`：由 `tools/fetch-bus.ps1` 抓 TDX 產生（需 `tdx-secret.json`，該檔**永不 commit**）。

## 4. 115 學年度切換（大型作業——先讀 memory 再動）

- **鐵則：還沒拿到「舊里鄰 → 新里鄰對照表」之前，絕對不動 `LI`／`COMMUNITY`／`HOUSE`。**
  只換 `LI` 會跟舊編號的 `COMMUNITY`/`HOUSE` 對不起來，整個工具查錯（比不更新更糟）。
- 背景：2026/7/1 林口 17 里改 21 里（南勢里分出新林/力行、湖南里分出頭湖/文湖），但政府開放資料延遲數週～兩個月才會反映。
- 完整計畫、資料集 ID、下一步：memory `linkou-115-switch-plan`（找不到就問使用者）。

## 5. HOUSE 門牌庫重建

- 來源：新北開放平台門牌數值資料（xlsx/CSV，每月更新）。**只留 `areacode=65000170`（林口）**——曾因混入外區同名路門牌導致地圖座標飛走。
- `x_3826`/`y_3826` 是 TM2 座標，要反算經緯度。值格式 `"里碼|鄰*緯偏,經偏"`：`lat=25+緯偏/1e5`、`lon=121.3+經偏/1e5`；門牌跨鄰時多組候選以分號隔開，如 `"4|11;4|14*7884,9766"`。
- 細節見 memory `house-table-rebuild`。重建後必跑 selftest ＋ CHECKLIST A 的地圖 pin 檢查。
