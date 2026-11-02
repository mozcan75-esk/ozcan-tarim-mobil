// V3.1.4 UI-only navigation; no database writes.
(()=>{
 const menu=document.querySelector('.module-menu');
 const tabs=[...document.querySelectorAll('[data-tab]')];
 function sync(tab){
  tabs.forEach(b=>b.classList.toggle('selected',b.dataset.tab===tab));
  if(menu)menu.open=false;
  window.scrollTo({top:0,behavior:'instant'});
 }
 tabs.forEach(b=>b.addEventListener('click',()=>sync(b.dataset.tab)));
 document.querySelectorAll('[data-dash-tab]').forEach(b=>b.addEventListener('click',()=>sync(b.dataset.dashTab)));
 sync('home');
})();
