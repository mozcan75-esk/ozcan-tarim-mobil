'use strict';
// V3.1.9: Calculation assistance only; existing harvest and sales persistence remains unchanged.
(()=>{
 const harvest=document.getElementById('harvestForm'),sale=document.getElementById('saleForm');
 if(!harvest||!sale)return;
 const area=document.getElementById('harvestArea'),yieldInput=document.getElementById('harvestYield');
 const preview=document.getElementById('harvestPreview'),salePreview=document.getElementById('salePreview');
 const qty=harvest.elements.quantity;
 const fmt=x=>x.toLocaleString('tr-TR',{maximumFractionDigits:3});
 async function updateArea(){
   const code=harvest.elements.parcel_code.value,season=harvest.elements.season.value;
   const [source,parcels]=await Promise.all([all('sourceRecords'),all('parcels')]);
   const found=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).find(x=>String(x.parcel_code)===code&&String(x.season)===season);
   const parcel=parcels.find(x=>x.code===code);
   const val=found?Number(found.worked_area_da):Number(parcel?.area_m2||0)/1000;
   area.value=Number.isFinite(val)&&val>0?val:'';
   updateHarvest();
 }
 function updateHarvest(){
   const da=Number(area.value),perDa=Number(yieldInput.value);
   if(!(da>0)||!(perDa>0)||!Number.isFinite(da*perDa)){preview.textContent='İşlenen alan ve verim girildiğinde toplam hasat hesaplanır.';return}
   const total=Math.round(da*perDa*1000)/1000;
   preview.textContent=`${fmt(da)} da × ${fmt(perDa)} kg/da = ${fmt(total)} kg. Toplam miktar alanına aktarılır.`;
   qty.value=String(total);
 }
 async function updateSale(){
   const season=sale.elements.season.value,crop=sale.elements.crop.value;
   if(!season||!crop){salePreview.textContent='Sezon ve ürün seçin.';return}
   try{
     const [harvests,sales]=await Promise.all([all('harvests'),all('sales')]);
     const key=s=>String(s||'').trim().toLocaleLowerCase('tr-TR');
     const received=harvests.filter(x=>x.season===season&&key(x.crop)===key(crop)&&!Number(x.is_cancelled)).reduce((a,x)=>a+Number(x.quantity||0),0);
     const sold=sales.filter(x=>x.season===season&&key(x.crop)===key(crop)&&!Number(x.is_cancelled)).reduce((a,x)=>a+Number(x.quantity||0),0);
     const remaining=received-sold;
     const requested=Number(sale.elements.quantity.value||0);
     salePreview.textContent=`${season} ${crop} stok: ${fmt(remaining)} kg`+(requested>remaining+1e-7?' · UYARI: Girilen satış miktarı stoktan fazla.':'');
   }catch(e){salePreview.textContent='Stok önizlemesi alınamadı.'}
 }
 harvest.elements.parcel_code.addEventListener('change',()=>updateArea().catch(console.error));
 harvest.elements.season.addEventListener('change',()=>updateArea().catch(console.error));
 area.addEventListener('input',updateHarvest);yieldInput.addEventListener('input',updateHarvest);
 sale.addEventListener('input',()=>updateSale().catch(console.error));
 sale.addEventListener('change',()=>updateSale().catch(console.error));
 // renderExtended refreshes parcel/crop selections asynchronously.
 const prior=window.renderExtended;
 if(typeof prior==='function')window.renderExtended=async function(...args){const result=await prior.apply(this,args);await updateArea();await updateSale();return result};
 updateArea().catch(console.error);updateSale().catch(console.error);
})();
