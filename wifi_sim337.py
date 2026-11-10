"""V3.3.7: read-only source inspection + isolated in-memory sync simulation.
No writes to application database, including on POST.
"""
import collections
import json
import sqlite3
from flask import render_template_string, request

PAGE = '''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.7</title><style>body{font:16px system-ui;background:#edf4ee;color:#173d2b;padding:18px}main{max-width:960px;margin:auto;background:white;border-radius:14px;padding:24px}table{width:100%;border-collapse:collapse}td,th{padding:11px;border-bottom:1px solid #ddd;text-align:left}button{background:#17683e;color:white;padding:12px 18px;border:0;border-radius:8px}.note{background:#fff1d7;padding:14px;border-radius:8px}.good{background:#e0f2e6;padding:14px;border-radius:8px}.bad{color:#9d1b1b}code{overflow-wrap:anywhere}</style><main><h2>🌾 Özcan Tarım V3.3.7 — Yalıtılmış eşitleme simülasyonu</h2><p class="note"><b>Gerçek eşitleme değildir.</b> Senaryolar yalnızca RAM'deki geçici SQLite veritabanında çalışır. Ana veritabanına faaliyet, stok alımı veya tüketimi yazılmaz. Mevcut iPhone kayıtları değiştirilmez.</p><form method="post"><button>Simülasyonu çalıştır</button></form>{% if error %}<p class="bad">{{error}}</p>{% endif %}{% if results %}<h3>Senaryo testleri</h3><table><tr><th>Test</th><th>Sonuç</th><th>Açıklama</th></tr>{% for x in results %}<tr><td>{{x.name}}</td><td>{{'BAŞARILI' if x.ok else 'BAŞARISIZ'}}</td><td>{{x.detail}}</td></tr>{% endfor %}</table><p class="{{'good' if all_ok else 'note'}}">{{'Tüm sentetik testler geçti.' if all_ok else 'Bir veya daha fazla sentetik test başarısız.'}} Bunlar üretim veritabanına aktarımın hazır olduğunu kanıtlamaz.</p>{% if actual %}<h3>Son alınan iPhone yedeği (salt okunur)</h3><p>SHA-256: <code>{{actual.sha}}</code></p><p>Faaliyet: {{actual.ops}} · Stok hareketi: {{actual.moves}} · PC kökenli faaliyet: {{actual.pc}} · Mobil kimlikli faaliyet adayı: {{actual.mobile}} · Alım: {{actual.purchases}} · Kaynaksız tüketim: {{actual.orphans}}</p><p class="note">Mobil adayların muhasebe ve kaynak kimliği doğrulanmadığından bu ekranda gerçek aktarım yapılmaz.</p>{% else %}<p>Gerçek yedek analizi için önce <a href="/wifi-transfer">Wi-Fi aktarım ekranından</a> yedek yükleyin.</p>{% endif %}{% endif %}<p><a href="/wifi-stok-denetim">Önceki denetim</a> · <a href="/">Ana sayfa</a></p></main></html>'''

def simulate():
    """Exercise atomic op+stock handling, replay, rollback, and separate purchases."""
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE ops (id TEXT PRIMARY KEY, parcel TEXT NOT NULL)')
    db.execute('CREATE TABLE moves (id TEXT PRIMARY KEY, op_id TEXT REFERENCES ops(id), item TEXT NOT NULL, qty REAL NOT NULL CHECK(qty>0))')
    db.execute('CREATE TABLE inventory (item TEXT PRIMARY KEY, qty REAL NOT NULL CHECK(qty>=0))')
    db.execute('CREATE TABLE purchases (id TEXT PRIMARY KEY, item TEXT NOT NULL, qty REAL NOT NULL CHECK(qty>0))')
    db.execute('INSERT INTO inventory VALUES (?,?)',('Motorin',100.0))
    db.commit()
    def apply(op_id, move_id, qty, item='Motorin'):
        with db:
            if db.execute('SELECT 1 FROM ops WHERE id=?',(op_id,)).fetchone():
                raise ValueError('Mükerrer faaliyet kimliği')
            if db.execute('SELECT 1 FROM moves WHERE id=?',(move_id,)).fetchone():
                raise ValueError('Mükerrer stok hareketi kimliği')
            available=db.execute('SELECT qty FROM inventory WHERE item=?',(item,)).fetchone()
            if not available or available[0] < qty: raise ValueError('Yetersiz stok')
            db.execute('INSERT INTO ops VALUES (?,?)',(op_id,'TEST'))
            db.execute('INSERT INTO moves VALUES (?,?,?,?)',(move_id,op_id,item,qty))
            db.execute('UPDATE inventory SET qty=qty-? WHERE item=?',(qty,item))
    results=[]
    def check(name,ok,detail):results.append(dict(name=name,ok=bool(ok),detail=detail))
    apply('mobile-op-A','mobile-move-A',5)
    check('Faaliyet + tüketim birlikte',db.execute('SELECT qty FROM inventory').fetchone()[0]==95 and db.execute('SELECT count(*) FROM ops').fetchone()[0]==1,'5 litre tüketim; faaliyet ve hareket tek işlemde')
    try:apply('mobile-op-A','mobile-move-A',5)
    except ValueError:pass
    check('Tekrar aktarım engeli',db.execute('SELECT qty FROM inventory').fetchone()[0]==95 and db.execute('SELECT count(*) FROM moves').fetchone()[0]==1,'Aynı kimlik tekrar stok düşürmedi')
    try:apply('mobile-op-B','mobile-move-B',999)
    except ValueError:pass
    check('Yetersiz stokta geri alma',db.execute('SELECT qty FROM inventory').fetchone()[0]==95 and not db.execute("SELECT 1 FROM ops WHERE id='mobile-op-B'").fetchone(),'İşlem ve stok değişmedi')
    try:
        with db:
            db.execute("INSERT INTO ops VALUES ('mobile-op-C','TEST')")
            db.execute("INSERT INTO moves VALUES ('mobile-move-A','mobile-op-C','Motorin',2)")
    except sqlite3.IntegrityError:pass
    check('Hareket çakışmasında atomiklik',not db.execute("SELECT 1 FROM ops WHERE id='mobile-op-C'").fetchone(),'Hareket çakışması faaliyeti de geri aldı')
    try:
        with db:
            if not db.execute("SELECT 1 FROM ops WHERE id='missing'").fetchone():raise ValueError('Kaynak faaliyet bulunamadı')
    except ValueError:pass
    check('Kaynaksız hareket reddi',db.execute('SELECT count(*) FROM moves').fetchone()[0]==1,'Faaliyet bağlantısı olmayan tüketim eklenmedi')
    with db:
        db.execute("INSERT INTO purchases VALUES ('mobile-buy-A','Motorin',20)")
        db.execute("UPDATE inventory SET qty=qty+20 WHERE item='Motorin'")
    check('Alım ayrı işlenir',db.execute('SELECT qty FROM inventory').fetchone()[0]==115 and db.execute('SELECT count(*) FROM ops').fetchone()[0]==1,'20 litre alım faaliyete bağlanmadan işlendi')
    db.close()
    return results

def actual_snapshot(db_path):
    conn=sqlite3.connect('file:'+db_path+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wifi_inbox'").fetchone():return None
        row=conn.execute('SELECT sha256,payload FROM wifi_inbox ORDER BY id DESC LIMIT 1').fetchone()
        if not row:return None
        data=json.loads(row['payload'])
        if data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'):raise ValueError('Yedek biçimi tanınmadı')
        ops=data.get('operations');moves=data.get('stockMoves')
        if not isinstance(ops,list) or not isinstance(moves,list):raise ValueError('Faaliyet veya stok hareketi listesi eksik')
        return dict(sha=row['sha256'],ops=len(ops),moves=len(moves),pc=sum(isinstance(o,dict) and str(o.get('id','')).startswith('pc-op-') for o in ops),mobile=sum(isinstance(o,dict) and not str(o.get('id','')).startswith('pc-op-') for o in ops),purchases=sum(isinstance(m,dict) and m.get('kind')=='purchase' for m in moves),orphans=sum(isinstance(m,dict) and m.get('kind')=='use' and m.get('source_operation_id') is None for m in moves))
    finally:conn.close()

def register(app,login_required,db_path):
    @app.route('/wifi-simulasyon',methods=['GET','POST'])
    @login_required
    def wifi_simulation():
        results=None;actual=None;error=None
        if request.method=='POST':
            try:
                results=simulate()
                actual=actual_snapshot(db_path)
            except (ValueError,sqlite3.Error,KeyError,TypeError) as exc:error='Simülasyon raporu hazırlanamadı: '+str(exc)[:220]
        return render_template_string(PAGE,results=results,actual=actual,error=error,all_ok=bool(results) and all(x['ok'] for x in results))
