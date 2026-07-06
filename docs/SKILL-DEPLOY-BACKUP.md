# /deploy skill 備份副本

> 正本在 `C:\Users\s1568\.claude\skills\deploy\SKILL.md`（不在 git 內），本檔是備份，**兩份要一起改**。
> 電腦重灌時把下面內容（含 frontmatter）複製回正本路徑即可還原。

---
name: deploy
description: 上線同步：把 my-project dev 的改動照 SOP 同步到 linkou-toolbox 並 push 上線。使用者說「上線」「同步」「部署」時使用。
---

# 上線同步（my-project dev → linkou-toolbox）

> 本檔不在 git 內，備份副本在 `C:\repo\linkou-toolbox\docs\SKILL-DEPLOY-BACKUP.md`，兩份要一起改。
> 權威文件是 `C:\repo\linkou-toolbox\docs\DEPLOY.md`，本 skill 與它衝突時以 DEPLOY.md 為準。
> 照順序做，不要即興發揮；任何一步出現解釋不了的狀況 → 停下來問使用者。

## 第 0 步：判斷階段

先讀 `C:\repo\linkou-toolbox\docs\DEPLOY.md` 第 0 節：

- **過渡期**（～2026年7月底）：照本 skill 往下走。
- **已收斂**（DECISIONS.md 有「收斂完成」紀錄）：本 skill 的同步流程已作廢，直接在 linkou-toolbox 改、push `main` 即上線。告知使用者並改走簡易流程。

## 第 1 步：確認起點狀態

```powershell
git -C C:\repo\my-project branch --show-current   # 必須是 dev
git -C C:\repo\my-project status -sb              # 必須乾淨（改動都已 commit）
```

- 不在 dev 或有未 commit 的改動 → 先處理完再繼續。
- 這次改動應已照 `CHECKLIST.md` 驗證過；還沒驗證就先驗證。

## 第 2 步：跑差異報告（安全，不改檔）

```powershell
powershell -NoProfile -File C:\repo\my-project\tools\sync-toolbox.ps1
```

**每一筆「內容不同／缺少」都要能說出是 dev 的哪個 commit 造成的**（用 `git log --oneline -10` 對照）。
有任何一筆解釋不了 → 停下來，把該筆差異列給使用者確認，不准直接套用。

注意事項：
- `mortgage-data.js` **不在白名單**是故意的（真相來源在 toolbox，Actions 每月自動更新）。要手改它請直接改 toolbox 那份，再複製回 dev。
- 這次若有**新增網站檔**（新頁面、新資料檔），要先把它加進 `sync-toolbox.ps1` 的白名單再跑。

## 第 3 步：套用並 push

```powershell
powershell -NoProfile -File C:\repo\my-project\tools\sync-toolbox.ps1 -Apply
git -C C:\repo\linkou-toolbox diff          # 肉眼再看一次，內容要跟差異報告一致
git -C C:\repo\linkou-toolbox add -A
git -C C:\repo\linkou-toolbox commit -m "（沿用 dev 那則 commit 訊息）"
git -C C:\repo\linkou-toolbox push
```

## 第 4 步：驗證上線（必做，做完才能回報完成）

```powershell
gh api repos/s156843217/linkou-toolbox/pages/builds/latest --jq '.status'   # 等到出現 built
curl -s https://s156843217.github.io/linkou-toolbox/<對應頁面> | Select-String "<這次改動的關鍵字>"
```

- 用「這次改動才會出現的關鍵字」確認新內容真的上線，不能只看 build 成功。
- 回報時標明完成等級（通常此流程做完＝L2），並附線上網址請使用者親眼確認。

## 第 5 步：資料複本傳播檢查

這次若動到 `linkou-data.js`（學區資料）：提醒使用者 LINE bot 那份要手動複製再 push（`DATA-UPDATE.md` 第 2 節第 5 步），問是否現在一起做。
