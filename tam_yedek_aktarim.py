import json,sqlite3,os,shutil,tempfile,hashlib,datetime,uuid
from pathlib import Path
from flask import request,redirect,send_file,render_template_string
from functools import wraps

STORES=['parcels','operations','inputs','stockMoves','harvests','sales','rents','rentPayments','supports','maintenance','services','servicePayments','bales','baleSales','soilAnalyses','marketPrices','sourceRecords']
MAPPING={'parcels':'parcels','operations':'operations','rents':'rent_contracts','rentPayments':'rent_payments','supports':'supports','maintenance':'machine_maintenance','services':'field_service_charges','servicePayments':'field_service_payments','bales':'bale_batches','baleSales':'bale_sales','soilAnalyses':'soil_analyses','marketPrices':'market_prices'}
DB=Path(os.environ.get('OZCAN_TARIM_DB',str(Path(__file__).resolve().parent/'ozcan_tarim.db')))
PAGE='''<!doctype html><html lang="tr"><meta charset="utf-8"><title>Özcan Tarım - Tam Yedek Aktarımı</title><style>body{font:16px system-ui;max-width:850px;margin:35px auto;padding:0 20px;color:#193d2a}h1{color:#176b44}section{background:#f1f7f3;border-radius:10px;padding:18px;margin:18px 0}button,a.btn{background:#176b44;color:white;padding:11px 17px;border:0;border-radius:6px;display:inline-block;text-decoration:none}input{margin:12px 0}.warn{color:#a33}li{margin:8px 0}</style><a href="/">← Ana sayfa</a><h1>İki Yönlü Tam Yedek Aktarımı</h1><section><h2>Bilgisayar → iPhone</h2><p>Bilgisayardaki güncel verilerin mobil uyumlu JSON yedeğini indirin. iPhone'da Yedek Yükle ile açın.</p><a class="btn" href="/tam-yedek-indir">Bilgisayarın Tam Yedeğini İndir</a></section><section><h2>iPhone → Bilgisayar</h2><p>iPhone JSON yedeğini yükleyin. Önce inceleme, ardından ayrı onay ile veritabanına aktarım yapılır. Aktarımdan önce otomatik .db yedeği oluşturulur.</p><form action="/tam-yedek-onizle" method="post" enctype="multipart/form-data"><input type="file" name="backup" accept=".json" required><button>Yedeği İncele</button></form></section><p class="warn"><b>Önemli:</b> Bu işlem kayıt birleştirme değil, tam geri yüklemedir. Hedef cihazda yedek sonrasında yapılan değişiklikler kaybolabilir. İki cihazdan da önce ayrı yedek alın.</p>{% if message %}<section>{{message}}</section>{% endif %}</html>'''
PREVIEW='''<!doctype html><html lang="tr"><meta charset="utf-8"><title>Yedek Önizleme</title><style>body{font:16px system-ui;max-width:850px;margin:35px auto;padding:0 20px;color:#193d2a}button{padding:12px;background:#176b44;color:white;border:0;border-radius:6px}li{margin:7px 0}.warn{color:#a33}</style><a href="/tam-yedek">← Geri</a><h1>Yedek Önizleme</h1><p><b>Dosya:</b> {{name}}</p><p><b>SHA256:</b> {{digest}}</p><ul>{% for k,n in counts %}<li>{{k}}: {{n}}</li>{% endfor %}</ul><p class="warn">Onaylarsanız mevcut bilgisayar veritabanı yedeklenir ve mobil yedekteki kayıtlarla değiştirilir. Önizlemedeki dosya dışında başka dosya kullanılmaz.</p><form method="post" action="/tam-yedek-uygula"><input type="hidden" name="token" value="{{token}}"><label><input type="checkbox" name="accept" value="yes" required> Veritabanı yedeği alınarak TAM GERİ YÜKLEME yapılmasını onaylıyorum</label><p><button>Onayla ve Bilgisayara Aktar</button></p></form></html>'''

def cols(c,t):return [r[1] for r in c.execute('pragma table_info("'+t+'")')]
def table_rows(c,t):return [dict(x) for x in c.execute('select * from "'+t+'"')]
def validate(d):
 if not isinstance(d,dict) or d.get('format') not in ('ozcan-mobile-test-v3','ozcan-mobile-test-v2','ozcan-mobile-test-v1'):raise ValueError('Geçersiz yedek biçimi')
 for s in STORES:
  a=d.get(s)
  if not isinstance(a,list):raise ValueError('Eksik kayıt grubu: '+s)
  ids=[]
  for x in a:
   if not isinstance(x,dict):raise ValueError('Bozuk kayıt: '+s)
   k=x.get('code' if s=='parcels' else 'id')
   if k is None or str(k)=='':raise ValueError('Eksik kayıt kimliği: '+s)
   ids.append(str(k))
  if len(ids)!=len(set(ids)):raise ValueError('Tekrarlanan kayıt kimliği: '+s)
 ps={p['code'] for p in d['parcels']}
 for o in d['operations']:
  if o.get('parcel_code') and o['parcel_code'] not in ps:raise ValueError('İşlem parseli bulunamadı: '+str(o['parcel_code']))
 return d

def export_mobile():
 with sqlite3.connect(DB) as c:
  c.row_factory=sqlite3.Row
  ts=[r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
  data={'format':'ozcan-mobile-test-v3','appVersion':'3.5.0','exportedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exportOrigin':'pc'}
  for s in STORES:data[s]=[]
  data['parcels']=table_rows(c,'parcels')
  data['operations']=[dict(r,id='pc-op-'+str(r['id'])) for r in table_rows(c,'operations')]
  data['rents']=[dict(r,id='pc-rent-'+str(r['id'])) for r in table_rows(c,'rent_contracts')]
  data['supports']=[dict(r,id='pc-support-'+str(r['id']),date=r['payment_date']) for r in table_rows(c,'supports')]
  data['maintenance']=[dict(r,id='pc-maint-'+str(r['id']),date=r['service_date']) for r in table_rows(c,'machine_maintenance')]
  data['rentPayments']=[dict(r,id='pc-rentpay-'+str(r['id'])) for r in table_rows(c,'rent_payments')]
  data['services']=[dict(r,id='pc-service-'+str(r['id'])) for r in table_rows(c,'field_service_charges')]
  data['servicePayments']=[dict(r,id='pc-servicepay-'+str(r['id'])) for r in table_rows(c,'field_service_payments')]
  data['bales']=[dict(r,id='pc-bale-'+str(r['id'])) for r in table_rows(c,'bale_batches')]
  data['baleSales']=[dict(r,id='pc-balesale-'+str(r['id'])) for r in table_rows(c,'bale_sales')]
  data['soilAnalyses']=[dict(r,id='pc-soil-'+str(r['id'])) for r in table_rows(c,'soil_analyses')]
  data['marketPrices']=[dict(r,id='pc-price-'+str(r['item'])+'-'+str(r['unit'])) for r in table_rows(c,'market_prices')]
  inputs={}
  def get_input(category,item,unit,detail=''):
   key=(category,item,unit,detail or '')
   if key not in inputs:
    name=item if not detail else item+' / '+detail
    inputs[key]='pc-input-'+str(len(inputs)+1)
    data['inputs'].append(dict(id=inputs[key],name=name,category=category,unit=unit))
   return inputs[key]
  for r in table_rows(c,'stock_purchases'):
   if r.get('is_cancelled'):continue
   iid=get_input(r['category'],r['item'],r['unit'],r.get('item_detail'))
   data['stockMoves'].append(dict(id='pc-buy-'+str(r['id']),kind='purchase',input_id=iid,date=r['purchase_date'],quantity=r['quantity'],unit_price=r['unit_price'],total=round(r['quantity']*r['unit_price'],4),season=r['season'],source_id=r['id']))
  for r in table_rows(c,'operations'):
   if r['direction']!='Gider' or r['category'] not in ('Mazot','Tohum','Gübre'):continue
   iid=get_input(r['category'],r['item'],r['unit'],r.get('item_detail'))
   data['stockMoves'].append(dict(id='pc-use-'+str(r['id']),kind='use',input_id=iid,date=r['op_date'],quantity=r['quantity'],unit_price=r['unit_price'],total=r['amount'],parcel_code=r['parcel_code'],season=r['season'],source_operation_id=r['id']))
  for t in ts:
   if t=='sqlite_sequence':continue
   for r in table_rows(c,t):
    rid=str(r.get('id',r.get('code',r.get('name',r.get('item',uuid.uuid4())))))
    data['sourceRecords'].append({'id':t+':'+rid,'table':t,'record':r})
  validate(data)
  return data

def restore(d,target):
 # Rebuild on a copy of the current DB so the schema and all migrations remain intact.
 # Source records contain the exact PC tables, including field activities and season areas.
 # Harvest and sale structures differ across platforms; never silently discard them.
 for unsupported in ('harvests','sales'):
  if d[unsupported]:raise ValueError('Bu sürüm '+unsupported+' kayıtlarını güvenle dönüştüremiyor. Canlı veritabanı değiştirilmedi.')
 source={}
 for x in d['sourceRecords']:
  t=x.get('table');r=x.get('record')
  if isinstance(t,str) and isinstance(r,dict):source.setdefault(t,[]).append(r)
 with sqlite3.connect(target) as c:
  c.row_factory=sqlite3.Row;c.execute('pragma foreign_keys=off')
  tables={r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
  # The backup must contain the base PC snapshot for every nonempty auxiliary table.
  core={'parcels','operations','stock_purchases','rent_contracts','supports','machine_maintenance','market_prices','soil_analyses','rent_payments','field_service_charges','field_service_payments','bale_batches','bale_sales'}
  for t in tables-core-{'change_log','app_migrations','market_price_history'}:
   if c.execute('select count(*) from "'+t+'"').fetchone()[0] and t not in source:raise ValueError('Kaynak verisi eksik, korunamayan tablo: '+t)
  for t in tables:
   if t in ('app_migrations',):continue
   c.execute('delete from "'+t+'"')
  def insert(t,r,allow_id=True):
   if t not in tables:return
   valid=set(cols(c,t));v={k:val for k,val in r.items() if k in valid and (allow_id or k!='id')}
   if not v:return
   keys=list(v);c.execute('insert into "'+t+'" ('+','.join('"'+k+'"' for k in keys)+') values ('+','.join('?' for _ in keys)+')',[v[k] for k in keys])
  # Recover all PC-specific auxiliary records from the source snapshot.
  for t,rows in source.items():
   if t in tables and t not in core and t not in ('app_migrations',):
    for r in rows:insert(t,r)
  for r in d['parcels']:insert('parcels',r)
  used_ids={}
  def numeric_id(v,prefix):
   s=str(v)
   return int(s[len(prefix):]) if s.startswith(prefix) and s[len(prefix):].isdigit() else None
  for r in d['operations']:
   x=dict(r);n=numeric_id(x.pop('id'),'pc-op-')
   if n is not None:x['id']=n
   insert('operations',x)
   used_ids[str(r['id'])]=n if n is not None else c.execute('select last_insert_rowid()').fetchone()[0]
  for s,t in MAPPING.items():
   if s in ('parcels','operations'):continue
   prefix={'rents':'pc-rent-','supports':'pc-support-','maintenance':'pc-maint-','rentPayments':'pc-rentpay-','services':'pc-service-','servicePayments':'pc-servicepay-','bales':'pc-bale-','baleSales':'pc-balesale-','soilAnalyses':'pc-soil-'}.get(s,'')
   for r in d[s]:
    x=dict(r);rid=x.pop('id',None)
    if t=='market_prices':pass
    else:
     n=numeric_id(rid,prefix) if prefix else None
     if n is not None:x['id']=n
    if t=='rent_payments' and isinstance(x.get('rent_contract_id'),str):x['rent_contract_id']=numeric_id(x['rent_contract_id'],'pc-rent-') or x['rent_contract_id']
    if t=='bale_batches' and isinstance(x.get('harvest_operation_id'),str):x['harvest_operation_id']=used_ids.get(x['harvest_operation_id'],x['harvest_operation_id'])
    if t=='bale_sales' and isinstance(x.get('sale_operation_id'),str):x['sale_operation_id']=used_ids.get(x['sale_operation_id'],x['sale_operation_id'])
    insert(t,x)
  inputs={str(x['id']):x for x in d['inputs']}
  for m in d['stockMoves']:
   if m.get('kind')!='purchase':continue
   x=inputs.get(str(m.get('input_id')))
   if not x:raise ValueError('Satın alma girdisi bulunamadı: '+str(m.get('input_id')))
   n=numeric_id(m['id'],'pc-buy-')
   name=x.get('name','');cat=x.get('category','');item=name;detail=''
   if ' / ' in name:item,detail=name.split(' / ',1)
   r=dict(season=m.get('season') or '2026/2027',purchase_date=m.get('date'),category=cat,item=item,quantity=m.get('quantity'),unit=x.get('unit'),unit_price=m.get('unit_price',0),supplier_note=m.get('note',''),item_detail=detail)
   if n is not None:r['id']=n
   insert('stock_purchases',r)
  # Keep cancelled purchases that are absent from the mobile active-stock ledger.
  existing={int(str(m['id'])[7:]) for m in d['stockMoves'] if str(m.get('id','')).startswith('pc-buy-') and str(m['id'])[7:].isdigit()}
  for r in source.get('stock_purchases',[]):
   if r.get('is_cancelled') and r.get('id') not in existing:insert('stock_purchases',r)
  # Only source-less consumption without an operation is invalid: don't silently lose it.
  for m in d['stockMoves']:
   if m.get('kind')=='use':
    oid=m.get('source_operation_id') or m.get('stock_move_id')
    if oid is None:raise ValueError('İşleme bağlı olmayan stok tüketimi: '+str(m['id']))
    if str(oid) not in used_ids and not ('pc-op-'+str(oid)) in used_ids:raise ValueError('Stok hareketinin tarla işlemi bulunamadı: '+str(m['id']))
  bad=c.execute('pragma foreign_key_check').fetchall()
  if bad:raise ValueError('İlişkili kayıtlarda hata: '+str([tuple(x) for x in bad[:5]]))
  c.commit()

# Temporary preview is scoped to this process and cryptographically bound to bytes.
PENDING={}
def register(app,login_required):
 @app.route('/tam-yedek')
 @login_required
 def transfer_home():return render_template_string(PAGE,message=None)
 @app.route('/tam-yedek-indir')
 @login_required
 def transfer_download():
  d=export_mobile();b=json.dumps(d,ensure_ascii=False,indent=2).encode('utf-8');f=tempfile.SpooledTemporaryFile();f.write(b);f.seek(0)
  return send_file(f,as_attachment=True,download_name='Ozcan_Tarim_PC_Tam_Yedek_'+datetime.date.today().isoformat()+'.json',mimetype='application/json')
 @app.route('/tam-yedek-onizle',methods=['POST'])
 @login_required
 def transfer_preview():
  try:
   f=request.files.get('backup')
   if not f:raise ValueError('Dosya seçilmedi')
   raw=f.read(30*1024*1024+1)
   if len(raw)>30*1024*1024:raise ValueError('Dosya 30 MB sınırını aşıyor')
   d=validate(json.loads(raw.decode('utf-8-sig')))
   token=uuid.uuid4().hex;PENDING.clear();PENDING[token]=(raw,datetime.datetime.now().timestamp())
   return render_template_string(PREVIEW,name=f.filename,digest=hashlib.sha256(raw).hexdigest(),counts=[(s,len(d[s])) for s in STORES],token=token)
  except Exception as e:return render_template_string(PAGE,message='Hata: '+str(e)),400
 @app.route('/tam-yedek-uygula',methods=['POST'])
 @login_required
 def transfer_apply():
  token=request.form.get('token');p=PENDING.pop(token,None)
  if request.form.get('accept')!='yes' or not p or datetime.datetime.now().timestamp()-p[1]>900:return render_template_string(PAGE,message='Onay süresi doldu; yeniden yükleyin'),400
  raw=p[0];d=validate(json.loads(raw.decode('utf-8-sig')))
  backup_dir=DB.parent/'otomatik_db_yedekleri';backup_dir.mkdir(exist_ok=True)
  name='pc_onceki_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db';back=backup_dir/name
  with sqlite3.connect(DB) as src,sqlite3.connect(back) as dst:src.backup(dst)
  temp=DB.parent/('gecici_aktarim_'+uuid.uuid4().hex+'.db')
  try:
   shutil.copy2(back,temp)
   restore(d,temp)
   with sqlite3.connect(temp) as c:
    if c.execute('pragma integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite bütünlük testi başarısız')
   # Windows does not allow os.replace() over an open SQLite database.
   # SQLite's online backup API writes a consistent snapshot into the live
   # database without renaming its file. The destination is rolled back
   # automatically by SQLite if the backup cannot finish.
   with sqlite3.connect(temp, timeout=30) as src, sqlite3.connect(DB, timeout=30) as dst:
    dst.execute('PRAGMA busy_timeout=30000')
    src.backup(dst, pages=100, sleep=0.1)
   with sqlite3.connect(DB, timeout=30) as check:
    if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
     raise ValueError('Aktarım sonrası SQLite bütünlük kontrolü başarısız; otomatik yedeği kullanın')
   return render_template_string(PAGE,message='Aktarım tamamlandı. Önceki bilgisayar veritabanı: otomatik_db_yedekleri/'+name+'. Programı kapatıp yeniden açın.')
  except Exception as e:
   return render_template_string(PAGE,message='AKTARIM HATASI: '+str(e)+' — Otomatik önceki veritabanı yedeği: '+name+'. Verilerinizi kontrol etmeden yeniden denemeyin.'),400
  finally:
   try:
    if temp.exists():temp.unlink()
   except PermissionError:
    pass
