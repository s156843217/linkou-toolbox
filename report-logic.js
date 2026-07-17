/* ============================================================
   report-logic.js — 社區報告核心邏輯（純函式，不碰畫面）
   ------------------------------------------------------------
   report/（內部產生器）與 share/（客戶分享頁）共用同一份，
   改這裡兩頁同時生效，不會「改 A 忘了改 B」。
   依賴：linkou-data.js、mortgage-data.js、bus-data.js 先載入。
   ============================================================ */

/* ── 學區規則（搬自學區頁，語意完全相同） ── */
function inRange(n,rule){
  if(rule.r==="all")return true;
  if(rule.r==="else"){ if(n==null)return false; return !(rule.exclude||[]).some(([a,b])=>n>=a&&n<=b); }
  if(n==null)return false;
  return rule.r.some(([a,b])=>n>=a&&n<=b);
}
function rangeLabel(rule){
  if(rule.r==="all")return"全里";
  if(rule.r==="else")return"其餘鄰";
  return rule.r.map(([a,b])=>a===b?`${a}`:`${a}-${b}`).join("、")+"鄰";
}
function resolve(li,lin){
  const d=LI[li]; if(!d)return null;
  function pick(rules){
    if(lin!=null && lin!==""){ const n=parseInt(lin,10);
      const hit=rules.find(rl=>inRange(n,rl)); return hit?[hit]:[];
    }
    return rules.length===1?[rules[0]]:rules;
  }
  return {es:pick(d.es), jh:pick(d.jh)};
}

/* ── 門牌 → 里鄰＋座標（搬自學區/公車頁；用本地 HOUSE 表，免連網） ── */
const _FWMAP={'０':'0','１':'1','２':'2','３':'3','４':'4','５':'5','６':'6','７':'7','８':'8','９':'9','－':'-','～':'~','／':'/','　':' '};
function toHalf(s){return (s||'').replace(/[０-９－～／　]/g,c=>_FWMAP[c]);}
function parseHouse(addr){
  let a=toHalf(addr).trim();
  if(a.indexOf('林口')>=0) a=a.replace(/^.*林口區/,'');
  a=a.replace(/^\d{3}/,'').replace(/(新北市|臺北市|台北市)/g,'');
  a=a.replace(/[一-鿿]+(村|里)/g,'').replace(/\d+鄰/g,'').trim();
  const mFirst=a.search(/\d/); if(mFirst<0) return null;
  const road=a.slice(0,mFirst).replace(/[\s\-,，、]/g,'').trim();
  let rest=a.slice(mFirst),lane='',alley='';
  const ml=rest.match(/(\d+)\s*巷/); if(ml)lane=ml[1];
  const ma=rest.match(/(\d+)\s*弄/); if(ma)alley=ma[1];
  let r2=rest.replace(/\d+\s*巷/,'').replace(/\d+\s*弄/,'').replace(/之/g,'-');
  const mn=r2.match(/(\d+(?:-\d+)?)/); if(!mn)return null;
  if(!road)return null;
  return {road,lk:lane+'-'+alley,num:mn[1]};
}
/* 門牌完整查詢：地址 → {cands:[{li,lin}...], lat, lon}
   門牌表本身帶里＋鄰，所以「輸地址」的學區可以精準到鄰。 */
function houseLookup(addr){
  const p=parseHouse(addr); if(!p)return null;
  const node=(typeof HOUSE!=='undefined')&&HOUSE[p.road]; if(!node)return null;
  function dec(val){ // "里|鄰;里|鄰*緯偏,經偏" → {codes, lat, lon}
    const [codes,co]=val.split('*');
    let lat=null,lon=null;
    if(co){const [a,b]=co.split(',');lat=25.0+(+a)/100000;lon=121.3+(+b)/100000;}
    return {codes,lat,lon};
  }
  let codes=null, lat=null, lon=null;
  if(node[p.lk]&&node[p.lk][p.num]){                       // 路+巷+弄+號 完全命中
    const d=dec(node[p.lk][p.num]); codes=d.codes; lat=d.lat; lon=d.lon;
  }else if(node[p.lk]){                                    // 同巷弄、找同基底號（如 100 對 100-1）
    const base=p.num.split('-')[0]; const s=new Set();
    for(const k in node[p.lk]) if(k.split('-')[0]===base){const d=dec(node[p.lk][k]);d.codes.split(';').forEach(x=>s.add(x));if(lat==null){lat=d.lat;lon=d.lon;}}
    if(s.size)codes=[...s].join(';');
  }
  if(!codes){                                              // 退一步：忽略巷弄，該號若只屬單一里
    const s=new Set(); let rl=null,rn=null;
    for(const lk in node) if(node[lk][p.num]){const d=dec(node[lk][p.num]);d.codes.split(';').forEach(x=>s.add(x));if(rl==null){rl=d.lat;rn=d.lon;}}
    if(s.size===1){codes=[...s][0];lat=rl;lon=rn;}
  }
  if(!codes)return null;
  const cands=codes.split(';').map(c=>{const [i,n]=c.split('|');return {li:LI_HOUSE_IDX[+i],lin:+n};});
  return {cands,lat,lon};
}
function houseCoord(addr){
  const h=houseLookup(addr);
  return (h&&h.lat!=null)?{lat:h.lat,lon:h.lon}:null;
}
/* 社區 → 門牌基底集合（"路|巷-弄|號基底"，口徑同 parseHouse）。
   優先用 community-doors.js 的對照庫（實價登錄社區簡稱歸戶，一社區一串門牌），
   並聯集建檔地址門牌（對照庫漏收時至少跟以前一樣）；都查不到回 null。
   行情頁與競品比較頁的「本社區成交」都靠這個，兩頁口徑一致。 */
function commDoorSet(name){
  const set=new Set();
  if(typeof COMM_DOORS!=='undefined'&&COMM_DOORS[name])
    for(const k of COMM_DOORS[name])set.add(k);
  const c=(typeof COMMUNITY!=='undefined')&&COMMUNITY[name];
  if(c&&c.addr){
    const p=parseHouse(c.addr);
    if(p)set.add(p.road+'|'+p.lk+'|'+p.num.split('-')[0]);
  }
  return set.size?set:null;
}

/* ── 社區級行情統計（吃 price-list-data.js 的逐筆成交） ──
   比對口徑與行情頁完全相同：成屋比「門牌基底集合」（對照庫整串門牌）、
   預售比官方「建案名稱」模糊比對；樣本不足自動放寬期間（近1年→2年→3年）。
   放寬到3年統計樣本仍不足5筆＝中位數會誤導，回 {insufficient:true} 讓頁面誠實退回商圈級；
   頁面沒載 price-list-data.js 時回 null，行情區塊自動維持商圈級顯示。 */
function _normComm(s){return (s||'').replace(/管理委員會|管委會|社區|大廈|大樓|公寓|住戶|集合住宅|管理負責人/g,'').toLowerCase().trim();}
function _median(a){if(!a.length)return null;const s=[...a].sort((x,y)=>x-y),m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2;}
function _quart(a,q){const s=[...a].sort((x,y)=>x-y),pos=(s.length-1)*q,lo=Math.floor(pos);return s[lo]+(s[Math.min(lo+1,s.length-1)]-s[lo])*(pos-lo);}
function commPriceStats(keys,commName){
  if(typeof PRICE_ROWS==='undefined'||(!keys&&!commName))return null;
  const iK=PRICE_COLS.indexOf('k'),iD=PRICE_COLS.indexOf('d'),iA=PRICE_COLS.indexOf('a'),
        iBt=PRICE_COLS.indexOf('bt'),iT=PRICE_COLS.indexOf('t'),iU=PRICE_COLS.indexOf('u'),
        iS=PRICE_COLS.indexOf('s'),iCm=PRICE_COLS.indexOf('cm');
  const nq=commName?_normComm(commName):null;
  const hit=[];
  for(const r of PRICE_ROWS){
    if(nq&&r[iK]==='p'&&r[iCm]){                       // 預售：建案名稱模糊比對
      const nc=_normComm(r[iCm]);
      if(nc&&nc.length>=2&&(nc===nq||nc.includes(nq)||nq.includes(nc))){hit.push(r);continue;}
    }
    if(keys){                                          // 成屋：門牌基底精準比對
      const p=parseHouse(r[iA]);
      if(p&&keys.has(p.road+'|'+p.lk+'|'+p.num.split('-')[0]))hit.push(r);
    }
  }
  if(!hit.length)return null;
  const md=PRICE_META.maxDate;
  for(const yrs of [1,2,3]){
    const w=hit.filter(r=>r[iD]>=md-yrs*10000);
    const st=w.filter(r=>r[iBt]!==3&&r[iBt]!==4&&r[iU]>0);   // 統計排除透天/別墅與無單價筆
    if(st.length>=5||yrs===3){
      if(st.length<5)return {insufficient:true,n:w.length,yrs:3};
      const us=st.map(r=>r[iU]);
      return {n:st.length,yrs,
        unitMed:_median(us),p25:_quart(us,.25),p75:_quart(us,.75),
        totalMed:_median(st.map(r=>r[iT])),sizeMed:_median(st.map(r=>r[iS]))};
    }
  }
}
/* ── 地址模式（公寓/華廈等）的鄰近「同建物型態」行情 ──
   商圈中位數以住宅大樓為大宗，公寓/華廈直接看會嚴重高估
   （實測：舊市區公寓約 24.5 萬/坪 vs 商圈中位 38.6），
   所以地址模式改抓「方圓內同型態成屋」統計：範圍自動放寬 150→300→500m、
   期間 1→3 年（先求近再求新），湊滿 5 筆統計樣本就停；
   500m 內近 3 年仍不足 5 筆回 {insufficient:true}，頁面退回商圈級並誠實說明。 */
function nearTypeStats(coord,bt){
  if(typeof PRICE_ROWS==='undefined'||!coord||bt==null)return null;
  const iK=PRICE_COLS.indexOf('k'),iD=PRICE_COLS.indexOf('d'),iA=PRICE_COLS.indexOf('a'),
        iBt=PRICE_COLS.indexOf('bt'),iT=PRICE_COLS.indexOf('t'),iU=PRICE_COLS.indexOf('u'),
        iS=PRICE_COLS.indexOf('s');
  const md=PRICE_META.maxDate;
  const rows=[];                                   // 一趟掃描先收 500m 內同型態成屋
  for(const r of PRICE_ROWS){
    if(r[iK]!=='r'||r[iBt]!==bt||r[iU]<=0)continue;
    if(r[iD]<md-30000)continue;
    const co=houseCoord(r[iA]); if(!co)continue;
    const dm=distM(coord.lat,coord.lon,co.lat,co.lon);
    if(dm<=500)rows.push({r,dm});
  }
  if(!rows.length)return {insufficient:true,n:0,btName:PRICE_BT[bt]};
  for(const radius of [150,300,500]){
    for(const yrs of [1,2,3]){
      const st=rows.filter(o=>o.dm<=radius&&o.r[iD]>=md-yrs*10000);
      if(st.length>=5){
        const us=st.map(o=>o.r[iU]);
        return {n:st.length,yrs,radius,btName:PRICE_BT[bt],
          unitMed:_median(us),p25:_quart(us,.25),p75:_quart(us,.75),
          totalMed:_median(st.map(o=>o.r[iT])),sizeMed:_median(st.map(o=>o.r[iS]))};
      }
    }
  }
  return {insufficient:true,n:rows.length,btName:PRICE_BT[bt]};
}
function distM(la1,lo1,la2,lo2){
  const R=6371000,rad=Math.PI/180;
  const dLa=(la2-la1)*rad,dLo=(lo2-lo1)*rad;
  const a=Math.sin(dLa/2)**2+Math.cos(la1*rad)*Math.cos(la2*rad)*Math.sin(dLo/2)**2;
  return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
}

/* ── 商圈判定：點在多邊形。
   多邊形內嵌自 linkou-toolbox/林口價格地圖.geojson（2026-07 快照，僅 3KB）；
   商圈名與 mortgage-data.js 的 LINKOU_ZONES 一一對應。
   ★ 若日後重畫商圈（geojson 換檔），這份內嵌資料要一起換。 ── */
const REPORT_ZONES=[
 ["三井Outlet",[[121.354533,25.065954],[121.364076,25.065578],[121.366357,25.065766],[121.370921,25.069994],[121.364073,25.076199],[121.361584,25.073942],[121.360159,25.072607],[121.358305,25.071159],[121.35717,25.069963],[121.35622,25.068536],[121.355687,25.067571],[121.355525,25.067004],[121.355594,25.067025],[121.354533,25.065954]]],
 ["南勢",[[121.363839,25.076172],[121.361286,25.077581],[121.35689,25.079484],[121.355823,25.078664],[121.351394,25.073862],[121.350489,25.069412],[121.355119,25.067288],[121.355876,25.068165],[121.356118,25.06848],[121.356844,25.069755],[121.357786,25.070799],[121.3588,25.071663],[121.361327,25.073773],[121.362447,25.074774],[121.363839,25.076172]]],
 ["家樂福商圈",[[121.36398,25.076215],[121.364957,25.075467],[121.366305,25.074343],[121.368243,25.0726],[121.37123,25.069797],[121.372165,25.07045],[121.376163,25.073363],[121.379196,25.075778],[121.381555,25.078608],[121.38226,25.079579],[121.38284,25.080799],[121.380516,25.081906],[121.377192,25.084287],[121.375984,25.085355],[121.373626,25.086997],[121.36398,25.076215]]],
 ["北側",[[121.373796,25.087186],[121.380145,25.082291],[121.380145,25.082291],[121.382969,25.081069],[121.387437,25.088703],[121.378965,25.093971],[121.373796,25.087186]]],
 ["林口舊市區",[[121.383161,25.08086],[121.382696,25.079878],[121.381991,25.078699],[121.379767,25.076144],[121.376404,25.073393],[121.378031,25.072557],[121.38096,25.071329],[121.382479,25.071231],[121.384866,25.07015],[121.385842,25.069855],[121.385951,25.071329],[121.387253,25.071624],[121.387795,25.067692],[121.390291,25.067692],[121.390074,25.068872],[121.393274,25.070149],[121.394522,25.072361],[121.389802,25.074228],[121.389965,25.07526],[121.390616,25.075456],[121.393653,25.07408],[121.396583,25.072999],[121.395064,25.068626],[121.395769,25.067988],[121.398969,25.068283],[121.399946,25.071525],[121.397885,25.075456],[121.400706,25.075161],[121.401959,25.075287],[121.403223,25.078455],[121.403645,25.08212],[121.40061,25.083533],[121.396775,25.078761],[121.392855,25.080937],[121.394204,25.08483],[121.387629,25.088724],[121.383161,25.08086]]],
 ["麗園國小",[[121.366552,25.065917],[121.378052,25.066654],[121.379896,25.066408],[121.382717,25.065917],[121.384073,25.066408],[121.384073,25.0697],[121.38033,25.071076],[121.377129,25.0725],[121.376207,25.073188],[121.373224,25.071026],[121.370891,25.069405],[121.369915,25.068619],[121.368125,25.067145],[121.366552,25.065917]]]
];
function pointInRing(lon,lat,ring){
  let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const [xi,yi]=ring[i],[xj,yj]=ring[j];
    if(((yi>lat)!==(yj>lat)) && (lon < (xj-xi)*(lat-yi)/(yj-yi)+xi)) inside=!inside;
  }
  return inside;
}
function zoneOf(lon,lat){
  for(const [name,ring] of REPORT_ZONES) if(pointInRing(lon,lat,ring)) return name;
  return null;
}

/* ── 附近公車站（同名站合併、由近到遠；邏輯與公車頁一致） ── */
const ROUTES=(window.BUS_DATA&&BUS_DATA.routes)||{};
const STOPS=(window.BUS_DATA&&BUS_DATA.stops)||[];
function nearStops(lat,lon,radius){
  const raw=STOPS.map(s=>({s,d:distM(lat,lon,s.la,s.lo)})).filter(o=>o.d<=radius);
  const byName={};
  raw.forEach(({s,d})=>{
    let o=byName[s.n];
    if(!o){o=byName[s.n]={n:s.n,la:s.la,lo:s.lo,d,r:new Set()};}
    if(d<o.d){o.d=d;o.la=s.la;o.lo=s.lo;}
    s.r.forEach(k=>o.r.add(k));
  });
  return Object.values(byName).map(o=>({n:o.n,la:o.la,lo:o.lo,d:o.d,r:[...o.r]})).sort((a,b)=>a.d-b.d);
}
/* 家點 → 站牌的八方位（東北 140m 這種說法，幫客戶抓方向感） */
function dirTxt(la1,lo1,la2,lo2){
  const y=Math.sin((lo2-lo1)*Math.PI/180)*Math.cos(la2*Math.PI/180);
  const x=Math.cos(la1*Math.PI/180)*Math.sin(la2*Math.PI/180)
        -Math.sin(la1*Math.PI/180)*Math.cos(la2*Math.PI/180)*Math.cos((lo2-lo1)*Math.PI/180);
  const deg=(Math.atan2(y,x)*180/Math.PI+360)%360;
  return ['北','東北','東','東南','南','西南','西','西北'][Math.round(deg/45)%8];
}
/* 路線是否可達捷運／台北（看兩端終點站名） */
function routeToTaipei(key){
  const r=ROUTES[key]; if(!r)return false;
  if(/捷運|台北|臺北/.test(r.n||''))return true;
  for(const d of (r.dirs||[])){
    const st=d.st||[]; if(!st.length)continue;
    const ends=[st[0][2],st[st.length-1][2]];
    if(ends.some(e=>/捷運|台北|臺北/.test(e||'')))return true;
  }
  return false;
}
function routeSortKey(n){const m=(n||'').match(/^\d+/);return [m?+m[0]:9999,n||''];}

/* ── 房貸：本息平均攤還月付（PMT，與房貸試算頁同式） ── */
function pmtMonthly(loanWan,ratePct,years){
  const P=loanWan*10000, r=ratePct/100/12, n=years*12;
  if(r<=0)return P/n;
  const f=Math.pow(1+r,n);
  return P*r*f/(f-1);
}

/* ── 組報告資料：核心（社區名或地址） → 一頁報告所需的全部資料 ── */
function finishReport(core,loan){
  const coord=core.coord;
  const zone=coord?zoneOf(coord.lon,coord.lat):null;
  const zoneData=zone?LINKOU_ZONES.find(z=>z.name===zone):null;
  const resale=(typeof LINKOU_TYPES!=='undefined')?LINKOU_TYPES.find(t=>t.key==='resale'):null;
  const commPrice=commPriceStats(core.doorKeys||null,core.presaleQ||null);   // 社區級行情（資料不足時為 null 或 insufficient）
  const nearType=(core.addrBt!=null&&coord)?nearTypeStats(coord,core.addrBt):null;   // 地址模式的鄰近同型態行情
  const school=core.li?resolve(core.li,core.lin):null;
  const stops=coord?nearStops(coord.lat,coord.lon,500):[];
  let mortgage=null;
  if(loan.price>0){
    const loanWan=Math.round(loan.price*loan.ratio);
    mortgage={
      price:loan.price, ratio:loan.ratio, rate:loan.rate, years:loan.years,
      loanWan, downWan:loan.price-loanWan,
      monthly:pmtMonthly(loanWan,loan.rate,loan.years),
      per100:pmtMonthly(100,loan.rate,loan.years)
    };
  }
  return Object.assign({zone,zoneData,resale,commPrice,nearType,school,stops,mortgage},core);
}
/* 社區模式：名稱查 COMMUNITY */
function buildFromCommunity(name,loan){
  const c=COMMUNITY[name]; if(!c)return null;
  return finishReport({
    name, addr:c.addr||'', li:c.li||null, lin:c.lin||null, cands:c.cands||null,
    coord:c.addr?houseCoord(c.addr):null,
    doorKeys:commDoorSet(name), presaleQ:name    // 社區級行情比對用：整串門牌＋建案名稱
  },loan);
}
/* 地址模式（公寓／華廈等無社區名）：門牌表直接給里＋鄰，學區精準到鄰。
   bt＝建物型態索引（PRICE_BT：0大樓/1華廈/2公寓…），有給才算鄰近同型態行情 */
function buildFromAddress(addr,loan,bt){
  const h=houseLookup(addr); if(!h)return null;
  const one=h.cands.length===1?h.cands[0]:null;   // 單一里鄰＝可精準判學區；跨里則列候選
  const disp=toHalf(addr).replace(/^(新北市)?林口區/,'').trim();
  const p=parseHouse(addr);                       // 社區級行情比對用：只有這一個門牌基底
  return finishReport({
    name:disp, addr:'新北市林口區'+disp,
    li:one?one.li:null, lin:one?one.lin:null,
    cands:one?null:h.cands.map(c=>c.li),
    coord:h.lat!=null?{lat:h.lat,lon:h.lon}:null,
    doorKeys:p?new Set([p.road+'|'+p.lk+'|'+p.num.split('-')[0]]):null, presaleQ:null,
    addrBt:(bt==null||isNaN(bt))?null:bt
  },loan);
}

/* ── 共用的顯示小工具與 HTML 片段（report 與 share 同款內容） ── */
const fmt=n=>Math.round(n).toLocaleString('zh-TW');

/* 網站網址：上線後自動抓「目前這個網域」——未來換自有網址會自動跟著變；
   只有本機 file:// 測試時才用寫死的備用網址。 */
const SITE_URL=/^http/.test(location.protocol)
  ? location.href.replace(/(report|share)\/.*$/,'')
  : 'https://swcasa.com/';

/* 學區單行（rl＝一條學區規則） */
function schoolLine(rl,kind,multi){
  const isJh=kind==='jh';
  const seg=multi?`<span class="tagx info">${rangeLabel(rl)}</span>`:'';
  if(!rl)return'';
  if(rl.base){
    const full=!isJh&&FULL_ES.includes(rl.base);
    let h=`<div class="sch-line"><span class="k">${isJh?'國中':'國小'}</span>${seg}
      <span class="nm">${rl.base}</span><span class="tagx base">基本學區</span>
      ${full?'<span class="tagx hot">🔥 額滿學校</span>':''}
      ${(INFO[rl.base]&&INFO[rl.base].tag)?`<span class="tagx info">${INFO[rl.base].tag}</span>`:''}</div>`;
    if(rl.free&&rl.free.length)h+=`<div class="free-mini">＋ 另可擇一選讀自由學區：${rl.free.map(s=>s+(FULL_ES.includes(s)?'（額滿校）':'')).join('、')}</div>`;
    if(rl.note)h+=`<div class="sch-note">※ ${rl.note}</div>`;
    return h;
  }
  let h=`<div class="sch-line"><span class="k">${isJh?'國中':'國小'}</span>${seg}
    <span class="nm">自由學區</span><span class="tagx base">可擇一就讀</span></div>
    <div class="free-mini">${(rl.free||[]).join('、')}</div>`;
  if(rl.note)h+=`<div class="sch-note">※ ${rl.note}</div>`;
  return h;
}
/* 額滿風險小卡（只針對結果中出現的額滿國小，含歷年最後設籍日趨勢） */
function riskMini(school){
  const rows=FULL_DATA[school]||[]; if(!rows.length)return'';
  const latest=rows[0];
  const trend=rows.slice(0,3).map(r=>`${r[0]}年：${r[1]}`).join('｜');
  return `<div class="risk-mini"><b>🔥 ${school} 額滿提醒</b>　${latest[0]}學年最後錄取設籍日 <b>${latest[1]}</b>（約需提前 ${latest[2]}設籍）。
    須父母與學童在學區內<b>共同設籍＋居住事實</b>，超額依設籍先後排序——越早設籍越保險。<br>
    <span style="color:var(--ink-soft)">歷年最後設籍日：${trend}</span></div>`;
}
