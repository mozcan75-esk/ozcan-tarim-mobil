'use strict';
(()=>{
  // Presentation only: keep original IndexedDB stores, forms and calculations.
  const legacy=['operationList','stockList','inputList','rentList','supportList','serviceList','baleSaleList'];
  const hideLegacy=()=>{
    legacy.forEach(id=>{const el=document.getElementById(id);if(el){el.classList.add('legacy359-hidden');const p=el.previousElementSibling;if(p&&/^H[234]$/.test(p.tagName)&&/son |hareket|kayıt|liste/i.test(p.textContent))p.classList.add('legacy359-hidden');}});
    const depot=document.getElementById('inputs');
    if(depot){const old=depot.querySelector('.records357');if(old)old.classList.add('legacy359-hidden');}
    const op=document.getElementById('operations');
    if(op){for(const h of op.querySelectorAll('h3,h4')){if(/son işlemler|işlem kayıtları/i.test(h.textContent))h.classList.add('legacy359-hidden');}}
  };
  const rename=()=>{
    const labels={operations:'Tarla faaliyetleri',harvest:'Hasat ve ürün satışları',rents:'İcar ve ödemeler',supports:'Destek gelir kayıtları',maintenance:'Bakım gider kayıtları',services:'Hizmet ve ödemeler',baleWarehouse:'Balya kayıtları ve satışlar'};
    for(const [id,label] of Object.entries(labels)){
      const sec=document.getElementById(id);const title=sec?.querySelector('.records357 > h3');if(title)title.textContent=label;
    }
    const depot=document.getElementById('depotPurchases358');
    if(depot){const heading=depot.querySelector('h3');if(heading)heading.textContent='Stok giriş kayıtları';}
  };
  document.addEventListener('DOMContentLoaded',()=>{hideLegacy();rename();setTimeout(()=>{hideLegacy();rename()},300)});
  window.addEventListener('load',()=>{hideLegacy();rename();setTimeout(()=>{hideLegacy();rename()},700)});
  document.addEventListener('click',e=>{if(e.target.closest('[data-tab],[data-dash-tab]'))setTimeout(()=>{hideLegacy();rename();window.refreshRecords357?.();window.refreshDepot358?.()},100)});
})();
