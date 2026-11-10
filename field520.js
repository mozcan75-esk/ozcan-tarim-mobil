
'use strict';
(()=>{
 const selector=document.getElementById('activityKind'),combined=document.getElementById('v52CombinedWrap'),harvest=document.getElementById('v51HarvestSection'),kind=document.getElementById('combinedKind'),hint=document.getElementById('activityHint');
 if(!selector||!combined||!harvest||!kind)return;
 function update(){
  const value=selector.value;
  combined.hidden=!value||value==='Hasat';
  harvest.hidden=value!=='Hasat';
  if(value&&value!=='Hasat'){kind.value=value;kind.dispatchEvent(new Event('change',{bubbles:true}));}
  hint.textContent=!value?'İşlem türünü seçtiğinizde yalnızca ilgili kayıt alanları açılır.':value==='Hasat'?'Ürün, traktör motorini ve biçerdöver ücreti tek hasat kaydında tutulur.':'Depo malzemeleri, seçtiğiniz işleme göre otomatik gösterilir.';
 }
 selector.addEventListener('change',update);
 // Hub navigasyonunda eski formu otomatik açma; işlem türünü kullanıcı seçer.
 update();
})();
