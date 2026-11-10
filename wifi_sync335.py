"""V3.3.5: cautious import of NEW mobile-origin operations, explicit preview/confirmation.
No stock/harvest/sale reconciliation; no modification of pre-existing rows.
"""
import json, sqlite3, os, datetime, re, hashlib
from io import BytesIO
from flask import request, render_template_string

PAGE='''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.5</title><style>body{font:16px system-ui;background:#edf4ee;color:#173d2b;padding:16px}main{max-width:950px;background:white;padding:22px;margin:auto;border-radius:12px}button{background:#17683e;color:white;border:0;border-radius:7px;padding:12px;margin:7px 0}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap} .warn{background:#fff1d7;padding:12px} .ok{background:#e0f3e6;padding:12px}</style><main><h2>🌾 Özcan Tarım V3.3.5 — Yeni mobil faaliyetleri aktar</h2><p class="warn">Bu ekran <b>tam çift yönlü eşitleme değildir</b>. Yalnızca iPhone'da oluşturulmuş, kimliği PC'den gelmeyen yeni <b>tarla faaliyetlerini</b> kontrollü olarak PC'ye ekler. Stok, hasat, satış, icar, parsel ve mevcut kayıtlar değişmez. Bu nedenle stok etkisi olan faaliyetleri şimdilik otomatik aktarmayın.</p><p>Önce <a href="/wifi-transfer">iPhone yedeğini bekleme alanına yükleyin</a>. Sonra aşağıdaki önizlemeyi kullanın.</p><form method="post"><input type="hidden" name="action" value="preview"><button>Son yedeği incele</button></form>{% if result %}<p class="ok">{{result}}</p>{% endif %}{% if error %}<p class="warn">{{error}}</p>{% endif %}{% if digest %}<p>Yedek SHA-256: <code>{{digest}}</code></p><p>Yeni faaliyet: <b>{{new|length}}</b> · Zaten aktarılmış: <b>{{done}}</b> · PC kökenli: <b>{{origin}}</b> · Riskli / inceleme gerektiren: <b>{{blocked|length}}</b></p>{% if new %}<h3>Aktarılabilir kayıtlar</h3><table><tr><th>Mobil kimlik</th><th>Tarih</th><th>Parsel</th><th>Tür</th><th>Tutar</th></tr>{% for x in new[:100] %}<tr><td>{{x.id}}</td><td>{{x.op_date}}</td><td>{{x.parcel_code}}</td><td>{{x.op_type}}</td><td>{{x.amount}}</td></tr>{% endfor %}</table><p class="warn">Onaylamadan önce PC veritabanının otomatik yedeği alınır. Bu işlem yalnızca yukarıdaki güvenli adayları ekler.</p><form method="post"><input type="hidden" name="action" value="commit"><input type="hidden" name="digest" value="{{digest}}"><label><input type="checkbox" name="approve" value="yes" required> Listeyi kontrol ettim, yeni kayıtların PC'ye eklenmesini onaylıyorum.</label><p><button>Yedekle ve {{new|length}} yeni kaydı ekle</button></p></form>{% endif %}{% if blocked %}<h3>Otomatik aktarılmayanlar</h3><table><tr><th>Kimlik</th><th>Neden</th></tr>{% for id,reason in blocked[:100] %}<tr><td>{{id}}</td><td>{{reason}}</td></tr>{% endfor %}</table>{% endif %}{% endif %}<p><a href="/">Ana sayfa</a></p></main>'''
COLUMNS=('season','op_date','parcel_code','op_type','item','quantity','unit','unit_price','amount','direction','category','note','is_cancelled','item_detail')
# Operations that can alter inventories/derived ledgers require dedicated accounting adapters.
RISK_TYPES={'Ekim','Gübreleme','İlaçlama','Yakıt','Hasat','Satış','İcar/Kiralama','Balya','Balyalama'}

def candidates(conn, data):
 conn.execute('CREATE TABLE IF NOT EXISTS wifi_import_map (mobile_id TEXT PRIMARY KEY,pc_id INTEGER NOT NULL UNIQUE,imported_at TEXT NOT NULL)')
 existing={r[0] for r in conn.execute('SELECT mobile_id FROM wifi_import_map')}
 pcids={r[0] for r in conn.execute('SELECT id FROM operations')}
 parcels={r[0] for r in conn.execute('SELECT code FROM parcels')}
 new=[];blocked=[];done=origin=0;seen=set()
 for op in data.get('operations',[]):
  if not isinstance(op,dict): blocked.append(('?', 'Geçersiz kayıt'));continue
  mid=op.get('id'); sid=str(mid)
  if not isinstance(mid,str) or not mid or len(mid)>150:blocked.append((sid,'Geçersiz kalıcı mobil kimliği'));continue
  if sid in seen:blocked.append((sid,'Yedekte yinelenen kimlik'));continue
  seen.add(sid)
  if re.fullmatch(r'pc-op-\d+',sid):
   origin+=1
   if int(sid[6:]) not in pcids:blocked.append((sid,'PC kökenli kimlik PC içinde yok; elle inceleyin'))
   continue
  if sid in existing:done+=1;continue
  if op.get('op_type') in RISK_TYPES or op.get('item') in ('Motorin','Tohum','Gübre'):
   blocked.append((sid,'Stok / hasat / satış etkisi olabilecek işlem; ayrı muhasebe eşleştirmesi gerekli'));continue
  if op.get('parcel_code') not in parcels and op.get('parcel_code') not in (None,''):
   blocked.append((sid,'Parsel PC içinde bulunamadı'));continue
  if op.get('direction') not in ('Gelir','Gider','Nötr') or op.get('unit') not in ('L','kg','adet','da','saat','TL'):
   blocked.append((sid,'Yön veya birim doğrulanamadı'));continue
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(op.get('op_date',''))):blocked.append((sid,'Tarih biçimi hatalı'));continue
  try:
   datetime.date.fromisoformat(op['op_date'])
   qty=float(op.get('quantity'));amount=float(op.get('amount'))
   if not (0<qty<1e9 and 0<=amount<1e12):raise ValueError()
   if op.get('unit_price') is not None and not (0<=float(op['unit_price'])<1e12):raise ValueError()
  except (TypeError,ValueError,OverflowError):blocked.append((sid,'Miktar / tutar geçersiz'));continue
  if not all(isinstance(op.get(k),str) and op[k].strip() for k in ('season','op_type','item')):
   blocked.append((sid,'Zorunlu alan eksik'));continue
  new.append(op)
 return new,blocked,done,origin

def register(app,login_required,db_path):
 @app.route('/wifi-yeni-islemler',methods=['GET','POST'])
 @login_required
 def wifi_new_ops():
  kw={'new':[],'blocked':[],'done':0,'origin':0,'digest':None,'result':None,'error':None}
  if request.method!='POST':return render_template_string(PAGE,**kw)
  try:
   with sqlite3.connect(db_path,timeout=20) as conn:
    conn.row_factory=sqlite3.Row
    row=conn.execute("SELECT name FROM sqlite_master WHERE name='wifi_inbox'").fetchone()
    if not row:raise ValueError('Önce /wifi-transfer sayfasından yedek yükleyin.')
    inbox=conn.execute('SELECT sha256,payload FROM wifi_inbox ORDER BY id DESC LIMIT 1').fetchone()
    if not inbox:raise ValueError('Bekleme alanında yedek yok.')
    digest=inbox['sha256']; data=json.loads(inbox['payload'])
    if data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'):raise ValueError('Desteklenmeyen yedek')
    kw['digest']=digest
    new,blocked,done,origin=candidates(conn,data)
    kw.update(new=new,blocked=blocked,done=done,origin=origin)
    if request.form.get('action')=='commit':
     if request.form.get('approve')!='yes' or request.form.get('digest')!=digest:raise ValueError('Onay veya yedek kimliği geçersiz.')
     # SQLite online backup before any business row changes.
     backup_dir=os.path.join(os.path.dirname(db_path),'backups');os.makedirs(backup_dir,exist_ok=True)
     stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
     backup_path=os.path.join(backup_dir,'wifi335_once_'+stamp+'.db')
     with sqlite3.connect(backup_path) as dst:conn.backup(dst)
     conn.execute('BEGIN IMMEDIATE')
     # Recheck after locking, so repeated requests do not duplicate records.
     new,blocked,done,origin=candidates(conn,data)
     for op in new:
      values=[op.get(c) for c in COLUMNS]
      values[COLUMNS.index('is_cancelled')]=int(bool(op.get('is_cancelled',0)))
      cur=conn.execute('INSERT INTO operations ('+','.join(COLUMNS)+') VALUES ('+','.join('?' for _ in COLUMNS)+')',values)
      conn.execute('INSERT INTO wifi_import_map(mobile_id,pc_id,imported_at) VALUES(?,?,?)',(op['id'],cur.lastrowid,datetime.datetime.now(datetime.timezone.utc).isoformat()))
     conn.commit()
     kw['result']=f'{len(new)} yeni faaliyet PC veritabanına eklendi. Ön yedek: backups/{os.path.basename(backup_path)}. Stok ve diğer tablolar değiştirilmedi.'
     kw['new']=[];kw['done']=done+len(new)
  except (ValueError,sqlite3.Error,TypeError,OSError) as exc:kw['error']='İşlem durduruldu: '+str(exc)[:220]
  return render_template_string(PAGE,**kw)
