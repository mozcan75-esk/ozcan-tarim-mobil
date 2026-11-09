'use strict';
// Separate, non-destructive record browser; updates preserve original IDs and unknown fields.
const RECORD_GROUPS=[
 ['operations','operations','Faaliyetler','op_date',['parcel_code','op_type','item','quantity','unit','amount']],
 ['inputs','inputs','Girdi tanımları','name',['name','category','unit']],
 ['inputs','stockMoves','Depo hareketleri','date',['kind','input_id','quantity','unit_price','total']],
 ['harvest','harvests','Hasat kayıtları','date',['parcel_code','crop','quantity','season']],
 ['harvest','sales','Satış kayıtları','date',['crop','quantity','unit_price','total']],
 ['rents','rents','İcar sözleşmeleri','season',['parcel_code','landlord','area_da','rate_per_da','total_amount']],
 ['rents','rentPayments','İcar ödemeleri','date',['rent_id','amount','date']],
 ['supports','supports','Destekler','date',['support_type','description','amount']],
 ['supports','maintenance','Bakım giderleri','date',['machine','description','cost']],
 ['services','services','Hizmetler','date',['parcel_code','kind','quantity','unit_price','amount']],
 ['services','servicePayments','Hizmet ödemeleri','date',['amount','date']],
 ['baleWarehouse','bales','Balyalar','date',['parcel_code','quantity','weight_kg']],
 ['baleWarehouse','baleSales','Balya satışları','date',['quantity','unit_price','total']]
];
const REC_LABEL={op_date:'Tarih',date:'Tarih',parcel_code:'Parsel',op_type:'Faaliyet',item:'Ürün / açıklama',quantity:'Miktar',unit:'Birim',amount:'Tutar (₺)',total:'Toplam (₺)',unit_price:'Birim fiyat (₺)',input_id:'Girdi',kind:'Tür',crop:'Ürün',season:'Sezon',landlord:'Mal sahibi',area_da:'Alan (da)',rate_per_da:'Birim icar (₺/da)',rent_id:'İcar sözleşmesi',support_type:'Destek türü',description:'Açıklama',machine:'Makine',cost:'Tutar (₺)',name:'Ad',category:'Kategori',weight_kg:'Ağırlık (kg)',payment_date:'Ödeme tarihi'};
const REC_SAFE={
 operations:['op_date','season','parcel_code','op_type','item','quantity','unit','unit_price','direction'],
 inputs:['name','category','unit'],
 stockMoves:['date','quantity','unit_price'],
 harvests:['date','season','parcel_code','crop','quantity'],
 sales:['date','season','crop','quantity','unit_price'],
 rents:['season','parcel_code','landlord','area_da','rate_per_da'],
 rentPayments:['date','amount'],
 supports:['date','season','support_type','description','amount'],
 maintenance:['date','season','machine','description','cost'],
 services:['date','season','parcel_code','kind','quantity','unit','unit_price'],
 servicePayments:['date','amount'],
 bales:['date','parcel_code','quantity','weight_kg'],
 baleSales:['date','quantity','unit_price']
};
const REC_LINKED=new Set(['operations','stockMoves','harvests','sales','rentPayments','services','servicePayments','bales','baleSales']);
function recText(v){return v==null||v===''?'—':String(v)}
function recFieldName(k){return REC_LABEL[k]||k.replaceAll('_',' ')}
function recFieldValue(k,v){if(['amount','total','cost','unit_price','rate_per_da'].includes(k)&&v!==''&&v!=null)return money(v)+' ₺';return recText(v)}
function recLinkedName(store,key,value,refs){if(key==='parcel_code')return ((refs.parcels||[]).find(p=>p.code===value)?.name||value)+' ('+value+')';if(key==='input_id')return (refs.inputs||[]).find(p=>String(p.id)===String(value))?.name||value;if(key==='rent_id'){const r=(refs.rents||[]).find(p=>String(p.id)===String(value));return r?`${r.parcel_code} / ${r.landlord}`:value}return recFieldValue(key,value)}
let recEditing=null;
async function renderRecordBrowser(){
 const refs={};for(const s of new Set(RECORD_GROUPS.map(g=>g[1]).concat(['parcels'])))refs[s]=await all(s);
 for(const [panel,store,title,sortKey,fields] of RECORD_GROUPS){
  const host=document.getElementById('records-'+store);if(!host)continue;const rows=[...refs[store]].sort((a,b)=>String(b[sortKey]||'').localeCompare(String(a[sortKey]||'')));
  const query=(host.querySelector('.record-search')?.value||'').toLocaleLowerCase('tr-TR');host.replaceChildren();
  const head=document.createElement('div');head.className='record-head';const h=document.createElement('h3');h.textContent=title+' ('+rows.length+')';head.append(h);
  const search=document.createElement('input');search.className='record-search';search.placeholder='Kayıt ara…';search.setAttribute('aria-label',title+' ara');search.value=query;head.append(search);host.append(head);
  const tableWrap=document.createElement('div');tableWrap.className='record-scroll';const table=document.createElement('table');table.className='record-table';const tr=document.createElement('tr');
  const display=['date','op_date','season',...fields].filter((k,i,a)=>a.indexOf(k)===i&&rows.some(r=>r[k]!=null&&r[k]!==''));
  for(const key of display.concat(['İşlem'])){const th=document.createElement('th');th.textContent=key==='İşlem'?key:recFieldName(key);tr.append(th)}const thead=document.createElement('thead');thead.append(tr);table.append(thead);const tbody=document.createElement('tbody');table.append(tbody);
  for(const r of rows){const row=document.createElement('tr');row.dataset.search=JSON.stringify(r).toLocaleLowerCase('tr-TR');for(const key of display){const td=document.createElement('td');td.dataset.label=recFieldName(key);td.textContent=recLinkedName(store,key,r[key],refs);row.append(td)}const td=document.createElement('td');const btn=document.createElement('button');btn.type='button';btn.className='parcel-edit-btn';btn.textContent=REC_LINKED.has(store)?'Görüntüle':'Düzenle';btn.onclick=()=>openRecordEditor(store,r);td.className='record-actions';td.dataset.label='İşlem';td.append(btn);row.append(td);tbody.append(row)}
  tableWrap.append(table);host.append(tableWrap);const apply=()=>{const q=search.value.trim().toLocaleLowerCase('tr-TR');for(const row of tbody.rows)row.hidden=!row.dataset.search.includes(q)};search.oninput=apply;apply();
 }
}
function openRecordEditor(store,record){
 const overlay=document.getElementById('recordEditOverlay'),form=document.getElementById('recordEditForm');form.replaceChildren();recEditing={store,record};document.getElementById('recordEditTitle').textContent='Kayıt ayrıntıları · '+(RECORD_GROUPS.find(g=>g[1]===store)?.[2]||store);
 const info=document.getElementById('recordEditInfo');info.textContent=REC_LINKED.has(store)?'Bu kayıt stok, gelir/gider veya başka kayıtlarla bağlantılı olabilir. Hesaplama güvenliği için bağlı kayıtlarda tutar ve miktar değişikliği bu ekrandan yapılamaz. Açıklama/tarih gibi alanları güncelleyebilirsiniz.':'Değişiklikler aynı kayıt üzerinde saklanır; kayıt numarası değişmez.';
 const allowed=REC_LINKED.has(store)?[]:REC_SAFE[store];
 if(!allowed.length){const detail=document.createElement('div');detail.className='record-detail';for(const [key,value] of Object.entries(record)){if(['id','source_id'].includes(key)||value===null||typeof value==='object')continue;const line=document.createElement('div');const name=document.createElement('strong');name.textContent=recFieldName(key)+': ';line.append(name,document.createTextNode(recFieldValue(key,value)));detail.append(line)}form.append(detail);const p=document.createElement('p');p.textContent='Bu kayıt başka hesaplamalarla bağlantılı olduğundan güvenli düzenleme henüz desteklenmiyor. Kaydı görüntüleyebilirsiniz; değişiklik için bağlı hesaplamaların birlikte güncellenmesi gerekir.';form.append(p);form.dataset.locked='1';}else form.dataset.locked='0';overlay.querySelectorAll('button[type=submit]').forEach(b=>b.hidden=!allowed.length);
 for(const key of allowed){if(!(key in record))continue;const label=document.createElement('label');label.textContent=recFieldName(key);const old=record[key];let field;if(key==='direction'){field=document.createElement('select');for(const v of ['Gider','Gelir','Nötr'])field.add(new Option(v,v))}else{field=document.createElement('input');field.type=['date','op_date'].includes(key)?'date':typeof old==='number'?'number':'text';if(field.type==='number')field.step='any'}field.name=key;field.value=old??'';label.append(field);form.append(label)}
 if(allowed.length){const save=document.createElement('button');save.type='submit';save.textContent='Değişiklikleri kaydet';form.append(save)}overlay.hidden=false;overlay.scrollIntoView({behavior:'smooth',block:'start'});
}
async function saveRecordEdit(e){e.preventDefault();if(!recEditing)return;const {store,record}=recEditing;const form=e.target;if(form.dataset.locked==='1')return alert('Bağlı kayıt düzenlemesi henüz desteklenmiyor');const updated={...record};for(const el of form.elements){if(!el.name)continue;updated[el.name]=typeof record[el.name]==='number'?Number(el.value):el.value.trim();if(typeof updated[el.name]==='number'&&!Number.isFinite(updated[el.name]))return alert('Geçersiz sayı: '+el.name)}
 if(store==='rents'){if(!(updated.area_da>0)||updated.rate_per_da<0)return alert('Alan ve icar tutarını kontrol edin');updated.total_amount=Math.round(updated.area_da*updated.rate_per_da*100)/100;const pays=(await all('rentPayments')).filter(x=>String(x.rent_id)===String(record.id)&&!Number(x.is_cancelled)).reduce((n,x)=>n+Number(x.amount||0),0);if(updated.total_amount<pays)return alert('İcar toplamı mevcut ödemelerden küçük olamaz')}
 if(store==='supports'){updated.payment_date=updated.date;updated.crop=/arpa/i.test((updated.description||'')+' '+(updated.support_type||''))?'Arpa':'';if(updated.crop==='Arpa'&&!/tohum/i.test((updated.description||'')+' '+(updated.support_type||'')))return alert('Arpa tohumu desteği açıklamasını belirtin')}
 if(store==='supports'&&!(updated.amount>0))return alert('Destek tutarı pozitif olmalı');
 if(store==='maintenance'&&updated.cost<0)return alert('Bakım tutarı negatif olamaz');
 if(store==='inputs'&&updated.unit!==record.unit)return alert('Stok hareketlerinin birimi korunmalıdır. Birim değiştirilemez');
 if(store==='inputs'&&(!updated.name||!updated.unit))return alert('Girdi adı ve birimi gerekli');
 if(store==='operations'&&updated.op_date!==record.op_date&&record.source_id!=null)return alert('Bilgisayardan aktarılan kaynak işlemin tarihi bu ekranda değiştirilemez');
 if(!confirm('Bu kaydın bilgileri güncellensin mi?'))return;
 try{await put(store,updated);closeRecordEdit();await render();await renderExtended();if(typeof renderCropStock==='function')await renderCropStock()}catch(err){alert('Kayıt güncellenemedi: '+err.message)}
}
function closeRecordEdit(){document.getElementById('recordEditOverlay').hidden=true;recEditing=null}
document.getElementById('recordEditForm').addEventListener('submit',saveRecordEdit);document.getElementById('recordEditCancel').onclick=closeRecordEdit;
const originalRenderRecords=render;render=async function(){await originalRenderRecords();await renderRecordBrowser()};
