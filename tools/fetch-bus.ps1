<#
====================================================================
 fetch-bus.ps1  —  林口公車資料抓取腳本（資料/邏輯分離：產出 bus-data.js）
====================================================================
 做的事：
   1. 讀 tdx-secret.json 的金鑰，向 TDX 換 access token
   2. 抓 NewTaipei / Taoyuan / InterCity(國道‧公路客運) 的：
        - StopOfRoute：每條路線、每個方向的「站序＋站牌座標」
        - Shape      ：每條路線的線型(WKT LINESTRING)，用來在地圖畫整條路徑
   3. 以「距林口中心 <= 半徑」過濾出『有停靠林口』的路線(含聯外通勤線)
   4. 壓成 bus-data.js(window.BUS_DATA)，供 bus.html 直接讀取

 執行方式：  在專案根目錄執行
     powershell -ExecutionPolicy Bypass -File tools/fetch-bus.ps1

 註：TDX token 不會持久化，腳本每次執行都重新認證。金鑰只存在本機 tdx-secret.json
     (已列入 .gitignore)，不會進 Git、也不會出現在 bus-data.js。
====================================================================
#>

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = "Stop"

# --- 設定 ---------------------------------------------------------
# 腳本固定從專案根目錄執行(CWD=根目錄)；$PSScriptRoot 在某些呼叫方式下為空，故以 CWD 為準
$ROOT      = (Get-Location).Path                        # 專案根目錄
$SECRET    = Join-Path $ROOT "tdx-secret.json"
$OUT       = Join-Path $ROOT "bus-data.js"
$BASE      = "https://tdx.transportdata.tw/api/basic/v2"
# 林口中心與過濾半徑(公尺)：站牌落在此範圍內的路線才保留
$LK_LAT    = 25.0775
$LK_LON    = 121.3645
$RADIUS_M  = 4000
# 資料來源(City 路徑用 City/{name}；InterCity 為公路客運，路徑不同)
$SOURCES   = @(
  @{ name="NewTaipei"; kind="City" },   # 新北市公車(林口在地＋跨北市主力)
  @{ name="Taoyuan";   kind="City" },   # 桃園市(長庚/A7/龜山交界)
  @{ name="InterCity"; kind="Inter" }   # 國道‧公路客運(往台北等聯外線)
)

# --- 工具函式 -----------------------------------------------------
# 兩經緯度距離(公尺)，haversine
function Get-DistM($lat1,$lon1,$lat2,$lon2){
  $R=6371000.0; $rad=[Math]::PI/180
  $dLat=($lat2-$lat1)*$rad; $dLon=($lon2-$lon1)*$rad
  $a=[Math]::Sin($dLat/2)*[Math]::Sin($dLat/2) +
     [Math]::Cos($lat1*$rad)*[Math]::Cos($lat2*$rad)*[Math]::Sin($dLon/2)*[Math]::Sin($dLon/2)
  return $R*2*[Math]::Atan2([Math]::Sqrt($a),[Math]::Sqrt(1-$a))
}
# 解析 WKT 線型 → [[lat,lon],...]，支援 LINESTRING 與 MULTILINESTRING
function Parse-Wkt($wkt){
  if(-not $wkt){ return @() }
  $pts = New-Object System.Collections.ArrayList
  foreach($m in [regex]::Matches($wkt,'(-?\d+\.\d+)\s+(-?\d+\.\d+)')){
    $lon=[double]$m.Groups[1].Value; $lat=[double]$m.Groups[2].Value
    [void]$pts.Add(@([Math]::Round($lat,5),[Math]::Round($lon,5)))
  }
  return $pts
}
# Douglas–Peucker 線型抽稀：刪掉直線段上的冗餘點、保留轉折，大幅縮小檔案。
# eps 為容差(度)，約 0.00012 度 ≈ 13 公尺；對市區/國道路線在地圖上視覺幾乎無差。
function Simplify-DP($pts,$eps){
  if(-not $pts -or $pts.Count -lt 3){ return $pts }
  $n=$pts.Count
  $keep=New-Object 'bool[]' $n
  $keep[0]=$true; $keep[$n-1]=$true
  $stack=New-Object System.Collections.Stack
  $stack.Push(@(0,($n-1)))   # 注意：PowerShell 逗號優先於減號，$n-1 須加括號，否則被解析成 (0,$n)-1
  while($stack.Count){
    $seg=$stack.Pop(); $first=$seg[0]; $last=$seg[1]
    $ax=$pts[$first][0]; $ay=$pts[$first][1]
    $bx=$pts[$last][0];  $by=$pts[$last][1]
    $dx=$bx-$ax; $dy=$by-$ay
    $den=[Math]::Sqrt($dx*$dx+$dy*$dy)
    $maxD=-1.0; $idx=-1
    for($i=$first+1; $i -lt $last; $i++){
      $px=$pts[$i][0]; $py=$pts[$i][1]
      if($den -eq 0){ $dist=[Math]::Sqrt((($px-$ax)*($px-$ax))+(($py-$ay)*($py-$ay))) }
      else { $dist=[Math]::Abs($dy*$px - $dx*$py + $bx*$ay - $by*$ax)/$den }
      if($dist -gt $maxD){ $maxD=$dist; $idx=$i }
    }
    if($maxD -gt $eps -and $idx -ge 0){
      $keep[$idx]=$true
      $stack.Push(@($first,$idx)); $stack.Push(@($idx,$last))
    }
  }
  $out=New-Object System.Collections.ArrayList
  for($i=0;$i -lt $n;$i++){ if($keep[$i]){ [void]$out.Add($pts[$i]) } }
  return $out
}

# 帶 token 的 GET(單引號片段串接，避免 PowerShell 把 $format 當變數)
# 內建節流與「撞速率限制自動退避重試」，尊重 TDX 流量限制(比照專案對外部 API 的節流規範)
function Get-Tdx($H,$path,$query){
  $uri = $BASE + $path + '?' + $query
  $delay = 2
  for($try=1; $try -le 6; $try++){
    try {
      Start-Sleep -Milliseconds 600        # 每次請求前的基本間隔
      return Invoke-RestMethod -Headers $H -Uri $uri
    } catch {
      $msg = "$($_.Exception.Message) $($_.ErrorDetails.Message)"
      if($msg -match "rate limit" -or $msg -match "429"){
        Write-Host "  ↻ 撞到速率限制，等 $delay 秒後重試($try/6)..."
        Start-Sleep -Seconds $delay
        $delay = [Math]::Min($delay*2, 30)   # 指數退避，上限 30 秒
        continue
      }
      throw
    }
  }
  throw "重試多次仍被速率限制：$uri"
}

# --- 1) 認證 ------------------------------------------------------
if(-not (Test-Path $SECRET)){ throw "找不到金鑰檔 $SECRET" }
$cfg = Get-Content -Raw $SECRET | ConvertFrom-Json
Write-Host "→ 向 TDX 認證..."
$tok = (Invoke-RestMethod -Method Post `
  -Uri "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token" `
  -Body @{ grant_type="client_credentials"; client_id=$cfg.client_id; client_secret=$cfg.client_secret } `
  -ContentType "application/x-www-form-urlencoded").access_token
if(-not $tok){ throw "認證失敗：未取得 token" }
$H = @{ Authorization = "Bearer $tok"; "Accept-Encoding"="gzip" }
Write-Host "  認證成功`n"

# --- 2~3) 逐來源抓取並過濾 ---------------------------------------
$stops  = @{}   # StopUID → @{ u;n;la;lo; r=HashSet(routeKey) }
$routes = @{}   # routeKey → @{ n;src;dirs=[ @{to;st;sh} ] }

foreach($s in $SOURCES){
  $cityPath  = if($s.kind -eq "City"){ "/Bus/StopOfRoute/City/" + $s.name } else { "/Bus/StopOfRoute/InterCity" }
  $shapePath = if($s.kind -eq "City"){ "/Bus/Shape/City/" + $s.name }       else { "/Bus/Shape/InterCity" }
  Write-Host "→ 抓取 $($s.name) StopOfRoute ..."
  $sor = Get-Tdx $H $cityPath '$format=JSON'
  Write-Host "  路線方向數(全市): $($sor.Count)，開始過濾林口..."

  Write-Host "→ 抓取 $($s.name) Shape ..."
  $shp = Get-Tdx $H $shapePath '$format=JSON'
  # 建 Shape 查找表：RouteUID + '_' + Direction → 點陣列
  $shapeMap = @{}
  foreach($g in $shp){
    $k = "$($g.RouteUID)_$($g.Direction)"
    if(-not $shapeMap.ContainsKey($k)){ $shapeMap[$k] = Simplify-DP (Parse-Wkt $g.Geometry) 0.00012 }
  }

  $kept = 0
  foreach($r in $sor){
    # 判斷此路線方向是否有站牌落在林口範圍
    $hit = $false
    foreach($st in $r.Stops){
      $p = $st.StopPosition
      if($p -and (Get-DistM $LK_LAT $LK_LON $p.PositionLat $p.PositionLon) -le $RADIUS_M){ $hit=$true; break }
    }
    if(-not $hit){ continue }
    $kept++

    $routeKey = "$($s.name)|$($r.RouteUID)"
    if(-not $routes.ContainsKey($routeKey)){
      $routes[$routeKey] = @{ n=$r.RouteName.Zh_tw; src=$s.name; dirs=@() }
    }
    # 該方向的站序(內嵌座標與站名，畫路線時自給自足)
    $stList = New-Object System.Collections.ArrayList
    foreach($st in ($r.Stops | Sort-Object StopSequence)){
      $p = $st.StopPosition
      $la=[Math]::Round([double]$p.PositionLat,5); $lo=[Math]::Round([double]$p.PositionLon,5)
      [void]$stList.Add(@($la,$lo,$st.StopName.Zh_tw))
      # 若站牌在林口範圍，登錄到 stops(供「附近站牌」搜尋)
      if((Get-DistM $LK_LAT $LK_LON $p.PositionLat $p.PositionLon) -le $RADIUS_M){
        $uid = $st.StopUID
        if(-not $stops.ContainsKey($uid)){
          $stops[$uid] = @{ u=$uid; n=$st.StopName.Zh_tw; la=$la; lo=$lo; r=(New-Object System.Collections.Generic.HashSet[string]) }
        }
        [void]$stops[$uid].r.Add($routeKey)
      }
    }
    $headsign = if($stList.Count){ $stList[$stList.Count-1][2] } else { "" }   # 往(終點站名)
    $shapePts = $shapeMap["$($r.RouteUID)_$($r.Direction)"]
    if(-not $shapePts){ $shapePts = @() }
    $routes[$routeKey].dirs += ,@{ to=$headsign; st=$stList; sh=$shapePts }
  }
  Write-Host "  保留 $kept 條(方向)`n"
}

Write-Host "彙整：林口範圍站牌 $($stops.Count) 個，相關路線 $($routes.Count) 條"

# --- 4) 產出 bus-data.js -----------------------------------------
# 整理成精簡結構；HashSet 轉陣列
$stopsArr = foreach($v in $stops.Values){
  [pscustomobject]@{ u=$v.u; n=$v.n; la=$v.la; lo=$v.lo; r=@($v.r) }
}
$payload = [ordered]@{
  generated = (Get-Date).ToString("yyyy-MM-dd HH:mm")
  center    = @($LK_LAT,$LK_LON)
  stops     = @($stopsArr)
  routes    = $routes
}
$json = $payload | ConvertTo-Json -Depth 12 -Compress
$header = "/* 由 tools/fetch-bus.ps1 自動產生，請勿手改。資料來源：交通部 TDX 運輸資料流通服務平台。*/`n"
Set-Content -Encoding utf8 -Path $OUT -Value ($header + "window.BUS_DATA = " + $json + ";`n")

$sizeKB = [Math]::Round((Get-Item $OUT).Length/1KB,1)
Write-Host "`n✅ 已寫出 $OUT（$sizeKB KB）"
