# -*- coding: utf-8 -*-
"""
update_prices.py — 自動更新林口實價登錄資料（房貸頁地段單價＋行情逐筆表）
============================================================================
流程：
  1. 從「新北市政府資料開放平臺」API 抓不動產買賣實價登錄（全新北滾動快照）
  2. 篩出林口區、住宅、近一年、排除土地/車位/特殊交易
  3. 商圈分配（兩段式）：
       (a) 主：用門牌查 HOUSE 取「座標」→ 看落在哪個商圈多邊形內（點在多邊形）。
           這能正確處理「同一條路跨兩個商圈」（如文化北路二段跨北側／家樂福）。
       (b) 備援：HOUSE 查不到座標時，退回 road_zone_map.csv 的路名→商圈。
  4. 各商圈算 單價中位數 / IQR / 屋齡 / 房數 / 室內佔比
  5. 覆寫 mortgage-data.js 中 <<AUTO-ZONES-START>>～<<AUTO-ZONES-END>> 之間
  6. 行情逐筆表：下載內政部季檔（成屋+預售）→ 累積合併 price-history.json
     → 產出 price-list-data.js（近三年、瀏覽器用），並供 LINKOU_TYPES 預售統計

設計重點：
  - 只用 Python 標準庫，不需 pip install（雲端 GitHub Actions 最穩、最快）。
  - HOUSE 門牌座標表「線上」從學區 repo 直接抓（永遠最新、不留過期複製檔）；
    抓不到時自動降級為純 road_zone_map.csv（不中斷）。
  - 商圈多邊形 林口價格地圖.geojson 是「你畫的區域」，放在本 repo 當快照；重畫後換檔即可。
  - 「近一年」以「資料本身最新一筆日期」往回推一年（非系統時鐘），避免快照落後抓到 0 筆。
  - 找不到標記、或篩完無資料時，直接中止且不覆寫（保留舊資料）。

執行：python update_prices.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

# ── 設定 ──────────────────────────────────────────────────
API = ("https://data.ntpc.gov.tw/api/datasets/"
       "ACCE802D-58CC-4DFF-9E7A-9ECC517F78BE/json")          # 成屋（含透天，用建物型態拆）
# 預售不再用新北 API：原資料集 9238CCC2 自 2026-07 起回傳的是「租賃」資料（已驗證），
# 預售改吃內政部季檔（見下方「行情逐筆表」段，還多了建案名稱/解約情形欄位）。
PAGE_SIZE = 5000
MAX_PAGES = 40
PING_M2 = 3.305785
MIN_COUNT = 3

# 門牌座標表：抓本 repo（整合站）自己的 linkou-data.js（學區資料的正式維護版）
HOUSE_URL = ("https://raw.githubusercontent.com/"
             "s156843217/linkou-toolbox/main/linkou-data.js")

DATA_JS = Path("mortgage-data.js")
ROAD_MAP = Path("road_zone_map.csv")                 # 備援用
GEOJSON = Path("林口價格地圖.geojson")                # 你畫的商圈多邊形

ZONE_ORDER = ["三井Outlet", "南勢", "家樂福商圈", "北側", "林口舊市區", "麗園國小"]
RESIDENTIAL = {"住家用", "住商用"}
# 排除的建物型態（rps11）：透天厝/別墅含大片土地，每坪單價與集合住宅不可比，會拉低中位數。
# 保留 大樓/華廈/公寓（同屬集合住宅、每坪可比）。
EXCLUDE_BTYPE = ("透天", "別墅")
SPECIAL = ["親友", "二親等", "特殊關係", "急售", "債務", "拍賣", "法拍",
           "贈與", "含增建", "毛胚", "含裝潢", "含傢俱", "含家具", "瑕疵"]

# rps 欄位：rps01 交易標的｜rps02 門牌｜rps07 交易年月日｜rps12 主要用途
#   rps14 建築完成年月｜rps15_area 建物面積｜rps16 房｜rps21 總價｜rps24_area 車位面積
#   rps25 車位總價｜rps26 備註｜rps28/29/30 主建物/附屬/陽台


# ── 通用工具 ──────────────────────────────────────────────
def num(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def roc_int(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() and len(s) >= 6 else None


def roc_year(s):
    s = (s or "").strip()
    if len(s) < 5:
        return None
    try:
        return int(s[:-4])
    except ValueError:
        return None


# ── 門牌解析 / 取座標（移植自學區 index.html 的 parseHouse / houseLookup） ──
_FW = str.maketrans("０１２３４５６７８９－～／　", "0123456789-~/ ")


def to_half(s):
    return (s or "").translate(_FW)


def parse_house(addr):
    """正規化地址，拆出 road / lk(巷-弄) / num。對不到回 None。"""
    a = to_half(addr).strip()
    if "林口" in a:
        a = re.sub(r"^.*林口區", "", a)
    a = re.sub(r"^\d{3}", "", a)
    a = re.sub(r"(新北市|臺北市|台北市)", "", a)
    a = re.sub(r"[一-鿿]+[村里]", "", a)   # 去 X村 / X里
    a = re.sub(r"\d+鄰", "", a).strip()
    m = re.search(r"\d", a)
    if not m:
        return None
    road = re.sub(r"[\s\-,，、]", "", a[:m.start()]).strip()
    if not road:
        return None
    rest = a[m.start():]
    ml = re.search(r"(\d+)\s*巷", rest)
    mz = re.search(r"(\d+)\s*弄", rest)
    lane = ml.group(1) if ml else ""
    alley = mz.group(1) if mz else ""
    r2 = re.sub(r"\d+\s*巷", "", rest)
    r2 = re.sub(r"\d+\s*弄", "", r2).replace("之", "-")
    mn = re.search(r"(\d+(?:-\d+)?)", r2)
    if not mn:
        return None
    return {"road": road, "lk": lane + "-" + alley, "num": mn.group(1)}


def dec_coord(val):
    """HOUSE 值 "里|鄰*緯偏,經偏" → (lat, lon)；無座標回 None。"""
    codes, _, co = val.partition("*")
    if not co:
        return None
    a, _, b = co.partition(",")
    try:
        return (25.0 + float(a) / 100000, 121.3 + float(b) / 100000)
    except ValueError:
        return None


def house_coord(addr, house):
    """查 HOUSE 取門牌座標 (lat, lon)；查不到回 None。"""
    p = parse_house(addr)
    if not p:
        return None
    node = house.get(p["road"])
    if not node:
        return None
    lk, n = p["lk"], p["num"]
    sub = node.get(lk)
    if sub:
        if n in sub:                                  # 巷弄號完全命中
            d = dec_coord(sub[n])
            if d:
                return d
        base = n.split("-")[0]                         # 同巷弄、同基底號
        for k, v in sub.items():
            if k.split("-")[0] == base:
                d = dec_coord(v)
                if d:
                    return d
    for s2 in node.values():                           # 退一步：忽略巷弄
        if n in s2:
            d = dec_coord(s2[n])
            if d:
                return d
    return None


# ── 點在多邊形（射線法），商圈多邊形來自你畫的 geojson ───────
def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def zone_of(lon, lat, zones):
    for name, ring in zones:
        if point_in_ring(lon, lat, ring):
            return name
    return None


def load_zones():
    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    zones = []
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            ring = [(c[0], c[1]) for c in g["coordinates"][0]]  # [lon, lat]
            zones.append((f["properties"].get("name", "?"), ring))
    return zones


_LINKOU_TXT = None


def _linkou_txt():
    """抓 linkou-data.js 原文（只抓一次快取）。失敗回空字串。"""
    global _LINKOU_TXT
    if _LINKOU_TXT is None:
        try:
            req = Request(HOUSE_URL, headers={"User-Agent": "linkou-mortgage-bot/1.0"})
            with urlopen(req, timeout=60) as r:
                _LINKOU_TXT = r.read().decode("utf-8")
        except Exception as e:                          # noqa: BLE001
            print(f"⚠ 抓 linkou-data.js 失敗（{e}）")
            _LINKOU_TXT = ""
    return _LINKOU_TXT


def _linkou_const(name):
    """從 linkou-data.js 取某個 const 的 JSON 內容（單行宣告）。失敗回 {}。"""
    prefix = f"const {name} = "
    for line in _linkou_txt().splitlines():
        if line.startswith(prefix):
            try:
                return json.loads(line[len(prefix):].rstrip().rstrip(";"))
            except ValueError as e:
                print(f"⚠ 解析 {name} 失敗（{e}）")
                return {}
    if _linkou_txt():
        print(f"⚠ 線上 linkou-data.js 找不到 {name} 行")
    return {}


def load_house():
    """HOUSE 門牌座標表。失敗回 {}（呼叫端降級為純路名對照）。"""
    return _linkou_const("HOUSE")


def load_community():
    """COMMUNITY 社區→建檔地址對照（行情摘要用）。失敗回 {}。"""
    return _linkou_const("COMMUNITY")


# ── 抓 API ────────────────────────────────────────────────
def _get_json(url, tries=4):
    """抓 JSON，遇暫時性網路錯誤自動重試（GitHub runner 偶發 Network unreachable）。"""
    req = Request(url, headers={"User-Agent": "linkou-mortgage-bot/1.0"})
    for i in range(tries):
        try:
            with urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                          # noqa: BLE001
            if i == tries - 1:
                raise
            wait = 5 * (i + 1)
            print(f"  ⚠ 連線失敗（{e}），{wait}s 後重試（{i + 1}/{tries}）")
            time.sleep(wait)


def fetch_all(api):
    rows = []
    for p in range(MAX_PAGES):
        url = f"{api}?page={p}&size={PAGE_SIZE}"
        chunk = _get_json(url)
        rows.extend(chunk)
        print(f"  page={p} 取得 {len(chunk)} 筆（累計 {len(rows)}）")
        if len(chunk) < PAGE_SIZE:
            break
    return rows


def road_of(addr):
    """備援用：粗抽路名（去「…區」前綴、取到第一個半/全形數字前）。"""
    s = re.sub(r"^.*?區", "", addr or "")
    m = re.match(r"([^0-9０-９]+)", s)
    return m.group(1).strip() if m else ""


# ── 主流程 ────────────────────────────────────────────────
def build_zones(raw):
    print("載入商圈多邊形 …")
    zones = load_zones()
    print(f"  {len(zones)} 個商圈：{[z[0] for z in zones]}")

    print("線上抓 HOUSE 門牌座標表 …")
    house = load_house()
    print(f"  HOUSE 路名數：{len(house)}")

    road_zone = {}
    with open(ROAD_MAP, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = (row.get("路名") or "").strip()
            if r:
                road_zone[r] = (row.get("商圈") or "").strip()

    cand = []
    by_coord = by_fallback = unmatched = excl_btype = 0
    miss_roads = {}
    for r in raw:
        if r.get("district") != "林口區":
            continue
        if "建物" not in (r.get("rps01") or ""):
            continue
        if (r.get("rps12") or "") not in RESIDENTIAL:
            continue
        if any(t in (r.get("rps11") or "") for t in EXCLUDE_BTYPE):  # 排除透天/別墅
            excl_btype += 1
            continue
        if any(k in (r.get("rps26") or "") for k in SPECIAL):
            continue

        d = roc_int(r.get("rps07_yyymmddroc"))
        total = num(r.get("rps21_amountsunitdollars"))
        area = num(r.get("rps15_area"))
        if d is None or not total or not area:
            continue
        park_area = num(r.get("rps24_area")) or 0.0
        park_price = num(r.get("rps25_amountsunitdollars")) or 0.0
        house_ping = (area - park_area) / PING_M2
        if house_ping <= 0:
            continue
        unit = (total - park_price) / 10000 / house_ping
        if unit <= 0:
            continue

        addr = r.get("rps02")
        # 商圈分配：先座標+多邊形，退回路名對照
        zone = None
        coord = house_coord(addr, house) if house else None
        if coord:
            zone = zone_of(coord[1], coord[0], zones)   # (lon, lat)
            if zone:
                by_coord += 1
        if not zone:
            road = road_of(addr)
            zone = road_zone.get(road)
            if zone:
                by_fallback += 1
            else:
                unmatched += 1
                miss_roads[road] = miss_roads.get(road, 0) + 1
                continue

        ty, by = roc_year(r.get("rps07_yyymmddroc")), roc_year(r.get("rps14_yyymmddroc"))
        age = (ty - by) if (ty and by and ty >= by) else None
        rooms = num(r.get("rps16_quantity"))
        main_a = num(r.get("rps28_area")) or 0.0
        sub_a = num(r.get("rps29_area")) or 0.0
        bal_a = num(r.get("rps30_area")) or 0.0
        denom = area - park_area
        indoor = (main_a + sub_a + bal_a) / denom if denom > 0 else None

        cand.append({"date": d, "zone": zone, "unit": unit,
                     "age": age, "rooms": rooms, "indoor": indoor})

    if not cand:
        sys.exit("⚠ 林口住宅無資料，中止（不覆寫）")

    print(f"排除透天/別墅 {excl_btype} 筆")
    print(f"商圈分配：座標命中 {by_coord}、路名備援 {by_fallback}、未命中丟棄 {unmatched}")
    if miss_roads:
        top = sorted(miss_roads.items(), key=lambda kv: -kv[1])[:10]
        print("  未命中路名（前 10）：" + "  ".join(f"{r}×{n}" for r, n in top))

    # 近一年（以資料最新日回推）
    max_d = max(c["date"] for c in cand)
    cutoff = max_d - 10000
    recs = [c for c in cand if c["date"] >= cutoff]
    print(f"林口住宅 {len(cand)} 筆；近一年（{cutoff}~{max_d}）取 {len(recs)} 筆")

    # 去極端值 1%~99%
    units = sorted(c["unit"] for c in recs)
    lo, hi = percentile(units, 0.01), percentile(units, 0.99)
    recs = [c for c in recs if lo <= c["unit"] <= hi]

    out = []
    for name in ZONE_ORDER:
        g = [c for c in recs if c["zone"] == name]
        if len(g) < MIN_COUNT:
            print(f"  {name}: 樣本 {len(g)} 不足，略過")
            continue
        u = sorted(c["unit"] for c in g)
        ages = [c["age"] for c in g if c["age"] is not None]
        rooms = [c["rooms"] for c in g if c["rooms"] is not None]
        indoors = sorted(c["indoor"] for c in g if c["indoor"] is not None)
        out.append({
            "name": name,
            "medPrice": round(statistics.median(u), 1),
            "q1": round(percentile(u, 0.25), 1),
            "q3": round(percentile(u, 0.75), 1),
            "count": len(g),
            "ageMed": round(statistics.median(ages)) if ages else 0,
            "roomMed": round(statistics.median(rooms)) if rooms else 0,
            "indoorPct": round(statistics.median(indoors), 3) if indoors else 0,
        })
        print(f"  {name}: med={out[-1]['medPrice']} n={len(g)}")

    if not out:
        sys.exit("⚠ 無任何商圈達樣本門檻，中止（不覆寫）")
    return out, max_d


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = q * (len(sorted_vals) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = i - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# ── 覆寫 mortgage-data.js ────────────────────────────────
def write_js(zones, max_d):
    today = date.today().isoformat()
    total_n = sum(z["count"] for z in zones)
    data_month = f"民國{str(max_d)[:3]}年{str(max_d)[3:5]}月"

    out = []
    out.append("// <<AUTO-ZONES-START>>  ← 此區塊由 update_prices.py 自動產生，請勿手改")
    out.append(f"// ── 林口各商圈每坪單價（自動更新：{today}；資料截至 {data_month}，"
               f"近一年共 {total_n} 筆） ──")
    out.append("// 來源：新北市政府資料開放平臺 不動產買賣實價登錄（每 10 日更新）")
    out.append("// 商圈分配：門牌座標 × 商圈多邊形（點在多邊形），跨區路自動切分")
    out.append("// 僅集合住宅（大樓/華廈/公寓）；已排除透天厝/別墅、車位、特殊交易")
    out.append("// medPrice：中位數（萬/坪）｜priceRange：[Q1,Q3]｜"
               "ageMed：屋齡中位數｜roomMed：房數中位數")
    out.append("// indoorPct：室內(主建物+附屬+陽台)/扣車位登記坪數 之中位數")
    out.append("const LINKOU_ZONES = [")
    for z in zones:
        out.append(
            f'  {{ name: "{z["name"]}", medPrice: {z["medPrice"]}, '
            f'priceRange: [{z["q1"]}, {z["q3"]}], count: {z["count"]}, '
            f'ageMed: {z["ageMed"]}, roomMed: {z["roomMed"]}, '
            f'indoorPct: {z["indoorPct"]} }},'
        )
    out.append("];")
    out.append("// <<AUTO-ZONES-END>>")
    block = "\n".join(out)

    content = DATA_JS.read_text(encoding="utf-8")
    new, n = re.subn(r"// <<AUTO-ZONES-START>>.*?// <<AUTO-ZONES-END>>",
                     lambda _m: block, content, flags=re.S)
    if n == 0:
        sys.exit("⚠ 找不到 <<AUTO-ZONES-START/END>> 標記，未變更")
    DATA_JS.write_text(new, encoding="utf-8")
    print(f"✅ 已更新 {DATA_JS}（{len(zones)} 商圈，{total_n} 筆，資料截至 {data_month}）")


# ── 三類（成屋／預售／透天）全區行情 → LINKOU_TYPES ──────────
OFFICE_KW = ("辦公", "商業", "店", "廠", "工業")


def btype_class(bt):
    """依建物型態(rps11)分類：'house' 透天/別墅｜'apt' 集合住宅｜None 其他(辦公/店面…)。"""
    bt = bt or ""
    if "透天" in bt or "別墅" in bt:
        return "house"
    if any(k in bt for k in OFFICE_KW):
        return None
    if "大樓" in bt or "華廈" in bt or "公寓" in bt:
        return "apt"
    return None


def row_metrics(r):
    """從一筆 rps 算 metrics；不合格回 None。
       單價=(總價−車位價)/不含車位坪（與 LINKOU_ZONES 地段表同口徑，保持一致、不丟樣本）。"""
    total = num(r.get("rps21_amountsunitdollars"))
    area = num(r.get("rps15_area"))
    if not total or not area:
        return None
    park_area = num(r.get("rps24_area")) or 0.0
    park_price = num(r.get("rps25_amountsunitdollars")) or 0.0
    ping = (area - park_area) / PING_M2
    if ping <= 0:
        return None
    unit = (total - park_price) / 10000 / ping
    if unit <= 5 or unit > 200:                      # 去離譜值
        return None
    date_raw = r.get("rps07_yyymmddroc")
    build_raw = r.get("rps14_yyymmddroc")
    ty, by = roc_year(date_raw), roc_year(build_raw)
    age = (ty - by) if (ty and by and 0 <= ty - by < 80) else None
    return {"unit": unit, "ping": ping, "total": total / 10000,
            "age": age, "rooms": num(r.get("rps16_quantity")), "date": roc_int(date_raw)}


def collect_type(raw, kind):
    """收集某類(kind:'apt'/'house')全區 metrics（新北 API 成屋資料）。"""
    out = []
    for r in raw:
        if r.get("district") != "林口區":
            continue
        if "建物" not in (r.get("rps01") or ""):
            continue
        if btype_class(r.get("rps11")) != kind:
            continue
        if (r.get("rps12") or "") not in RESIDENTIAL:
            continue
        if any(k in (r.get("rps26") or "") for k in SPECIAL):
            continue
        m = row_metrics(r)
        if m and m["date"]:
            out.append(m)
    return out


def recent_year(recs):
    """以資料最新日回推一年，再去極端值 1%~99%。"""
    if not recs:
        return recs
    max_d = max(c["date"] for c in recs)
    recs = [c for c in recs if c["date"] >= max_d - 10000]
    units = sorted(c["unit"] for c in recs)
    if len(units) >= 20:
        lo, hi = percentile(units, 0.01), percentile(units, 0.99)
        recs = [c for c in recs if lo <= c["unit"] <= hi]
    return recs


def type_stat(recs):
    if not recs:
        return None
    u = sorted(c["unit"] for c in recs)
    tp = sorted(c["total"] for c in recs)
    pg = sorted(c["ping"] for c in recs)
    ages = [c["age"] for c in recs if c["age"] is not None]
    rooms = [c["rooms"] for c in recs if c["rooms"] is not None]
    return {
        "unit": round(statistics.median(u), 1),
        "q1": round(percentile(u, 0.25), 1),
        "q3": round(percentile(u, 0.75), 1),
        "total": round(statistics.median(tp)),
        "ping": round(statistics.median(pg), 1),
        "age": round(statistics.median(ages)) if ages else None,
        "room": round(statistics.median(rooms)) if rooms else 0,
        "n": len(recs),
    }


def build_types(raw_resale, presale_apt, presale_house):
    """presale_apt / presale_house：由行情主檔（內政部季檔）轉出的預售 metrics。"""
    resale = type_stat(recent_year(collect_type(raw_resale, "apt")))
    presale = type_stat(recent_year(presale_apt))
    house = type_stat(recent_year(collect_type(raw_resale, "house")
                                  + presale_house))
    for label, s in (("成屋", resale), ("預售", presale), ("透天", house)):
        if s:
            print(f"  {label}: n={s['n']} 單價中位={s['unit']} [Q1Q3 {s['q1']}-{s['q3']}] "
                  f"總價中位={s['total']}萬 屋齡={s['age']} 坪={s['ping']} 房={s['room']}")
        else:
            print(f"  {label}: 無足量資料")
    return {"resale": resale, "presale": presale, "house": house}


def write_types_js(types):
    r, p, h = types["resale"], types["presale"], types["house"]
    if not r or not p:
        print("⚠ 成屋或預售三類統計不足，略過 LINKOU_TYPES（保留舊值）")
        return
    today = date.today().isoformat()
    L = []
    L.append("// <<AUTO-TYPES-START>>  ← 此區塊由 update_prices.py 自動產生，請勿手改")
    L.append(f"// ── 林口 成屋／預售／透天 三類行情（自動更新：{today}；近一年） ──")
    L.append("// 來源：成屋=新北開放平臺 實價登錄(ACCE802D，透天同源用建物型態拆出)；預售=內政部季檔")
    L.append("// 單價=(總價−車位價)/不含車位坪/10000（與地段表同口徑）；預售排除解約、無屋齡")
    L.append("// calc=true 可依預算精準試算坪數；false 樣本少、僅作總價門檻參考")
    L.append("const LINKOU_TYPES = [")
    L.append(f'  {{ key: "resale", name: "成屋", sub: "電梯大樓／華廈", tag: "看屋即入住",')
    L.append(f'    unit: {r["unit"]}, unitRange: [{r["q1"]}, {r["q3"]}], totalMed: {r["total"]}, '
             f'ageMed: {r["age"] if r["age"] is not None else "null"}, pingMed: {r["ping"]}, roomMed: {r["room"]},')
    L.append(f'    n: {r["n"]}, window: "近一年", calc: true,')
    L.append(f'    note: "現成可看實屋、可立即入住，屋齡中位約 {r["age"]} 年。" }},')
    L.append(f'  {{ key: "presale", name: "預售屋", sub: "興建中／全新", tag: "全新可分期",')
    L.append(f'    unit: {p["unit"]}, unitRange: [{p["q1"]}, {p["q3"]}], totalMed: {p["total"]}, '
             f'ageMed: null, pingMed: {p["ping"]}, roomMed: {p["room"]},')
    L.append(f'    n: {p["n"]}, window: "近一年", calc: true,')
    L.append(f'    note: "全新、可依工程期分期付款；單價約比成屋高三成，需等交屋。" }},')
    if h and h["n"] >= 8:
        L.append(f'  {{ key: "house", name: "透天／別墅", sub: "獨棟含土地", tag: "樣本少·參考",')
        L.append(f'    unit: {h["unit"]}, unitRange: [{h["q1"]}, {h["q3"]}], totalMed: {h["total"]}, '
                 f'threshold: 3000, ageMed: {h["age"] if h["age"] is not None else "null"}, pingMed: {h["ping"]}, roomMed: {h["room"]},')
        L.append(f'    n: {h["n"]}, window: "近一年", calc: false,')
        L.append(f'    note: "總價門檻約 3,000 萬起、中位約 {h["total"]:,} 萬；近一年林口僅 {h["n"]} 筆成交，僅供方向參考。" }},')
    L.append("];")
    L.append("// <<AUTO-TYPES-END>>")
    block = "\n".join(L)

    content = DATA_JS.read_text(encoding="utf-8")
    new, n = re.subn(r"// <<AUTO-TYPES-START>>.*?// <<AUTO-TYPES-END>>",
                     lambda _m: block, content, flags=re.S)
    if n == 0:
        print("⚠ 找不到 <<AUTO-TYPES-START/END>> 標記，略過三類更新")
        return
    DATA_JS.write_text(new, encoding="utf-8")
    print(f"✅ 已更新 LINKOU_TYPES（成屋 {r['n']}／預售 {p['n']}／透天 {h['n'] if h else 0}）")


# ── 行情逐筆表：內政部季檔 → price-history.json + price-list-data.js ────────
# 為什麼用內政部季檔而不是新北 API：
#   ① 逐筆明細需要近三年歷史，新北 API 是滾動快照、深度不足且由政府決定；
#   ② 季檔預售專檔有「建案名稱／棟及號／解約情形」欄位（社區對照直接可用）；
#   ③ 新北 API 的預售資料集 9238CCC2 自 2026-07 起實測回傳「租賃」資料，已不可用。
# 累積模式：每月抓最近幾季「合併」進主檔（編號去重、後出覆蓋），從開跑起不漏筆；
# 首次執行（主檔不存在）自動回填約 3.5 年。
MOI_URL = ("https://plvr.land.moi.gov.tw/DownloadSeason"
           "?season={season}&fileName=f_lvr_land_{f}.csv")
HISTORY_JSON = Path("price-history.json")     # 累積主檔（被排除筆也留著、只加旗標，改政策不用重回填）
PRICE_JS = Path("price-list-data.js")         # 瀏覽器用（近三年、已過濾）
SUMMARY_JSON = Path("price-summary.json")     # LINE bot 行情摘要卡用的小檔（每社區筆數/中位價）
DOORS_JS = Path("community-doors.js")         # 社區↔門牌對照庫（repo 內同步複本，網頁同款）
BACKFILL_SEASONS = 14   # 首次回填抓 14 季（約 3.5 年，含登記時差餘裕）
REFRESH_SEASONS = 5     # 每月重抓最近 5 季（涵蓋登記時差與預售解約異動）

BT_NAMES = ["住宅大樓", "華廈", "公寓", "透天厝", "別墅", "套房"]     # bt 代碼 0~5
PT_NAMES = ["", "坡道平面", "坡道機械", "升降平面", "升降機械",
            "塔式車位", "一樓平面", "其他"]                          # pt 代碼 0~7
PRICE_COLS = ["k", "d", "a", "f", "tf", "bt", "by", "t", "u",
              "s", "ps", "pt", "pp", "r", "gs", "cm"]

_ZH_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}


def zh2int(s):
    """中文數字 一～九十九 → int；解不了回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _ZH_NUM.get(a, 1 if a == "" else None)
        ones = _ZH_NUM.get(b, 0 if b == "" else None)
        return tens * 10 + ones if tens is not None and ones is not None else None
    return _ZH_NUM.get(s)


def floors_of(s):
    """移轉層次 → 精簡字串："十三層"→"13"、"三層，陽台"→"3"、"地下一層"→"B1"、含全→"全"。"""
    s = to_half(s or "").replace(",", "，")
    if not s:
        return ""
    if "全" in s:
        return "全"
    out = []
    for tok in s.split("，"):
        tok = tok.replace("層", "").strip()
        if not tok:
            continue
        if tok.startswith("地下"):
            n = zh2int(tok[2:])
            if n:
                out.append(f"B{n}")
            continue
        n = zh2int(tok)
        if n:
            out.append(str(n))
    return ",".join(out)


def fetch_season_rows(season, f):
    """下載某季新北季檔（f='a' 成屋、'b' 預售），回傳林口區的列。
       季檔尚無內容（季初）回 []；網路錯誤重試後仍失敗則拋例外（由呼叫端決定保留舊檔）。"""
    url = MOI_URL.format(season=season, f=f)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (linkou-toolbox-bot)"})
    raw = None
    for i in range(4):
        try:
            with urlopen(req, timeout=180) as r:
                raw = r.read().decode("utf-8-sig")
            break
        except Exception as e:                          # noqa: BLE001
            if i == 3:
                raise
            wait = 10 * (i + 1)
            print(f"  ⚠ {season} f_{f} 下載失敗（{e}），{wait}s 後重試")
            time.sleep(wait)
    if "鄉鎮市區" not in raw[:300]:
        print(f"  {season} f_{f}：無資料（季初或格式異常），略過")
        return []
    rows = [r for r in csv.DictReader(io.StringIO(raw))
            if (r.get("鄉鎮市區") or "").strip() == "林口區"]   # 第二列英文表頭也在此被濾掉
    print(f"  {season} f_{f}：林口 {len(rows)} 筆")
    return rows


def parse_moi_row(r, kind):
    """季檔一列 → (編號, 精簡紀錄)；非住宅建物或關鍵欄位缺漏回 None。
       特殊交易 sp／預售解約 x／離譜值 o 只加旗標不丟棄（輸出時才過濾）。"""
    if "建物" not in (r.get("交易標的") or ""):
        return None
    btxt = r.get("建物型態") or ""
    bt = None
    for i, name in enumerate(BT_NAMES):
        if name[:2] in btxt:
            bt = i
            break
    if bt is None:                                     # 店面/廠辦/其他 → 不進住宅行情表
        return None
    rid = (r.get("編號") or "").strip()
    d = roc_int(r.get("交易年月日"))
    total = num(r.get("總價元"))
    area = num(r.get("建物移轉總面積平方公尺"))
    if not rid or d is None or not total or not area:
        return None
    park_a = num(r.get("車位移轉總面積平方公尺")) or 0.0
    park_p = num(r.get("車位總價元")) or 0.0
    ping_h = (area - park_a) / PING_M2                 # 不含車位坪（單價分母，與地段表同口徑）
    unit = round((total - park_p) / 10000 / ping_h, 1) if ping_h > 0 else 0

    addr = to_half((r.get("土地位置建物門牌") or "").strip())
    if addr.startswith("新北市林口區"):
        addr = addr[len("新北市林口區"):]

    pt_txt = (r.get("車位類別") or "").strip()
    pt = PT_NAMES.index(pt_txt) if pt_txt in PT_NAMES else (7 if pt_txt else 0)

    rec = {"k": kind, "d": d, "a": addr,
           "f": floors_of(r.get("移轉層次")),
           "tf": zh2int((r.get("總樓層數") or "").replace("層", "").strip()) or 0,
           "bt": bt, "by": roc_year(r.get("建築完成年月")) or 0,
           "t": round(total / 10000), "u": unit,
           "s": round(area / PING_M2, 1), "ps": round(park_a / PING_M2, 1),
           "pt": pt, "pp": round(park_p / 10000),
           "r": int(num(r.get("建物現況格局-房")) or 0)}

    # 公設比 =（1 − 室內/扣車位面積）×100；室內＝主建物＋附屬＋陽台（同 indoorPct 口徑）
    m_a = num(r.get("主建物面積")) or 0.0
    s_a = num(r.get("附屬建物面積")) or 0.0
    b_a = num(r.get("陽台面積")) or 0.0
    if ping_h > 0 and m_a > 0:
        rec["gs"] = max(round((1 - (m_a + s_a + b_a) / (area - park_a)) * 100), 0)
    else:
        rec["gs"] = -1                                 # -1＝無資料（預售或未填主建物）

    if kind == "p":
        rec["cm"] = (r.get("建案名稱") or "").strip()
        if (r.get("解約情形") or "").strip():
            rec["x"] = 1
    if any(kw in (r.get("備註") or "") for kw in SPECIAL):
        rec["sp"] = 1
    if unit and not (5 <= unit <= 200):
        rec["o"] = 1
    return rid, rec


def roc_seasons(n):
    """由當季往回共 n 季，回傳舊→新（如 ["112S2", …, "115S3"]）。"""
    t = date.today()
    y, q = t.year - 1911, (t.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append(f"{y}S{q}")
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out[::-1]


def write_price_js(records):
    """主檔 → price-list-data.js（近三年、排除旗標筆、日期新→舊）。整檔重新產生。"""
    recs = [r for r in records.values()
            if not r.get("sp") and not r.get("x") and not r.get("o")]
    if not recs:
        print("⚠ 行情主檔過濾後無資料，price-list-data.js 不更新")
        return
    max_d = max(r["d"] for r in recs)
    cutoff = max_d - 30000                             # 民國 yyymmdd 減 3 年
    recs = [r for r in recs if r["d"] >= cutoff]
    recs.sort(key=lambda r: (-r["d"], r["a"]))

    today = date.today().isoformat()
    n_r = sum(1 for r in recs if r["k"] == "r")
    n_p = len(recs) - n_r
    L = []
    L.append("// price-list-data.js — 林口實價登錄逐筆明細（update_prices.py 自動產生，請勿手改）")
    L.append("// 來源：內政部實價登錄季檔（成屋+預售），每月自動累積更新；僅住宅類建物")
    L.append("// 口徑：u 單價 =（總價 − 車位總價）÷ 不含車位坪；已排除特殊交易、預售解約、離譜單價")
    L.append("// 欄位（每列依 PRICE_COLS 順序）：")
    L.append("//   k 成屋r/預售p｜d 交易日(民國yyymmdd)｜a 門牌｜f 移轉層次｜tf 總樓層")
    L.append("//   bt 建物型態(PRICE_BT 索引)｜by 建成民國年(0=無，預售即此類)｜t 總價(萬)")
    L.append("//   u 單價(萬/坪，0=無法計算)｜s 登記總坪(含車位)｜ps 車位坪｜pt 車位類別(PRICE_PT 索引)")
    L.append("//   pp 車位價(萬)｜r 房數｜gs 公設比%(-1=無資料)｜cm 建案名稱(預售才有)")
    L.append(f'const PRICE_META = {{ updated: "{today}", maxDate: {max_d}, '
             f'n: {len(recs)}, nResale: {n_r}, nPresale: {n_p} }};')
    L.append("const PRICE_COLS = " + json.dumps(PRICE_COLS) + ";")
    L.append("const PRICE_BT = " + json.dumps(BT_NAMES, ensure_ascii=False) + ";")
    L.append("const PRICE_PT = " + json.dumps(PT_NAMES, ensure_ascii=False) + ";")
    L.append("const PRICE_ROWS = [")
    for r in recs:
        row = [r.get(c, "") if c in ("k", "a", "f", "cm") else r.get(c, 0)
               for c in PRICE_COLS]
        L.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + ",")
    L.append("];")
    txt = "\n".join(L) + "\n"
    PRICE_JS.write_text(txt, encoding="utf-8")
    print(f"✅ 已更新 {PRICE_JS}（近三年 {len(recs)} 筆＝成屋 {n_r}＋預售 {n_p}，"
          f"{len(txt.encode('utf-8')) // 1024} KB）")


# 與網頁/school-logic 的 normalizeComm 同一套：去掉通用字再比對，提升建案名命中率
_COMM_STRIP = re.compile("管理委員會|管委會|社區|大廈|大樓|公寓|住戶|集合住宅|管理負責人")


def norm_comm(s):
    return _COMM_STRIP.sub("", s or "").lower().strip()


# 對照庫每行長相：「"社區名":["路|巷-弄|號基底",…],」（檔尾可能帶逗號）
_DOORS_LINE = re.compile(r'^"(.+?)":(\[.*\]),?$')


def load_comm_doors():
    """讀 repo 內 community-doors.js（社區→一串門牌基底）。失敗回 {}＝退回舊行為。"""
    if not DOORS_JS.exists():
        print("⚠ 找不到 community-doors.js，行情摘要退回只比對建檔門牌")
        return {}
    doors = {}
    for line in DOORS_JS.read_text(encoding="utf-8").splitlines():
        m = _DOORS_LINE.match(line.strip())
        if m:
            try:
                doors[m.group(1)] = json.loads(m.group(2))
            except ValueError:
                pass
    if not doors:
        print("⚠ community-doors.js 解析不出任何社區，行情摘要退回只比對建檔門牌")
    return doors


def build_price_summary(records):
    """主檔＋COMMUNITY 對照 → price-summary.json（LINE bot 查行情按鈕的摘要來源）。
       口徑與 price/ 網頁完全一致（同 report-logic.js 的 commDoorSet）：
       成屋比對「community-doors.js 對照庫 ∪ 建檔門牌」的整串門牌基底、
       預售比對建案名稱（正規化互含）；近 1 年不足 5 筆放寬至 2、3 年；
       單價/總價中位數不含透天別墅。失敗保留舊檔。"""
    comm = load_community()
    if not comm:
        print("⚠ 抓不到 COMMUNITY，略過 price-summary.json（保留舊檔）")
        return
    doors = load_comm_doors()
    recs = [r for r in records.values()
            if not r.get("sp") and not r.get("x") and not r.get("o")]
    if not recs:
        return
    max_d = max(r["d"] for r in recs)
    recs = [r for r in recs if r["d"] >= max_d - 30000]

    by_addr = {}    # 成屋：(路,巷弄,基底號) → rows
    by_proj = {}    # 預售：建案名稱 → rows
    for r in recs:
        if r["k"] == "r":
            p = parse_house(r["a"])
            if p:
                by_addr.setdefault((p["road"], p["lk"], p["num"].split("-")[0]), []).append(r)
        elif r.get("cm"):
            by_proj.setdefault(r["cm"], []).append(r)

    def stat(rows):
        w = []
        yrs = 3
        for yrs in (1, 2, 3):
            w = [x for x in rows if x["d"] >= max_d - yrs * 10000]
            if len(w) >= 5 or yrs == 3:
                break
        if not w:
            return None
        core = [x for x in w if x["bt"] not in (3, 4) and x["u"]]
        ent = {"n": len(w), "yrs": yrs, "last": max(x["d"] for x in w)}
        if core:
            ent["u"] = round(statistics.median([x["u"] for x in core]), 1)
            ent["t"] = round(statistics.median([x["t"] for x in core]))
        return ent

    out_c = {}
    for name, c in comm.items():
        # 門牌基底集合＝對照庫 ∪ 建檔地址（key 去重，每筆成交只屬一個基底、不會重複計）
        keys = set()
        for k in doors.get(name, []):
            parts = k.split("|")
            if len(parts) == 3:                    # "路|巷-弄|號基底"
                keys.add(tuple(parts))
        addr = (c.get("addr") or "").strip()
        if addr:
            p = parse_house(addr)
            if p:
                keys.add((p["road"], p["lk"], p["num"].split("-")[0]))
        rows = []
        for k in keys:
            rows += by_addr.get(k, [])
        nn = norm_comm(name)
        if len(nn) >= 2:
            for cm_name, prows in by_proj.items():
                nc = norm_comm(cm_name)
                if nc and (nc == nn or nn in nc or nc in nn):
                    rows += prows
        ent = stat(rows)
        if ent:
            out_c[name] = ent

    out_p = {cm_name: ent for cm_name, prows in by_proj.items()
             if (ent := stat(prows))}

    SUMMARY_JSON.write_text(json.dumps(
        {"updated": date.today().isoformat(), "maxDate": max_d,
         "comm": out_c, "pre": out_p},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ 已更新 {SUMMARY_JSON}（有成交的社區 {len(out_c)}、預售建案 {len(out_p)}）")


def moi_presale_metrics(records):
    """從主檔取預售筆，轉成與 row_metrics 同構的 dict 餵給 type_stat（LINKOU_TYPES 用）。"""
    apt, house = [], []
    for r in records.values():
        if r["k"] != "p" or r.get("x") or r.get("sp") or r.get("o") or not r["u"]:
            continue
        m = {"unit": r["u"], "ping": round(r["s"] - r["ps"], 1), "total": r["t"],
             "age": None, "rooms": r["r"] or None, "date": r["d"]}
        (house if r["bt"] in (3, 4) else apt).append(m)
    return apt, house


def build_price_list():
    """下載季檔、合併主檔、產出前端檔。回傳預售 metrics (apt, house)；
       失敗回 (None, None) 且不動舊檔（與 LINKOU_TYPES「保留舊值」同一安全設計）。"""
    records = {}
    if HISTORY_JSON.exists():
        records = json.loads(HISTORY_JSON.read_text(encoding="utf-8")).get("records", {})
    seasons = roc_seasons(REFRESH_SEASONS if records else BACKFILL_SEASONS)
    print(f"{'每月更新' if records else '首次回填'}：抓 {seasons[0]}～{seasons[-1]} 共 {len(seasons)} 季")
    added = changed = 0
    try:
        for season in seasons:                          # 舊→新：後出的更正/解約覆蓋舊值
            for f, kind in (("a", "r"), ("b", "p")):
                for row in fetch_season_rows(season, f):
                    parsed = parse_moi_row(row, kind)
                    if not parsed:
                        continue
                    rid, rec = parsed
                    if rid not in records:
                        added += 1
                    elif records[rid] != rec:
                        changed += 1
                    records[rid] = rec
    except Exception as e:                              # noqa: BLE001
        print(f"⚠ 季檔下載/解析失敗（{e}），行情檔保留舊值不更新")
        return None, None
    if not records:
        print("⚠ 季檔無林口住宅資料，行情檔不更新")
        return None, None
    print(f"行情主檔：共 {len(records)} 筆（本次新增 {added}、異動 {changed}）")
    HISTORY_JSON.write_text(
        json.dumps({"updated": date.today().isoformat(), "records": records},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    write_price_js(records)
    build_price_summary(records)
    return moi_presale_metrics(records)


def main():
    print("抓取新北開放平臺 API（成屋）…")
    raw_resale = fetch_all(API)
    print(f"全新北成屋累計 {len(raw_resale)} 筆")
    zones, max_d = build_zones(raw_resale)
    write_js(zones, max_d)

    print("更新行情逐筆檔（內政部季檔，成屋＋預售）…")
    presale_apt, presale_house = build_price_list()
    if presale_apt is None:
        print("⚠ 無預售資料，LINKOU_TYPES 保留舊值")
        return
    write_types_js(build_types(raw_resale, presale_apt, presale_house))


if __name__ == "__main__":
    main()
