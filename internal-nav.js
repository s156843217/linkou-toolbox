/* ============================================================
   internal-nav.js — 全站「內部模式」導覽
   ------------------------------------------------------------
   曾在 report/（社區一頁報告）輸入過通關碼的裝置，本機會留下記號；
   之後開任何一頁，導覽列自動多出「社區報告」「CRM」兩顆金色按鈕。
   一般訪客沒有記號，看到的網站與現在完全相同。
   ★ 記號鑰匙名須與 report/index.html 的 GATE_KEY 一致。
   ============================================================ */
(function(){
  try{ if(localStorage.getItem('lkToolboxInternal')!=='1')return; }catch(e){ return; }
  var links=document.querySelector('.site-nav .nav-links'); if(!links)return;

  // 依所在層級決定相對路徑：首頁的 nav-logo href 是 "./"、工具頁是 "../"
  var logo=document.querySelector('.site-nav .nav-logo');
  var prefix=(logo&&logo.getAttribute('href'))||'./';

  // 目前所在頁（避免在該工具自己的頁面重複加它自己的按鈕）
  var here=location.pathname;

  // report 頁自己的導覽列已有「社區報告」，不重複加
  var hasReport=Array.prototype.some.call(links.querySelectorAll('a'),function(a){
    return a.textContent.indexOf('社區報告')>=0;
  });
  if(!hasReport){
    var r=document.createElement('a');
    r.href=prefix+'report/';
    r.textContent='📋 社區報告';
    r.style.color='var(--gold)';
    links.appendChild(r);
  }

  // 競品比較（591 在售盤點）——同為內部工具，登入後每頁可直接點進
  if(here.indexOf('/listing/')<0){
    var l=document.createElement('a');
    l.href=prefix+'listing/';
    l.textContent='📊 競品比較';
    l.style.color='var(--gold)';
    links.appendChild(l);
  }

  var c=document.createElement('a');
  c.href='https://s156843217.github.io/linkou-crm/';
  c.target='_blank'; c.rel='noopener';
  c.textContent='👥 CRM';
  c.style.color='var(--gold)';
  links.appendChild(c);
})();
