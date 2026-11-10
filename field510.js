 'use strict';
(()=>{
const form=document.getElementById('v51HarvestForm');if(!form)return;
const fmt=n=>Number(n).toLocaleString('tr-TR',{maximumFractionDigits:6});
const round6=n=>Math.round(n*1e6)/1e6;
const classify=x=>/motorin|mazot/i.test((x.category||'')+' '+(x.name||''));
let currentMoves=[], currentInputs=[];
async function populate(){
 const [parcels,inputs,moves,source]=await Promise.all(['parcels','inputs','stockMoves','sourceRecords'].map(all));
 currentInputs=inputs;currentMoves=moves;
 const sel=form.elements.parcel_code,old=sel.value;
 sel.replaceChildren(new Option('Parsel seçin',''),...parcels.filter(p=>p.active!==0&&p.active!=='0').map(p=>new Option(`${p.name} (${p.code})`,p.code)));
 if([...sel.options].some(o=>o.value===old))sel.value=old;
 const fuel=form.elements.diesel_id,was=fuel.value;
 fuel.replaceChildren(new Option('Motorin seçin',''),...inputs.filter(classify).map(i=>new Option(`${i.name} (${i.unit})`,i.id)));
 if([...fuel.options].some(o=>o.value===was))fuel.value=was;
 else if(fuel.options.length===2)fuel.selectedIndex=1;
 if(sel.value){const rec=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).find(x=>x.parcel_code===sel.value&&x.season===form.elements.season.value);
 const parcel=parcels.find(x=>x.code===sel.value),a=Number(rec?.worked_area_da||parcel?.area_m2/1000||0);
 if(a>0&&!form.elements.area_da.value)form.elements.area_da.value=round6(a);
 }
 preview();
}
function stock(id,dt){return currentMoves.filter(x=>String(x.input_id)===String(id)&&String(x.date)<=dt).reduce((n,x)=>n+(x.kind==='purchase'?Number(x.quantity):x.kind==='use'?-Number(x.quantity):0),0)}
function preview(){const f=form.elements,a=Number(f.area_da.value),r=Number(f.diesel_rate.value),q=round6(a*r),input=currentInputs.find(x=>String(x.id)===String(f.diesel_id.value));const available=input?stock(input.id,f.date.value):0;
 const msg=[`Hasat: ${fmt(Number(f.quantity.value||0))} kg`,`Traktör motorini: ${fmt(q)} L`,`Biçerdöver: ${fmt(a*Number(f.combine_rate.value||0))} ₺`];
 if(input){msg.push(`Motorin stoku: ${fmt(available)} ${input.unit}`);if(q>available+1e-7)msg.push('⚠ Stok yetersiz');}
 document.getElementById('v51HarvestPreview').textContent=msg.join(' · ');
}
function fifo(moves,id,date,qty){const relevant=moves.filter(x=>String(x.input_id)===String(id));if(relevant.some(x=>x.kind==='use'&&String(x.date)>date))throw Error('Motorinin ileri tarihli kullanımı var; geçmiş tarihli tüketim eklenemez.');
 const lots=relevant.filter(x=>x.kind==='purchase'&&String(x.date)<=date).sort((a,b)=>String(a.date).localeCompare(String(b.date))||String(a.id).localeCompare(String(b.id))).map(x=>({left:Number(x.quantity),price:Number(x.unit_price)}));
 function consume(q){let cost=0;for(const lot of lots){const take=Math.min(q,lot.left);if(take>0){lot.left-=take;q-=take;cost+=take*lot.price;}if(q<=1e-8)break;}if(q>1e-8)throw Error('İşlem tarihinde motorin stoku yetersiz.');return cost;}
 for(const x of relevant.filter(x=>x.kind==='use'&&String(x.date)<=date).sort((a,b)=>String(a.date).localeCompare(String(b.date))||String(a.id).localeCompare(String(b.id))))consume(Number(x.quantity));
 return Math.round(consume(qty)*100)/100;
}
form.elements.date.value=localDate();
form.addEventListener('input',preview);form.addEventListener('change',preview);
form.elements.parcel_code.addEventListener('change',()=>{form.elements.area_da.value='';populate().catch(console.error)});
form.elements.season.addEventListener('change',()=>{form.elements.area_da.value='';populate().catch(console.error)});
document.addEventListener('click',e=>{if(e.target.closest('[data-tab="operations"], [data-tab="operationsHub"]'))setTimeout(()=>populate().catch(console.error),80)},true);
form.addEventListener('submit',async e=>{e.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;try{
 const f=form.elements,date=f.date.value,season=f.season.value,code=f.parcel_code.value,crop=f.crop.value.trim(),a=Number(f.area_da.value),kg=Number(f.quantity.value),rate=Number(f.diesel_rate.value),fee=Number(f.combine_rate.value);
 if(!date||!season||!code||!crop)throw Error('Tarih, sezon, parsel ve ürün zorunlu.');
 if(![a,kg,rate,fee].every(Number.isFinite)||a<=0||kg<=0||rate<=0||fee<0)throw Error('Hasat miktarı, alan ve motorin pozitif; biçerdöver ücreti sıfır veya pozitif olmalı.');
 const diesel=round6(a*rate);if(diesel<=0)throw Error('Motorin miktarı geçersiz.');
 const [inputs,moves,parcels]=await Promise.all(['inputs','stockMoves','parcels'].map(all));
 if(!parcels.some(p=>p.code===code))throw Error('Parsel bulunamadı.');
 const input=inputs.find(x=>String(x.id)===String(f.diesel_id.value)&&classify(x));if(!input)throw Error('Depodan motorin seçin.');
 if(!/^(l|lt|litre|liter)$/i.test(String(input.unit).trim()))throw Error('Motorin birimi litre olmalı; depo tanımını kontrol edin.');
 const total=fifo(moves,input.id,date,diesel),id=crypto.randomUUID(),moveId=crypto.randomUUID(),unitCost=total/diesel;
 const harvest={id,date,season,parcel_code:code,crop,quantity:round6(kg),area_da:a,yield_per_da:round6(kg/a),bundle_version:'5.1'};
 const movement={id:moveId,kind:'use',input_id:input.id,date,quantity:diesel,unit_price:unitCost,total,parcel_code:code,area_da:a,per_da:rate,activity_id:id,activity_type:'Hasat',source_harvest_id:id};
 const op={id:crypto.randomUUID(),op_date:date,season,parcel_code:code,op_type:'Hasat traktör motorini',item:input.name,quantity:diesel,unit:input.unit,unit_price:unitCost,amount:total,direction:'Gider',stock_move_id:moveId,area_da:a,per_da:rate,activity_id:id};
 const service={id:crypto.randomUUID(),date,season,parcel_code:code,kind:'Biçerdöver',quantity:a,unit:'da',unit_price:fee,amount:Math.round(a*fee*100)/100,provider:f.provider.value.trim(),bundle_harvest_id:id};
 if(!confirm(`${fmt(kg)} kg ${crop} depoya girsin; ${fmt(diesel)} L motorin düşülsün; ${fmt(service.amount)} ₺ biçerdöver gideri kaydedilsin mi?`))return;
 await tx(['harvests','stockMoves','operations','services'],'readwrite',t=>{t.objectStore('harvests').add(harvest);t.objectStore('stockMoves').add(movement);t.objectStore('operations').add(op);t.objectStore('services').add(service)});
 alert('Hasat, traktör motorini ve biçerdöver gideri tek işlemde kaydedildi.');form.elements.quantity.value='';await render();if(typeof renderExtended==='function')await renderExtended();await populate();
 }catch(err){alert('Kayıt yapılmadı: '+err.message)}finally{btn.disabled=false;}});
setTimeout(()=>populate().catch(console.error),300);
})();
