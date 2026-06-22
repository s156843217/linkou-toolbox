/* mortgage-data.js — 房貸試算頁資料
   資料來源：內政部實價登錄 近一年（114Q1～115Q1，買賣成交，林口區住宅）
   排除：土地、車位、親友／股東特殊交易、預售屋、海砂屋
   依路名對照商圈後統計，單價單位：萬元／坪（不含車位）
   ※ 北側商圈樣本數不足（近一年僅 11 筆），維持前期數字供參考
*/

// ── 林口各商圈每坪單價（近一年實價登錄） ──────────────────
// medPrice：中位數（萬/坪）
// priceRange：[Q1, Q3]（25%～75% 分位）
// ageMed：成交屋齡中位數（年）
// roomMed：成交房數中位數
// indoorPct：室內坪數佔登記坪數比例（中位數）
//   室內 = 主建物 + 附屬建物 + 陽台（即扣除「公設」與「車位」後的實際室內面積）
//   依各地段實價登錄分項面積（rps28 主建物 + rps29 附屬 + rps30 陽台）統計，樣本 1,451 筆
const LINKOU_ZONES = [
  { name: "三井Outlet",  medPrice: 56.2, priceRange: [50.1, 66.1], count: 127, ageMed: 11, roomMed: 3, indoorPct: 0.671 },
  { name: "南勢",        medPrice: 54.2, priceRange: [46.3, 57.3], count:  66, ageMed:  9, roomMed: 3, indoorPct: 0.668 },
  { name: "家樂福商圈",  medPrice: 47.2, priceRange: [41.0, 54.4], count: 196, ageMed: 15, roomMed: 3, indoorPct: 0.669 },
  { name: "北側",        medPrice: 57.0, priceRange: [54.1, 59.6], count:  14, ageMed:  4, roomMed: 2, indoorPct: 0.697 },
  { name: "林口舊市區",  medPrice: 50.2, priceRange: [41.6, 62.2], count: 123, ageMed:  8, roomMed: 3, indoorPct: 0.670 },
  { name: "麗園國小",    medPrice: 39.1, priceRange: [29.3, 47.9], count:  82, ageMed: 19, roomMed: 3, indoorPct: 0.658 },
];

// ── 各產品類型行情（林口・依建物型態分類，供底部「這筆預算能買什麼」三類比較） ──
// 來源：內政部實價登錄 opendata 季 zip（plvr.land.moi.gov.tw/DownloadSeason）
//   成屋 f_lvr_land_a（依「建物型態」拆出 集合住宅／透天）；預售 f_lvr_land_b
//   本批：114S2+114S3+114S4+115S1 合併（≈114/4–115/3 近一年），依「編號」去重；預售排除「解約」
//   ※ 115S2（115/4–6）內政部尚未釋出；未來自動管線抓最近數季滾動更新即可
// 計算口徑：房屋單價 = (總價 − 車位價) ÷ (不含車位坪數) ÷ 10000（萬/坪）
//   並排除「車位面積>0 但車位價=0」之綁約筆（拆不開、會高估）
//   ※ 已驗證：車位有計價時與政府「單價元平方公尺」欄逐筆相同
// 欄位：unit 單價中位(萬/坪)；unitRange [Q1,Q3]；totalMed 總價中位(萬)；
//       ageMed 屋齡中位(年，預售為 null)；pingMed 坪中位；roomMed 房數中位；n 樣本數
//       calc=true 可依預算精準試算坪數；false 樣本少、僅作總價門檻參考
const LINKOU_TYPES = [
  {
    key: "resale", name: "成屋", sub: "電梯大樓／華廈", tag: "看屋即入住",
    unit: 46.3, unitRange: [42.4, 53.7], totalMed: 1615, ageMed: 15, pingMed: 29.7, roomMed: 2,
    n: 1470, window: "近一年", calc: true,
    note: "現成可看實屋、可立即入住，屋齡中位約 15 年。",
  },
  {
    key: "presale", name: "預售屋", sub: "興建中／全新", tag: "全新可分期",
    unit: 60.1, unitRange: [55.8, 67.1], totalMed: 1746, ageMed: null, pingMed: 26.0, roomMed: 2,
    n: 1000, window: "近一年", calc: true,
    note: "全新、可依工程期分期付款；單價約比成屋高三成，需等交屋。",
  },
  {
    key: "house", name: "透天／別墅", sub: "獨棟含土地", tag: "樣本少·參考",
    unit: 41.9, unitRange: [33.0, 50.7], totalMed: 3708, threshold: 3000, ageMed: 19, pingMed: 84.2, roomMed: 4,
    n: 63, window: "近一年", calc: false,
    note: "總價門檻約 3,000 萬起、中位約 3,700 萬；近一年林口僅 63 筆成交，僅供方向參考。",
  },
];
