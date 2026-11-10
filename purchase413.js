/* V4.0.13 - Giderler / Girdi Alimi: tur ve tanimli malzeme secimi. */
(()=>{'use strict';
const norm=s=>String(s||'').trim().toLocaleLowerCase('tr-TR');
const categories=['Gübre','Tohum','İlaç','Motorin','Diğer'];
function init(){
 const form=document.getElementById('purchaseForm');const material=form?.elements.input_id;
 if(!material||document.getElementById('purchaseCategory413'))return;
 const wrapper=document.createElement('label');wrapper.textContent='Girdi türü';
 const category=document.createElement('select');category.id='purchaseCategory413';category.required=true;
 category.add(new Option('Tür seçin',''));
 categories.forEach(x=>category.add(new Option(x,x)));
 wrapper.append(category);material.closest('label')?.before(wrapper);
 const hint=document.createElement('small');hint.id='purchaseHint413';hint.textContent='Önce girdi türünü seçin.';
 material.closest('label')?.after(hint);
 const source=document.createElement('select');source.hidden=true;document.body.append(source);
 let items=[],busy=false;
 async function refresh(preserve=true){
  if(busy)return;busy=true;
  try{
   items=await all('inputs');
   const chosen=preserve?material.value:'';
   const filtered=items.filter(x=>norm(x.category)===norm(category.value));
   material.replaceChildren(new Option(category.value?'Malzeme seçin':'Önce girdi türünü seçin',''));
   for(const x of filtered)material.add(new Option(x.name+' ('+x.unit+')',x.id));
   material.value=filtered.some(x=>String(x.id)===String(chosen))?chosen:'';
   material.disabled=!category.value;
   hint.textContent=!category.value?'Önce girdi türünü seçin.':filtered.length?'Ayarlar bölümünde tanımlanan malzemeler gösteriliyor.':'Bu türde tanımlı malzeme yok. Ayarlar → Girdi Tanımları bölümünden ekleyin.';
  }catch(e){console.warn('Girdi alımı seçimleri',e);hint.textContent='Malzemeler yüklenemedi.'}finally{busy=false}
 }
 category.addEventListener('change',()=>refresh(false));
 document.addEventListener('ozcan:inputs-updated',()=>refresh(true));
 // Mevcut render() girdi secimini yeniden doldurdugunda tur filtresini tekrar uygula.
 let pending=false;
 const observer=new MutationObserver(()=>{if(busy||pending)return;pending=true;queueMicrotask(()=>{pending=false;if(!busy&&category.value){const expected=items.filter(x=>norm(x.category)===norm(category.value));const actual=[...material.options].slice(1).map(o=>o.value);if(expected.length!==actual.length||expected.some((x,i)=>String(x.id)!==actual[i]))refresh(true)}})});
 observer.observe(material,{childList:true});
 form.addEventListener('submit',e=>{if(!category.value||!material.value){e.preventDefault();e.stopImmediatePropagation();alert('Önce girdi türünü ve tanımlı malzemeyi seçin.');(!category.value?category:material).focus()}},true);
 form.addEventListener('reset',()=>setTimeout(()=>{category.value='';refresh(false)},0));
 refresh(false);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
