# 實價登錄官網匯出 xlsx 合併統整
# 來源：price_data\官網匯出\*.xlsx（官網「買賣查詢」下載，含社區簡稱欄）
# 輸出：price_data\官網匯出\合併-成交歷史.csv（UTF-8 BOM，Excel 可直接開）
# 用法：powershell -File tools\lvr-export-merge.ps1
# 純 PowerShell 解析 xlsx（ZIP→sharedStrings.xml＋sheet1.xml），本機無 Node/Python 也能跑

Add-Type -AssemblyName System.IO.Compression.FileSystem

# --- xlsx 解析 ---

# 取 <si>（sharedString）或 <is>（inlineStr）節點的完整文字（含富文字 run 合併）
function Get-SiText($si) {
    $texts = @()
    foreach ($node in $si.ChildNodes) {
        if ($node.LocalName -eq 't') { $texts += $node.InnerText }
        elseif ($node.LocalName -eq 'r') {
            foreach ($n2 in $node.ChildNodes) {
                if ($n2.LocalName -eq 't') { $texts += $n2.InnerText }
            }
        }
    }
    return ($texts -join '')
}

# 儲存格參照 "B3" → 欄序號 2
function ColIndex($ref) {
    $letters = ([regex]::Match($ref, '^[A-Z]+')).Value
    $n = 0
    foreach ($ch in $letters.ToCharArray()) { $n = $n * 26 + ([int]$ch - 64) }
    return $n
}

# 讀出一個 xlsx 的所有列；每列是 hashtable（欄序號→字串值）。讀不到工作表回傳 $null
function Read-XlsxRows($path) {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    try {
        $shared = New-Object System.Collections.ArrayList
        $ssEntry = $zip.GetEntry('xl/sharedStrings.xml')
        if ($ssEntry) {
            $sr = New-Object System.IO.StreamReader($ssEntry.Open(), [System.Text.Encoding]::UTF8)
            $doc = New-Object System.Xml.XmlDocument
            $doc.LoadXml($sr.ReadToEnd()); $sr.Close()
            foreach ($si in $doc.DocumentElement.ChildNodes) {
                [void]$shared.Add((Get-SiText $si))
            }
        }
        $shEntry = $zip.Entries | Where-Object { $_.FullName -like 'xl/worksheets/sheet*.xml' } | Select-Object -First 1
        if (-not $shEntry) { return $null }
        $sr = New-Object System.IO.StreamReader($shEntry.Open(), [System.Text.Encoding]::UTF8)
        $doc = New-Object System.Xml.XmlDocument
        $doc.LoadXml($sr.ReadToEnd()); $sr.Close()
        $nsmgr = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
        $nsmgr.AddNamespace('m', $doc.DocumentElement.NamespaceURI)
        $rows = New-Object System.Collections.ArrayList
        foreach ($rowNode in $doc.SelectNodes('//m:sheetData/m:row', $nsmgr)) {
            $cells = @{}
            foreach ($c in $rowNode.SelectNodes('m:c', $nsmgr)) {
                $idx = ColIndex $c.GetAttribute('r')
                $t = $c.GetAttribute('t')
                $vNode = $c.SelectSingleNode('m:v', $nsmgr)
                $val = ''
                if ($t -eq 's' -and $vNode) { $val = $shared[[int]$vNode.InnerText] }
                elseif ($t -eq 'inlineStr') {
                    $isNode = $c.SelectSingleNode('m:is', $nsmgr)
                    if ($isNode) { $val = Get-SiText $isNode }
                }
                elseif ($vNode) { $val = $vNode.InnerText }
                $cells[$idx] = $val
            }
            [void]$rows.Add($cells)
        }
        return $rows
    } finally { $zip.Dispose() }
}

# --- 正規化 ---

# 全形字元→半形（門牌的６０號→60號），並去空白
function ToHalfWidth($s) {
    if (-not $s) { return '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $s.ToCharArray()) {
        $code = [int]$ch
        if ($code -ge 0xFF01 -and $code -le 0xFF5E) { [void]$sb.Append([char]($code - 0xFEE0)) }
        elseif ($code -eq 0x3000) { [void]$sb.Append(' ') }
        else { [void]$sb.Append($ch) }
    }
    return $sb.ToString().Trim()
}

# 民國日期 "101/09/30" → 排序用數字 1010930；解析不了回傳 0
function DateNum($s) {
    if ($s -match '^(\d{2,3})/(\d{1,2})/(\d{1,2})$') {
        return [int]$Matches[1] * 10000 + [int]$Matches[2] * 100 + [int]$Matches[3]
    }
    return 0
}

# --- 主流程 ---

$dir = Join-Path $PSScriptRoot '..\price_data\官網匯出'
$dir = (Resolve-Path $dir).Path
$outCsv = Join-Path $dir '合併-成交歷史.csv'

$expectHeader = '地段位置或門牌'
$all = New-Object System.Collections.ArrayList
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
$dupCount = 0
$fileStats = New-Object System.Collections.ArrayList
$badFiles = New-Object System.Collections.ArrayList

foreach ($f in (Get-ChildItem $dir -Filter '*.xlsx' | Sort-Object Name)) {
    $rows = Read-XlsxRows $f.FullName
    if (-not $rows -or $rows.Count -lt 3) {
        [void]$badFiles.Add($f.Name)
        [void]$fileStats.Add([pscustomobject]@{ 檔案 = $f.Name; 資料筆數 = 0; 有社區 = 0; 期間 = '（無資料）' })
        continue
    }
    # 找欄名列（第1欄=地段位置或門牌），之後才是資料
    $headerAt = -1
    for ($i = 0; $i -lt [Math]::Min(5, $rows.Count); $i++) {
        if ($rows[$i][1] -eq $expectHeader) { $headerAt = $i; break }
    }
    if ($headerAt -lt 0) { [void]$badFiles.Add("$($f.Name)（找不到欄名列）"); continue }

    $n = 0; $nComm = 0; $dmin = 9999999; $dmax = 0
    for ($i = $headerAt + 1; $i -lt $rows.Count; $i++) {
        $c = $rows[$i]
        $addr = ToHalfWidth $c[1]
        if (-not $addr) { continue }   # 空列略過
        $comm = ('' + $c[2]).Trim()
        $dnum = DateNum ('' + $c[3]).Trim()
        # 跨檔去重：同門牌+日期+總價+樓別+面積視為同一筆
        $key = "$addr|$($c[3])|$($c[4])|$($c[10])|$($c[6])"
        if (-not $seen.Add($key)) { $dupCount++; continue }
        [void]$all.Add([pscustomobject]@{
            門牌       = $addr
            社區       = $comm
            交易日期   = ('' + $c[3]).Trim()
            日期序     = $dnum
            總價萬     = ('' + $c[4]).Trim()
            單價萬坪   = ('' + $c[5]).Trim()
            總面積坪   = ('' + $c[6]).Trim()
            主建物佔比 = ('' + $c[7]).Trim()
            型態       = ('' + $c[8]).Trim()
            屋齡       = ('' + $c[9]).Trim()
            樓別樓高   = ('' + $c[10]).Trim()
            交易標的   = ('' + $c[11]).Trim()
            交易筆棟數 = ('' + $c[12]).Trim()
            格局       = ('' + $c[13]).Trim()
            車位總價萬 = ('' + $c[14]).Trim()
            管理組織   = ('' + $c[15]).Trim()
            電梯       = ('' + $c[16]).Trim()
            主要用途   = ('' + $c[17]).Trim()
            備註       = ('' + $c[18]).Trim()
            來源檔     = $f.Name
        })
        $n++
        if ($comm) { $nComm++ }
        if ($dnum -gt 0) {
            if ($dnum -lt $dmin) { $dmin = $dnum }
            if ($dnum -gt $dmax) { $dmax = $dnum }
        }
    }
    $period = if ($dmax -gt 0) { "$dmin ~ $dmax" } else { '（無法解析日期）' }
    [void]$fileStats.Add([pscustomobject]@{ 檔案 = $f.Name; 資料筆數 = $n; 有社區 = $nComm; 期間 = $period })
}

# 依日期排序輸出
$sorted = $all | Sort-Object 日期序, 門牌
$sorted | Export-Csv -Path $outCsv -NoTypeInformation -Encoding UTF8

# --- 對照庫輸入檔：社區↔門牌(含出現次數)，供 tools/build-community-doors.html 產生 COMM_DOORS ---
# 段的寫法先正規化（官方偶有「1段」「ㄧ段(注音)」的髒寫法），門牌解析交給網站的 parseHouse 做
$pairs = @{}
foreach ($r in $all) {
    if (-not $r.社區) { continue }
    $addr = $r.門牌 -replace 'ㄧ段', '一段' -replace '1段', '一段' -replace '2段', '二段' -replace '3段', '三段'
    $key = $r.社區 + "`t" + $addr
    if ($pairs.ContainsKey($key)) { $pairs[$key]++ } else { $pairs[$key] = 1 }
}
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('// doors-input.js — 由 tools/lvr-export-merge.ps1 自動產生，勿手改')
[void]$sb.AppendLine('// 格式：[官方社區簡稱, 門牌(段已正規化), 出現次數]')
[void]$sb.AppendLine('const DOORS_INPUT=[')
foreach ($k in ($pairs.Keys | Sort-Object)) {
    $parts = $k -split "`t"
    $c = $parts[0] -replace '\\', '\\\\' -replace '"', '\"'
    $a = $parts[1] -replace '\\', '\\\\' -replace '"', '\"'
    [void]$sb.AppendLine("[""$c"",""$a"",$($pairs[$k])],")
}
[void]$sb.AppendLine('];')
$doorsOut = Join-Path $dir 'doors-input.js'
[System.IO.File]::WriteAllText($doorsOut, $sb.ToString(), [System.Text.UTF8Encoding]::new($true))

# --- 統計報告 ---
Write-Output "===== 各檔統計 ====="
$fileStats | Format-Table -AutoSize | Out-String -Width 200 | Write-Output
Write-Output "===== 總計 ====="
$total = $all.Count
$withComm = ($all | Where-Object { $_.社區 }).Count
$commList = $all | Where-Object { $_.社區 } | Group-Object 社區
Write-Output "總筆數：$total（跨檔重複剔除 $dupCount 筆）"
Write-Output ("有社區簡稱：{0} 筆（{1:P1}），共 {2} 個社區" -f $withComm, ($withComm / $total), $commList.Count)
Write-Output "輸出：$outCsv"
Write-Output "對照庫輸入：$doorsOut（$($pairs.Count) 個社區×門牌組合）"
if ($badFiles.Count -gt 0) {
    Write-Output "⚠ 無資料/異常檔案：$($badFiles -join '、')"
}
