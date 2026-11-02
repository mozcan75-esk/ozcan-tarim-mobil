'use strict';
// Dashboard is read-only; all amounts are derived from existing IndexedDB stores.
const dashMoney=n=>Number(n||0).toLocaleString('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2});
const dashNum=n=>Number(n||0).toLocaleString('tr-TR',{maximumFractionDigits:2});
const dashN=x=>Number(x||0);
const dashLive=x=>!dashN(x.is_cancelled);
const dashSeason=x=>String(x.season||'');
const dashEl=id=>document.getElementById(id);
async function renderDashboard(){
 const names=['parcels','operations','rents','rentPayments','supports','maintenance','harvests','sales','stockMoves','inputs','sourceRecords'];
 const data=await Promise.all(names.map(all));const d=Object.fromEntries(names.map((n,i)=>[n,data[i]]));
 const seasons=[...new Set([...d.operations,...d.supports,...d.maintenance,...d.rents,...d.harvests,...d.sales].map(dashSeason).filter(Boolean))].sort().reverse();
 const pick=dashEl('dashSeason'),old=pick.value;pick.replaceChildren(...seasons.map(s=>new Option(s,s)));pick.value=seasons.includes(old)?old:seasons[0]||'';
 const season=pick.value,ops=d.operations.filter(x=>dashLive(x)&&dashSeason(x)===season),supports=d.supports.filter(x=>dashLive(x)&&dashSeason(x)===season),maintenance=d.maintenance.filter(x=>dashLive(x)&&dashSeason(x)===season),rents=d.rents.filter(x=>dashLive(x)&&dashSeason(x)===season),sales=d.sales.filter(x=>dashLive(x)&&dashSeason(x)===season),harvests=d.harvests.filter(x=>dashLive(x)&&dashSeason(x)===season);
 const expense=ops.filter(x=>x.direction==='Gider').reduce((a,x)=>a+dashN(x.amount),0);
 const operationIncome=ops.filter(x=>x.direction==='Gelir').reduce((a,x)=>a+dashN(x.amount),0);
 const subsidy=supports.reduce((a,x)=>a+dashN(x.amount),0),maint=maintenance.reduce((a,x)=>a+dashN(x.cost),0);
 const saleIncome=sales.reduce((a,x)=>a+dashN(x.amount||dashN(x.quantity)*dashN(x.unit_price)),0);
 const income=operationIncome+subsidy+saleIncome, totalExpense=expense+maint;
 const debt=rents.reduce((a,x)=>a+dashN(x.total_amount),0),rentIds=new Set(rents.map(x=>String(x.id)));
 const paid=d.rentPayments.filter(x=>dashLive(x)&&rentIds.has(String(x.rent_id))).reduce((a,x)=>a+dashN(x.amount),0);
 // Desktop V1.9.31 dashboard parity: only distinct parcels with actual expense
 // operations, excluding sale/harvest/rent. Seasonal area is a cap, not evidence of work.
 const active=d.parcels.filter(x=>x.active===undefined||dashN(x.active)!==0);
 const areas=d.sourceRecords.filter(x=>x.table==='parcel_season_areas').map(x=>x.record).filter(x=>dashSeason(x)===season);
 const areaMap=new Map(areas.map(x=>[String(x.parcel_code),dashN(x.worked_area_da)]));
 const leaseMap=new Map(areas.map(x=>[String(x.parcel_code),dashN(x.leased_area_da)]));
 const parcelMap=new Map(active.map(x=>[String(x.code),x]));
 const workedCodes=new Set(ops.filter(x=>x.direction==='Gider'&&!['Satış','Hasat','İcar/Kiralama'].includes(String(x.op_type||''))&&parcelMap.has(String(x.parcel_code||''))).map(x=>String(x.parcel_code)));
 const parcelWorked=code=>areaMap.has(code)?areaMap.get(code):dashN(parcelMap.get(code)?.area_m2)/1000;
 const worked=[...workedCodes].reduce((n,code)=>n+parcelWorked(code),0);
 // Managed footprint: owned + leased, capped at cadastral area; allow cultivated
 // extensions only when an actual operation exists. Mirrors desktop app.py.
 const totalArea=active.reduce((n,p)=>{
   const code=String(p.code),tapu=dashN(p.area_m2)/1000;
   const owned=p.owned_area_da===null||p.owned_area_da===undefined?tapu:dashN(p.owned_area_da);
   const base=Math.min(tapu,owned+Math.max(0,leaseMap.get(code)||0));
   const actual=workedCodes.has(code)?parcelWorked(code):0;
   return n+Math.max(base,actual);
 },0);
 const kv=(id,value)=>{const el=dashEl(id);if(el)el.textContent=value;};
 kv('dashArea',dashNum(totalArea)+' da');kv('dashWorked',worked?dashNum(worked)+' da':'—');kv('dashParcels',String(active.length));
 kv('dashFieldCount',workedCodes.size+' işlem yapılan parsel');
 kv('dashAreaNote',`P022 tapu 10 da / işlenen 5 da · P010 işlenen 36,704 da (icar ikinci kez eklenmez)`);
 kv('dashExpense',dashMoney(totalExpense)+' ₺');kv('dashIncome',dashMoney(income)+' ₺');kv('dashNet',dashMoney(income-totalExpense)+' ₺');kv('dashPerDa',worked?dashMoney((income-totalExpense)/worked)+' ₺/da':'—');
 kv('dashDebt',dashMoney(Math.max(0,debt-paid))+' ₺');kv('dashDebtTotal',dashMoney(debt)+' ₺');kv('dashPaid',dashMoney(paid)+' ₺');
 kv('dashSeed',dashMoney(ops.filter(x=>/tohum/i.test([x.category,x.item].join(' '))).reduce((a,x)=>a+(x.direction==='Gider'?dashN(x.amount):0),0))+' ₺');
 kv('dashFert',dashMoney(ops.filter(x=>/gübre/i.test([x.category,x.item].join(' '))).reduce((a,x)=>a+(x.direction==='Gider'?dashN(x.amount):0),0))+' ₺');
 kv('dashDiesel',dashMoney(ops.filter(x=>/motorin|mazot/i.test([x.category,x.item].join(' '))).reduce((a,x)=>a+(x.direction==='Gider'?dashN(x.amount):0),0))+' ₺');
 kv('dashMaint',dashMoney(maint)+' ₺');kv('dashSupport',dashMoney(subsidy)+' ₺');kv('dashSales',dashMoney(saleIncome)+' ₺');
 const stock=dashEl('dashStock');stock.replaceChildren();
 for(const input of d.inputs){const moves=d.stockMoves.filter(m=>m.input_id===input.id),qty=moves.reduce((a,m)=>a+(m.kind==='purchase'?1:-1)*dashN(m.quantity),0);const line=document.createElement('div');line.className='dash-line';const a=document.createElement('span'),b=document.createElement('strong');a.textContent=input.name;b.textContent=dashNum(Math.abs(qty)<1e-8?0:qty)+' '+(input.unit||'');line.append(a,b);stock.append(line);}
 if(!d.inputs.length)stock.textContent='Henüz girdi kaydı yok.';
 const crops=new Map();for(const h of harvests)crops.set(h.crop,(crops.get(h.crop)||0)+dashN(h.quantity));for(const s of sales)crops.set(s.crop,(crops.get(s.crop)||0)-dashN(s.quantity));
 const cropBox=dashEl('dashCrops');cropBox.replaceChildren();for(const [crop,qty] of crops){const line=document.createElement('div');line.className='dash-line';const a=document.createElement('span'),b=document.createElement('strong');a.textContent=crop;b.textContent=dashNum(qty)+' kg';line.append(a,b);cropBox.append(line);}if(!crops.size)cropBox.textContent='Henüz hasat kaydı yok.';
 kv('dashCaveat','İşlem gideri '+dashMoney(expense)+' ₺ + bakım '+dashMoney(maint)+' ₺. İcar '+dashMoney(debt)+' ₺ açık borç olarak ayrı izlenir; bu göstergeye gider olarak eklenmez. Kesin sezon kârı değildir.');
}
function dashShow(tab){for(const p of document.querySelectorAll('.panel'))p.hidden=p.id!==tab;for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('selected',b.dataset.tab===tab);if(tab==='home')renderDashboard().catch(console.error);}
for(const b of document.querySelectorAll('[data-tab]'))b.addEventListener('click',()=>dashShow(b.dataset.tab));
for(const b of document.querySelectorAll('[data-dash-tab]'))b.addEventListener('click',()=>dashShow(b.dataset.dashTab));
dashEl('dashSeason').addEventListener('change',()=>renderDashboard().catch(console.error));
// Keep dashboard fresh after returning to the app or making changes in other tabs.
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!dashEl('home').hidden)renderDashboard().catch(console.error)});
dashShow('home');
