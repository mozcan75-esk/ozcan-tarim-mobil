(function(){'use strict';
const key='ozcan_catalog_crops_v407';
const defaults=['Buğday','Arpa','Yulaf','Çavdar','Mısır','Ayçiçeği','Mercimek','Nohut'];
function names(){try{const x=JSON.parse(localStorage.getItem(key));return Array.isArray(x)?x:defaults}catch(e){return defaults}}
function refresh(){
 document.querySelectorAll('#harvestForm input[name="crop"],#harvestBundleForm input[name="crop"]').forEach((input,i)=>{
  const id='cropCatalog409_'+i;let dl=document.getElementById(id);if(!dl){dl=document.createElement('datalist');dl.id=id;document.body.appendChild(dl)}
  dl.replaceChildren(...names().map(n=>{const o=document.createElement('option');o.value=n;return o}));input.setAttribute('list',id);
 });
 const sale=document.querySelector('#saleForm select[name="crop"]');
 // Sale options are stock-driven; do not inject items with zero inventory.
 if(sale&&!sale.dataset.catalog409){sale.dataset.catalog409='1';sale.title='Satış için yalnızca depoda kayıtlı ürünler seçilebilir.'}
}
function init(){refresh();document.getElementById('settingsCropForm407')?.addEventListener('submit',()=>setTimeout(refresh,0));}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
