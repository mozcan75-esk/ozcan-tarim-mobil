 'use strict';
const number=x=>Number(x||0), uid=()=>crypto.randomUUID();
const escapeText=x=>String(x??'');
// V3.0.9: Ürün deposu için hasat partisi bazında FIFO tahsis (parsel geliri).
const cropKey=x=>String(x||'').trim().toLocaleLowerCase('tr-TR');
function allocateCropSale(harvests,sales,crop,quantity,date,season){
 const key=cropKey(crop), lots=harvests.filter(h=>cropKey(h.crop)===key&&h.season===season&&!number(h.is_cancelled)&&String(h.date||'')<=date).sort((a,b)=>String(a.date).localeCompare(String(b.date))||String(a.id).localeCompare(String(b.id)));
 const used=new Map();
 for(const sale of sales.filter(x=>cropKey(x.crop)===key&&x.season===season&&!number(x.is_cancelled)&&String(x.date||'')<=date)){
   if(Array.isArray(sale.allocations)&&sale.allocations.length){for(const a of sale.allocations)used.set(String(a.harvest_id),(used.get(String(a.harvest_id))||0)+number(a.quantity));}
   else { // Eski satışlar: parseli bilinmese de stoğu tüketir.
     let pending=number(sale.quantity);
     for(const h of lots){const left=Math.max(0,number(h.quantity)-(used.get(String(h.id))||0));const take=Math.min(left,pending);used.set(String(h.id),(used.get(String(h.id))||0)+take);pending-=take;if(pending<=1e-7)break;}
   }
 }
 let remaining=quantity;const allocations=[];
 for(const h of lots){const left=Math.max(0,number(h.quantity)-(used.get(String(h.id))||0));const take=Math.min(left,remaining);if(take>1e-7){allocations.push({harvest_id:String(h.id),parcel_code:h.parcel_code,quantity:take});remaining-=take;}if(remaining<=1e-7)break;}
 if(remaining>1e-7)throw Error('Bu tarihte ve sezonda yeterli ürün stoku yok. Eksik: '+remaining.toLocaleString('tr-TR')+' kg');
 return allocations;
}
const extraForms=[['harvestForm','harvests'],['saleForm','sales'],['rentForm','rents'],['rentPaymentForm','rentPayments'],['supportForm','supports'],['maintenanceForm','maintenance'],['serviceForm','services']];
async function renderExtended(){
 const [parcels,harvests,sales,rents,payments,supports,maintenance,services,ops,moves,inputs]=await Promise.all(['parcels','harvests','sales','rents','rentPayments','supports','maintenance','services','operations','stockMoves','inputs'].map(all));
 for(const sel of document.querySelectorAll('.extraParcel')){const val=sel.value;sel.replaceChildren();for(const x of parcels)sel.add(new Option(`${x.name} (${x.code})`,x.code));sel.value=val||sel.options[0]?.value||''}
 const crops=[...new Set(harvests.filter(x=>!number(x.is_cancelled)).map(x=>x.crop))].sort(),sel=$('cropSelect'),old=sel.value;sel.replaceChildren();for(const crop of crops)sel.add(new Option(crop,crop));sel.value=old||sel.options[0]?.value||'';
 $('cropList').replaceChildren();for(const crop of crops){const total=harvests.filter(x=>cropKey(x.crop)===cropKey(crop)&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.quantity),0)-sales.filter(x=>cropKey(x.crop)===cropKey(crop)&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.quantity),0);item($('cropList'),`${crop}: ${total.toLocaleString('tr-TR')} kg stok`)}
 const rsel=$('rentSelect'),rv=rsel.value;rsel.replaceChildren();$('rentList').replaceChildren();for(const r of rents){const paid=payments.filter(x=>String(x.rent_id)===String(r.id)&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.amount),0);rsel.add(new Option(`${r.landlord} / ${r.parcel_code} / ${r.season}`,r.id));item($('rentList'),`${r.season} · ${r.parcel_code} · ${r.landlord} · İcar: ${money(r.total_amount)} ₺ · Ödenen: ${money(paid)} ₺ · Kalan: ${money(number(r.total_amount)-paid)} ₺`)}rsel.value=rv||rsel.options[0]?.value||'';
 $('supportList').replaceChildren();for(const x of supports)item($('supportList'),`Destek · ${x.season} · ${x.support_type}: ${money(x.amount)} ₺ · ${x.description||''}`);for(const x of maintenance)item($('supportList'),`Bakım · ${x.season} · ${x.machine}: ${money(x.cost)} ₺`);
 $('serviceList').replaceChildren();for(const x of services)item($('serviceList'),`${x.season} · ${x.parcel_code} · ${x.kind} · ${money(x.amount)} ₺`);
 const seasons=[...new Set([...ops,...harvests,...rents,...supports,...maintenance,...services].map(x=>x.season).filter(Boolean))].sort().reverse(),sf=$('seasonFilter'),sv=sf.value;sf.replaceChildren();for(const x of seasons)sf.add(new Option(x,x));sf.value=sv||sf.options[0]?.value||'';
 const source=await all('sourceRecords');
 const areas=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record);
 const activities=source.filter(x=>x.table==='field_activities').map(x=>x.record);
 const season=sf.value, filter=x=>x.season===season;
 const selectedActivities=activities.filter(filter);
 const selectedAreas=areas.filter(filter);
 $('analysisList').replaceChildren();
 const profitability=document.getElementById('parcelProfitability');if(profitability)profitability.replaceChildren();
 if(season){
   item($('analysisList'),`Sezon: ${season}`);
   item($('analysisList'),`Bilgisayardan korunan tarla faaliyetleri: ${selectedActivities.length} kayıt`);
   item($('analysisList'),`Ayrı işlenen alan kaydı: ${selectedAreas.length} parsel`);
   for(const a of selectedAreas.sort((a,b)=>a.parcel_code.localeCompare(b.parcel_code)))
     item($('analysisList'),`${a.parcel_code}: işlenen ${number(a.worked_area_da).toLocaleString('tr-TR')} da · icar ${number(a.leased_area_da).toLocaleString('tr-TR')} da`);
     // Salt okunur mutabakat: bilgisayardan gelen özgün kayıtlar esas alınır.
   const sourceOps=source.filter(x=>x.table==='operations').map(x=>x.record).filter(x=>!Number(x.is_cancelled)&&x.season===season);
   const mobileOps=ops.filter(x=>x.season===season&&!number(x.is_cancelled));
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
   // V3.0.6: Salt okunur, işlem giderlerini iki kez saymayan parsel maliyet dökümü.
   const profitability=document.getElementById('parcelProfitability');
   if(profitability){
     profitability.replaceChildren();
     const heading=document.createElement('h3');heading.textContent='V3.0.6 · Parsel maliyet analizi';profitability.append(heading);
     const note=document.createElement('p');note.textContent='Yalnızca kayıtlı işlemler üzerinden maliyet analizi. Hasat satış geliri değildir; icar, destek, bakım ve FIFO denetim farkı bu toplamda yer almaz. Kesin net kâr hesaplanmaz.';profitability.append(note);
     const grouped=new Map();
     for(const op of sourceOps){if(!op.parcel_code)continue;const code=String(op.parcel_code);if(!grouped.has(code))grouped.set(code,[]);grouped.get(code).push(op)}
     const tbl=document.createElement('table');tbl.className='profit-table';
     const header=document.createElement('tr');for(const name of ['Parsel','Alan (da)','Tohum (₺)','Gübre (₺)','Motorin (₺)','Diğer (₺)','Toplam gider (₺)','Gider/da (₺)']){const th=document.createElement('th');th.textContent=name;header.append(th)}tbl.append(header);
     let totalCost=0, areaSum=0, unknownAreas=0;
     for(const code of [...grouped.keys()].sort()){
       const rows=grouped.get(code), parcel=parcels.find(x=>x.code===code), a=selectedAreas.find(x=>x.parcel_code===code);
       const da=a?number(a.worked_area_da):number(parcel?.area_m2)/1000;
       if(!(da>0))unknownAreas++;else areaSum+=da;
       const buckets={seed:0,fertilizer:0,diesel:0,other:0};
       for(const op of rows.filter(x=>x.direction==='Gider')){
         const name=String(op.category||'').toLocaleLowerCase('tr-TR');
         const key=name.includes('tohum')?'seed':name.includes('gübre')?'fertilizer':name.includes('motorin')||name.includes('mazot')?'diesel':'other';buckets[key]+=number(op.amount);
       }
       const cost=Object.values(buckets).reduce((a,b)=>a+b,0);totalCost+=cost;
       const tr=document.createElement('tr');
       const values=[code,da>0?da.toLocaleString('tr-TR',{maximumFractionDigits:3})+(a?'':'*'):'—',money(buckets.seed),money(buckets.fertilizer),money(buckets.diesel),money(buckets.other),money(cost),da>0?money(cost/da):'—'];
       for(const v of values){const td=document.createElement('td');td.textContent=v;tr.append(td)}tbl.append(tr);
     }
     const scroller=document.createElement('div');scroller.className='profit-scroll';scroller.append(tbl);profitability.append(scroller);
     const summary=document.createElement('p');summary.textContent=`Parsellere bağlı kayıtlı gider: ${money(totalCost)} ₺ · Kaynak işlem toplamı: ${money(pcExpense)} ₺ · Parselsiz/ayrıştırılmamış fark: ${money(pcExpense-totalCost)} ₺. * Sezon işlenen alan kaydı olmayan parsellerde tapu alanı geçici olarak kullanıldı. ${unknownAreas} parselde alan bulunamadı.`;profitability.append(summary);
     const extra=document.createElement('p');extra.textContent=`Ayrı izlenen tutarlar: destek ${money(supports.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.amount),0))} ₺; icar ${money(rents.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.total_amount),0))} ₺; bakım ${money(maintenance.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.cost),0))} ₺. Bu tutarlar parsel giderine eklenmedi.`;profitability.append(extra);
     const seasonHarvest=harvests.filter(x=>x.season===season),seasonSales=sales.filter(x=>x.season===season);
     const harvested=seasonHarvest.reduce((n,x)=>n+number(x.quantity),0),sold=seasonSales.reduce((n,x)=>n+number(x.quantity),0),revenue=seasonSales.reduce((n,x)=>n+number(x.total),0);
     const crop=document.createElement('p');crop.textContent=`Hasat: ${harvested.toLocaleString('tr-TR')} kg · Satış: ${sold.toLocaleString('tr-TR')} kg · Satış tutarı: ${money(revenue)} ₺. Satış kaydında parsel bağı bulunmadığı için gelir parsele dağıtılmaz; ürün stoku küresel olarak izlenir.`;profitability.append(crop);
   }

   // V3.0.9: hasat lotlarından satışa tahsis edilmiş parsel gelirleri.
   const p309=document.getElementById('parcelProfitability');
   if(p309){
     const section=document.createElement('section');const heading=document.createElement('h3');heading.textContent='V3.0.9 · Hasat, satış ve parsel geliri';section.append(heading);
     const text=document.createElement('p');text.textContent='Hasat depoya girer, gelir sayılmaz. Yeni satışlar aynı sezon ve satış tarihine kadar hasat edilmiş ürünlerden FIFO ile karşılanır. Önceki sürümlerin tahsissiz satışları parsel gelirine dağıtılmaz.';section.append(text);
     const sh=harvests.filter(x=>x.season===season&&!number(x.is_cancelled)),ss=sales.filter(x=>x.season===season&&!number(x.is_cancelled));
     const byParcel=new Map();let unallocated=0;
     for(const sale of ss){const total=number(sale.total);if(!Array.isArray(sale.allocations)||!sale.allocations.length){unallocated+=total;continue;}const totalKg=sale.allocations.reduce((n,a)=>n+number(a.quantity),0);if(!(totalKg>0)){unallocated+=total;continue;}let allocated=0;for(let i=0;i<sale.allocations.length;i++){const a=sale.allocations[i],revenue=i===sale.allocations.length-1?total-allocated:Math.round(total*number(a.quantity)/totalKg*100)/100;allocated+=revenue;const key=String(a.parcel_code||'');byParcel.set(key,(byParcel.get(key)||0)+revenue);}}
     const table=document.createElement('table');table.className='profit-table';const head=document.createElement('tr');for(const n of ['Parsel','Hasat (kg)','Satış geliri (₺)','Kayıtlı işlem gideri (₺)','İşlem bazlı fark (₺)']){const th=document.createElement('th');th.textContent=n;head.append(th)}table.append(head);
     const keys=[...new Set([...sh.map(x=>x.parcel_code),...byParcel.keys()])].filter(Boolean).sort();
     for(const code of keys){const kg=sh.filter(x=>x.parcel_code===code).reduce((n,x)=>n+number(x.quantity),0),income=byParcel.get(code)||0,cost=sourceOps.filter(x=>x.parcel_code===code&&x.direction==='Gider').reduce((n,x)=>n+number(x.amount),0);const row=document.createElement('tr');for(const val of [code,kg.toLocaleString('tr-TR'),money(income),money(cost),money(income-cost)]){const td=document.createElement('td');td.textContent=val;row.append(td)}table.append(row)}
     const scroll=document.createElement('div');scroll.className='profit-scroll';scroll.append(table);section.append(scroll);
     const gross=ss.reduce((n,x)=>n+number(x.total),0),stockKg=sh.reduce((n,x)=>n+number(x.quantity),0)-ss.reduce((n,x)=>n+number(x.quantity),0);
     const summary=document.createElement('p');summary.textContent=`Sezon hasadı: ${sh.reduce((n,x)=>n+number(x.quantity),0).toLocaleString('tr-TR')} kg · Satış: ${ss.reduce((n,x)=>n+number(x.quantity),0).toLocaleString('tr-TR')} kg · Kalan ürün: ${stockKg.toLocaleString('tr-TR')} kg · Satış geliri: ${money(gross)} ₺ · Parsele tahsis edilemeyen eski satış: ${money(unallocated)} ₺.`;section.append(summary);
     const caveat=document.createElement('p');caveat.textContent='İşlem bazlı fark kesin net kâr değildir. İcar, destek, bakım, hasat hizmetleri ve geçmiş satış tahsisleri ayrıca değerlendirilmelidir.';section.append(caveat);
     p309.append(section);
   }
   // V3.0.7: salt-okunur icar tahakkuku, açık borç ve arpa tohum desteği dağıtımı.
   const p307=document.getElementById('parcelProfitability');
   if(p307){
     const block=document.createElement('section');
     const title=document.createElement('h3');title.textContent='V3.0.7 · İcar, borç ve arpa tohum desteği';block.append(title);
     const note=document.createElement('p');
     note.textContent='Bu tablo denetim amaçlıdır. Kaynak işlem giderleri değiştirilmez. Destek yalnızca arpa ekim alanına göre dağıtılır; destek sonrası maliyet bir gösterge olup destek ayrıca ikinci kez gelir yazılmaz.';
     block.append(note);
     const activeRents=rents.filter(x=>x.season===season&&!number(x.is_cancelled));
     const activeSupports=supports.filter(x=>x.season===season&&!number(x.is_cancelled));
     const rentByParcel=new Map(), paidByParcel=new Map(), duplicates=new Map();
     for(const r of activeRents){
       const code=String(r.parcel_code||'');
       rentByParcel.set(code,(rentByParcel.get(code)||0)+number(r.total_amount));
       const paid=payments.filter(x=>String(x.rent_id)===String(r.id)&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.amount),0);
       paidByParcel.set(code,(paidByParcel.get(code)||0)+paid);
     }
     // Aynı gider işlemler tablosunda varsa ikinci kez tahakkuk ettirme.
     for(const op of sourceOps.filter(x=>x.direction==='Gider')){
       if(/icar|kira/i.test([op.category,op.op_type,op.item].join(' '))){
         const code=String(op.parcel_code||'');
         duplicates.set(code,(duplicates.get(code)||0)+number(op.amount));
       }
     }
     const barleyArea=new Map();
     for(const op of sourceOps.filter(x=>x.direction==='Gider')){
       if(!/arpa/i.test(String(op.item||''))||!/tohum/i.test(String(op.category||'')))continue;
       const code=String(op.parcel_code||'');
       const sowing=selectedActivities.filter(x=>x.parcel_code===code&&/ekim/i.test(String(x.activity_type||'')));
       const a=sowing.length?Math.max(...sowing.map(x=>number(x.area_da))):0;
       if(a>0)barleyArea.set(code,a);
     }
     const totalBarleyArea=[...barleyArea.values()].reduce((n,x)=>n+x,0);
     const barleySupports=activeSupports.filter(x=>/arpa/i.test([x.crop,x.description,x.support_type].join(' '))&&/tohum/i.test([x.description,x.support_type].join(' ')));
     const supportAmount=barleySupports.reduce((n,x)=>n+number(x.amount),0);
     const sourceCosts=new Map();
     for(const op of sourceOps.filter(x=>x.direction==='Gider'&&x.parcel_code)){
       const code=String(op.parcel_code);sourceCosts.set(code,(sourceCosts.get(code)||0)+number(op.amount));
     }
     const codes=[...new Set([...sourceCosts.keys(),...rentByParcel.keys(),...barleyArea.keys()])].sort();
     const table=document.createElement('table');table.className='profit-table';
     const head=document.createElement('tr');
     for(const name of ['Parsel','Arpa ekim (da)','Kayıtlı gider (₺)','İcar tahakkuku (₺)','İcar ödenen (₺)','Açık borç (₺)','Destek payı (₺)','Destek sonrası maliyet (₺)']){
       const th=document.createElement('th');th.textContent=name;head.append(th);
     }table.append(head);
     let allocated=0,rentAddition=0,openDebt=0,duplicated=0;
     for(let i=0;i<codes.length;i++){
       const code=codes[i], base=sourceCosts.get(code)||0, rent=rentByParcel.get(code)||0;
       const already=Math.min(rent,duplicates.get(code)||0);
       const addition=Math.max(0,rent-already);
       const paid=paidByParcel.get(code)||0;
       const debt=Math.max(0,rent-paid);
       const lastBarley=[...barleyArea.keys()].sort().at(-1);const support=totalBarleyArea>0&&barleyArea.has(code)?(code===lastBarley?Math.round((supportAmount-allocated)*100)/100:Math.round(supportAmount*(barleyArea.get(code)||0)/totalBarleyArea*100)/100):0;
       allocated+=support;rentAddition+=addition;openDebt+=debt;duplicated+=already;
       const row=document.createElement('tr');
       const values=[code,barleyArea.has(code)?number(barleyArea.get(code)).toLocaleString('tr-TR',{maximumFractionDigits:3}):'—',money(base),money(addition),money(paid),money(debt),money(support),money(base+addition-support)];
       for(const v of values){const td=document.createElement('td');td.textContent=v;row.append(td)}table.append(row);
     }
     // Kuruş yuvarlama farkı raporda görülebilir; hiçbir kayıt değiştirilmez.
     const wrap=document.createElement('div');wrap.className='profit-scroll';wrap.append(table);block.append(wrap);
     const summary=document.createElement('p');
     summary.textContent=`Kayıtlı işlem gideri: ${money(pcExpense)} ₺ · İcar tahakkuk ilavesi: ${money(rentAddition)} ₺ · Açık icar borcu: ${money(openDebt)} ₺ · Arpa ekim alanı: ${totalBarleyArea.toLocaleString('tr-TR',{maximumFractionDigits:3})} da · Dağıtılan destek: ${money(allocated)} ₺ / ${money(supportAmount)} ₺ · Destek sonrası maliyet: ${money(pcExpense+rentAddition-allocated)} ₺.`;
     block.append(summary);const v308=document.createElement('p');v308.textContent='V3.0.8: İcar ödemeleri açık borçtan düşülür, yeni gider oluşturulmaz. Yeni arpa tohumu desteği kayıtları ekim alanına göre rapora dağıtılır. Hasat depoya, satış yalnız mevcut ürün stokundan kaydedilir; net kâr kesinleşmeden önce kaynak eşleşmesi gerekir.';block.append(v308);
     const warning=document.createElement('p');
     warning.textContent=`İcar için işlemlerde bulunan olası mükerrer gider: ${money(duplicated)} ₺. İcar ödemesi gideri tekrar artırmaz. Bakım giderleri henüz dağıtılmadı. Destek tutarı yalnızca arpa tohumu desteği olarak tanımlanan kayıtlardan alınır.`;
     block.append(warning);
     if(supportAmount>0&&!totalBarleyArea){const w=document.createElement('p');w.textContent='UYARI: Arpa ekim alanı doğrulanamadığı için destek dağıtılmadı.';block.append(w)}
     p307.append(block);
   }

   // V3.1.0: Salt-okunur konsolide parsel performansı. Veri kayıtlarını değiştirmez.
   const p310=document.getElementById('parcelProfitability');
   if(p310){
     const sec=document.createElement('section');
     const h=document.createElement('h3');h.textContent='V3.1.0 · Konsolide parsel maliyeti ve gerçekleşen satış';sec.append(h);
     const n=document.createElement('p');n.textContent='Bakım, sezonluk işlenen alan oranında dağıtılır. Sezon alan kaydı yoksa tarla faaliyeti alanı geçici olarak kullanılır ve işaretlenir; tapu alanı bakım dağıtımında kullanılmaz. Hasat satış geliri değildir. Kâr yalnızca gerçekleşen satışlara dayalı dönemsel sonuçtur; satılmamış ürünlerin değeri dahil değildir.';sec.append(n);
     const codes=[...new Set([...parcels.map(x=>x.code),...sourceOps.map(x=>x.parcel_code).filter(Boolean)])].sort();
     const areaMap=new Map(),provisional=new Set();
     for(const code of codes){
       const explicit=selectedAreas.find(x=>x.parcel_code===code&&number(x.worked_area_da)>0);
       if(explicit){areaMap.set(code,number(explicit.worked_area_da));continue}
       const candidates=selectedActivities.filter(x=>x.parcel_code===code&&number(x.area_da)>0).map(x=>number(x.area_da));
       if(candidates.length){areaMap.set(code,Math.max(...candidates));provisional.add(code)}
     }
     const areaTotal=[...areaMap.values()].reduce((a,b)=>a+b,0);
     const maintenanceTotal=maintenance.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((a,x)=>a+number(x.cost),0);
     const rentsSeason=rents.filter(x=>x.season===season&&!number(x.is_cancelled));
     const supportsSeason=supports.filter(x=>x.season===season&&!number(x.is_cancelled));
     const barleySupports=supportsSeason.filter(x=>/arpa/i.test([x.crop,x.description,x.support_type].join(' '))&&/tohum/i.test([x.description,x.support_type].join(' ')));
     const supportTotal=barleySupports.reduce((a,x)=>a+number(x.amount),0);
     const barleyMap=new Map();
     for(const op of sourceOps.filter(x=>x.direction==='Gider'&&/arpa/i.test(String(x.item||''))&&/tohum/i.test(String(x.category||'')))){
       const code=String(op.parcel_code||'');if(code&&areaMap.has(code))barleyMap.set(code,areaMap.get(code));
     }
     const barleyTotal=[...barleyMap.values()].reduce((a,b)=>a+b,0);
     const incomeByParcel=new Map(),harvestByParcel=new Map(),soldByParcel=new Map();let untiedIncome=0;
     for(const x of harvests.filter(x=>x.season===season&&!number(x.is_cancelled))){const c=String(x.parcel_code||'');harvestByParcel.set(c,(harvestByParcel.get(c)||0)+number(x.quantity))}
     for(const sale of sales.filter(x=>x.season===season&&!number(x.is_cancelled))){
       const alloc=Array.isArray(sale.allocations)?sale.allocations:[],kg=alloc.reduce((a,x)=>a+number(x.quantity),0),total=number(sale.total);
       if(!(kg>0)){untiedIncome+=total;continue}
       let assigned=0;
       for(let i=0;i<alloc.length;i++){const x=alloc[i],c=String(x.parcel_code||''),value=i===alloc.length-1?Math.round((total-assigned)*100)/100:Math.round(total*number(x.quantity)/kg*100)/100;assigned+=value;
         if(!c){untiedIncome+=value;continue}
         incomeByParcel.set(c,(incomeByParcel.get(c)||0)+value);soldByParcel.set(c,(soldByParcel.get(c)||0)+number(x.quantity));
       }
     }
     const round=x=>Math.round((x+Number.EPSILON)*100)/100;
     const maintainCodes=[...areaMap.keys()].sort(),barleyCodes=[...barleyMap.keys()].sort();
     let maintenanceAssigned=0,supportAssigned=0,baseSum=0,rentSum=0,profitSum=0;
     const table=document.createElement('table');table.className='profit-table';const trh=document.createElement('tr');
     for(const label of ['Parsel','İşlenen alan (da)','İşlem gideri','İcar ilavesi','Bakım payı','Arpa destek payı','Destek sonrası maliyet','Hasat (kg)','Satış (kg)','Satış geliri','Dönemsel sonuç','Sonuç/da']){const th=document.createElement('th');th.textContent=label;trh.append(th)}table.append(trh);
     for(const code of codes){
       const base=sourceOps.filter(x=>x.parcel_code===code&&x.direction==='Gider').reduce((a,x)=>a+number(x.amount),0);baseSum+=base;
       const rent=rentsSeason.filter(x=>x.parcel_code===code).reduce((a,x)=>a+number(x.total_amount),0);
       const existingRent=sourceOps.filter(x=>x.parcel_code===code&&x.direction==='Gider'&&/icar|kira/i.test([x.category,x.op_type,x.item].join(' '))).reduce((a,x)=>a+number(x.amount),0);
       const rentAdd=Math.max(0,round(rent-existingRent));rentSum+=rentAdd;
       const area=areaMap.get(code)||0;
       const maintenanceShare=areaTotal>0&&areaMap.has(code)?(code===maintainCodes.at(-1)?round(maintenanceTotal-maintenanceAssigned):round(maintenanceTotal*area/areaTotal)):0;maintenanceAssigned+=maintenanceShare;
       const supportShare=barleyTotal>0&&barleyMap.has(code)?(code===barleyCodes.at(-1)?round(supportTotal-supportAssigned):round(supportTotal*area/barleyTotal)):0;supportAssigned+=supportShare;
       const cost=base+rentAdd+maintenanceShare-supportShare,revenue=incomeByParcel.get(code)||0,result=revenue-cost;profitSum+=result;
       const row=document.createElement('tr');for(const value of [code,area?area.toLocaleString('tr-TR',{maximumFractionDigits:3})+(provisional.has(code)?'*':''):'—',money(base),money(rentAdd),money(maintenanceShare),money(supportShare),money(cost),money(harvestByParcel.get(code)||0),money(soldByParcel.get(code)||0),money(revenue),money(result),area?money(result/area):'—']){const td=document.createElement('td');td.textContent=value;row.append(td)}table.append(row);
     }
     const wrap=document.createElement('div');wrap.className='profit-scroll';wrap.append(table);sec.append(wrap);
     const totals=document.createElement('p');totals.textContent=`İşlem gideri: ${money(baseSum)} ₺ · İcar ilavesi: ${money(rentSum)} ₺ · Bakım dağıtımı: ${money(maintenanceAssigned)} / ${money(maintenanceTotal)} ₺ · Arpa desteği dağıtımı: ${money(supportAssigned)} / ${money(supportTotal)} ₺ · Gerçekleşen satışlardan dönemsel sonuç: ${money(profitSum)} ₺ · Parsellere bağlanamayan satış geliri: ${money(untiedIncome)} ₺.`;sec.append(totals);
     const warning=document.createElement('p');warning.textContent=`Alanı tarla faaliyetinden geçici alınan ${provisional.size} parsel (*) bulunuyor. Alanı olmayan parseller bakım payı alamaz. ${!areaTotal?'UYARI: Bakım dağıtılamadı. ':''}${supportTotal>0&&!barleyTotal?'UYARI: Arpa desteği dağıtılamadı. ':''}Satılmayan ürünler ve doğrulanmamış genel giderler dahil olmadığından bu sonuç kesin sezon net kârı değildir. Gider ve destekleri tekrar muhasebeleştirmez.`;sec.append(warning);
     p310.append(sec);
   }
   const sourceSupports=source.filter(x=>x.table==='supports').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   const sourceMaintenance=source.filter(x=>x.table==='machine_maintenance').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   const sourceRents=source.filter(x=>x.table==='rent_contracts').map(x=>x.record).filter(x=>x.season===season&&!Number(x.is_cancelled));
   item($('analysisList'),`Ayrı kayıtlar (işlem toplamına EKLENMEDİ): ${sourceSupports.length} destek, ${sourceMaintenance.length} bakım, ${sourceRents.length} icar sözleşmesi.`);
   // Salt okunur FIFO mutabakatı: kaynak stok hareketlerinin kendi tarih ve alış sırasına göre hesaplanır.
   const byInput=new Map();for(const m of moves.filter(m=>String(m.id).startsWith('pc-'))){if(!byInput.has(m.input_id))byInput.set(m.input_id,[]);byInput.get(m.input_id).push(m)}
   let fifoUseCost=0, recordedUseCost=0, matched=0, mismatch=0, missing=0;const fifoByInput=new Map();
   for(const [inputId,entries] of byInput){
     const lots=[];
     const sorted=[...entries].sort((a,b)=>String(a.date||'').localeCompare(String(b.date||''))||(a.kind==='purchase'?-1:1)-(b.kind==='purchase'?-1:1)||Number(a.source_id||0)-Number(b.source_id||0)||String(a.id).localeCompare(String(b.id)));
     for(const m of sorted){
       if(m.kind==='purchase'){lots.push({left:number(m.quantity),price:number(m.unit_price)});continue}
       if(m.kind!=='use'||m.season!==season)continue;
       let q=number(m.quantity),cost=0;
       for(const lot of lots){const taken=Math.max(0,Math.min(q,lot.left));lot.left-=taken;q-=taken;cost+=taken*lot.price;if(q<1e-8)break}
       if(q>1e-6){missing++;continue}
       fifoUseCost+=cost;recordedUseCost+=number(m.total);matched++;
       if(Math.abs(cost-number(m.total))>0.02)mismatch++;
       const k=String(inputId),stat=fifoByInput.get(k)||{count:0,diffCount:0,recorded:0,recomputed:0};stat.count++;stat.recorded+=number(m.total);stat.recomputed+=cost;if(Math.abs(cost-number(m.total))>0.02)stat.diffCount++;fifoByInput.set(k,stat);
     }
   }
   item($('analysisList'),`FIFO kaynak hareket kontrolü: ${matched} kullanım hesaplandı · ${missing} yetersiz/tarihi uyumsuz kullanım · ${mismatch} maliyet farkı`);
   item($('analysisList'),`FIFO hesaplanan kullanım maliyeti: ${money(fifoUseCost)} ₺ · aktarılan kullanım tutarı: ${money(recordedUseCost)} ₺ (yalnızca hesaplanabilen hareketler)`);
   item($('analysisList'),`V3.0.5 · FIFO denetim farkı: ${money(fifoUseCost-recordedUseCost)} ₺. Bu fark geçmiş işlem giderlerine EKLENMEZ; kayıtlı maliyet korunur.`);
   for(const [inputId,stat] of fifoByInput){const input=inputs.find(x=>String(x.id)===inputId);item($('analysisList'),`${input?.name||inputId}: ${stat.count} kullanım · ${stat.diffCount} farklı · kayıtlı ${money(stat.recorded)} ₺ · yeniden FIFO ${money(stat.recomputed)} ₺ · fark ${money(stat.recomputed-stat.recorded)} ₺`)}
   item($('analysisList'),'Bilgisayar FIFO kuralı: alışlar tarih ve kayıt ID sırasıyla, tüketimler tarih ve kayıt ID sırasıyla işlenir. Geçmiş tutarlar salt okunur korunur. Yeni tarihli kullanımlar yalnızca mevcut alımlardan hesaplanır.');
   item($('analysisList'),'UYARI: FIFO hareket maliyetleri işlem giderlerine ayrıca EKLENMEDİ. Stok hareketleri ile işlemler arasındaki birebir bağ ve bilgisayar FIFO kuralı doğrulanmadan kesin kâr hesaplanamaz.');
   const income=sourceOps.filter(x=>x.direction==='Gelir').reduce((n,x)=>n+number(x.amount),0);
   const expenses=sourceOps.filter(x=>x.direction==='Gider').reduce((n,x)=>n+number(x.amount),0);
   const salesTotal=sales.filter(x=>x.season===season).reduce((n,x)=>n+number(x.total),0);
   const supportsTotal=supports.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.amount),0);
   const rentTotal=rents.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.total_amount),0);
   const maintenanceTotal=maintenance.filter(x=>x.season===season&&!number(x.is_cancelled)).reduce((n,x)=>n+number(x.cost),0);
   item($('analysisList'),`Ayrı kayıt kontrolü (işlem toplamına eklenmedi): satış ${money(salesTotal)} ₺ · destek ${money(supportsTotal)} ₺ · icar sözleşme bedeli ${money(rentTotal)} ₺ · bakım ${money(maintenanceTotal)} ₺`);
   item($('analysisList'),`Kaynak işlem bakiyesi (KESİN KÂR DEĞİL): ${money(income-expenses)} ₺. İcar tahakkuku, destek ve bakımın hangi gider/gelire dahil olduğu doğrulanmadan net kâr hesaplanmaz.`);
   item($('analysisList'),'ÖNEMLİ: Bu ekran salt okunur mutabakat raporudur. Bilgisayar veritabanını ve telefon kayıtlarını değiştirmez.');
 }

}
for(const [formId,store] of extraForms){$(formId).onsubmit=async e=>{e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));x.id=uid();for(const key of ['quantity','unit_price','amount','cost','area_da','rate_per_da'])if(key in x){x[key]=number(x[key]);if(!Number.isFinite(x[key])||x[key]<0)throw Error('Negatif veya geçersiz sayı');}if(store==='harvests'||store==='sales'||store==='services')if(!(x.quantity>0))throw Error('Miktar pozitif olmalı');if(store==='rents'){if(!(x.area_da>0))throw Error('Alan pozitif olmalı');x.total_amount=Math.round(x.area_da*x.rate_per_da*100)/100}if(store==='harvests'){x.crop=x.crop.trim();if(!x.crop)throw Error('Ürün adı gerekli');if(!(await all('parcels')).some(p=>p.code===x.parcel_code))throw Error('Geçerli parsel seçin')}if(store==='sales'){const h=await all('harvests'),s=await all('sales');x.allocations=allocateCropSale(h,s,x.crop,x.quantity,x.date,x.season);x.total=Math.round(x.quantity*x.unit_price*100)/100}if(store==='supports'){if(!(x.amount>0))throw Error('Destek tutarı sıfırdan büyük olmalı');x.amount=Math.round(x.amount*100)/100;x.payment_date=x.date;x.crop=/arpa/i.test(x.description+' '+x.support_type)?'Arpa':'';if(x.crop==='Arpa'&&!/tohum/i.test(x.description+' '+x.support_type))throw Error('Arpa tohumu desteği açıklamasını belirtin');}if(store==='services')x.amount=Math.round(x.quantity*x.unit_price*100)/100;if(store==='rentPayments'){const r=(await all('rents')).find(y=>String(y.id)===String(x.rent_id)&&!number(y.is_cancelled));if(!r)throw Error('Geçerli icar sözleşmesi seçin');const paid=(await all('rentPayments')).filter(y=>String(y.rent_id)===String(x.rent_id)&&!number(y.is_cancelled)).reduce((n,y)=>n+number(y.amount),0);const remaining=Math.round((number(r.total_amount)-paid)*100)/100;if(!(x.amount>0)||Math.round(x.amount*100)/100>remaining)throw Error('Ödeme kalan borcu aşamaz: '+money(remaining)+' ₺');x.amount=Math.round(x.amount*100)/100;x.season=r.season;x.parcel_code=r.parcel_code;x.payment_date=x.date;}await put(store,x);e.target.reset();for(const d of e.target.querySelectorAll('input[type=date]'))d.value=localDate();await render();await renderExtended()}catch(err){alert(err.message)}}}
$('seasonFilter').onchange=renderExtended;
for(const d of document.querySelectorAll('input[type=date]'))if(!d.value)d.value=localDate();
const originalRender=render;render=async function(){await originalRender();await renderExtended()};
renderExtended().catch(console.error);
