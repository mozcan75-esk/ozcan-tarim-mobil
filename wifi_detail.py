"""Read-only, field-level comparison for an iPhone JSON export and desktop SQLite."""
import json, sqlite3, math, re
from collections import Counter
from flask import request, render_template_string

MAP = {
 'parcels': ('parcels','code',None),
 'operations': ('operations','id','pc-op-'),
 'maintenance': ('machine_maintenance','id','pc-maint-'),
 'supports': ('supports','id','pc-support-'),
 'rents': ('rent_contracts','id','pc-rent-'),
 'rentPayments': ('rent_payments','id','pc-rentpay-'),
 'services': ('field_service_charges','id','pc-service-'),
 'servicePayments': ('field_service_payments','id','pc-servicepay-'),
 'bales': ('bale_batches','id','pc-bale-'),
 'baleSales': ('bale_sales','id','pc-balesale-'),
 'soilAnalyses': ('soil_analyses','id','pc-soil-'),
}
# All shared stored columns are compared, except the generated primary key and
# creation timestamps (which are not business fields). No assumptions on unmatched IDs.
SKIP={'id','created_at'}

def canon(v):
 if v is None or v=='': return None
 if isinstance(v,bool): return int(v)
 if isinstance(v,(float,int)) and not isinstance(v,bool):
  return round(float(v),6) if math.isfinite(float(v)) else str(v)
 return str(v).strip()

def compare(conn, backup):
 out=[]; details=[]
 available={x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 for key,(table,pk,prefix) in MAP.items():
  mobile=backup.get(key,[])
  if not isinstance(mobile,list): raise ValueError(f'{key}: liste bekleniyor')
  if table not in available:
   out.append((key,len(mobile),'—',0,0,0,'Bilgisayarda tablo yok')); continue
  pc=[dict(r) for r in conn.execute('SELECT * FROM "'+table+'"')]
  pc_by={str(x[pk]):x for x in pc}
  matched=set(); equal=changed=only_mobile=unmatched=0
  for i,m in enumerate(mobile):
   if not isinstance(m,dict): raise ValueError(f'{key}: geçersiz kayıt')
   mid=m.get(pk)
   if pk=='code': lookup=str(mid) if mid is not None else None
   elif prefix and isinstance(mid,str) and mid.startswith(prefix) and mid[len(prefix):].isdigit(): lookup=str(int(mid[len(prefix):]))
   else: lookup=None
   if lookup is None:
    unmatched+=1
    details.append((key,str(mid or '—'),'Kimlik eşleştirilemedi','Mobil kayıt PC kimliğine güvenle bağlanamadı'))
    continue
   if lookup not in pc_by:
    only_mobile+=1
    details.append((key,str(mid),'Yalnızca iPhone','PC veritabanında karşılığı yok'))
    continue
   matched.add(lookup)
   desktop=pc_by[lookup]
   fields=(set(m)&set(desktop))-SKIP
   changes=[]
   for field in sorted(fields):
    if canon(m[field])!=canon(desktop[field]):
     changes.append(f'{field}: iPhone={str(m[field])[:90]!r} / PC={str(desktop[field])[:90]!r}')
   if changes:
    changed+=1
    details.append((key,str(mid),'Alan farkı','; '.join(changes[:12]) + ('; …' if len(changes)>12 else '')))
   else: equal+=1
  only_pc=len(pc_by)-len(matched)
  for pcid in pc_by.keys()-matched:
   details.append((key,str(pcid),'Yalnızca PC / eşleşmeyen','Mobil JSON içinde bu PC kimliği eşleşmedi'))
  out.append((key,len(mobile),len(pc),equal,changed,only_mobile+only_pc, f'Kimliği belirsiz mobil: {unmatched}' if unmatched else ''))
 # Inputs are master item definitions on iPhone, purchase transactions on desktop.
 out.append(('inputs ↔ stock_purchases',len(backup.get('inputs',[])),conn.execute('SELECT COUNT(*) FROM stock_purchases').fetchone()[0],0,0,0,'Farklı veri türleri; doğrudan karşılaştırılamaz'))
 return out,details

PAGE='''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.3</title><style>body{font:15px system-ui;background:#f3f7f3;color:#20352b;padding:20px}main{max-width:1100px;margin:auto;background:white;padding:24px;border-radius:12px}h1{font-size:24px}button{background:#18663c;color:white;padding:12px 18px;border:0;border-radius:7px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:9px;text-align:left;vertical-align:top}section{overflow:auto}.note{background:#fff2d8;padding:12px;border-radius:7px;margin:15px 0}.error{color:#a00}details{margin:12px 0}td:last-child{overflow-wrap:anywhere}small{color:#555}</style></head><body><main><h1>🌾 Özcan Tarım V3.3.3</h1><h2>iPhone–PC kayıt ve alan karşılaştırması</h2><p class="note"><b>Salt okunur:</b> Hiçbir kayıt silinmez, aktarılmaz veya güncellenmez. Yalnızca <code>pc-...</code> kimlikli aktarılan kayıtlar güvenle eşleştirilir. Mobilde sonradan oluşturulan farklı kimlikli kayıtlar ayrı işaretlenir.</p><form method="post" enctype="multipart/form-data"><label>iPhone JSON yedeği <input type="file" name="backup" accept=".json,application/json" required></label> <button>Alanları karşılaştır</button></form>{% if error %}<p class="error">{{error}}</p>{% endif %}{% if summary %}<p><small>Yedek: {{filename}}</small></p><section><table><tr><th>Tür</th><th>iPhone</th><th>PC</th><th>Alanları eşit</th><th>Farklı</th><th>Yalnızca bir tarafta / eşleşmeyen</th><th>Açıklama</th></tr>{% for r in summary %}<tr>{% for x in r %}<td>{{x}}</td>{% endfor %}</tr>{% endfor %}</table></section><details open><summary><b>Ayrıntılı farklar ({{details|length}} kayıt)</b></summary><section><table><tr><th>Tür</th><th>Kimlik</th><th>Durum</th><th>Farklı alanlar / açıklama</th></tr>{% for row in details[:400] %}<tr>{% for x in row %}<td>{{x}}</td>{% endfor %}</tr>{% endfor %}</table></section>{% if details|length>400 %}<p>İlk 400 kayıt gösteriliyor.</p>{% endif %}</details>{% endif %}<p class="note">Önemli: Bu rapor tek başına çift yönlü eşitleme için yeterli değildir. İki cihazın bağımsız oluşturduğu kayıtlar için ortak kalıcı kimlik ve çakışma yönetimi gereklidir.</p><p><a href="/">Ana sayfa</a></p></main></body></html>'''

def register(app, login_required, db_path):
 @app.route('/wifi-detay',methods=['GET','POST'])
 @login_required
 def wifi_detail():
  summary=details=None;error=None;filename=''
  if request.method=='POST':
   f=request.files.get('backup')
   if not f or not f.filename.lower().endswith('.json'): error='JSON yedeği seçin.'
   else:
    raw=f.stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024: error='Dosya 8 MB sınırını aşıyor.'
    else:
     try:
      data=json.loads(raw.decode('utf-8-sig'))
      if not isinstance(data,dict) or not isinstance(data.get('parcels'),list): raise ValueError('Geçerli Özcan Tarım yedeği değil')
      with sqlite3.connect('file:'+db_path+'?mode=ro',uri=True) as c:
       c.row_factory=sqlite3.Row
       summary,details=compare(c,data)
      filename=f.filename
     except (ValueError,UnicodeError,sqlite3.Error) as e: error='Karşılaştırma hatası: '+str(e)[:180]
  return render_template_string(PAGE,summary=summary,details=details,error=error,filename=filename)
