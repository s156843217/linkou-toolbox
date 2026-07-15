/* ============================================================
   listing-logic.js — 競品比較（591 在售盤點）核心邏輯（純函式，不碰畫面）
   ------------------------------------------------------------
   分兩塊：
   一、591 貼上解析：parse591()——輸入剪貼簿的 HTML 字串，輸出物件清單。
       靠「物件詳情連結＋文字樣式」解析，刻意不依賴 591 的 class 名稱，
       591 改版時比較不容易整組壞掉。欄位樣式已用真實清單頁樣本校正（2026-07）。
   二、比較邏輯：社區歸屬判定、同戶歸戶、鄰近社區建議、社區成交行情摘要。
       依賴先載入：linkou-data.js（COMMUNITY/ALIASES）、report-logic.js
       （parseHouse/houseCoord/distM）、price-list-data.js（PRICE_ROWS）。
   ★ tools/591-paste-test.html 也載入本檔（只用解析那一塊）。
   ============================================================ */

/* ======================= 一、591 貼上解析 ======================= */

/* 解析一整份貼上的 HTML。
   回傳 { items: [{id,url,title,community,price,unitPrice,size,sizeMain,layout,floor,floorTotal,age,raw}], skipped: [...] }
   price=總價(萬)、unitPrice=單價(萬/坪)、size=權狀坪、sizeMain=主建坪；抓不到的欄位為 null。 */
function parse591(htmlString){
  const doc = new DOMParser().parseFromString(htmlString || '', 'text/html');
  const anchors = Array.from(doc.querySelectorAll('a[href*="house/detail/"]'));
  const byId = new Map();   // 同一張卡片常有多個連結（圖片＋標題），用物件編號去重
  const skipped = [];

  for (const a of anchors){
    const href = a.getAttribute('href') || '';
    const m = href.match(/house\/detail\/(\d+)\/(\d+)/);
    if (!m) continue;
    const id = m[2];

    const card = card591Root(a);
    const text = (card.textContent || '').replace(/\s+/g, ' ').trim();
    if (!/萬/.test(text)){
      skipped.push({ id, why: '卡片文字裡沒有價格（可能是廣告或圖片連結）', text: text.slice(0, 120) });
      continue;
    }

    const item = parse591CardText(text);
    item.id = id;
    item.url = 'https://sale.591.com.tw/home/house/detail/' + m[1] + '/' + id + '.html';
    item.raw = text.slice(0, 250);

    /* 社區名：卡片上的社區標籤是連到 591 社區專頁（market.591）的連結 */
    const ca = card.querySelector('a[href*="market.591.com.tw"]');
    const cname = ca ? (ca.textContent || '').replace(/\s+/g, ' ').trim() : '';
    item.community = (cname && cname.length <= 20) ? cname : null;

    /* 連結本身的文字通常是標題（若含價格代表整張卡都是連結，不能當標題） */
    const at = (a.textContent || '').replace(/\s+/g, ' ').trim();
    if (at.length >= 6 && at.length <= 60 && !/萬/.test(at)) item.title = at;

    /* 沒有乾淨標題時，從卡片文字推一個：去掉開頭的「N分鐘前更新／曝光」雜訊，
       切在第一個規格數字（房/坪/萬）之前 */
    if (!item.title){
      let g = text.replace(/^.*?次曝光\s*/, '').replace(/^\d+\s*(分鐘|小時|天)前更新\s*/, '');
      const cut = g.search(/\d+\s*房|[\d,.]+\s*坪|[\d,]+\s*萬/);
      if (cut > 0) g = g.slice(0, cut);
      item.title = g.trim().slice(0, 40) || null;
    }

    const old = byId.get(id);
    if (!old || fieldCount591(item) > fieldCount591(old)){
      if (old && old.title && !item.title) item.title = old.title;  // 合併時別把標題弄丟
      byId.set(id, item);
    } else if (old && !old.title && item.title){
      old.title = item.title;
    }
  }
  return { items: Array.from(byId.values()), skipped };
}

/* 卡片邊界：從連結往上爬，爬到「還只包含這一個物件連結」的最上層。
   一旦某層出現別的物件編號，代表爬到整個清單容器了，就停在前一層。 */
function card591Root(a){
  let card = a, node = a.parentElement;
  for (let i = 0; i < 12 && node; i++){
    const ids = new Set();
    for (const x of node.querySelectorAll('a[href*="house/detail/"]')){
      const mm = (x.getAttribute('href') || '').match(/house\/detail\/\d+\/(\d+)/);
      if (mm) ids.add(mm[1]);
    }
    if (ids.size > 1) break;
    card = node;
    node = node.parentElement;
  }
  return card;
}

/* 從一張卡片的純文字抽欄位 */
function parse591CardText(text){
  /* 先把「萬/坪」改寫成「萬每坪」，免得單價跟總價、坪數的樣式互相咬到 */
  const t = text.replace(/萬\s*\/\s*坪/g, '萬每坪');
  const num = s => parseFloat(String(s).replace(/,/g, ''));

  /* 單價（萬/坪） */
  const um = t.match(/([\d,.]+)\s*萬每坪/);

  /* 總價：卡片裡所有「N萬」取最大值（最大的金額幾乎一定是總價）；
     100 萬以下視為雜訊（例如廣告文案「10萬人領取」） */
  let price = null;
  for (const mm of t.matchAll(/([\d,]+(?:\.\d+)?)\s*萬(?!每坪)/g)){
    const v = num(mm[1]);
    if (v >= 100 && (price === null || v > price)) price = v;
  }

  /* 坪數：清單卡常寫「權狀30.31坪 主建18.14坪」，權狀優先當主坪數；
     沒寫權狀的（如廣告卡「44.1坪」）就抓一般坪數，但要避開主建與車位 */
  const km = t.match(/權狀\s*([\d,.]+)\s*坪/);
  const mainm = t.match(/主建\s*([\d,.]+)\s*坪/);
  const pkm = t.match(/車位\s*([\d,.]+)\s*坪/);   // 車位坪：拆算單價用
  const t2 = t.replace(/(主建|車位)\s*[\d,.]+\s*坪/g, ' ');
  const sm = km || t2.match(/([\d,]+(?:\.\d+)?)\s*坪/);

  /* 格局：標題常出現「2房車」之類的字眼，所以不能抓第一個，
     要在整張卡裡挑「房廳衛寫得最完整」的那一組 */
  let lm = null, lmScore = -1;
  for (const g of t.matchAll(/(\d+)\s*房(?:\s*(\d+)\s*廳)?(?:\s*(\d+)\s*衛)?/g)){
    const score = (g[2] ? 1 : 0) + (g[3] ? 1 : 0);
    if (score > lmScore){ lm = g; lmScore = score; }
  }

  /* 樓層：常見「12F/21F」「12樓/21樓」「12/21F」幾種寫法都試 */
  const fm = t.match(/(\d+)\s*[F樓]\s*[\/~]\s*(\d+)\s*[F樓]/i)
          || t.match(/(\d+)\s*\/\s*(\d+)\s*[F樓]/i);

  /* 屋齡：「屋齡12.5年」優先；退而求其次抓「N年」但擋掉年份（>80 不採信） */
  const am = t.match(/屋齡\s*([\d.]+)\s*年/) || t.match(/([\d.]+)\s*年(?!前)/);
  let age = am ? parseFloat(am[1]) : null;
  if (age !== null && !(age > 0 && age < 80)) age = null;

  return {
    title: null,
    price,
    unitPrice: um ? num(um[1]) : null,
    size: sm ? num(sm[1]) : null,
    sizeMain: mainm ? num(mainm[1]) : null,
    sizePark: pkm ? num(pkm[1]) : null,
    layout: lm ? lm[0].replace(/\s+/g, '') : null,
    floor: fm ? fm[1] + 'F' : null,
    floorTotal: fm ? fm[2] + 'F' : null,
    age
  };
}

/* 有幾個欄位有抓到值（用來在重複連結之間挑資訊最齊的那筆） */
function fieldCount591(it){
  return ['title','price','unitPrice','size','sizeMain','sizePark','layout','floor','age','community']
    .reduce((n, k) => n + (it[k] !== null && it[k] !== undefined ? 1 : 0), 0);
}

/* ======================= 二、比較邏輯 ======================= */

/* 社區名正規化（比行情頁 normalizeComm 多去掉標點）：
   591 的標籤常帶括號或連字號（例「玄泰PTW(日光區)」vs 建檔「玄泰PTW日光區」），
   所以括號、空白、連字號等符號一律拿掉再比對。 */
function normComm591(s){
  return (s || '').replace(/管理委員會|管委會|社區|大廈|大樓|公寓|住戶|集合住宅|管理負責人/g, '')
    .replace(/[()（）\[\]【】〈〉《》「」『』\-—–‧·．・&＆\s]/g, '')
    .toLowerCase().trim();
}

/* ── 快取（第一次用到才建，開頁不卡） ── */
let _L_COORD = null;    // 社區名 → {lat,lon}
let _L_NIDX  = null;    // 正規化名（含俗稱）→ 官方社區名
let _L_RECS  = null;    // 實價登錄展開列
let _L_PARSED = null;   // 實價登錄各列的門牌解析

function ensureCommCoords591(){
  if (_L_COORD) return;
  _L_COORD = {};
  for (const n in COMMUNITY){
    const c = COMMUNITY[n];
    const co = c.addr ? houseCoord(c.addr) : null;
    if (co) _L_COORD[n] = co;
  }
}
function ensureNameIndex591(){
  if (_L_NIDX) return;
  _L_NIDX = {};
  for (const n in COMMUNITY) _L_NIDX[normComm591(n)] = n;
  if (typeof ALIASES !== 'undefined')
    for (const a in ALIASES) if (COMMUNITY[ALIASES[a]]) _L_NIDX[normComm591(a)] = ALIASES[a];
}
function ensurePriceCache591(){
  if (_L_RECS) return;
  _L_RECS = PRICE_ROWS.map(row => { const o = {}; PRICE_COLS.forEach((c, i) => o[c] = row[i]); return o; });
  _L_PARSED = _L_RECS.map(r => parseHouse(r.a));
}

/* 591 卡片的社區標籤 → 我們資料庫的官方社區名（對不上回 null） */
function resolveComm591(tag){
  if (!tag) return null;
  ensureNameIndex591();
  const nt = normComm591(tag);
  if (!nt) return null;
  if (_L_NIDX[nt]) return _L_NIDX[nt];
  for (const k in _L_NIDX){
    if (k.length >= 3 && (nt.includes(k) || k.includes(nt))) return _L_NIDX[k];
  }
  return null;
}

/* 這筆刊登是不是「目標社區」的？社區標籤優先；沒標籤時退而看標題有沒有社區名（含俗稱） */
function isMine591(item, targetName){
  const names = [targetName];
  if (typeof ALIASES !== 'undefined')
    for (const a in ALIASES) if (ALIASES[a] === targetName) names.push(a);
  const norm = names.map(normComm591).filter(x => x.length >= 2);
  const ct = normComm591(item.community || '');
  if (ct) return norm.some(n => ct === n || ct.includes(n) || n.includes(ct));
  const tt = normComm591(item.title || '');
  return norm.some(n => tt.includes(n));
}

/* 兩個社區的直線距離（公尺；任一方查無座標回 null） */
function commDist591(a, b){
  ensureCommCoords591();
  const x = _L_COORD[a], y = _L_COORD[b];
  return (x && y) ? Math.round(distM(x.lat, x.lon, y.lat, y.lon)) : null;
}

/* 鄰近社區建議：radius 公尺內的其他社區，由近到遠 */
function nearby591(name, radius){
  ensureCommCoords591();
  const me = _L_COORD[name];
  if (!me) return [];
  const meN = normComm591(name);
  const out = [];
  for (const n in _L_COORD){
    if (n === name || normComm591(n) === meN) continue;
    const d = distM(me.lat, me.lon, _L_COORD[n].lat, _L_COORD[n].lon);
    if (d <= radius) out.push({ name: n, dist: Math.round(d) });
  }
  return out.sort((a, b) => a.dist - b.dist);
}

/* 591 單價疑似「沒拆車位」的自動判斷：
   刊登者有填車位價時 591 會自動拆算（單價會高於 總價÷權狀坪）；
   反過來說，卡片看得到車位坪、單價卻 ≈ 總價÷權狀坪（誤差 2% 內），
   就代表刊登者沒填車位價、591 沒拆 → 這筆單價偏低，提醒人工填車位價修正。 */
function looksUnsplit591(price, size, unit, sizePark){
  if (price === null || size === null || unit === null || sizePark === null || !size) return false;
  const raw = price / size;
  return raw > 0 && Math.abs(unit - raw) / raw < 0.02;
}

/* 拆算單價（萬/坪）：(總價 − 車位價) ÷ (權狀坪 − 車位坪)。
   總價或坪數缺、或扣完剩 0 以下（車位數字填錯）→ 回 null，讓畫面退回原單價。 */
function adjUnit591(price, size, parkPrice, parkSize){
  if (price === null || size === null) return null;
  const pr = price - (parkPrice || 0), sz = size - (parkSize || 0);
  return (pr > 0 && sz > 0) ? pr / sz : null;
}

function median591(arr){
  if (!arr.length) return null;
  const a = [...arr].sort((x, y) => x - y), m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

/* 社區成交行情摘要（近 3 年成屋、排除透天，比對法與行情頁相同：
   commDoorSet 的整串門牌基底精準比對）→ {u 中位單價, age 中位屋齡, n 筆數} */
function commStats591(name){
  const keys = commDoorSet(name);
  if (!keys) return null;
  ensurePriceCache591();
  const md = PRICE_META.maxDate;
  const rows = [];
  _L_RECS.forEach((r, i) => {
    if (r.k !== 'r' || r.bt === 3 || r.bt === 4 || !r.u) return;
    if (r.d < md - 3 * 10000) return;
    const q = _L_PARSED[i];
    if (q && keys.has(q.road + '|' + q.lk + '|' + q.num.split('-')[0])) rows.push(r);
  });
  if (!rows.length) return null;
  const ages = rows.filter(r => r.by > 0).map(r => Math.floor(r.d / 10000) - r.by);
  return { u: median591(rows.map(r => r.u)), age: ages.length ? Math.round(median591(ages)) : null, n: rows.length };
}

/* 同戶歸戶：同社區＋同樓層＋權狀坪相近（取到小數一位相同）＝同一戶多家代理。
   缺樓層或坪數的無法歸戶，各自成一組。回傳每組＝一戶，listings 依開價由低到高。 */
function groupUnits591(items){
  const map = new Map();
  for (const it of items){
    const key = (it.floor && it.size !== null)
      ? normComm591(it.community || '') + '|' + it.floor + '|' + it.size.toFixed(1)
      : 'single|' + it.id;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(it);
  }
  return Array.from(map.values()).map(ls => {
    ls.sort((a, b) => (a.price === null) - (b.price === null) || a.price - b.price);
    const best = ls[0];   // 開價最低的那筆當代表
    const sp = ls.map(l => l.sizePark).find(v => v !== null && v !== undefined);   // 車位坪：組內任一筆有寫就用
    return {
      listings: ls, count: ls.length,
      minPrice: best.price, unit: best.unitPrice,
      floor: best.floor, floorTotal: best.floorTotal,
      size: best.size, sizeMain: best.sizeMain,
      sizePark: sp === undefined ? null : sp,
      layout: best.layout, age: best.age, community: best.community
    };
  });
}
