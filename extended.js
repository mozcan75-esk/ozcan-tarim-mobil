 'use strict';
const number=x=>Number(x||0), uid=()=>crypto.randomUUID();
const escapeText=x=>String(x??'');
const extraForms=[['harvestForm','harvests'],['saleForm','sales'],['rentForm','rents'],['rentPaymentForm','rentPayments'],['supportForm','supports'],['maintenanceForm','maintenance'],['serviceForm','services']];
async function renderExtended(){
 const [parcels,harvests,sales,rents,payments,supports,maintenance,services,ops]=await Promise.all(['parcels','harvests','sales','rents','rentPayments','supports','maintenance','services','operations'].map(all));
 for(const sel of document.querySelectorAll('.extraParcel')){const val=sel.value;sel.replaceChildren();for(const x of parcels)sel.add(new Option(`${x.name} (${x.code})`,x.code));sel.value=val||sel.options[0]?.value||''}
 const crops=[...new Set(harvests.map(x=>x.crop))].sort(),sel=$('cropSelect'),old=sel.value;sel.replaceChildren();for(const crop of crops)sel.add(new Option(crop,crop));sel.value=old||sel.options[0]?.value||'';
 $('cropList').replaceChildren();for(const crop of crops){const total=harvests.filter(x=>x.crop===crop).reduce((n,x)=>n+number(x.quantity),0)-sales.filter(x=>x.crop===crop).reduce((n,x)=>n+number(x.quantity),0);item($('cropList'),`${crop}: ${total.toLocaleString('tr-TR')} kg stok`)}
 const rsel=$('rentSelect'),rv=rsel.value;rsel.replaceChildren();$('rentList').replaceChildren();for(const r of rents){const paid=payments.filter(x=>x.rent_id===r.id).reduce((n,x)=>n+number(x.amount),0);rsel.add(new Option(`${r.landlord} / ${r.parcel_code} / ${r.season}`,r.id));item($('rentList'),`${r.season} · ${r.parcel_code} · ${r.landlord} · İcar: ${money(r.total_amount)} ₺ · Ödenen: ${money(paid)} ₺ · Kalan: ${money(number(r.total_amount)-paid)} ₺`)}rsel.value=rv||rsel.options[0]?.value||'';
 $('supportList').replaceChildren();for(const x of supports)item($('supportList'),`Destek · ${x.season} · ${x.support_type}: ${money(x.amount)} ₺`);for(const x of maintenance)item($('supportList'),`Bakım · ${x.season} · ${x.machine}: ${money(x.cost)} ₺`);
 $('serviceList').replaceChildren();for(const x of services)item($('serviceList'),`${x.season} · ${x.parcel_code} · ${x.kind} · ${money(x.amount)} ₺`);
 const seasons=[...new Set([...ops,...harvests,...rents,...supports,...maintenance,...services].map(x=>x.season).filter(Boolean))].sort().reverse(),sf=$('seasonFilter'),sv=sf.value;sf.replaceChildren();for(const x of seasons)sf.add(new Option(x,x));sf.value=sv||sf.options[0]?.value||'';
 const source=await all('sourceRecords');
 const areas=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record);
 const activities=source.filter(x=>x.table==='field_activities').map(x=>x.record);
 const season=sf.value, filter=x=>x.season===season;
 const selectedActivities=activities.filter(filter);
 const selectedAreas=areas.filter(filter);
 $('analysisList').replaceChildren();
 if(season){
   item($('analysisList'),`Sezon: ${season}`);
   item($('analysisList'),`Bilgisayardan korunan tarla faaliyetleri: ${selectedActivities.length} kayıt`);
   item($('analysisList'),`Ayrı işlenen alan kaydı: ${selectedAreas.length} parsel`);
   for(const a of selectedAreas.sort((a,b)=>a.parcel_code.localeCompare(b.parcel_code)))
     item($('analysisList'),`${a.parcel_code}: işlenen ${number(a.worked_area_da).toLocaleString('tr-TR')} da · icar ${number(a.leased_area_da).toLocaleString('tr-TR')} da`);
     // Salt okunur mutabakat: bilgisayardan gelen özgün kayıtlar esas alınır.
   const sourceOps=source.filter(x=>x.table==='operations').map(x=>x.record).filter(x=>!Number(x.is_cancelled)&&x.season===season);
   const mobileOps=ops.filter(x=>x.season===season);
   const sum=(rows,dir)=>rows.filter(x=>x.direction===dir).reduce((n,x)=>n+number(x.amount),0);
   const pcIncome=sum(sourceOps,'Gelir'),pcExpense=sum(sourceOps,'Gider');
   const mobileImported=mobileOps.filter(x=>String(x.id).startsWith('pc-op-'));
   const importedIncome=sum(mobileImported,'Gelir'),importedExpense=sum(mobileImported,'Gider');
   const equal=(a,b)=>Math.abs(a-b)<0.011;
   item($('analysisList'),`Bilgisayar kaynak işlemleri: ${sourceOps.length} kayıt · Gelir ${money(pcIncome)} ₺ · Gider ${money(pcExpense)} ₺`);
   item($('analysisList'),`Mobilde korunan kaynak işlemler: ${mobileImported.length} kayıt · Gelir ${money(importedIncome)} ₺ · Gider ${money(importedExpense)} ₺`);
   item($('analysisList'),`Kaynak işlem mutabakatı: ${sourceOps.length===mobileImported.length&&equal(pcIncome,importedIncome)&&equal(pcExpense,importedExpense)?'UYUMLU':'FARK VAR — mobil kaynak işlemlerini kontrol edin'}`);
   const cats=[...new Set(sourceOps.filter(x=>x.direction==='Gider').map(x=>x.category||'Diğer'))].sort();
   for(const cat of cats){const rows=sourceOps.filter(x=>x.direction==='Gider'&&(x.category||'Diğer')===cat);item($('analysisList'),`${cat}: ${rows.length} kayıt · ${money(rows.reduce((n,x)=>n+number(x.amount),0))} ₺ (bilgisayar kaynak gideri)`)}
   const parcelCodes=[...new Set(sourceOps.map(x=>x.parcel_code).filter(Boolean))].sort();
   for(const code of parcelCodes){const pOps=sourceOps.filter(x=>x.parcel_code===code);const cost=sum(pOps,'Gider'),income=sum(pOps,'Gelir');const area=selectedAreas.find(x=>x.parcel_code===code);const parcel=parcels.find(x=>x.code===code);const da=area?number(area.worked_area_da):number(parcel?.area_m2)/1000;item($('analysisList'),`${code}: kaynak gider ${money(cost)} ₺ · kaynak gelir ${money(income)} ₺ · ${da>0?money(cost/da)+' ₺/da':'alan bulunamadı'} (${area?'sezon işlenen alan':'parsel alanı — doğrulanmalı'})`)}
   const sourceSupports=source.filter(x=>x.table==='supports').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   const sourceMaintenance=source.filter(x=>x.table==='machine_maintenance').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   const sourceRents=source.filter(x=>x.table==='rent_contracts').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   item($('analysisList'),`Ayrı kayıtlar (işlem toplamına EKLENMEDİ): ${sourceSupports.length} destek, ${sourceMaintenance.length} bakım, ${sourceRents.length} icar sözleşmesi.`);
   item($('analysisList'),'ÖNEMLİ: Bu rapor kaynak işlemleri karşılaştırır; stok alışları ikinci kez gider yazılmaz. Kesin net kâr, tam FIFO ve tahakkuk/ödeme mutabakatı henüz doğrulanmadı.');
 }

}
for(const [formId,store] of extraForms){$(formId).onsubmit=async e=>{e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));x.id=uid();for(const key of ['quantity','unit_price','amount','cost','area_da','rate_per_da'])if(key in x){x[key]=number(x[key]);if(!Number.isFinite(x[key])||x[key]<0)throw Error('Negatif veya geçersiz sayı');}if(store==='harvests'||store==='sales'||store==='services')if(!(x.quantity>0))throw Error('Miktar pozitif olmalı');if(store==='rents'){if(!(x.area_da>0))throw Error('Alan pozitif olmalı');x.total_amount=Math.round(x.area_da*x.rate_per_da*100)/100}if(store==='sales'){const h=await all('harvests'),s=await all('sales');const stock=h.filter(y=>y.crop===x.crop).reduce((n,y)=>n+number(y.quantity),0)-s.filter(y=>y.crop===x.crop).reduce((n,y)=>n+number(y.quantity),0);if(x.quantity>stock+1e-8)throw Error(`Yetersiz ürün stoku: ${stock} kg`);x.total=Math.round(x.quantity*x.unit_price*100)/100}if(store==='services')x.amount=Math.round(x.quantity*x.unit_price*100)/100;if(store==='rentPayments'){const r=(await all('rents')).find(y=>y.id===x.rent_id);if(!r)throw Error('İcar seçin');const paid=(await all('rentPayments')).filter(y=>y.rent_id===x.rent_id).reduce((n,y)=>n+number(y.amount),0);if(x.amount<=0||x.amount>r.total_amount-paid+0.001)throw Error('Ödeme kalan borcu aşamaz')}await put(store,x);e.target.reset();for(const d of e.target.querySelectorAll('input[type=date]'))d.value=localDate();await render();await renderExtended()}catch(err){alert(err.message)}}}
$('seasonFilter').onchange=renderExtended;
for(const d of document.querySelectorAll('input[type=date]'))if(!d.value)d.value=localDate();
const originalRender=render;render=async function(){await originalRender();await renderExtended()};
renderExtended().catch(console.error);
