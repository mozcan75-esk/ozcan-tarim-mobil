 'use strict';
const number=x=>Number(x||0), uid=()=>crypto.randomUUID();
const escapeText=x=>String(x??'');
const extraForms=[['harvestForm','harvests'],['saleForm','sales'],['rentForm','rents'],['rentPaymentForm','rentPayments'],['supportForm','supports'],['maintenanceForm','maintenance'],['serviceForm','services']];
async function renderExtended(){
 const [parcels,harvests,sales,rents,payments,supports,maintenance,services,ops,moves,inputs]=await Promise.all(['parcels','harvests','sales','rents','rentPayments','supports','maintenance','services','operations','stockMoves','inputs'].map(all));
 for(const sel of document.querySelectorAll('.extraParcel')){const val=sel.value;sel.replaceChildren();for(const x of parcels)sel.add(new Option(`${x.name} (${x.code})`,x.code));sel.value=val||sel.options[0]?.value||''}
 const crops=[...new Set(harvests.map(x=>x.crop))].sort(),sel=$('cropSelect'),old=sel.value;sel.replaceChildren();for(const crop of crops)sel.add(new Option(crop,crop));sel.value=old||sel.options[0]?.value||'';
 $('cropList').replaceChildren();for(const crop of crops){const total=harvests.filter(x=>x.crop===crop).reduce((n,x)=>n+number(x.quantity),0)-sales.filter(x=>x.crop===crop).reduce((n,x)=>n+number(x.quantity),0);item($('cropList'),`${crop}: ${total.toLocaleString('tr-TR')} kg stok`)}
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
for(const [formId,store] of extraForms){$(formId).onsubmit=async e=>{e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));x.id=uid();for(const key of ['quantity','unit_price','amount','cost','area_da','rate_per_da'])if(key in x){x[key]=number(x[key]);if(!Number.isFinite(x[key])||x[key]<0)throw Error('Negatif veya geçersiz sayı');}if(store==='harvests'||store==='sales'||store==='services')if(!(x.quantity>0))throw Error('Miktar pozitif olmalı');if(store==='rents'){if(!(x.area_da>0))throw Error('Alan pozitif olmalı');x.total_amount=Math.round(x.area_da*x.rate_per_da*100)/100}if(store==='sales'){const h=await all('harvests'),s=await all('sales');const stock=h.filter(y=>y.crop===x.crop).reduce((n,y)=>n+number(y.quantity),0)-s.filter(y=>y.crop===x.crop).reduce((n,y)=>n+number(y.quantity),0);if(x.quantity>stock+1e-8)throw Error(`Yetersiz ürün stoku: ${stock} kg`);x.total=Math.round(x.quantity*x.unit_price*100)/100}if(store==='supports'){if(!(x.amount>0))throw Error('Destek tutarı sıfırdan büyük olmalı');x.amount=Math.round(x.amount*100)/100;x.payment_date=x.date;x.crop=/arpa/i.test(x.description+' '+x.support_type)?'Arpa':'';if(x.crop==='Arpa'&&!/tohum/i.test(x.description+' '+x.support_type))throw Error('Arpa tohumu desteği açıklamasını belirtin');}if(store==='services')x.amount=Math.round(x.quantity*x.unit_price*100)/100;if(store==='rentPayments'){const r=(await all('rents')).find(y=>String(y.id)===String(x.rent_id)&&!number(y.is_cancelled));if(!r)throw Error('Geçerli icar sözleşmesi seçin');const paid=(await all('rentPayments')).filter(y=>String(y.rent_id)===String(x.rent_id)&&!number(y.is_cancelled)).reduce((n,y)=>n+number(y.amount),0);const remaining=Math.round((number(r.total_amount)-paid)*100)/100;if(!(x.amount>0)||Math.round(x.amount*100)/100>remaining)throw Error('Ödeme kalan borcu aşamaz: '+money(remaining)+' ₺');x.amount=Math.round(x.amount*100)/100;x.season=r.season;x.parcel_code=r.parcel_code;x.payment_date=x.date;}await put(store,x);e.target.reset();for(const d of e.target.querySelectorAll('input[type=date]'))d.value=localDate();await render();await renderExtended()}catch(err){alert(err.message)}}}
$('seasonFilter').onchange=renderExtended;
for(const d of document.querySelectorAll('input[type=date]'))if(!d.value)d.value=localDate();
const originalRender=render;render=async function(){await originalRender();await renderExtended()};
renderExtended().catch(console.error);
