"""V3.3.4: Real phone->PC LAN transfer to isolated staging, never live tables."""
import json,sqlite3,hashlib,datetime
from flask import request,render_template_string,send_file
from io import BytesIO
from wifi_detail import MAP,compare
MAX=8*1024*1024
PAGE="""<!doctype html><html lang=tr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Özcan Tarım V3.3.4</title><style>body{font:16px system-ui;background:#eef4ee;padding:20px;color:#193d2b}main{max-width:820px;background:white;padding:24px;margin:auto;border-radius:12px}button{padding:12px;background:#17673f;color:white;border:0;border-radius:8px}input{padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef4ee;padding:12px}a{color:#17673f}</style><main><h2>🌾 Özcan Tarım V3.3.4</h2><h3>iPhone → PC: Güvenli aktarım alanı</h3><p>iPhone JSON yedeğini seçerek bilgisayara Wi-Fi üzerinden aktarın. Dosya, ana veritabanından <b>ayrı bir bekleme alanına</b> kaydedilir. Parsel ve faaliyet kayıtlarına dokunulmaz.</p><form method=post enctype=multipart/form-data><input type=file name=backup accept='.json,application/json' required><button>Yedeği bilgisayara aktar</button></form>{% if message %}<pre>{{message}}</pre>{% endif %}<p><a href='/wifi-transfer/son'>Son alınan yedeği indir</a> · <a href='/wifi-detay'>Ayrıntılı karşılaştırma</a></p><p><b>Henüz yapılmayan:</b> PC ana tablolarına yazma ve PC → iPhone IndexedDB'ye yazma. Bu nedenle bu sürüm tam çift yönlü eşitleme değildir.</p></main></html>"""
def register(app,login_required,db_path):
 @app.route('/wifi-transfer',methods=['GET','POST'])
 @login_required
 def transfer():
  message=''
  if request.method=='POST':
   f=request.files.get('backup')
   if not f or not f.filename.lower().endswith('.json'): message='Geçerli JSON dosyası seçin.'
   else:
    raw=f.stream.read(MAX+1)
    if len(raw)>MAX: message='Dosya 8 MB sınırını aşıyor.'
    else:
     try:
      data=json.loads(raw.decode('utf-8-sig'))
      if data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'): raise ValueError('Yedek biçimi tanınmadı')
      if not isinstance(data.get('parcels'),list) or not isinstance(data.get('operations'),list): raise ValueError('Eksik kayıt listesi')
      if any(not isinstance(data.get(k,[]),list) for k in MAP): raise ValueError('Geçersiz liste')
      with sqlite3.connect(db_path,timeout=15) as conn:
       conn.execute('CREATE TABLE IF NOT EXISTS wifi_inbox (id INTEGER PRIMARY KEY,received_at TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,format TEXT NOT NULL,record_counts TEXT NOT NULL,payload TEXT NOT NULL)')
       digest=hashlib.sha256(raw).hexdigest()
       counts={k:len(v) for k,v in data.items() if isinstance(v,list)}
       conn.execute('INSERT OR IGNORE INTO wifi_inbox(received_at,sha256,format,record_counts,payload) VALUES(?,?,?,?,?)',(datetime.datetime.now(datetime.timezone.utc).isoformat(),digest,data['format'],json.dumps(counts,ensure_ascii=False),json.dumps(data,ensure_ascii=False)))
       n=conn.execute('SELECT COUNT(*) FROM wifi_inbox').fetchone()[0]
      message='AKTARIM BAŞARILI. Yedek bilgisayarda ayrı bekleme alanına alındı.\nSHA-256: '+digest[:16]+'...\nKayıt sayıları: '+json.dumps(counts,ensure_ascii=False)+'\nToplam alınan yedek: '+str(n)+'\nAna kayıtlar değiştirilmedi.'
     except (ValueError,UnicodeError,sqlite3.Error,TypeError) as exc: message='Hata: '+str(exc)[:250]
  return render_template_string(PAGE,message=message)
 @app.get('/wifi-transfer/son')
 @login_required
 def latest():
  with sqlite3.connect(db_path) as conn:
   row=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wifi_inbox'").fetchone()
   if not row: return 'Henüz aktarım yok',404
   record=conn.execute('SELECT payload FROM wifi_inbox ORDER BY id DESC LIMIT 1').fetchone()
  if not record: return 'Henüz aktarım yok',404
  return send_file(BytesIO(record[0].encode('utf-8')),mimetype='application/json',as_attachment=True,download_name='ozcan_iphone_son_alinan_yedek.json')
