'use strict';
// V3.2.4: Parcel-based bale inventory and sales. No legacy record mutation.
(()=>{
 const form=document.getElementById('baleSaleForm');if(!form)return;
 const $id=id=>document.getElementById(id),num=x=>Number(x||0),fmt=x=>num(x).toLocaleString('tr-TR',{maximumFractionDigits:2});
 const seasonKey=x=>String(x||'').replace(/\D/g,'');
 const live=x=>!num(x.is_cancelled);
 const byDate=(a,b)=>String(a.date||'').localeCompare(String(b.date||''))||String(a.id||'').localeCompare(String(b.id||''));
 const units=x=>num(x.quantity||x.bale_count);
 function salesFor(sales,season,code,cutoff){
  return sales.filter(x=>live(x)&&seasonKey(x.season)===seasonKey(season)&&x.parcel_code===code&&(!cutoff||String(x.date||'')<=cutoff));
 }
 function available(bales,sales,season,code,cutoff){
  const lots=bales.filter(x=>live(x)&&seasonKey(x.season)===seasonKey(season)&&x.parcel_code===code&&(!cutoff||String(x.date||'')<=cutoff));
  const sold=salesFor(sales,season,code,cutoff).reduce((a,x)=>a+units(x),0);
  return {received:lots.reduce((a,x)=>a+units(x),0),sold,remaining:lots.reduce((a,x)=>a+units(x),0)-sold,lots:lots.sort(byDate)};
 }
 async function draw(){
  const [bales,sales,services,parcels]=await Promise.all(['bales','baleSales','services','parcels'].map(all));
  const sel=form.elements.parcel_code,old=sel.value;
  // The existing renderExtended function populates .extraParcel too; preserve selection.
  if(!sel.options.length){for(const x of parcels)sel.add(new Option(`${x.name} (${x.code})`,x.code));sel.value=old||sel.options[0]?.value||''}
  const season=form.elements.season.value,code=sel.value,date=form.elements.date.value;
  const stock=available(bales,sales,season,code);
  const dated=available(bales,sales,season,code,date);
  const qty=Number(form.elements.quantity.value),price=Number(form.elements.unit_price.value);
  $id('baleSalePreview').textContent=`${code||'Parsel'} · ${season||'Sezon'} · Tarihte kullanılabilir ${fmt(dated.remaining)} balya`+(qty>0?` · Satış ${fmt(qty*price)} ₺`:'')+(qty>dated.remaining?' · UYARI: Stok yetersiz':'');
  const activeBales=bales.filter(live),activeSales=sales.filter(live),activeServices=services.filter(live);
  const keys=[...new Set(activeBales.map(x=>`${seasonKey(x.season)}|${x.parcel_code}`).concat(activeSales.map(x=>`${seasonKey(x.season)}|${x.parcel_code}`)))].sort();
  $id('baleStockSummary').textContent=`Seçili parsel (${code||'—'}) · ${season||'—'}: ${fmt(stock.received)} balya giriş · ${fmt(stock.sold)} satış · ${fmt(stock.remaining)} kalan`;
  const report=$id('baleParcelReport');report.replaceChildren();
  if(!keys.length){report.textContent='Henüz balya kaydı yok.'}
  for(const key of keys){
   const [sk,parcel]=key.split('|'),reference=[...activeBales,...activeSales].find(x=>seasonKey(x.season)===sk&&x.parcel_code===parcel);
   const seasonName=reference?.season||sk;
   const a=available(bales,sales,seasonName,parcel);
   const revenue=activeSales.filter(x=>seasonKey(x.season)===sk&&x.parcel_code===parcel).reduce((n,x)=>n+num(x.total||num(x.quantity)*num(x.unit_price)),0);
   const cost=activeServices.filter(x=>seasonKey(x.season)===sk&&x.parcel_code===parcel&&/balya/i.test(x.kind||'')).reduce((n,x)=>n+num(x.amount),0);
   const row=document.createElement('p');row.textContent=`${seasonName} · ${parcel}: ${fmt(a.received)} üretilen / ${fmt(a.sold)} satılan / ${fmt(a.remaining)} kalan · Balya satış geliri ${fmt(revenue)} ₺ · Balyalama hizmet gideri ${fmt(cost)} ₺`;report.append(row);
  }
  const list=$id('baleSaleList');list.replaceChildren();
  for(const x of activeSales.sort(byDate).reverse().slice(0,30)){
   const row=document.createElement('p');row.textContent=`${x.date} · ${x.season} · ${x.parcel_code} · ${fmt(x.quantity)} balya × ${fmt(x.unit_price)} ₺ = ${fmt(x.total)} ₺`;list.append(row);
  }
  if(!list.childNodes.length)list.textContent='Henüz balya satışı yok.';
 }
 let pending=false;
 async function refresh(){if(pending)return;pending=true;try{await draw()}catch(e){console.error(e);$id('baleStockSummary').textContent='Balya bilgileri okunamadı.'}finally{pending=false}}
 form.elements.date.value=localDate();
 form.addEventListener('input',refresh);form.addEventListener('change',refresh);
 form.addEventListener('submit',async event=>{
  event.preventDefault();
  const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
   const x=Object.fromEntries(new FormData(form)),q=Number(x.quantity),price=Number(x.unit_price);
   if(!x.date||!x.season||!x.parcel_code||!Number.isInteger(q)||q<=0||!Number.isFinite(price)||price<0)throw Error('Tarih, sezon, parsel, adet veya fiyat geçersiz.');
   const [bales,sales,parcels]=await Promise.all(['bales','baleSales','parcels'].map(all));
   if(!parcels.some(p=>p.code===x.parcel_code))throw Error('Parsel bulunamadı.');
   // Do not allow backdated sales that invalidate already-recorded later sales.
   if(sales.some(s=>live(s)&&seasonKey(s.season)===seasonKey(x.season)&&s.parcel_code===x.parcel_code&&String(s.date)>x.date))throw Error('Bu parselde daha sonraki tarihli balya satışı var. Önce kronolojik sırayla kayıt yapın.');
   const a=available(bales,sales,x.season,x.parcel_code,x.date);
   if(q>a.remaining)throw Error(`Yetersiz stok. Bu tarihte ${fmt(a.remaining)} balya var.`);
   let left=q;const allocations=[];
   const consumed=new Map();
   for(const s of salesFor(sales,x.season,x.parcel_code,x.date)){
    if(Array.isArray(s.allocations)&&s.allocations.length)for(const v of s.allocations)consumed.set(String(v.bale_id),(consumed.get(String(v.bale_id))||0)+num(v.quantity));
    else {let n=units(s);for(const lot of a.lots){const free=Math.max(0,units(lot)-(consumed.get(String(lot.id))||0));const take=Math.min(n,free);if(take){consumed.set(String(lot.id),(consumed.get(String(lot.id))||0)+take);n-=take}if(n<=0)break}}
   }
   for(const lot of a.lots){const free=Math.max(0,units(lot)-(consumed.get(String(lot.id))||0)),take=Math.min(left,free);if(take){allocations.push({bale_id:String(lot.id),parcel_code:x.parcel_code,quantity:take});left-=take}if(left<=0)break}
   if(left>0)throw Error('Balya parti tahsisi tamamlanamadı.');
   const record={id:crypto.randomUUID(),date:x.date,season:x.season,parcel_code:x.parcel_code,quantity:q,unit:'adet',unit_price:price,total:Math.round(q*price*100)/100,allocations,source:'mobile-v3.2.4'};
   if(!confirm(`${q} balya · ${fmt(record.total)} ₺ satış kaydedilsin mi?`))return;
   // Recheck inventory within the same readwrite transaction to prevent duplicate sale on concurrent tabs.
   await tx(['bales','baleSales'],'readwrite',t=>{
    const bReq=t.objectStore('bales').getAll(),sReq=t.objectStore('baleSales').getAll();
    let br,sr;
    const verify=()=>{
     if(!br||!sr)return;
     const check=available(br,sr,x.season,x.parcel_code,x.date);
     const newer=sr.some(s=>live(s)&&seasonKey(s.season)===seasonKey(x.season)&&s.parcel_code===x.parcel_code&&String(s.date)>x.date);
     if(newer||check.remaining<q||allocations.some(a=>!check.lots.some(l=>String(l.id)===a.bale_id))){t.abort();return}
     t.objectStore('baleSales').add(record);
    };
    bReq.onsuccess=()=>{br=bReq.result;verify()};
    sReq.onsuccess=()=>{sr=sReq.result;verify()};
   });
   form.elements.quantity.value='';form.elements.unit_price.value='';
   await render();await refresh();alert('Balya satışı kaydedildi; stok ve parsel satış geliri güncellendi.');
  }catch(err){alert('Satış kaydedilemedi: '+err.message)}finally{button.disabled=false}
 });
 // refresh after existing app renders; no modifications to old stores.
 const previous=window.renderExtended;
 if(typeof previous==='function')window.renderExtended=async function(...args){const result=await previous.apply(this,args);await refresh();return result};
 setTimeout(refresh,400);
})();
