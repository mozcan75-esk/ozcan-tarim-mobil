(function(){'use strict';
// Navigation-only layer; no persistence, stock or accounting mutations.
const panels=()=>document.querySelectorAll('main .panel');
const nav=document.querySelector('.v404-bottom');
const modules=document.getElementById('v4Modules');
const groups={inputs:'expensesHub',rents:'expensesHub',maintenance:'expensesHub',services:'expensesHub',operations:'operationsHub',harvest:'operationsHub',baleWarehouse:'incomeHub',supports:'incomeHub'};
function navigate(id,focus){
 const target=document.getElementById(id);if(!target)return;
 panels().forEach(p=>p.hidden=p!==target);
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('selected',b.dataset.tab===id));
 nav?.querySelectorAll('button').forEach(b=>b.classList.toggle('v4-active',b.dataset.tab===(groups[id]||id)));
 if(modules)modules.open=false;
 document.dispatchEvent(new CustomEvent('ozcan:panel',{detail:{id,focus}}));
 back.hidden=['home','parcels','expensesHub','operationsHub','incomeHub','analysis','backup'].includes(id);
 if(focus){const node=document.getElementById(focus);if(node){const parent=node.closest('details');if(parent)parent.open=true;setTimeout(()=>node.scrollIntoView({block:'start',behavior:'smooth'}),120);return;}}
 window.scrollTo({top:0,behavior:'instant'});
}
// app.js registers onclick; capturing handler supersedes it for new navigation.
document.addEventListener('click',e=>{const btn=e.target.closest('[data-tab]');if(!btn)return;const id=btn.dataset.tab;if(!document.getElementById(id))return;e.preventDefault();e.stopImmediatePropagation();navigate(id,btn.dataset.focus);},true);
// Provide a clear return path from detailed screens.
const back=document.createElement('button');back.type='button';back.className='v404-back';back.textContent='‹ Ana bölüme dön';back.hidden=true;
const main=document.querySelector('main');main.prepend(back);
back.addEventListener('click',()=>navigate(groups[document.querySelector('main .panel:not([hidden])')?.id]||'home'));
// The back button is updated only when navigation occurs; avoid recursive MutationObserver updates.
navigate('home');
})();
// V4.0.6: only presentation/navigation, no IndexedDB writes.
(function(){'use strict';
const groups={inputs:'Giderler',rents:'Giderler',maintenance:'Giderler',services:'Giderler',operations:'İşlemler',harvest:'İşlemler',supports:'Gelirler',baleWarehouse:'Gelirler'};
const panelIds=Object.keys(groups);
function makeToolbar(id){
 const sec=document.getElementById(id);if(!sec||sec.querySelector('.v406-toolbar'))return;
 const bar=document.createElement('div');bar.className='v406-toolbar';
 const breadcrumb=document.createElement('span');breadcrumb.className='v406-crumb';breadcrumb.textContent=groups[id]+' / '+(sec.querySelector('h2')?.textContent||id);
 const actions=document.createElement('div');actions.className='v406-actions';
 const add=document.createElement('button');add.type='button';add.textContent='＋ Yeni kayıt';add.className='v406-action';
 const records=document.createElement('button');records.type='button';records.textContent='☷ Kayıtları gör';records.className='v406-action';
 actions.append(add,records);bar.append(breadcrumb,actions);sec.prepend(bar);
 const getForms=()=>Array.from(sec.querySelectorAll('form')).filter(f=>f.id);
 const getRecords=()=>sec.querySelector('#depotPurchases358')||sec.querySelector('.records357')||sec.querySelector('.records358');
 function scrollTo(node){if(!node)return;const details=node.closest('details');if(details)details.open=true;node.scrollIntoView({behavior:'smooth',block:'start'});}
 add.addEventListener('click',()=>scrollTo(getForms()[0]));
 records.addEventListener('click',()=>{window.refreshRecords357?.();window.refreshDepot358?.();setTimeout(()=>scrollTo(getRecords()),160)});
 if(!getForms().length)add.hidden=true;
 if(id==='inputs'){records.textContent='☷ Stok girişleri';}
 if(id==='harvest'){add.textContent='＋ Hasat / satış';}
}
function setupHubs(){
 document.querySelectorAll('.v404-hub').forEach(sec=>{
 const filter=sec.querySelector('.v406-filter');if(!filter)return;
 const tiles=Array.from(sec.querySelectorAll('.v404-tiles > button'));
 const empty=document.createElement('p');empty.className='v406-noresult';empty.hidden=true;empty.textContent='Bu aramayla eşleşen işlem bulunamadı.';sec.querySelector('.v404-tiles').after(empty);
 filter.addEventListener('input',()=>{const q=filter.value.trim().toLocaleLowerCase('tr-TR');let count=0;tiles.forEach(btn=>{const show=btn.textContent.toLocaleLowerCase('tr-TR').includes(q);btn.hidden=!show;if(show)count++;});empty.hidden=count>0;});
 });
}
function updateFocus(ev){const {id,focus}=ev.detail||{};if(!panelIds.includes(id))return;
 const sec=document.getElementById(id);if(!sec)return;
 // When navigating to a particular form, keep it in view; otherwise expose existing list shortcuts.
 if(focus){const node=document.getElementById(focus);if(node)setTimeout(()=>node.scrollIntoView({block:'start',behavior:'smooth'}),150);}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{panelIds.forEach(makeToolbar);setupHubs();});
else{panelIds.forEach(makeToolbar);setupHubs();}
document.addEventListener('ozcan:panel',updateFocus);
})();
