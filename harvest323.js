 'use strict';
// V3.2.3: A new optional atomic harvest bundle. Existing single-entry forms remain unchanged.
(()=>{
 const form=document.getElementById('harvestBundleForm');if(!form)return;
 const norm=x=>String(x||'').trim().toLocaleLowerCase('tr-TR');
 const sk=x=>String(x||'').replace(/[^0-9]/g,'');
 const n=x=>Number(x),fmt=x=>Number(x).toLocaleString('tr-TR',{maximumFractionDigits:3});
 const cropName=x=>{const v=norm(x);if(v.includes('arpa'))return 'Arpa';if(v.includes('buğday')||v.includes('bugday'))return 'Buğday';if(v.includes('yulaf'))return 'Yulaf';if(v.includes('çavdar')||v.includes('cavdar'))return 'Çavdar';if(v.includes('tritikale'))return 'Tritikale';return ''};
 let seq=0, autoCrop='';
 function preview(){
  const a=n(form.elements.area_da.value),y=n(form.elements.yield_per_da.value),c=n(form.elements.combine_rate.value),b=n(form.elements.bale_count.value),w=n(form.elements.bale_weight.value),r=n(form.elements.bale_rate.value);
  document.getElementById('bundlePreview').textContent=a>0&&y>0?`Hasat: ${fmt(a)} da × ${fmt(y)} kg/da = ${fmt(a*y)} kg`:'Hasat miktarı: —';
  document.getElementById('bundleCost').textContent=`Biçerdöver: ${fmt(a*c||0)} ₺ · Balya: ${fmt(b*w||0)} kg / ${fmt(b*r||0)} ₺ · Toplam hizmet gideri: ${fmt((a*c||0)+(b*r||0))} ₺`;
 }
 async function sync(){
  const ticket=++seq,season=form.elements.season.value,code=form.elements.parcel_code.value;
  if(!season||!code)return;
  const [source,ops,inputs,parcels]=await Promise.all(['sourceRecords','operations','inputs','parcels'].map(all));if(ticket!==seq)return;
  const area=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).find(x=>x.parcel_code===code&&sk(x.season)===sk(season));
  const parcel=parcels.find(x=>x.code===code);
  const da=area?n(area.worked_area_da):n(parcel?.area_m2)/1000;
  if(da>0)form.elements.area_da.value=String(Math.round(da*1000)/1000);
  const inputMap=new Map(inputs.map(x=>[String(x.id),x]));
  const rows=[...source.filter(x=>x.table==='operations').map(x=>x.record),...ops];
  const crops=new Set();
  for(const x of rows){if(x.parcel_code!==code||sk(x.season)!==sk(season)||Number(x.is_cancelled)||!/ekim/i.test(x.op_type||''))continue;
   const input=inputMap.get(String(x.input_id||''));const label=String(x.item||x.item_detail||input?.name||'');
   if(/tohum/i.test(String(x.category||input?.category||''))||cropName(label)){const crop=cropName(label);if(crop)crops.add(crop)}
  }
  const crop=form.elements.crop;
  if(crops.size===1){const value=[...crops][0];if(!crop.value||crop.value===autoCrop)crop.value=value;autoCrop=value}
  else if(crops.size>1){if(crop.value===autoCrop)crop.value='';autoCrop='';crop.placeholder='Birden fazla ekim var: ürünü yazın'}
  else {if(crop.value===autoCrop)crop.value='';autoCrop='';crop.placeholder='Ekim kaydı bulunamadı: ürünü yazın'}
  preview();
 }
 form.elements.date.value=localDate();
 for(const el of form.elements)if(el.matches('input,select'))el.addEventListener('input',preview);
 form.elements.parcel_code.addEventListener('change',()=>sync().catch(console.error));
 form.elements.season.addEventListener('change',()=>sync().catch(console.error));
 const prev=window.renderExtended;
 if(typeof prev==='function')window.renderExtended=async function(...args){const result=await prev.apply(this,args);const old=form.elements.parcel_code.value;const parcels=await all('parcels');const select=form.elements.parcel_code;select.replaceChildren(...parcels.map(x=>new Option(`${x.name} (${x.code})`,x.code)));select.value=old&&parcels.some(x=>x.code===old)?old:select.options[0]?.value||'';await sync();return result};
 setTimeout(async()=>{try{const parcels=await all('parcels');form.elements.parcel_code.replaceChildren(...parcels.map(x=>new Option(`${x.name} (${x.code})`,x.code)));await sync()}catch(e){console.error(e)}},500);
 form.addEventListener('submit',async e=>{
  e.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
   const x=Object.fromEntries(new FormData(form));const a=n(x.area_da),y=n(x.yield_per_da),c=n(x.combine_rate),b=n(x.bale_count),w=n(x.bale_weight),r=n(x.bale_rate);
   if(!x.season||!x.parcel_code||!x.date||!x.crop.trim())throw Error('Tarih, sezon, parsel ve ürün gerekli');
   if(![a,y,c,b,w,r].every(Number.isFinite)||!(a>0)||!(y>0)||c<0||b<0||!Number.isInteger(b)||!(w>0)||r<0)throw Error('Alan, verim, balya sayısı veya fiyat geçersiz');
   if(!b&&r>0)throw Error('Balya sayısı sıfırken balyalama ücreti girilemez');
   const parcels=await all('parcels');if(!parcels.some(p=>p.code===x.parcel_code))throw Error('Parsel bulunamadı');
   const quantity=Math.round(a*y*1000)/1000;if(!(quantity>0))throw Error('Hasat miktarı geçersiz');
   const harvest={id:crypto.randomUUID(),date:x.date,season:x.season,parcel_code:x.parcel_code,crop:x.crop.trim(),quantity,area_da:a,yield_per_da:y,bundle_version:'3.2.3'};
   const services=[],bales=[];
   if(c>0)services.push({id:crypto.randomUUID(),date:x.date,season:x.season,parcel_code:x.parcel_code,kind:'Biçerdöver',quantity:a,unit:'da',unit_price:c,amount:Math.round(a*c*100)/100,bundle_harvest_id:harvest.id});
   if(b>0){bales.push({id:crypto.randomUUID(),date:x.date,season:x.season,parcel_code:x.parcel_code,quantity:b,unit:'adet',weight_per_bale_kg:w,total_weight_kg:Math.round(b*w*1000)/1000,bundle_harvest_id:harvest.id});if(r>0)services.push({id:crypto.randomUUID(),date:x.date,season:x.season,parcel_code:x.parcel_code,kind:'Balya',quantity:b,unit:'adet',unit_price:r,amount:Math.round(b*r*100)/100,bundle_harvest_id:harvest.id})}
   if(!confirm(`Hasat ${fmt(quantity)} kg, biçerdöver ${fmt(a*c)} ₺, balya ${fmt(b)} adet, balyalama ${fmt(b*r)} ₺ kaydedilsin mi?`))return;
   await tx(['harvests','services','bales'],'readwrite',t=>{t.objectStore('harvests').add(harvest);for(const v of services)t.objectStore('services').add(v);for(const v of bales)t.objectStore('bales').add(v)});
   form.reset();form.elements.date.value=localDate();await render();await renderExtended();alert('Hasat ve ilgili hizmetler birlikte kaydedildi.');
  }catch(err){alert('Kayıt yapılamadı: '+err.message)}finally{button.disabled=false}
 });
})();
