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
 if(focus){const node=document.getElementById(focus);if(node){const parent=node.closest('details');if(parent)parent.open=true;setTimeout(()=>node.scrollIntoView({block:'start',behavior:'smooth'}),50);return;}}
 window.scrollTo({top:0,behavior:'instant'});
}
// app.js registers onclick; capturing handler supersedes it for new navigation.
document.addEventListener('click',e=>{const btn=e.target.closest('[data-tab]');if(!btn)return;const id=btn.dataset.tab;if(!document.getElementById(id))return;e.preventDefault();e.stopImmediatePropagation();navigate(id,btn.dataset.focus);},true);
// Provide a clear return path from detailed screens.
const back=document.createElement('button');back.type='button';back.className='v404-back';back.textContent='‹ Ana bölüme dön';back.hidden=true;
const main=document.querySelector('main');main.prepend(back);
back.addEventListener('click',()=>navigate(groups[document.querySelector('main .panel:not([hidden])')?.id]||'home'));
const observer=new MutationObserver(()=>{const visible=document.querySelector('main .panel:not([hidden])');back.hidden=!visible||['home','parcels','expensesHub','operationsHub','incomeHub','analysis'].includes(visible.id);});
observer.observe(main,{subtree:true,attributes:true,attributeFilter:['hidden']});
navigate('home');
})();