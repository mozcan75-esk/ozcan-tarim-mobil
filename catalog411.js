/* V4.0.11: Catalog selectors; existing data and accounting are unchanged. */
(()=>{'use strict';
const key='ozcan_catalog_crops_v407';
const defaults=['Buğday','Arpa','Yulaf','Çavdar','Mısır','Ayçiçeği','Mercimek','Nohut','Tritikale'];
const norm=s=>String(s||'').trim().toLocaleLowerCase('tr-TR');
function crops(){try{const v=JSON.parse(localStorage.getItem(key));return [...new Set([...defaults,...(Array.isArray(v)?v:[])].map(s=>String(s).trim()).filter(Boolean))]}catch{return defaults}}
function setupCrop(formId){const form=document.getElementById(formId),input=form?.elements.crop;if(!input||input.dataset.catalog411)return;input.dataset.catalog411='1';
 const sel=document.createElement('select');sel.className='catalog411-crop';sel.setAttribute('aria-label','Tanımlı ürün seç');sel.required=true;
 input.parentElement.insertBefore(sel,input);input.classList.add('catalog411-hidden');input.readOnly=true;
 function refresh(){const v=input.value.trim(),options=crops();if(v&&!options.some(x=>norm(x)===norm(v)))options.push(v);sel.replaceChildren(new Option('Ürün seçin',''),...options.map(x=>new Option(x,x)));sel.value=v||''}
 sel.addEventListener('change',()=>{input.value=sel.value;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}))});
 form.elements.parcel_code?.addEventListener('change',()=>setTimeout(refresh,250));form.elements.season?.addEventListener('change',()=>setTimeout(refresh,250));
 form.addEventListener('submit',e=>{if(!sel.value){e.preventDefault();e.stopImmediatePropagation();alert('Tanımlı bir ürün seçin. Yeni ürün eklemek için Ayarlar → Ürün Tanımları bölümünü kullanın.');sel.focus()}},true);
 document.getElementById('settingsCropForm407')?.addEventListener('submit',()=>setTimeout(refresh,30));
 refresh();setTimeout(refresh,750);
 }
function setupUse(){const form=document.getElementById('useForm'),sel=form?.elements.input_id;if(!sel)return;const kind=document.createElement('select');kind.className='catalog411-type';kind.setAttribute('aria-label','Girdi türü');kind.add(new Option('Tüm girdi türleri',''));for(const v of ['Tohum','Gübre','İlaç','Motorin','Diğer'])kind.add(new Option(v,v));const label=document.createElement('label');label.textContent='Girdi türüne göre filtrele';label.append(kind);sel.closest('label')?.before(label);
 async function filter(){const selected=sel.value;try{const items=await all('inputs');const allowed=new Set(items.filter(x=>!kind.value||norm(x.category)===norm(kind.value)).map(x=>String(x.id)));for(const o of sel.options)o.hidden=!!kind.value&&!allowed.has(o.value);if(kind.value&&!allowed.has(sel.value))sel.value=[...sel.options].find(o=>!o.hidden)?.value||'';else if(selected&&[...sel.options].some(o=>o.value===selected&&!o.hidden))sel.value=selected}catch(e){console.warn('Girdi filtresi',e)}}
 kind.addEventListener('change',filter);document.getElementById('settingsInputForm407')?.addEventListener('submit',()=>setTimeout(filter,200));filter();
 }
function init(){setupCrop('harvestForm');setupCrop('harvestBundleForm');setupUse()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
