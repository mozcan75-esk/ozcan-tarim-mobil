 'use strict';
// V3.2.5: read-only parcel comparison. Does not post entries or double-count stock movements.
(()=>{
 const $=id=>document.getElementById(id),n=x=>Number(x||0),sk=x=>String(x||'').replace(/\D/g,''),active=x=>!n(x.is_cancelled);
 const fmt=x=>n(x).toLocaleString('tr-TR',{minimumFractionDigits:0,maximumFractionDigits:2});
 const report=$('profit325Table'),summary=$('profit325Summary'),seasonFilter=$('seasonFilter');if(!report||!seasonFilter)return;
 const sum=(xs,f)=>xs.reduce((a,x)=>a+n(f(x)),0);
 let version=0;
 async function update(){const v=++version,season=seasonFilter.value;if(!season){report.textContent='Sezon seçin.';return}
  const names=['parcels','operations','sourceRecords','harvests','sales','bales','baleSales','services','rents','maintenance'];
  const data=await Promise.all(names.map(all));if(v!==version)return;
  const [parcels,ops,source,harvests,sales,bales,baleSales,services,rents,maintenance]=data;
  const same=x=>active(x)&&sk(x.season)===sk(season);
  const areas=source.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).filter(same);
  const sourceOps=source.filter(x=>x.table==='operations').map(x=>x.record).filter(same);
  const mobileOps=ops.filter(same);
  const baseOps=sourceOps.concat(mobileOps.filter(x=>!String(x.id||'').startsWith('pc-op-')&&!sourceOps.some(y=>String(y.id)===String(x.id))));
  const hs=harvests.filter(same),ss=sales.filter(same),bs=bales.filter(same),bss=baleSales.filter(same),sv=services.filter(same),rs=rents.filter(same);
  const cropIncome=new Map(),cropSold=new Map();let unassigned=0;
  for(const sale of ss){const allocations=Array.isArray(sale.allocations)?sale.allocations:[],kg=sum(allocations,x=>x.quantity),total=n(sale.total);if(!kg){unassigned+=total;continue}
   for(const a of allocations){const code=String(a.parcel_code||'');if(!code){unassigned+=total*n(a.quantity)/kg;continue}cropIncome.set(code,(cropIncome.get(code)||0)+total*n(a.quantity)/kg);cropSold.set(code,(cropSold.get(code)||0)+n(a.quantity))}
  }
  const codes=[...new Set([...parcels.map(x=>x.code),...baseOps.map(x=>x.parcel_code),...hs.map(x=>x.parcel_code),...bs.map(x=>x.parcel_code),...bss.map(x=>x.parcel_code)].filter(Boolean))].sort();
  const table=document.createElement('table');table.className='profit-table';const header=document.createElement('tr');
  for(const label of ['Parsel','Alan (da)','Hasat (kg)','Ürün satış (kg)','Ürün geliri (₺)','Balya üretim','Balya satış','Balya kalan','Balya geliri (₺)','Kayıtlı işlem gideri (₺)','Hizmet gideri (ayrı) (₺)','İcar (ayrı) (₺)','Satışlar − işlem gideri (₺)','Fark/da (₺)']){const th=document.createElement('th');th.textContent=label;header.append(th)}table.append(header);
  let totalIncome=0,totalCost=0,unmatched=0;
  for(const code of codes){const a=areas.find(x=>x.parcel_code===code),parcel=parcels.find(x=>x.code===code),da=a?n(a.worked_area_da):(parcel?n(parcel.area_m2)/1000:0),areaEstimated=!a&&!!parcel;
   const hkg=sum(hs.filter(x=>x.parcel_code===code),x=>x.quantity),made=sum(bs.filter(x=>x.parcel_code===code),x=>x.quantity||x.bale_count),sold=sum(bss.filter(x=>x.parcel_code===code),x=>x.quantity),baleIncome=sum(bss.filter(x=>x.parcel_code===code),x=>x.total);
   const cropRevenue=cropIncome.get(code)||0,expense=sum(baseOps.filter(x=>x.parcel_code===code&&x.direction==='Gider'),x=>x.amount),incomeOps=sum(baseOps.filter(x=>x.parcel_code===code&&x.direction==='Gelir'),x=>x.amount);
   const serviceExpense=sum(sv.filter(x=>x.parcel_code===code),x=>x.amount),rentExpense=sum(rs.filter(x=>x.parcel_code===code),x=>x.total_amount);
   const income=cropRevenue+baleIncome+incomeOps,delta=income-expense;totalIncome+=income;totalCost+=expense;
   const values=[code,da?(fmt(da)+(areaEstimated?'*':'')):'—',fmt(hkg),fmt(cropSold.get(code)||0),fmt(cropRevenue),fmt(made),fmt(sold),fmt(made-sold),fmt(baleIncome),fmt(expense),fmt(serviceExpense),fmt(rentExpense),fmt(delta),da?fmt(delta/da):'—'];
   const row=document.createElement('tr');for(const value of values){const cell=document.createElement('td');cell.textContent=value;row.append(cell)}table.append(row);
  }
  const wrap=document.createElement('div');wrap.className='profit-scroll';wrap.append(table);report.replaceChildren(wrap);
  unmatched=sum(baseOps.filter(x=>!x.parcel_code),x=>x.direction==='Gider'?x.amount:0);
  summary.textContent=`Sezon ${season} · Parsele bağlanan satış ve işlem gelirleri ${fmt(totalIncome)} ₺ · Parsele bağlanan işlem giderleri ${fmt(totalCost)} ₺ · Parselsiz işlem gideri ${fmt(unmatched)} ₺ · Parsele bağlanamayan ürün satışı ${fmt(unassigned)} ₺. Hizmet ve icar tutarları, işlem giderlerinde bulunabilecekleri için ayrıca gösterilir fakat fark hesabına yeniden eklenmez. * işaretli alanlar, sezonluk işlenen alan kaydı bulunmadığından parselin kayıtlı alanından alınmıştır; gerçek işlenen alanı temsil etmeyebilir. Bakım, destek dağıtımı ve diğer genel giderler bu fark hesabına dahil değildir. Bu tablo kesin net kâr değildir.`;
 }
 seasonFilter.addEventListener('change',()=>update().catch(console.error));
 const prior=window.renderExtended;if(typeof prior==='function')window.renderExtended=async function(...args){const result=await prior.apply(this,args);await update();return result};
 setTimeout(()=>update().catch(console.error),500);
})();
