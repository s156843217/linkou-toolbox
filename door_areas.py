# -*- coding: utf-8 -*-
"""
door_areas.py — 林口門牌坪數庫（戶級標示面積，估價／查坪數功能的基礎資料層）
============================================================================
做什麼：從內政部實價登錄季檔（成屋 f_lvr_land_a）擷取每一戶的登記面積，
        以「路｜巷-弄｜號｜樓」為 key 累積成門牌坪數庫。每戶取最可信的一筆
        （有主建物面積者優先，其次交易日最新）。

產出兩個檔：
  door-area.json  累積主檔（真相來源，只由 GitHub Actions 維護）
  area-data.js    前端用巢狀結構（file:// 直接載入，估價頁／查坪數用）

用法：
  python door_areas.py backfill   # 一次回填 101S3 起全部季（backfill-areas.yml 用）
  被 update_prices.py import：update_from_rows(rows) 每月增量更新

設計重點（與 update_prices.py 相同原則）：
  - 只用標準庫；自足式（不 import update_prices，避免循環相依）。
  - 任一步失敗就保留舊檔不覆寫，不中斷主管線。
  - 門牌正規化規則以 55 季實資料驗證過：全形→半形、注音「ㄧ」→「一」、
    去空白、樓層「N樓／N樓之N／地下N層」、門牌「N之M號」；
    一筆交易含多戶（「及」「、」串接）或解析不出者直接跳過（占比 <0.1%）。
  - 預售(b)檔沒有真門牌與面積拆分，不進本庫。
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

MOI_URL = ("https://plvr.land.moi.gov.tw/DownloadSeason"
           "?season={season}&fileName=f_lvr_land_a.csv")
AREA_JSON = Path("door-area.json")   # 累積主檔
AREA_JS = Path("area-data.js")       # 前端用
PING_M2 = 3.305785
FIRST_SEASON = (101, 3)              # 實價登錄自 101S3 開始有資料

# 建物型態代碼（AREA_BT 索引；比對時「廠辦」要先於「工廠」、「辦公」先於「大樓」）
BT_NAMES = ["住宅大樓", "華廈", "公寓", "透天厝", "別墅", "套房",
            "店面", "辦公商業大樓", "廠辦", "工廠", "農舍", "倉庫", "其他"]
_BT_KEYS = [("透天", 3), ("別墅", 4), ("華廈", 1), ("公寓", 2), ("套房", 5),
            ("店面", 6), ("店鋪", 6), ("辦公", 7), ("廠辦", 8), ("工廠", 9),
            ("農舍", 10), ("倉庫", 11), ("住宅大樓", 0), ("大樓", 0)]

# 每戶輸出欄位順序（area-data.js 的 u 陣列；單位＝坪，2 位小數）
AREA_COLS = ["m", "sa", "ba", "gs", "ps", "tot", "bt"]
# m 主建物｜sa 附屬建物｜ba 陽台｜gs 共有(不含車位)｜ps 車位｜tot 登記總坪(含車位)｜bt 型態代碼


# ── 正規化工具 ────────────────────────────────────────────
_FW = str.maketrans("０１２３４５６７８９－～／　", "0123456789-~/ ")
_ZH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9}


def to_half(s):
    return (s or "").translate(_FW)


def num(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def roc_int(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() and len(s) >= 6 else None


def ping(m2):
    return round(m2 / PING_M2, 2)


def zh2int(s):
    """中文或阿拉伯數字 → int；解不了回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _ZH.get(a, 1 if a == "" else None)
        ones = _ZH.get(b, 0 if b == "" else None)
        return tens * 10 + ones if tens is not None and ones is not None else None
    return _ZH.get(s)


_NUM_ZH = "0-9一二三四五六七八九十"


def parse_floor(tail):
    """門牌「號」之後的字串 → 樓層 key。
       "十三樓"→"13"｜"5樓之1"→"5-1"｜"地下一層"→"B1"｜""→""（透天/一樓/整棟）
       解析不出（含多戶、殘缺字串）回 None，呼叫端跳過該筆。"""
    t = tail.replace(" ", "")
    if not t:
        return ""
    if re.search(r"[及、;；‧·，,]", t):                 # 一筆含多戶 → 不進戶級庫
        return None
    m = re.fullmatch(rf"地下([{_NUM_ZH}]*)[層樓](?:之([{_NUM_ZH}]+)|([{_NUM_ZH}]+)號)?", t)
    if m:
        n = zh2int(m.group(1)) if m.group(1) else 1
        if not n:
            return None
        sub = zh2int(m.group(2) or m.group(3)) if (m.group(2) or m.group(3)) else None
        return f"B{n}-{sub}" if sub else f"B{n}"
    m = re.fullmatch(rf"([{_NUM_ZH}]+)樓(?:之([{_NUM_ZH}]+))?", t)
    if m:
        n = zh2int(m.group(1))
        if n is None:
            return None
        if m.group(2):
            s = zh2int(m.group(2))
            return f"{n}-{s}" if s is not None else None
        return str(n)
    return None


def parse_addr(addr):
    """完整門牌 → (路, 巷-弄, 號, 樓層key)；解析不出回 None。
       規則與學區 parseHouse 同源（road/lk/num 同格式），另補樓層。"""
    a = to_half(addr).strip().replace("ㄧ", "一")       # 注音「ㄧ」混用實資料出現過
    if "林口" in a:
        a = re.sub(r"^.*林口區", "", a)
    a = re.sub(r"(新北市|臺北市|台北市)", "", a)
    a = re.sub(r"[一-鿿]+里", "", a)                    # 只刪「里」；「村」可能是路名（醒吾新村）
    a = re.sub(r"\d+鄰", "", a)
    a = a.replace(" ", "")
    # 數字段 →中文段（「文化三路1段」實資料約 370 筆），路名判定才不會在段號切斷
    a = re.sub(r"([1-9])段",
               lambda m: "一二三四五六七八九"[int(m.group(1)) - 1] + "段", a)
    m = re.search(r"\d", a)
    if not m:
        return None
    road = a[:m.start()]
    if not road:
        return None
    rest = a[m.start():]
    ml = re.search(r"(\d+)巷", rest)
    mz = re.search(r"(\d+)弄", rest)
    lk = (ml.group(1) if ml else "") + "-" + (mz.group(1) if mz else "")
    r2 = re.sub(r"\d+巷", "", rest)
    r2 = re.sub(r"\d+弄", "", r2)
    mn = re.match(r"(\d+)(?:[之\-](\d+))?號(?:之(\d+))?", r2)
    if not mn:
        return None
    sub = mn.group(2) or mn.group(3)                    # 「1之2號」＝「1-2號」＝「1號之2」
    door_no = mn.group(1) + (f"-{sub}" if sub else "")
    fl = parse_floor(r2[mn.end():])
    if fl is None:
        return None
    return road, lk, door_no, fl


def bt_of(btxt):
    btxt = btxt or ""
    for kw, i in _BT_KEYS:
        if kw in btxt:
            return i
    return 12                                           # 其他


# ── 一列季檔 → (key, 戶紀錄) ─────────────────────────────
def make_rec(r):
    if "建物" not in (r.get("交易標的") or ""):
        return None
    p = parse_addr((r.get("土地位置建物門牌") or "").strip())
    if not p:
        return None
    d = roc_int(r.get("交易年月日"))
    area = num(r.get("建物移轉總面積平方公尺"))
    if d is None or not area:
        return None
    park = num(r.get("車位移轉總面積平方公尺")) or 0.0
    m_a = num(r.get("主建物面積")) or 0.0
    s_a = num(r.get("附屬建物面積")) or 0.0
    b_a = num(r.get("陽台面積")) or 0.0
    gs = max(area - park - m_a - s_a - b_a, 0.0)        # 共有(不含車位)＝總−車−主−附−陽
    tf = zh2int(to_half(r.get("總樓層數") or "").replace("層", "").strip()) or 0
    rec = {"d": d, "m": ping(m_a), "sa": ping(s_a), "ba": ping(b_a),
           "gs": ping(gs), "ps": ping(park), "tot": ping(area),
           "by": roc_int(r.get("建築完成年月")) or 0, "tf": tf,
           "bt": bt_of(r.get("建物型態"))}
    return "|".join(p), rec


def better(new, old):
    """同一戶多筆交易的取捨：有主建物面積者優先，再比交易日新。"""
    if old is None:
        return True
    if (new["m"] > 0) != (old["m"] > 0):
        return new["m"] > 0
    return new["d"] >= old["d"]


# ── 前端檔輸出 ────────────────────────────────────────────
def _door_sort(k):
    """號/樓 key 排序用："116-2" → (116, 2)。"""
    a, _, b = k.partition("-")
    return (int(a) if a.isdigit() else 999999, int(b) if b.isdigit() else 0)


def write_js(doors):
    nested = {}
    for key, rec in doors.items():
        road, lk, no, fl = key.split("|")
        nested.setdefault(road, {}).setdefault(lk, {}).setdefault(no, {})[fl] = rec
    max_d = max(r["d"] for r in doors.values())
    n_base = sum(len(nos) for lks in nested.values() for nos in lks.values())

    L = []
    L.append("// area-data.js — 林口門牌坪數庫（door_areas.py 自動產生，請勿手改）")
    L.append("// 來源：內政部實價登錄季檔（成屋）；每戶取最新一筆交易的登記面積")
    L.append("// 結構：AREA_DATA[路][巷-弄][號][樓] = [m,sa,ba,gs,ps,tot,bt]（AREA_COLS 順序）")
    L.append("//   巷-弄 無巷弄時為 \"-\"；號「1之2」＝\"1-2\"；樓 \"13\"/\"5-1\"/\"B1\"/\"\"(透天、整棟或一樓)")
    L.append("//   m 主建物｜sa 附屬｜ba 陽台｜gs 共有(不含車位)｜ps 車位｜tot 登記總坪(含車位)")
    L.append("//   bt 建物型態＝AREA_BT 索引。單位＝坪(2位小數)。車位/總坪取自單一交易，僅供參考")
    L.append("//   ⚠ 面積為該戶「歷史成交當時」的登記值；從沒交易過的戶查不到（可查同棟其他戶）")
    L.append(f'const AREA_META = {{ updated: "{date.today().isoformat()}", '
             f'maxDate: {max_d}, doors: {len(doors)}, bases: {n_base} }};')
    L.append("const AREA_COLS = " + json.dumps(AREA_COLS) + ";")
    L.append("const AREA_BT = " + json.dumps(BT_NAMES, ensure_ascii=False) + ";")
    L.append("const AREA_DATA = {")
    for road in sorted(nested):
        R = []
        for lk in sorted(nested[road]):
            NOS = []
            for no in sorted(nested[road][lk], key=_door_sort):
                units = nested[road][lk][no]
                # 棟資訊 i＝[總樓層, 建築完成年月日]，取該棟交易日最新一筆
                top = max(units.values(), key=lambda r: r["d"])
                U = ",".join(
                    f'"{fl}":' + json.dumps([units[fl][c] for c in AREA_COLS],
                                            separators=(",", ":"))
                    for fl in sorted(units, key=_door_sort))
                NOS.append(f'"{no}":{{"i":[{top["tf"]},{top["by"]}],"u":{{{U}}}}}')
            R.append(f'"{lk}":{{' + ",".join(NOS) + "}")
        L.append(f'"{road}":{{' + ",".join(R) + "},")
    L.append("};")
    txt = "\n".join(L) + "\n"
    AREA_JS.write_text(txt, encoding="utf-8")
    print(f"✅ 已產出 {AREA_JS}（{len(doors)} 戶／{n_base} 棟，"
          f"{len(txt.encode('utf-8')) // 1024} KB）")


# ── 主檔維護 ─────────────────────────────────────────────
def load_doors():
    if AREA_JSON.exists():
        return json.loads(AREA_JSON.read_text(encoding="utf-8")).get("doors", {})
    return {}


def update_from_rows(rows):
    """把一批季檔成屋列（林口區）併入主檔並重產前端檔。供 update_prices.py 月更呼叫。"""
    doors = load_doors()
    added = updated = 0
    for r in rows:
        parsed = make_rec(r)
        if not parsed:
            continue
        key, rec = parsed
        old = doors.get(key)
        if better(rec, old):
            if old is None:
                added += 1
            elif old != rec:
                updated += 1
            doors[key] = rec
    if not doors:
        print("⚠ 門牌坪數庫無資料，不產出")
        return
    print(f"門牌坪數庫：共 {len(doors)} 戶（本次新增 {added}、更新 {updated}）")
    AREA_JSON.write_text(
        json.dumps({"updated": date.today().isoformat(), "doors": doors},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    write_js(doors)


# ── 回填（backfill-areas.yml 用） ─────────────────────────
def all_seasons():
    """101S3 起到今天所在季，舊→新。"""
    t = date.today()
    ey, eq = t.year - 1911, (t.month - 1) // 3 + 1
    y, q = FIRST_SEASON
    out = []
    while (y, q) <= (ey, eq):
        out.append(f"{y}S{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def fetch_season(season):
    """下載某季成屋檔，回傳林口區列；季初無內容回 []。"""
    url = MOI_URL.format(season=season)
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
            print(f"  ⚠ {season} 下載失敗（{e}），{wait}s 後重試")
            time.sleep(wait)
    if "鄉鎮市區" not in raw[:300]:
        print(f"  {season}：無資料，略過")
        return []
    rows = [r for r in csv.DictReader(io.StringIO(raw))
            if (r.get("鄉鎮市區") or "").strip() == "林口區"]
    print(f"  {season}：林口 {len(rows)} 筆")
    return rows


def backfill():
    seasons = all_seasons()
    print(f"回填 {seasons[0]}～{seasons[-1]} 共 {len(seasons)} 季 …")
    rows = []
    for s in seasons:
        rows.extend(fetch_season(s))
        time.sleep(1)                                   # 對政府主機客氣一點
    print(f"合計 {len(rows)} 筆，開始併入主檔 …")
    update_from_rows(rows)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        backfill()
    else:
        sys.exit("用法：python door_areas.py backfill（月更由 update_prices.py 呼叫）")
