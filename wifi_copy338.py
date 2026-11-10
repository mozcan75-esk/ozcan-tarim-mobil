"""V3.3.8: real-schema, disposable SQLite copy transaction tests. Never mutate source."""
import os, sqlite3, tempfile
from flask import render_template_string, request

HTML='''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.8</title><style>body{font:16px system-ui;background:#edf4ee;color:#173d2b;padding:24px}main{max-width:900px;margin:auto;background:white;padding:24px;border-radius:14px}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}button{background:#17683e;color:white;padding:13px;border:0;border-radius:8px}.warn{background:#fff0d1;padding:14px;border-radius:8px}.ok{background:#e0f3e5;padding:14px;border-radius:8px}</style><main><h2>🌾 V3.3.8 — Gerçek SQLite kopyasında aktarım denemesi</h2><p class="warn">Bu bir <b>kopya veritabanı testidir</b>, telefonla otomatik eşitleme değildir. Ana PC veritabanına ve iPhone kayıtlarına yazılmaz. Deneme kaydı yalnızca geçici kopyaya eklenir ve kopya işlem sonunda silinir.</p><form method="post"><button>Kopyada güvenli aktarımı test et</button></form>{% if result %}<h3>Denetim sonuçları</h3><table><tr><th>Kontrol</th><th>Sonuç</th></tr>{% for label,ok,detail in result %}<tr><td>{{label}}</td><td>{{'BAŞARILI' if ok else 'BAŞARISIZ'}} — {{detail}}</td></tr>{% endfor %}</table><p class="{{'ok' if passed else 'warn'}}">{{'Kopya testleri geçti. Gerçek mobil eşitleme hâlâ uygulanmadı.' if passed else 'Bir test başarısız. Ana veritabanına yazılmadı.'}}</p>{% endif %}<p><a href="/wifi-simulasyon">Önceki simülasyon</a> · <a href="/">Ana sayfa</a></p></main></html>'''

def run_copy_test(source):
    results=[]
    def add(name,condition,detail):results.append((name,bool(condition),detail))
    with tempfile.TemporaryDirectory(prefix='ozcan_v338_') as d:
        target=os.path.join(d,'test.sqlite')
        with sqlite3.connect(source) as src,sqlite3.connect(target) as dest:
            src.backup(dest)
        db=sqlite3.connect(target)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            before=db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
            # Insert into the REAL operations schema on the disposable copy.
            parcel=db.execute('SELECT code FROM parcels LIMIT 1').fetchone()[0]
            season=db.execute('SELECT season FROM operations LIMIT 1').fetchone()[0]
            marker='V338_DISPOSABLE_TEST_ONLY'
            db.execute('BEGIN')
            db.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(season,'2026-11-05',parcel,'Deneme','Test',1,'adet',0,0,'Nötr','Test',marker))
            add('Gerçek operations tablosuna ekleme',db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==before+1,'Geçici kopyada 1 faaliyet eklendi')
            db.execute('ROLLBACK')
            add('İşlem geri alma',db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==before and db.execute('SELECT COUNT(*) FROM operations WHERE note=?',(marker,)).fetchone()[0]==0,'Kopyadaki test kaydı geri alındı')
            # Force a real CHECK constraint violation in the actual schema and verify no partial row remains.
            db.execute('BEGIN')
            try:
                db.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(season,'2026-11-05',parcel,'Deneme','Test',-1,'adet',0,0,'Nötr','Test',marker))
                rejected=False
            except sqlite3.IntegrityError:
                rejected=True
            db.execute('ROLLBACK')
            add('Geçersiz miktarı reddetme',rejected and db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==before,'Gerçek quantity > 0 kısıtı uygulandı')
            add('Kopya bütünlüğü',db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLite integrity_check: ok')
        finally:db.close()
    # Read source again to ensure untouched, even if source has been opened by other processes.
    with sqlite3.connect('file:'+os.path.abspath(source)+'?mode=ro',uri=True) as db:
        add('Ana veritabanı değişmedi',db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==before and db.execute('SELECT COUNT(*) FROM operations WHERE note=?',(marker,)).fetchone()[0]==0,'Kaynak operations tablosuna test kaydı yazılmadı')
    return results

def register(app,login_required,db_path):
    @app.route('/wifi-kopya-test',methods=['GET','POST'])
    @login_required
    def wifi_copy_test():
        result=None
        if request.method=='POST':
            try:result=run_copy_test(db_path)
            except Exception as e:result=[('Test yürütülemedi',False,str(e)[:250])]
        return render_template_string(HTML,result=result,passed=bool(result) and all(r[1] for r in result))
