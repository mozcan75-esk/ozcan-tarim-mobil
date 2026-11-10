'use strict';
// Live stock availability in the unified field-activity form.
(()=>{
 const form=document.getElementById('combinedForm');
 if(!form)return;
 const rows=document.getElementById('combinedRows');
 const fmt=n=>Number(n).toLocaleString('tr-TR',{maximumFractionDigits:3});
 let pending=0;
 async function update(){
  const [inputs,moves]=await Promise.all([all('inputs'),all('stockMoves')]);
  const date=form.elements.date.value||'9999-12-31',area=Number(form.elements.area_da.value)||0;
  for(const row of rows.querySelectorAll('.combined-row')){
   const sel=row.querySelector('.combined-input'),rate=Number(row.querySelector('.combined-rate').value)||0;
   const current=sel.value;
   const candidates=inputs.filter(x=>{const c=((x.category||'')+' '+(x.name||'')).toLocaleLowerCase('tr-TR');const kind=row.dataset.kind;return kind==='Motorin'?/motorin|mazot/.test(c):kind==='İlaç'?c.includes('ilaç'):kind==='Gübre'?c.includes('gübre'):c.includes('tohum')});
   const stockAt=id=>moves.filter(m=>String(m.input_id)===String(id)&&String(m.date)<=date).reduce((n,m)=>n+(m.kind==='purchase'?Number(m.quantity):-Number(m.quantity)),0);
   // Keep selection while showing both in-stock and out-of-stock defined inputs.
   sel.replaceChildren(new Option(candidates.length?'Depodan malzeme seçin':'Bu tür malzeme tanımlı değil',''));
   for(const x of candidates){const stock=stockAt(x.id);sel.add(new Option(`${x.name} — stok ${fmt(stock)} ${x.unit}`,x.id));}
   if(candidates.some(x=>String(x.id)===String(current)))sel.value=current;
   else if(candidates.length===1)sel.value=String(candidates[0].id);
   const x=candidates.find(x=>String(x.id)===String(sel.value));
   let info=row.querySelector('.stock530-status');if(!info){info=document.createElement('p');info.className='stock530-status';info.setAttribute('aria-live','polite');row.append(info)}
   const need=area*rate,available=x?stockAt(x.id):0;
   info.textContent=!x?'Depodaki malzemeyi seçin.':`İşlem tarihindeki stok: ${fmt(available)} ${x.unit} · Gereken: ${fmt(need)} ${x.unit}`+(need>available+1e-8?' · YETERSİZ STOK':'');
   info.style.color=need>available+1e-8?'#b91c1c':'';
  }
 }
 function schedule(){clearTimeout(pending);pending=setTimeout(()=>update().catch(console.error),60)}
 rows.addEventListener('input',schedule);rows.addEventListener('change',schedule);
 form.addEventListener('input',schedule);form.addEventListener('change',schedule);
 document.getElementById('activityKind')?.addEventListener('change',()=>setTimeout(schedule,120));
 document.addEventListener('ozcan:inputs-updated',schedule);
 document.addEventListener('click',e=>{if(e.target.closest('[data-tab="operations"],[data-tab="operationsHub"]'))setTimeout(schedule,180)},true);
 const observer=new MutationObserver(schedule);observer.observe(rows,{childList:true});
 setTimeout(schedule,350);
})();
