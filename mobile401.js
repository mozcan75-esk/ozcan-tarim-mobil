(function(){'use strict';
// Tek, tam ozellikli kullanim: mod secimi yok; eski tercih veri kayitlarini etkilemez.
document.body.dataset.uiMode='advanced';
document.querySelectorAll('[data-advanced]').forEach(el=>el.hidden=false);
const modules=document.getElementById('v4Modules');
const finance=document.getElementById('v4Finance');finance.addEventListener('click',()=>{modules.open=true;modules.scrollIntoView({behavior:'smooth',block:'start'});document.querySelectorAll('.v4-module-grid [data-tab="rents"],.v4-module-grid [data-tab="supports"],.v4-module-grid [data-tab="maintenance"]').forEach(el=>el.classList.add('finance-link'));});
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{if(modules)modules.open=false;document.querySelectorAll('.v4-bottom button').forEach(n=>n.classList.toggle('v4-active',n.dataset.tab===b.dataset.tab));}));
})();