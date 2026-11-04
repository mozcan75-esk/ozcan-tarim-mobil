'use strict';
// V3.2.1: Derive harvested crop from recorded sowing seed, scoped by season and parcel.
(()=>{
 const form=document.getElementById('harvestForm');if(!form)return;
 const crop=form.elements.crop, hint=document.getElementById('harvestCropHint'),choices=document.getElementById('harvestCropChoices');
 const norm=x=>String(x??'').trim().toLocaleLowerCase('tr-TR');
 const seasonKey=x=>String(x??'').trim().replace(/\s/g,'').replace(/[–—\/._]/g,'-');
 const cropName=x=>{const s=String(x??'').trim();if(/\barpa\b/i.test(s))return 'Arpa';if(/buğday|bugday/i.test(s))return 'Buğday';if(/yulaf/i.test(s))return 'Yulaf';if(/çavdar|cavdar/i.test(s))return 'Çavdar';if(/tritikale/i.test(s))return 'Tritikale';return '';};
 let lastKey='',lastAuto='',ticket=0;
 async function syncCrop(){
  const code=form.elements.parcel_code.value,season=form.elements.season.value,key=seasonKey(season)+'|'+code,seq=++ticket;
  if(!code||!season){hint.textContent='Önce sezon ve parsel seçin.';return}
  try{
   const [source,ops,inputs]=await Promise.all([all('sourceRecords'),all('operations'),all('inputs')]);
   if(seq!==ticket)return;
   const inputsById=new Map(inputs.map(i=>[String(i.id),i]));
   const rows=[...source.filter(x=>x.table==='operations').map(x=>x.record),...ops];
   const found=[];
   for(const op of rows){
    if(String(op.parcel_code)!==code||seasonKey(op.season)!==seasonKey(season)||Number(op.is_cancelled))continue;
    if(!/ekim/i.test(String(op.op_type||'')))continue;
    const input=inputsById.get(String(op.input_id||''));
    const label=String(op.item||op.item_detail||input?.name||'');
    const isSeed=/tohum/i.test(String(op.category||input?.category||''))||/arpa|buğday|bugday|yulaf|çavdar|cavdar|tritikale/i.test(label);
    if(!isSeed)continue;
    const name=cropName(label)||cropName(String(op.item_detail||''));if(name)found.push(name);
   }
   const unique=[...new Set(found)];choices.replaceChildren(...unique.map(x=>new Option(x,x)));
   const shouldReplace=key!==lastKey||!crop.value.trim()||crop.value===lastAuto;
   if(unique.length===1){if(shouldReplace){crop.value=unique[0];lastAuto=unique[0]}hint.textContent=`Ekim kaydından bulunan ürün: ${unique[0]}. Gerekirse değiştirebilirsiniz.`}
   else if(unique.length>1){if(shouldReplace){crop.value='';lastAuto=''}hint.textContent='Bu parselde birden fazla ürün kaydı var. Ürünü listeden seçin.'}
   else {if(shouldReplace){crop.value='';lastAuto=''}hint.textContent='Bu sezon ve parsel için ekimde kullanılan tohum kaydı bulunamadı. Ürünü elle girin.'}
   lastKey=key;
  }catch(e){hint.textContent='Ekim kayıtları okunamadı; ürünü elle girebilirsiniz.';console.error(e)}
 }
 form.elements.parcel_code.addEventListener('change',syncCrop);
 form.elements.season.addEventListener('change',syncCrop);
 // Extended render may rebuild parcel selections; wait until its update completes.
 const old=window.renderExtended;
 if(typeof old==='function')window.renderExtended=async function(...args){const r=await old.apply(this,args);await syncCrop();return r};
 // If the season input is empty, use the recorded season of this parcel, not the placeholder.
 async function suggestSeason(){
  if(form.elements.season.value.trim())return;
  const code=form.elements.parcel_code.value;if(!code)return;
  const [ops,source]=await Promise.all([all('operations'),all('sourceRecords')]);
  const rows=[...ops,...source.filter(x=>x.table==='operations').map(x=>x.record)];
  const seasons=[...new Set(rows.filter(x=>x.parcel_code===code&&/ekim/i.test(String(x.op_type||''))&&!Number(x.is_cancelled)).map(x=>String(x.season||'')).filter(Boolean))].sort().reverse();
  if(seasons.length)form.elements.season.value=seasons[0];
 }
 form.elements.parcel_code.addEventListener('change',()=>suggestSeason().then(syncCrop).catch(console.error));
 suggestSeason().then(syncCrop).catch(console.error);
})();
