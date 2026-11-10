 'use strict';
// V4.0.14: read-only product-equivalent view; no changes to accounting or IndexedDB.
(()=>{
 const root=document.getElementById('productEquivalent414');if(!root)return;
 const cropEl=document.getElementById('eqCrop414'),priceEl=document.getElementById('eqPrice414'),saveEl=document.getElementById('eqSave414'),info=document.getElementById('eqPriceInfo414'),out=document.getElementById('eqResults414'),seasonEl=document.getElementById('seasonFilter');
 const num=v=>Number(v)||0, key=v=>String(v||'').trim().toLocaleLowerCase('tr-TR'),sk=v=>String(v||'').replace(/\D/g,''),valid=x=>!num(x.is_cancelled),fmt=x=>Number(x).toLocaleString('tr-TR',{maximumFractionDigits:2}),sum=(xs,fn)=>xs.reduce((a,x)=>a+num(fn(x)),0);
 const prefs=()=>{try{return JSON.parse(localStorage.getItem('ozcan_eq_prices_414')||'{}')}catch{return {}}};
 const money=x=>fmt(x)+' ₺';let data=null,token=0;
 function option(c){const o=new Option(c,c);cropEl.add(o)}
 function cropOf(x){return String(x.crop||x.product||'').trim()}
 async function refresh(){const id=++token,season=seasonEl.value;if(!season){out.textContent='Önce sezon seçin.';return}
  const names=['parcels','operations','sourceRecords','harvests','sales','supports','inputs','stockMoves'];
  const d=await Promise.all(names.map(n=>all(n)));if(id!==token)return;
  const [parcels,ops,source,harvests,sales,supports,inputs,moves]=d;
  const same=x=>valid(x)&&sk(x.season)===sk(season);
  const sourceOps=source.filter(x=>x.table==='operations').map(x=>x.record).filter(same);
  const operations=sourceOps.concat(ops.filter(x=>same(x)&&!String(x.id||'').startsWith('pc-op-')&&!sourceOps.some(y=>String(y.id)===String(x.id))));
  const hs=harvests.filter(same),ss=sales.filter(same),sup=supports.filter(same);
  const areas=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).filter(same);
  const crops=[...new Set([...hs.map(cropOf),...ss.map(cropOf)].filter(Boolean))].sort((a,b)=>a.localeCompare(b,'tr'));
  const old=cropEl.value;cropEl.replaceChildren(new Option('Ürün seçin',''));crops.forEach(option);cropEl.value=crops.includes(old)?old:(crops[0]||'');
  data={season,parcels,operations,hs,ss,sup,areas,inputs,moves};updatePrice();render();
 }
 function seedPrice(crop){if(!data)return null;const related=data.inputs.filter(x=>/tohum/i.test(String(x.category||''))&&(key(x.name).includes(key(crop))||key(crop).includes(key(x.name))));
  const ids=new Set(related.map(x=>String(x.id)));const purchases=data.moves.filter(x=>x.kind==='purchase'&&ids.has(String(x.input_id))&&num(x.quantity)>0&&num(x.unit_price)>0);
  if(!purchases.length)return null;return sum(purchases,x=>num(x.quantity)*num(x.unit_price))/sum(purchases,x=>x.quantity);
 }
 function updatePrice(){if(!data)return;const c=cropEl.value,p=prefs(),id=sk(data.season)+'|'+key(c),stored=p[id],seed=seedPrice(c);priceEl.value=stored>0?stored:(seed>0?seed:'');info.textContent=stored>0?'Fiyat kaynağı: sezonluk kullanıcı referansı.':seed>0?'Fiyat kaynağı: kayıtlı tohum alışlarının ağırlıklı ortalaması (tohumluk fiyatı, mahsul fiyatından farklı olabilir).':'Bu ürün için fiyat bulunamadı. Hesaplama için referans TL/kg girin.'}
 function render(){if(!data)return;out.replaceChildren();const price=num(priceEl.value);if(!(price>0)){out.textContent='Kilogram karşılığı için pozitif referans fiyat gerekli.';return}
  const {parcels,operations,hs,ss,sup,areas}=data,crop=cropEl.value;if(!crop){out.textContent='Bu sezonda kayıtlı hasat/satış ürünü bulunamadı. Hasat öncesi rapor için önce ürünün parsel ekim kaydında tanımlanması gerekir.';return}
  const codes=[...new Set([...parcels.map(x=>x.code),...operations.map(x=>x.parcel_code),...hs.map(x=>x.parcel_code)].filter(Boolean))].sort();
  const table=document.createElement('table');table.className='profit-table';const head=document.createElement('tr');['Parsel','Alan (da)','Hasat (kg/da)','İşlem gideri (₺/da)','Gider karşılığı (kg/da)','Destek (kg/da)','Net (kg/da)','Tohum verim katı','Satış fiyatı (₺/kg)'].forEach(x=>{const th=document.createElement('th');th.textContent=x;head.append(th)});table.append(head);
  let shown=0;
  for(const code of codes){const ph=hs.filter(x=>x.parcel_code===code&&key(cropOf(x))===key(crop));const po=operations.filter(x=>x.parcel_code===code);const sow=po.filter(x=>/ekim|tohum/i.test(String(x.op_type||'')+' '+String(x.item||''))&&key(String(x.item||'')).includes(key(crop)));
   // Only include unharvested parcels if a matching crop is explicitly identifiable in sowing records.
   if(!ph.length&&!sow.length)continue;
   const areaRec=areas.find(x=>x.parcel_code===code),parcel=parcels.find(x=>x.code===code),da=areaRec?num(areaRec.worked_area_da):num(parcel?.area_m2)/1000;
   const harvestKg=sum(ph,x=>x.quantity),cost=sum(po.filter(x=>x.direction==='Gider'),x=>x.amount);
   const assigned=sup.filter(x=>x.parcel_code===code);const support=sum(assigned,x=>x.amount);
   const seedKg=sum(sow.filter(x=>/tohum/i.test(String(x.item||''))),x=>x.quantity);
   const allocations=ss.flatMap(x=>(x.allocations||[]).filter(a=>a.parcel_code===code&&key(cropOf(x))===key(crop)).map(a=>({kg:num(a.quantity),unitPrice:num(x.unit_price)})));
   const soldKg=sum(allocations,x=>x.kg),soldValue=sum(allocations,x=>x.kg*x.unitPrice),salePrice=soldKg?soldValue/soldKg:0;
   const net=harvestKg-cost/price+support/price;const cells=[code,da>0?fmt(da):'—',da>0?fmt(harvestKg/da):'—',da>0?fmt(cost/da):'—',da>0?fmt(cost/price/da):'—',da>0?fmt(support/price/da):'—',da>0?((net/da>=0?'+':'')+fmt(net/da)):'—',seedKg>0?fmt(harvestKg/seedKg)+' kat':'—',salePrice>0?fmt(salePrice):'—'];const tr=document.createElement('tr');cells.forEach((value,i)=>{const td=document.createElement('td');td.textContent=value;if(i===6)td.style.fontWeight='700';tr.append(td)});table.append(tr);shown++;
  }
  if(!shown){out.textContent='Bu ürün için parsel bağlantılı hasat veya açıkça tanımlanmış ekim kaydı bulunamadı.';return}
  const wrap=document.createElement('div');wrap.className='profit-scroll';wrap.append(table);out.append(wrap);
  const note=document.createElement('p');note.className='perda-note';note.textContent=`Referans ${fmt(price)} ₺/kg. Net (kg/da) = hasat (kg/da) − kayıtlı işlem gideri / fiyat / da + parsele bağlı destek / fiyat / da. Hasat öncesi hasat=0 olduğundan sonuç negatiftir. Tohum gideri işlem giderine zaten dâhilse tekrar düşülmez. Satış fiyatı, referans fiyatıyla karşılaştırma içindir.`;out.append(note);
 }
 seasonEl.addEventListener('change',()=>refresh().catch(e=>out.textContent=e.message));cropEl.addEventListener('change',()=>{updatePrice();render()});priceEl.addEventListener('input',render);
 saveEl.addEventListener('click',()=>{if(!data||!cropEl.value||!(num(priceEl.value)>0))return alert('Ürün ve pozitif fiyat seçin.');const p=prefs();p[sk(data.season)+'|'+key(cropEl.value)]=num(priceEl.value);localStorage.setItem('ozcan_eq_prices_414',JSON.stringify(p));updatePrice();render();info.textContent+=' Kaydedildi.'});
 const previous=window.renderExtended;if(typeof previous==='function')window.renderExtended=async function(...args){const r=await previous.apply(this,args);await refresh();return r};
 setTimeout(()=>refresh().catch(e=>out.textContent='Rapor yüklenemedi: '+e.message),700);
})();