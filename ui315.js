// V3.1.5: arayüz, stok özetleri ve yönlendirme; mevcut veri kayıt algoritmaları değişmez.
(()=>{'use strict';
 const $=id=>document.getElementById(id);
 const hint=$('activityHint'),kind=$('activityKind');
 const directions={Ekim:'Ekimde tohum, gübre ve motorini mevcut stoktan ayrı ayrı kaydedin. Tek kayıt olarak birleştirme henüz etkin değil.',Gübreleme:'Gübreyi ve kullanıldıysa motorini stoktan ayrı kaydedin.',Pulluk:'Motorin tüketimini stoktan kaydedin.',Kazayağı:'Motorin tüketimini stoktan kaydedin.',Tırmık:'Motorin tüketimini stoktan kaydedin.',Hasat:'Hasat miktarı için Hasat / Satış bölümünü kullanın. Motorini ayrıca kaydedin.',Diğer:'Diğer işlem kaydı bölümünü açın.'};
 function jump(id){const el=$(id);if(!el)return;const details=el.closest('details');if(details)details.open=true;el.scrollIntoView({behavior:'smooth',block:'start'});}
 document.querySelectorAll('[data-jump]').forEach(b=>b.addEventListener('click',()=>jump(b.dataset.jump)));
 kind?.addEventListener('change',()=>{hint.textContent=directions[kind.value]||'İşlem seçerek ilgili kayıt ekranına geçin.';if(kind.value==='Hasat'){hint.textContent+=' Alt menüdeki Diğer bölümlerden Hasat / Satış ekranını açabilirsiniz.'}else if(kind.value==='Diğer')$('operationForm')?.closest('details')?.setAttribute('open','');});
 async function updateStock(){try{const [inputs,moves]=await Promise.all([all('inputs'),all('stockMoves')]);const target=$('quickStockCards');if(!target)return;target.replaceChildren();if(!inputs.length){target.textContent='Henüz girdi tanımlanmamış.';return;}for(const x of inputs){const amount=moves.filter(m=>m.input_id===x.id).reduce((a,m)=>a+(m.kind==='purchase'?1:-1)*Number(m.quantity||0),0);const box=document.createElement('div');box.className='stock-mini';const name=document.createElement('small');name.textContent=x.name;const value=document.createElement('strong');value.textContent=(Math.abs(amount)<1e-7?0:amount).toLocaleString('tr-TR',{maximumFractionDigits:3})+' '+(x.unit||'');box.append(name,value);target.append(box);}}catch(err){const target=$('quickStockCards');if(target)target.textContent='Stok bilgisi okunamadı: '+err.message;}}
 const oldRender=render;render=async function(...args){const result=await oldRender(...args);await updateStock();return result;};
 updateStock();
})();
