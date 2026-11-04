// V3.2.2 – unified season selection; no database migration.
(()=>{
 const normalize=s=>{const m=String(s||'').match(/(20\d{2})\s*[-/]\s*(20\d{2})/);return m?m[1]+'/'+m[2]:String(s||'').trim()};
 const controls=[...document.querySelectorAll('select[data-season-select]')];
 const stores=['operations','harvests','sales','rents','supports','maintenance','services','sourceRecords'];
 let options=[];
 async function load(){
   const groups=await Promise.all(stores.map(s=>all(s).catch(()=>[])));
   const found=[];
   for(let i=0;i<groups.length;i++)for(const x of groups[i]){
     const r=i===7?(x.record||{}):x;
     if(r.season)found.push(normalize(r.season));
   }
   const dash=document.getElementById('dashSeason');
   if(dash)for(const opt of dash.options)if(opt.value)found.push(normalize(opt.value));
   options=[...new Set(found.filter(Boolean))].sort().reverse();
   if(!options.length)options=[normalize(dash?.value)||'2026/2027'];
   sync();
 }
 function sync(){
   const dash=document.getElementById('dashSeason');
   const selected=normalize(dash?.value)||options[0];
   for(const select of controls){
     const old=normalize(select.value),form=select.closest('form');
     const target=old&&options.includes(old)?old:selected;
     const previous=select.value;
     select.replaceChildren(...options.map(v=>new Option(v,v)));
     select.value=options.includes(target)?target:options[0];
     if(previous!==select.value)select.dispatchEvent(new Event('change',{bubbles:true}));
   }
 }
 const dash=document.getElementById('dashSeason');
 if(dash)dash.addEventListener('change',()=>{
   const v=normalize(dash.value);
   for(const select of controls){if(options.includes(v)){select.value=v;select.dispatchEvent(new Event('change',{bubbles:true}))}}
 });
 // Recompute options when returning to a form; do not replace a select while it is open.
 for(const c of controls)c.addEventListener('focus',()=>load().catch(console.error));
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)load().catch(console.error)});
 setTimeout(()=>load().catch(console.error),250);
})();
