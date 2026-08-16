/* ============================================================
   internal-nav.js — 全站「內部模式」導覽
   ------------------------------------------------------------
   曾在 report/（社區一頁報告）輸入過通關碼的裝置，本機會留下記號；
   之後開任何一頁，導覽列自動多出「社區報告」「CRM」兩顆金色按鈕。
   一般訪客沒有記號，看到的網站與現在完全相同。
   ★ 記號鑰匙名須與 report/index.html 的 GATE_KEY 一致。

   隱藏入口（長按站名）：
   iOS「加入主畫面」全螢幕模式的儲存空間跟 Safari 是分開的，沒有網址列
   可以打通關碼網址，所以留一個長按左上角站名跳到通關碼頁的暗門，跟解鎖
   狀態無關、每頁都在，一般訪客不會發現。
   ============================================================ */
(function(){
  // 依所在層級決定相對路徑：首頁的 nav-logo href 是 "./"、工具頁是 "../"
  var logo=document.querySelector('.site-nav .nav-logo');
  var prefix=(logo&&logo.getAttribute('href'))||'./';

  if(logo){
    var pressTimer;
    var startPress=function(){ pressTimer=setTimeout(function(){ location.href=prefix+'report/'; },1200); };
    var cancelPress=function(){ clearTimeout(pressTimer); };
    logo.addEventListener('touchstart',startPress,{passive:true});
    logo.addEventListener('touchend',cancelPress);
    logo.addEventListener('touchmove',cancelPress);
    logo.addEventListener('mousedown',startPress);
    logo.addEventListener('mouseup',cancelPress);
    logo.addEventListener('mouseleave',cancelPress);
  }

  try{ if(localStorage.getItem('lkToolboxInternal')!=='1')return; }catch(e){ return; }
  var links=document.querySelector('.site-nav .nav-links'); if(!links)return;

  // 導覽列已有某文字的連結就不重複加（含各頁自己靜態就放的那顆，例如 report 頁的「社區報告」）
  function has(txt){
    return Array.prototype.some.call(links.querySelectorAll('a'),function(a){
      return a.textContent.indexOf(txt)>=0;
    });
  }
  function addGold(text,href,external){
    var a=document.createElement('a');
    a.href=href; a.textContent=text; a.style.color='var(--gold)';
    if(external){ a.target='_blank'; a.rel='noopener'; }
    links.appendChild(a);
  }

  // 社區報告、競品比較都是內部工具：登入後每頁都留著按鈕（停在該頁時也不消失，只是不重複加）
  if(!has('社區報告')) addGold('📋 社區報告',prefix+'report/');
  if(!has('競品比較')) addGold('📊 競品比較',prefix+'listing/');
  if(!has('CRM'))     addGold('👥 CRM','https://s156843217.github.io/linkou-crm/',true);
})();
