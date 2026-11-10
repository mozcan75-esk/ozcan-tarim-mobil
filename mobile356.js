 'use strict';
// V3.5.6: Unified harvest, atomic across product, tractor fuel and service records.
(()=>{
 const form=document.getElementById('mobileHarvestForm');if(!form)return;
 const fmt=n=>Number(n).toLocaleString('tr-TR',{maximumFractionDigits:3});
 const num=v=>Number(String(v||'').replace(',','.'));
 const norm=s=>String(s||'').toLocaleLowerCase('tr-TR');
 const isDiesel=x=>norm(x.category+' '+x.name).includes('motorin')||norm(x.category+' '+x.name).includes('mazot');
 const round6=x=>Math.round(x*1e6)/1e6;
 const money2=x=>Math.round(x*100)/100;
 let snapshot=[],diesels=[],seq=0;
 async function fill(){
  const ticket=++seq;const [parcels,inputs,moves]=await Promise.all(['parcels','inputs','stockMoves'].map(all));if(ticket!==seq)return;
  snapshot=moves;diesels=inputs.filter(isDiesel);
  const ps=form.elements.parcel_code,old=ps.value;ps.replaceChildren(new Option('Parsel seçin',''));for(const p of parcels)ps.add(new Option(`${p.name} (${p.code})`,p.code));if(parcels.some(p=>p.code===old))ps.value=old;
  const ds=form.elements.diesel_id,prev=ds.value;ds.replaceChildren(new Option('Motorin seçin',''));for(const x of diesels)ds.add(new Option(`${x.name} (${x.unit})`,x.id));if(diesels.some(x=>String(x.id)===prev))ds.value=prev;else if(diesels.length===1)ds.value=String(diesels[0].id);
  await area();preview();
 }
 async function area(){const f=form.elements;if(!f.parcel_code.value)return;const [source,parcels]=await Promise.all([all('sourceRecords'),all('parcels')]);const a=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).find(x=>x.parcel_code===f.parcel_code.value&&x.season===f.season.value);const p=parcels.find(x=>x.code===f.parcel_code.value);const n=a?num(a.worked_area_da):num(p?.area_m2)/1000;if(n>0)f.area_da.value=round6(n);preview()}
 function stock(inputId,date){const rows=snapshot.filter(m=>String(m.input_id)===String(inputId));return rows.reduce((sum,m)=>sum+(m.kind==='purchase'&&m.date<=date?num(m.quantity):m.kind==='use'&&m.date<=date?-num(m.quantity):0),0)}
 function preview(){const f=form.elements,a=num(f.area_da.value),r=num(f.diesel_rate.value),q=round6(a*r),d=diesels.find(x=>String(x.id)===String(f.diesel_id.value)),available=d?stock(d.id,f.date.value):0,fee=a*num(f.combine_rate.value);const issues=[];if(!(a>0))issues.push('İşlenen alan gerekli');if(!(num(f.quantity.value)>0))issues.push('Hasat miktarı gerekli');if(!d)issues.push('Motorin seçin');if(!(r>0))issues.push('Motorin tüketimi sıfırdan büyük olmalı');if(d&&q>available+1e-8)issues.push('Motorin stoku yetersiz');if(f.combine_rate.value===''||!Number.isFinite(num(f.combine_rate.value))||num(f.combine_rate.value)<0)issues.push('Biçerdöver ücreti gerekli (bilinmiyorsa 0)');
  const box=document.getElementById('mobileHarvestPreview');box.textContent=`Traktör motorini: ${fmt(q)} ${d?.unit||'L'} · Mevcut: ${fmt(available)} ${d?.unit||'L'} · Kalan: ${fmt(available-q)} ${d?.unit||'L'} · Biçerdöver gideri: ${fmt(fee)} ₺`+(issues.length?'\n⚠ '+issues.join(' · '):'\n✓ Kayıt için hazır');box.style.whiteSpace='pre-line';box.style.color=issues.length?'#9c2727':'';form.querySelector('button[type=submit]').disabled=issues.length>0;
 }
 function fifo(moves,id,date,quantity){const relevant=moves.filter(m=>String(m.input_id)===String(id));if(relevant.some(m=>m.kind==='use'&&m.date>date))throw Error('Motorinin daha ileri tarihli kullanımı var; geçmiş tarihli işlem eklenemez');const lots=relevant.filter(m=>m.kind==='purchase'&&m.date<=date).sort((a,b)=>a.date.localeCompare(b.date)||String(a.id).localeCompare(String(b.id))).map(m=>({left:num(m.quantity),price:num(m.unit_price)}));const used=relevant.filter(m=>m.kind==='use'&&m.date<=date).sort((a,b)=>a.date.localeCompare(b.date)||String(a.id).localeCompare(String(b.id)));function consume(q){let cost=0;for(const l of lots){const take=Math.min(q,l.left);l.left-=take;q-=take;cost+=take*l.price;if(q<=1e-8)break}if(q>1e-8)throw Error('İşlem tarihinde motorin stoku yetersiz');return cost}for(const m of used)consume(num(m.quantity));return money2(consume(quantity))}
 form.elements.date.value=localDate();
 for(const e of form.querySelectorAll('input,select'))e.addEventListener('input',preview);
 form.elements.parcel_code.addEventListener('change',()=>area().catch(console.error));form.elements.season.addEventListener('change',()=>area().catch(console.error));
 document.querySelectorAll('[data-tab="operations"],[data-dash-tab="operations"]').forEach(b=>b.addEventListener('click',()=>fill().catch(console.error)));
 form.addEventListener('submit',async e=>{e.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;try{
  const f=form.elements,areaDa=num(f.area_da.value),kg=num(f.quantity.value),rate=num(f.diesel_rate.value),feeRate=num(f.combine_rate.value),quantity=round6(areaDa*rate);
  if(!f.date.value||!f.season.value||!f.parcel_code.value||!f.crop.value||!(areaDa>0)||!(kg>0)||!(rate>0)||!(quantity>0)||f.combine_rate.value===''||!(feeRate>=0)||![areaDa,kg,rate,feeRate,quantity].every(Number.isFinite))throw Error('Zorunlu alanları kontrol edin');
  const [parcels,inputs,moves]=await Promise.all(['parcels','inputs','stockMoves'].map(all));if(!parcels.some(p=>p.code===f.parcel_code.value))throw Error('Parsel bulunamadı');const fuel=inputs.find(x=>String(x.id)===String(f.diesel_id.value)&&isDiesel(x));if(!fuel)throw Error('Motorin seçin');if(!['l','lt','litre','liter'].includes(norm(fuel.unit)))throw Error('Motorin birimi litre olmalı');
  const fuelCost=fifo(moves,fuel.id,f.date.value,quantity),activityId=crypto.randomUUID(),harvestId=crypto.randomUUID(),moveId=crypto.randomUUID(),serviceId=crypto.randomUUID();const unitCost=fuelCost/quantity;
  const harvest={id:harvestId,date:f.date.value,season:f.season.value,parcel_code:f.parcel_code.value,crop:f.crop.value,quantity:kg,area_da:areaDa,yield_per_da:kg/areaDa,activity_id:activityId,bundle_version:'3.5.6'};
  const move={id:moveId,kind:'use',input_id:fuel.id,date:f.date.value,quantity,unit_price:unitCost,total:fuelCost,parcel_code:f.parcel_code.value,area_da:areaDa,per_da:rate,activity_id:activityId,activity_type:'Hasat'};
  const op={id:crypto.randomUUID(),op_date:f.date.value,season:f.season.value,parcel_code:f.parcel_code.value,op_type:'Hasat - Traktör motorini',item:fuel.name,quantity,unit:fuel.unit,unit_price:unitCost,amount:fuelCost,direction:'Gider',stock_move_id:moveId,area_da:areaDa,per_da:rate,activity_id:activityId};
  const service={id:serviceId,date:f.date.value,season:f.season.value,parcel_code:f.parcel_code.value,kind:'Biçerdöver',provider:f.provider.value||'',quantity:areaDa,unit:'da',unit_price:feeRate,amount:money2(areaDa*feeRate),bundle_harvest_id:harvestId,activity_id:activityId};
  if(!confirm(`Hasat ${fmt(kg)} kg, traktör motorini ${fmt(quantity)} ${fuel.unit}, biçerdöver gideri ${fmt(service.amount)} ₺ birlikte kaydedilsin mi?`))return;
  await tx(['harvests','stockMoves','operations','services'],'readwrite',t=>{t.objectStore('harvests').add(harvest);t.objectStore('stockMoves').add(move);t.objectStore('operations').add(op);t.objectStore('services').add(service)});
  alert('Hasat, traktör motorini ve biçerdöver gideri tek işlemde kaydedildi.');f.quantity.value='';await render();if(typeof renderExtended==='function')await renderExtended();await fill();
 }catch(err){alert('Kayıt yapılamadı: '+err.message)}finally{button.disabled=false;preview()}});
 fill().catch(console.error);
 // Keep the old separate forms in the DOM for backward compatibility, but do not display them.
})();
