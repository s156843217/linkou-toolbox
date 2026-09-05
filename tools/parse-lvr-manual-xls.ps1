# 實價登錄官網「進階條件查詢→匯出列表+明細」.xls → manual-updates/*.json
# 用途：手動補登最新成交（比自動排程的季檔/新北API更即時），給 linkou-toolbox 的
#       update_prices.py 讀取合併（見該檔的 merge_manual/parse_manual_case）。
# 這個 .xls 是舊版二進位 Excel 格式（非 ZIP），純 PowerShell 解析不了，靠這台電腦
# 已安裝的 Excel 程式（COM）讀取；跟 lvr-export-merge.ps1（純 PowerShell 解析 .xlsx，
# 給「社區門牌對照庫」用）是兩套獨立工具，用途與輸入格式都不同，互不影響。
#
# 用法：
#   powershell -File tools\parse-lvr-manual-xls.ps1 `
#       -XlsPath "C:\Users\xxx\Downloads\Price.xls" `
#       -OutJson "C:\repo\linkou-toolbox\manual-updates\2026-07-24-1.json" `
#       -Report

param(
    [Parameter(Mandatory = $true)][string]$XlsPath,
    [Parameter(Mandatory = $true)][string]$OutJson,
    [switch]$Report
)

# 去掉千分位逗號、"元"/"坪"/"%" 單位字，轉成數字；轉不了回 $null
function CleanNum($s) {
    if ($null -eq $s) { return $null }
    $t = ($s -replace '[,元坪%]', '').Trim()
    if ($t -eq '') { return $null }
    $v = 0.0
    if ([double]::TryParse($t, [ref]$v)) { return $v }
    return $null
}

# 在前 $maxRow 列裡找出包含 $keyword 的那一列（欄名列），找不到回 -1
function FindHeaderRow($ws, $keyword, $maxRow) {
    $cols = $ws.UsedRange.Columns.Count
    for ($r = 1; $r -le $maxRow; $r++) {
        for ($c = 1; $c -le $cols; $c++) {
            $txt = ($ws.Cells.Item($r, $c).Text -replace '\s', '')
            if ($txt -like "*$keyword*") { return $r }
        }
    }
    return -1
}

# 欄名列 → { 欄名(去空白換行) = 欄序 } 對照表
function BuildColMap($ws, $headerRow, $cols) {
    $map = @{}
    for ($c = 1; $c -le $cols; $c++) {
        $txt = ($ws.Cells.Item($headerRow, $c).Text -replace '\s', '')
        if ($txt) { $map[$txt] = $c }
    }
    return $map
}

# 用關鍵字模糊比對欄名（欄名偶爾會有換行/多餘字，不做 exact match）
function GetCol($map, $keyword) {
    foreach ($k in $map.Keys) {
        if ($k -like "*$keyword*") { return $map[$k] }
    }
    return $null
}

if (-not (Test-Path $XlsPath)) { throw "找不到檔案：$XlsPath" }

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    $wb = $excel.Workbooks.Open($XlsPath, 0, $true)   # 唯讀開啟，不留存檔紀錄

    # --- 案件列表：主表 ---
    $wsCase = $wb.Sheets.Item("案件列表")
    $caseRows = $wsCase.UsedRange.Rows.Count
    $caseCols = $wsCase.UsedRange.Columns.Count
    $hdrRow = FindHeaderRow $wsCase "地段位置或門牌" 5
    if ($hdrRow -lt 0) { throw "「案件列表」分頁找不到欄名列，請確認是否為官網「列表+明細」匯出的 .xls" }
    $cm = BuildColMap $wsCase $hdrRow $caseCols

    $colNo     = GetCol $cm "編號"
    $colAddr   = GetCol $cm "地段位置或門牌"
    $colComm   = GetCol $cm "社區簡稱"
    $colDate   = GetCol $cm "交易日期"
    $colTotal  = GetCol $cm "總價"
    $colArea   = GetCol $cm "總面積"
    $colRatio  = GetCol $cm "主建物佔比"
    $colType   = GetCol $cm "型態"
    $colAge    = GetCol $cm "屋齡"
    $colFloor  = GetCol $cm "樓別"
    $colUse    = GetCol $cm "主要用途"
    $colKind   = GetCol $cm "交易標的"
    $colLayout = GetCol $cm "建物現況格局"
    $colRemark = GetCol $cm "備註"

    if (-not ($colAddr -and $colDate -and $colTotal -and $colArea -and $colKind -and $colType)) {
        throw "「案件列表」缺少必要欄位（地段位置或門牌/交易日期/總價/總面積/交易標的/型態），請確認匯出格式"
    }

    $cases = @{}
    $order = New-Object System.Collections.ArrayList
    for ($r = $hdrRow + 1; $r -le $caseRows; $r++) {
        $addr = $wsCase.Cells.Item($r, $colAddr).Text.Trim()
        if (-not $addr) { continue }   # 空列（表尾）略過
        $no = $wsCase.Cells.Item($r, $colNo).Text.Trim()
        if (-not $no) { $no = "$r" }
        $case = [ordered]@{
            "地段位置或門牌" = $addr
            "社區簡稱"       = $(if ($colComm) { $wsCase.Cells.Item($r, $colComm).Text.Trim() } else { "" })
            "交易日期"       = $wsCase.Cells.Item($r, $colDate).Text.Trim()
            "總價萬元"       = CleanNum $wsCase.Cells.Item($r, $colTotal).Text
            "總面積坪"       = CleanNum $wsCase.Cells.Item($r, $colArea).Text
            "主建物佔比"     = $(if ($colRatio) { CleanNum $wsCase.Cells.Item($r, $colRatio).Text } else { $null })
            "型態"           = $wsCase.Cells.Item($r, $colType).Text.Trim()
            "屋齡"           = $(if ($colAge) { CleanNum $wsCase.Cells.Item($r, $colAge).Text } else { $null })
            "樓別樓高"       = $(if ($colFloor) { ($wsCase.Cells.Item($r, $colFloor).Text -replace '\s', '') } else { "" })
            "主要用途"       = $(if ($colUse) { $wsCase.Cells.Item($r, $colUse).Text.Trim() } else { "" })
            "交易標的"       = $wsCase.Cells.Item($r, $colKind).Text.Trim()
            "建物現況格局"   = $(if ($colLayout) { $wsCase.Cells.Item($r, $colLayout).Text.Trim() } else { "" })
            "備註"           = $(if ($colRemark) { $wsCase.Cells.Item($r, $colRemark).Text.Trim() } else { "" })
            "建物"           = New-Object System.Collections.ArrayList
            "車位"           = New-Object System.Collections.ArrayList
        }
        $cases[$no] = $case
        [void]$order.Add($no)
    }
    if ($order.Count -eq 0) { throw "「案件列表」沒有解析出任何資料列" }

    # --- 建物分頁：序號如 "1-1" 對回案件序號 "1" ---
    $wsB = $wb.Sheets.Item("建物")
    $bHdr = FindHeaderRow $wsB "建築完成日期" 5
    if ($bHdr -ge 0) {
        $bCols = $wsB.UsedRange.Columns.Count
        $bRows = $wsB.UsedRange.Rows.Count
        $bm = BuildColMap $wsB $bHdr $bCols
        $colBNo   = GetCol $bm "序號"
        $colBDate = GetCol $bm "建築完成日期"
        if ($colBNo -and $colBDate) {
            for ($r = $bHdr + 1; $r -le $bRows; $r++) {
                $sub = $wsB.Cells.Item($r, $colBNo).Text.Trim()
                if (-not $sub) { continue }
                $parent = ($sub -split '-')[0]
                if ($cases.ContainsKey($parent)) {
                    [void]$cases[$parent]["建物"].Add(@{
                        "建築完成日期" = $wsB.Cells.Item($r, $colBDate).Text.Trim()
                    })
                }
            }
        }
    } else {
        Write-Warning "「建物」分頁找不到欄名列，建築完成日期(屋齡)會缺漏，但不影響其他欄位"
    }

    # --- 車位分頁：序號同樣用父序號分組（同一案件可能多車位） ---
    $wsP = $wb.Sheets.Item("車位")
    $pHdr = FindHeaderRow $wsP "車位類別" 5
    if ($pHdr -ge 0) {
        $pCols = $wsP.UsedRange.Columns.Count
        $pRows = $wsP.UsedRange.Rows.Count
        $pm = BuildColMap $wsP $pHdr $pCols
        $colPNo    = GetCol $pm "序號"
        $colPType  = GetCol $pm "車位類別"
        $colPPrice = GetCol $pm "車位價格"
        $colPArea  = GetCol $pm "車位面積"
        if ($colPNo -and $colPType -and $colPArea) {
            for ($r = $pHdr + 1; $r -le $pRows; $r++) {
                $sub = $wsP.Cells.Item($r, $colPNo).Text.Trim()
                if (-not $sub) { continue }
                $parent = ($sub -split '-')[0]
                if ($cases.ContainsKey($parent)) {
                    [void]$cases[$parent]["車位"].Add(@{
                        "車位類別"   = $wsP.Cells.Item($r, $colPType).Text.Trim()
                        "車位價格元" = $(if ($colPPrice) { CleanNum $wsP.Cells.Item($r, $colPPrice).Text } else { $null })
                        "車位面積坪" = CleanNum $wsP.Cells.Item($r, $colPArea).Text
                    })
                }
            }
        }
    } else {
        Write-Warning "「車位」分頁找不到欄名列，含車位交易的單價會算不出來（update_prices.py 那端會直接跳過這幾筆，不會用錯的數字）"
    }

    $caseList = @()
    foreach ($no in $order) { $caseList += $cases[$no] }

    $obj = [ordered]@{
        "來源檔"   = (Split-Path $XlsPath -Leaf)
        "產生時間" = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
        "案件"     = $caseList
    }

    $json = $obj | ConvertTo-Json -Depth 6
    $outDir = Split-Path $OutJson -Parent
    if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
    [System.IO.File]::WriteAllText($OutJson, $json, [System.Text.UTF8Encoding]::new($true))

    if ($Report) {
        $dates = $caseList | ForEach-Object { $_["交易日期"] } | Where-Object { $_ } | Sort-Object
        Write-Output "讀到案件：$($caseList.Count) 筆"
        if ($dates.Count -gt 0) {
            Write-Output "交易日期範圍：$($dates[0]) ~ $($dates[-1])"
        }
        Write-Output "輸出：$OutJson"
    }
} finally {
    if ($wb) { $wb.Close($false) }
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
