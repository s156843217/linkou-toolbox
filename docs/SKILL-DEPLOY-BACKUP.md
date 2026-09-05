# /deploy skill 備份副本

> 正本在 `C:\Users\s1568\.claude\skills\deploy\SKILL.md`（不在 git 內），本檔是備份，**兩份要一起改**。
> 電腦重灌時把下面內容（含 frontmatter）複製回正本路徑即可還原。

---
name: deploy
description: 上線：確認 linkou-toolbox 的改動已驗證、push main、驗證線上生效。使用者說「上線」「部署」時使用。
---

# 上線（linkou-toolbox，已收斂）

> 本檔不在 git 內，備份副本在 `C:\repo\linkou-toolbox\docs\SKILL-DEPLOY-BACKUP.md`，兩份要一起改。
> 權威文件是 `C:\repo\linkou-toolbox\docs\DEPLOY.md`，本 skill 與它衝突時以 DEPLOY.md 為準。
> 2026-09-05 收斂完成：開發直接在 `linkou-toolbox` 進行，不再有 my-project↔toolbox 同步這件事。

## 第 1 步：確認起點狀態

```powershell
git -C C:\repo\linkou-toolbox branch --show-current   # 必須是 main
git -C C:\repo\linkou-toolbox status -sb
```

- 這次改動應已照 `CHECKLIST.md` 驗證過；還沒驗證就先驗證（動到學區資料要先跑 `tools/selftest.html` 全綠）。

## 第 2 步：commit 並 push

```powershell
git -C C:\repo\linkou-toolbox add -A
git -C C:\repo\linkou-toolbox status         # 肉眼看一次，確認沒有不該進版控的檔案
git -C C:\repo\linkou-toolbox commit -m "（描述這次做了什麼）"
git -C C:\repo\linkou-toolbox push
```

## 第 3 步：驗證上線（必做，做完才能回報完成）

```powershell
gh api repos/s156843217/linkou-toolbox/pages/builds/latest --jq '.status'   # 等到出現 built
curl -s https://swcasa.com/<對應頁面> | Select-String "<這次改動的關鍵字>"
```

- 用「這次改動才會出現的關鍵字」確認新內容真的上線，不能只看 build 成功。
- 回報時標明完成等級（通常此流程做完＝L2），並附線上網址請使用者親眼確認。

## 第 4 步：資料複本傳播檢查

這次若動到 `linkou-data.js`（學區資料）：提醒使用者 LINE bot 那份要手動複製再 push（`DATA-UPDATE.md` 第 2 節第 5 步），問是否現在一起做。
