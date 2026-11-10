// V5.3.3 - Independent read-only backup handler. No schema upgrades or writes.
(function(){
 'use strict';
 const btn=document.getElementById('export');
 const status=document.getElementById('status');
 const link=document.getElementById('backupManualLink');
 if(!btn||!status||!link)return;
 let lastUrl=null;
 function report(message){status.textContent=message;status.hidden=false;}
 function openExisting(){return new Promise((resolve,reject)=>{
   const req=indexedDB.open('ozcan_tarim_mobile_test');
   req.onsuccess=()=>resolve(req.result);
   req.onerror=()=>reject(req.error||new Error('Veritabanı açılamadı'));
   req.onblocked=()=>reject(new Error('Veritabanı başka bir sekmede açık'));
   req.onupgradeneeded=()=>{req.transaction.abort();reject(new Error('Mobil veritabanı bulunamadı; boş yedek oluşturulmadı'))};
 });}
 function readStore(db,name){return new Promise((resolve,reject)=>{
   const tx=db.transaction(name,'readonly');const req=tx.objectStore(name).getAll();
   req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error(name+' okunamadı'));
   tx.onabort=()=>reject(tx.error||new Error(name+' okuma iptal edildi'));
 });}
 async function backup(e){
   e.preventDefault();e.stopImmediatePropagation();
   if(btn.disabled)return;
   btn.disabled=true;link.hidden=true;
   report('Yedekleme başladı. Veritabanı okunuyor…');
   let db;
   try{
     if(!window.indexedDB)throw new Error('Bu tarayıcıda IndexedDB kullanılamıyor');
     db=await openExisting();
     const names=Array.from(db.objectStoreNames);
     if(!names.includes('parcels')||!names.includes('operations'))throw new Error('Beklenen veri tabloları bulunamadı');
     const data={format:'ozcan-mobile-test-v3',exportedAt:new Date().toISOString(),appVersion:'5.3.3'};
     for(let i=0;i<names.length;i++){
       report('Yedek hazırlanıyor: '+(i+1)+'/'+names.length+' tablo');
       data[names[i]]=await readStore(db,names[i]);
     }
     const json=JSON.stringify(data,null,2);
     const blob=new Blob([json],{type:'application/json;charset=utf-8'});
     const url=URL.createObjectURL(blob);
     if(lastUrl)URL.revokeObjectURL(lastUrl);
     lastUrl=url;
     const d=new Date();const date=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('');
     link.href=url;link.download='Ozcan_Tarim_Mobil_Yedek_'+date+'.json';link.textContent='JSON yedeğini aç / indir ('+Math.ceil(blob.size/1024)+' KB)';link.hidden=false;
     report('Yedek hazır: '+names.length+' tablo. Aşağıdaki bağlantıya dokunup dosyayı kaydet.');
   }catch(err){report('Yedekleme hatası: '+(err&&err.message?err.message:String(err)));}
   finally{if(db)db.close();btn.disabled=false;}
 }
 btn.addEventListener('click',backup,true);
 report('Yedekleme modülü hazır. JSON yedeği hazırla düğmesine dokun.');
})();
