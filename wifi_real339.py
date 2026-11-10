"""V3.3.9: transactional phone -> PC import of NEW stock-consuming operations.
Only explicit approval, immutable source IDs, and matching stockMoves. No automatic reverse sync.
"""
import os, json, re, math, sqlite3, datetime, hashlib
from flask import request, render_template_string

PAGE='''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.9</title><style>body{font:16px system-ui;background:#edf4ee;color:#173d2b;padding:18px}main{max-width:1020px;margin:auto;background:white;border-radius:12px;padding:24px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:9px;border-bottom:1px solid #ddd}button{padding:12px;background:#17683e;color:white;border:0;border-radius:7px}.warn{padding:13px;background:#fff1d7}.ok{padding:13px;background:#e1f3e7}code{overflow-wrap:anywhere}</style><main><h2>Özcan Tarım V3.3.9 — Gerçek iPhone → PC aktarımı</h2><p class="warn">Bu işlem yalnızca <b>yeni mobil faaliyet + doğrulanmış stok tüketimini</b> PC'nin gerçek <code>operations</code> tablosuna tek işlemde yazar. PC stok tüketimi bu tablodan hesaplanır; aynı tüketim ikinci kez eklenmez. Hasat, satış, icar, stok alımı, iptal, mevcut kayıt güncellemesi ve PC → iPhone aktarımı bu sürümde engellidir. Önce her iki cihazın yedeğini alın.</p><p>Önce <a href="/wifi-transfer">iPhone JSON yedeğini yükleyin</a>.</p><form method="post"><input type="hidden" name="action" value="preview"><button>Yeni kayıtları incele</button></form>{% if error %}<p class="warn">{{error}}</p>{% endif %}{% if message %}<p class="ok">{{message}}</p>{% endif %}{% if digest %}<p>Yedek SHA-256: <code>{{digest}}</code></p><p>Aktarılabilir: <b>{{ready|length}}</b> · Engellenen: <b>{{blocked|length}}</b> · Daha önce aktarılan: <b>{{done}}</b> · PC kökenli: <b>{{origin}}</b></p>{% if ready %}<table><tr><th>Mobil kimlik</th><th>Parsel</th><th>İşlem</th><th>Malzeme</th><th>Miktar</th></tr>{% for o in ready %}<tr><td>{{o.id}}</td><td>{{o.parcel_code}}</td><td>{{o.op_type}}</td><td>{{o.item}}</td><td>{{o.quantity}} {{o.unit}}</td></tr>{% endfor %}</table><form method="post"><input type="hidden" name="action" value="commit"><input type="hidden" name="digest" value="{{digest}}"><p><label><input type="checkbox" name="approve" value="yes" required> Yedeğimi aldım ve listedeki kayıtları PC'ye eklemeyi onaylıyorum.</label></p><button>Yedek al ve {{ready|length}} kaydı PC'ye işle</button></form>{% endif %}{% if blocked %}<h3>Engellenen kayıtlar</h3><table><tr><th>Kimlik</th><th>Neden</th></tr>{% for id,reason in blocked[:100] %}<tr><td>{{id}}</td><td>{{reason}}</td></tr>{% endfor %}</table>{% endif %}{% endif %}<p><a href="/wifi-stok-denetim">Stok denetimi</a> · <a href="/">Ana sayfa</a></p></main>'''
COLUMNS=('season','op_date','parcel_code','op_type','item','quantity','unit','unit_price','amount','direction','category','note','is_cancelled','item_detail')
DISALLOWED={'Hasat','Satış','İcar/Kiralama','Balya','Balyalama','Yakıt'}
def num(x):
 if isinstance(x,bool): raise ValueError('Sayı hatalı')
 v=float(x)
 if not math.isfinite(v) or v<0 or v>1e11:raise ValueError('Sayı sınır dışı')
 return v

def plan(conn,data):
 if not isinstance(data.get('operations'),list) or not isinstance(data.get('stockMoves'),list) or not isinstance(data.get('inputs'),list):raise ValueError('Mobil yedekte faaliyet, stok hareketi veya girdi tanımları eksik')
 conn.execute('CREATE TABLE IF NOT EXISTS wifi_real_import_map (mobile_id TEXT PRIMARY KEY, pc_id INTEGER NOT NULL UNIQUE, fingerprint TEXT NOT NULL, imported_at TEXT NOT NULL)')
 mapped={r[0]:r[1] for r in conn.execute('SELECT mobile_id,fingerprint FROM wifi_real_import_map')}
 pcids={r[0] for r in conn.execute('SELECT id FROM operations')}
 parcels={r[0] for r in conn.execute('SELECT code FROM parcels')}
 inputs={str(i['id']):i for i in data['inputs'] if isinstance(i,dict) and 'id' in i}
 # PC stores stock uses in operations, not a separate stockMoves table.
 moves={}
 for m in data['stockMoves']:
  if not isinstance(m,dict) or m.get('kind')!='use':continue
  sid=m.get('source_operation_id')
  if sid is not None:moves.setdefault(str(sid),[]).append(m)
 ready=[];blocked=[];done=origin=0;seen=set()
 for op in data['operations']:
  if not isinstance(op,dict):blocked.append(('?','Bozuk faaliyet'));continue
  mid=op.get('id');sid=str(mid)
  if not isinstance(mid,str) or not 1<=len(mid)<=150 or sid in seen:blocked.append((sid,'Geçersiz veya tekrarlanan mobil kimliği'));continue
  seen.add(sid)
  if re.fullmatch(r'pc-op-\d+',sid):
   origin+=1
   if int(sid[6:]) not in pcids:blocked.append((sid,'PC kökenli kayıt PC’de bulunamadı'))
   continue
  if sid in mapped:
   fingerprint=hashlib.sha256(json.dumps(op,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   if fingerprint!=mapped[sid]:blocked.append((sid,'Daha önce aktarılmış kayıt mobilde değiştirilmiş; çakışma'))
   else:done+=1
   continue
  try:
   if op.get('op_type') in DISALLOWED or op.get('direction')!='Gider' or op.get('is_cancelled') not in (None,0,False):raise ValueError('Bu işlem türü / iptal henüz desteklenmiyor')
   if op.get('parcel_code') not in parcels:raise ValueError('Parsel bulunamadı')
   if not all(isinstance(op.get(k),str) and op[k].strip() for k in ('season','op_type','item')):raise ValueError('Zorunlu alan eksik')
   datetime.date.fromisoformat(op['op_date'])
   qty=num(op['quantity']);amount=num(op['amount']);price=num(op.get('unit_price') or 0)
   if qty<=0:raise ValueError('Miktar sıfır')
   unit=op.get('unit')
   if unit not in ('L','kg','adet','da','saat','TL'):raise ValueError('Birim desteklenmiyor')
   linked=moves.get(sid,[])
   if not linked and op.get('stock_move_id'):
    linked=[m for m in data['stockMoves'] if isinstance(m,dict) and m.get('kind')=='use' and str(m.get('id'))==str(op['stock_move_id'])]
   if len(linked)!=1:raise ValueError('Faaliyete bağlı tek stok tüketimi bulunamadı; çoklu malzeme henüz desteklenmiyor')
   move=linked[0];inp=inputs.get(str(move.get('input_id')))
   if not inp:raise ValueError('Malzeme tanımı bulunamadı')
   if abs(num(move.get('quantity'))-qty)>0.00001:raise ValueError('Faaliyet ve stok hareketi miktarları farklı')
   if move.get('parcel_code') not in (None,'',op['parcel_code']):raise ValueError('Stok hareketi parseli farklı')
   if move.get('date') not in (None,'',op['op_date']):raise ValueError('Stok hareketi tarihi farklı')
   # Explicit stock-item match; no heuristic stock name conversions.
   if inp.get('name')!=op['item'] or inp.get('unit')!=unit:raise ValueError('Stok malzemesi / birimi faaliyetle eşleşmedi')
   if abs(num(move.get('total',amount))-amount)>0.02:raise ValueError('Stok maliyeti ile faaliyet tutarı farklı')
   ready.append(op)
  except (KeyError,TypeError,ValueError,OverflowError) as exc:blocked.append((sid,str(exc)[:180]))
 return ready,blocked,done,origin

def register(app,login_required,db_path):
 @app.route('/wifi-gercek-esitle',methods=['GET','POST'])
 @login_required
 def wifi_real_sync():
  kw=dict(ready=[],blocked=[],done=0,origin=0,digest=None,error=None,message=None)
  if request.method=='GET':return render_template_string(PAGE,**kw)
  try:
   with sqlite3.connect(db_path,timeout=20) as conn:
    conn.execute('PRAGMA foreign_keys=ON');conn.row_factory=sqlite3.Row
    inbox=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wifi_inbox'").fetchone()
    if not inbox:raise ValueError('Önce /wifi-transfer üzerinden mobil yedeği yükleyin')
    row=conn.execute('SELECT sha256,payload FROM wifi_inbox ORDER BY id DESC LIMIT 1').fetchone()
    if not row:raise ValueError('Bekleme alanı boş')
    digest=row['sha256'];data=json.loads(row['payload'])
    if data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'):raise ValueError('Bilinmeyen yedek biçimi')
    kw['digest']=digest
    ready,blocked,done,origin=plan(conn,data)
    conn.commit()  # finish metadata table creation before BEGIN IMMEDIATE
    kw.update(ready=ready,blocked=blocked,done=done,origin=origin)
    if request.form.get('action')=='commit':
     if request.form.get('approve')!='yes' or request.form.get('digest')!=digest:raise ValueError('Yedek kimliği / onay uyuşmuyor')
     if blocked:raise ValueError('Engellenen mobil kayıtlar var. Karışık yedeği otomatik işlemiyoruz; önce nedenleri çözün.')
     if not ready:raise ValueError('Yeni aktarılabilir kayıt yok')
     backup_dir=os.path.join(os.path.dirname(db_path),'backups');os.makedirs(backup_dir,exist_ok=True)
     filename='wifi339_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db'
     with sqlite3.connect(os.path.join(backup_dir,filename)) as dst:conn.backup(dst)
     conn.execute('BEGIN IMMEDIATE')
     ready2,blocked2,_,_=plan(conn,data)
     if blocked2 or [o['id'] for o in ready2]!=[o['id'] for o in ready]:raise ValueError('Onaydan sonra adaylar değişti, işlem iptal edildi')
     # Stock is calculated from operations in this PC schema. One operation = one stock use.
     for op in ready2:
      vals=[op.get(c) for c in COLUMNS];vals[COLUMNS.index('is_cancelled')]=0
      cur=conn.execute('INSERT INTO operations('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+')',vals)
      fingerprint=hashlib.sha256(json.dumps(op,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
      conn.execute('INSERT INTO wifi_real_import_map(mobile_id,pc_id,fingerprint,imported_at) VALUES(?,?,?,?)',(op['id'],cur.lastrowid,fingerprint,datetime.datetime.now(datetime.timezone.utc).isoformat()))
     conn.commit()
     kw.update(message=f'{len(ready2)} kayıt PC’ye yazıldı. Ön yedek: backups/{filename}.',ready=[],done=done+len(ready2))
  except (ValueError,TypeError,KeyError,sqlite3.Error,OSError) as exc:kw['error']='Aktarım durduruldu: '+str(exc)[:250]
  return render_template_string(PAGE,**kw)
