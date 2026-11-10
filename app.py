import math
import os, sqlite3, secrets, json, re
from datetime import date, datetime
from functools import wraps
from flask import Flask, g, request, redirect, url_for, session, render_template, flash, abort

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('OZCAN_TARIM_DB', os.path.join(BASE_DIR, 'ozcan_tarim.db'))
APP_PASSWORD = os.environ.get('OZCAN_TARIM_PASSWORD', '')
app = Flask(__name__)
app.secret_key = os.environ.get('OZCAN_TARIM_SECRET', 'change-this-secret-before-deployment-' + secrets.token_hex(8))
SEASONS = ['2026/2027', '2027/2028', '2028/2029', '2029/2030', '2030/2031']
OP_TYPES = ['Pulluk Sürme','Kazayağı Sürme','Tırmık Sürme','Ekim','Gübreleme','İlaçlama','Yakıt','Sulama','Hasat','Satış','İcar/Kiralama','İşçilik','Nakliye','Diğer']
UNITS = ['L','kg','adet','da','saat','TL']

def normalize_unit(unit):
    u=(unit or '').strip().casefold()
    if u in ('lt','l','litre','liter','litres'): return 'L'
    if u in ('kg','kilogram','kilograms'): return 'kg'
    if u in ('tl','₺'): return 'TL'
    if u in ('adet','da','saat'): return u
    return (unit or '').strip()
def tr_num(value, decimals=2):
    """Display numbers in Turkish notation: 1.234,56 (without changing stored values)."""
    try:
        formatted = f"{float(value):,.{int(decimals)}f}"
    except (ValueError, TypeError, OverflowError):
        return '—'
    return formatted.replace(',', '#').replace('.', ',').replace('#', '.')

app.jinja_env.globals['tr_num'] = tr_num

CATEGORIES = ['Mazot','Tohum','Gübre','İlaç','İşçilik','Makine','İcar/Kiralama','Nakliye','Diğer']

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(exc):
    conn = g.pop('db', None)
    if conn is not None: conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS parcels (
      code TEXT PRIMARY KEY, name TEXT NOT NULL, area_m2 REAL NOT NULL CHECK(area_m2>0),
      property_type TEXT, soil_type TEXT, irrigation TEXT, neighborhood TEXT, ada TEXT, parcel_no TEXT,
      owner TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS operations (
      id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, op_date TEXT NOT NULL,
      parcel_code TEXT REFERENCES parcels(code), op_type TEXT NOT NULL, item TEXT NOT NULL,
      quantity REAL NOT NULL CHECK(quantity>0), unit TEXT NOT NULL, unit_price REAL CHECK(unit_price>=0),
      amount REAL NOT NULL CHECK(amount>=0), direction TEXT NOT NULL CHECK(direction IN ('Gelir','Gider','Nötr')),
      category TEXT, note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS stock_purchases (
      id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, purchase_date TEXT NOT NULL,
      category TEXT NOT NULL, item TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity>0),
      unit TEXT NOT NULL, unit_price REAL NOT NULL CHECK(unit_price>=0), supplier_note TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS machine_maintenance (
      id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, service_date TEXT NOT NULL,
      machine TEXT NOT NULL, work_hours REAL, description TEXT NOT NULL, cost REAL NOT NULL CHECK(cost>=0), note TEXT
    );
    CREATE TABLE IF NOT EXISTS supports (
      id INTEGER PRIMARY KEY AUTOINCREMENT, payment_date TEXT NOT NULL, season TEXT NOT NULL,
      support_type TEXT NOT NULL, description TEXT NOT NULL, crop TEXT, amount REAL NOT NULL CHECK(amount>=0), note TEXT
    );
    CREATE TABLE IF NOT EXISTS rent_contracts (
      id INTEGER PRIMARY KEY AUTOINCREMENT, landlord TEXT NOT NULL, parcel_code TEXT NOT NULL REFERENCES parcels(code),
      season TEXT NOT NULL, start_date TEXT, end_date TEXT, area_da REAL NOT NULL CHECK(area_da>0),
      rate_per_da REAL NOT NULL CHECK(rate_per_da>=0), total_amount REAL NOT NULL CHECK(total_amount>=0), due_note TEXT,
      UNIQUE(parcel_code, season, landlord, start_date)
    );
    CREATE INDEX IF NOT EXISTS idx_ops_season ON operations(season);
    CREATE INDEX IF NOT EXISTS idx_ops_item ON operations(item);
    CREATE INDEX IF NOT EXISTS idx_stock_item ON stock_purchases(item);
    ''')
    conn.commit(); conn.close()

init_db()

def migrate_v130():
    conn=sqlite3.connect(DB_PATH)
    try:
        for table in ('operations','stock_purchases'):
            cols={r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            if 'item_detail' not in cols:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN item_detail TEXT')
        conn.commit()
    finally:
        conn.close()
migrate_v130()

def migrate_v180():
    conn=sqlite3.connect(DB_PATH)
    try:
        cols={r[1] for r in conn.execute("PRAGMA table_info(parcels)")}
        if 'owned_area_da' not in cols:
            conn.execute("ALTER TABLE parcels ADD COLUMN owned_area_da REAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS parcel_season_areas(
          parcel_code TEXT NOT NULL REFERENCES parcels(code),
          season TEXT NOT NULL,
          worked_area_da REAL NOT NULL CHECK(worked_area_da>0),
          PRIMARY KEY(parcel_code,season));
        CREATE TABLE IF NOT EXISTS soil_analyses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          parcel_code TEXT NOT NULL REFERENCES parcels(code),
          analysis_date TEXT NOT NULL,
          laboratory TEXT,ph REAL,organic_matter REAL,
          phosphorus REAL,potassium REAL,lime REAL,ec REAL,notes TEXT);
        """)
        conn.commit()
    finally: conn.close()
migrate_v180()

def migrate_v189():
    """Lease use is a seasonal area, independent from rent-payment contracts.
    Seed the user's explicitly confirmed P010 share once, without overwriting
    subsequent manual edits or existing data.
    """
    conn=sqlite3.connect(DB_PATH)
    try:
        cols={r[1] for r in conn.execute('PRAGMA table_info(parcel_season_areas)')}
        if 'leased_area_da' not in cols:
            conn.execute('ALTER TABLE parcel_season_areas ADD COLUMN leased_area_da REAL NOT NULL DEFAULT 0')
            row=conn.execute("SELECT area_m2,owned_area_da FROM parcels WHERE code='P010' AND active=1").fetchone()
            if row and row[1] is not None and abs(float(row[0])/1000-36.704)<0.001 and abs(float(row[1])-22)<0.001:
                conn.execute("UPDATE parcel_season_areas SET leased_area_da=14.704 WHERE parcel_code='P010' AND season='2026/2027'")
        conn.commit()
    finally:conn.close()
migrate_v189()

def migrate_v182():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS field_activities(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          season TEXT NOT NULL,activity_date TEXT NOT NULL,
          parcel_code TEXT NOT NULL REFERENCES parcels(code),
          activity_type TEXT NOT NULL,area_da REAL NOT NULL CHECK(area_da>0),
          note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cols={r[1] for r in conn.execute('PRAGMA table_info(operations)')}
        if 'activity_id' not in cols:
            conn.execute('ALTER TABLE operations ADD COLUMN activity_id INTEGER REFERENCES field_activities(id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operations_activity_id ON operations(activity_id)')
        conn.commit()
    finally:conn.close()
migrate_v182()

# v1.9.2: legacy material lines are grouped, never deleted.
def migrate_v192():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute('BEGIN IMMEDIATE')
        groups=conn.execute("""SELECT season,op_date,parcel_code,op_type,COUNT(*) n
          FROM operations WHERE is_cancelled=0 AND direction='Gider'
          AND op_type IN ('Ekim','Kazayağı Sürme','Tırmık Sürme','Pulluk Sürme')
          AND activity_id IS NULL AND parcel_code IS NOT NULL
          GROUP BY season,op_date,parcel_code,op_type""").fetchall()
        for season,dt,parcel,kind,n in groups:
            area=conn.execute('SELECT worked_area_da FROM parcel_season_areas WHERE season=? AND parcel_code=?',(season,parcel)).fetchone()
            if area is None:
                area=conn.execute('SELECT area_m2/1000.0 FROM parcels WHERE code=?',(parcel,)).fetchone()
            if not area or not area[0] or area[0]<=0:continue
            cur=conn.execute('INSERT INTO field_activities(season,activity_date,parcel_code,activity_type,area_da,note) VALUES(?,?,?,?,?,?)',
               (season,dt,parcel,kind,float(area[0]),'Eski tarla kayıtları birleştirildi; malzeme ve maliyet satırları korundu.'))
            conn.execute("""UPDATE operations SET activity_id=? WHERE season=? AND op_date=? AND parcel_code=? AND op_type=? AND is_cancelled=0 AND direction='Gider' AND activity_id IS NULL""",
                (cur.lastrowid,season,dt,parcel,kind))
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()
migrate_v192()

def migrate_v194():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS field_service_charges(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          activity_id INTEGER NOT NULL REFERENCES field_activities(id),
          season TEXT NOT NULL,parcel_code TEXT NOT NULL,
          service_type TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '',
          service_date TEXT NOT NULL,
          area_da REAL NOT NULL CHECK(area_da>0),
          rate_da REAL NOT NULL CHECK(rate_da>=0),
          total_amount REAL NOT NULL CHECK(total_amount>=0),
          expense_operation_id INTEGER REFERENCES operations(id),
          cancelled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS field_service_payments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          charge_id INTEGER NOT NULL REFERENCES field_service_charges(id),
          payment_date TEXT NOT NULL,
          amount REAL NOT NULL CHECK(amount>0),
          note TEXT NOT NULL DEFAULT '');
        """)
        conn.commit()
    finally:conn.close()
migrate_v194()

def migrate_v195():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS rent_payments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          rent_contract_id INTEGER NOT NULL REFERENCES rent_contracts(id),
          payment_date TEXT NOT NULL,
          amount REAL NOT NULL CHECK(amount>0),
          note TEXT NOT NULL DEFAULT '');
        """)
        conn.commit()
    finally:conn.close()
migrate_v195()

def migrate_v1914():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS bale_batches(
          id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER NOT NULL REFERENCES field_activities(id),
          item TEXT NOT NULL, count INTEGER NOT NULL CHECK(count>0), kg_per_bale REAL NOT NULL CHECK(kg_per_bale>0),
          harvest_operation_id INTEGER NOT NULL REFERENCES operations(id));
        CREATE TABLE IF NOT EXISTS bale_sales(
          id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL REFERENCES bale_batches(id),
          sale_operation_id INTEGER NOT NULL REFERENCES operations(id), count INTEGER NOT NULL CHECK(count>0));
        """)
        conn.commit()
    finally:conn.close()
migrate_v1914()


def worked_area(conn,code,season):
    row=conn.execute("SELECT worked_area_da FROM parcel_season_areas WHERE parcel_code=? AND season=?",(code,season)).fetchone()
    if row:return float(row['worked_area_da'])
    p=conn.execute("SELECT area_m2 FROM parcels WHERE code=?",(code,)).fetchone()
    return float(p['area_m2'])/1000 if p else 0


def migrate_v05():
    conn = sqlite3.connect(DB_PATH)
    try:
        for table in ('operations','stock_purchases','supports','machine_maintenance','rent_contracts'):
            columns = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            if 'is_cancelled' not in columns:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN is_cancelled INTEGER NOT NULL DEFAULT 0')
        conn.execute('''CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL,
            record_id TEXT NOT NULL, action TEXT NOT NULL, old_data TEXT,
            new_data TEXT, changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        # Database triggers record changes even when a record is edited through an existing form.
        for table in ('operations','stock_purchases','supports','machine_maintenance','rent_contracts','parcels'):
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
            pk = 'code' if table == 'parcels' else 'id'
            def snapshot(alias):
                return 'json_object(' + ','.join(repr(c)+','+alias+'."'+c+'"' for c in cols) + ')'
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS audit_v05_{table}_update
                AFTER UPDATE ON {table} BEGIN
                INSERT INTO change_log(table_name,record_id,action,old_data,new_data)
                VALUES('{table}',CAST(NEW."{pk}" AS TEXT),
                  CASE WHEN {('OLD.is_cancelled=0 AND NEW.is_cancelled=1' if 'is_cancelled' in cols else '0')} THEN 'İptal'
                       WHEN {('OLD.is_cancelled=1 AND NEW.is_cancelled=0' if 'is_cancelled' in cols else '0')} THEN 'Geri al'
                       ELSE 'Düzenle' END,
                  {snapshot('OLD')},{snapshot('NEW')});
                END""")
        conn.commit()
    finally:
        conn.close()

migrate_v05()

def migrate_v08():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS market_prices (
          item TEXT PRIMARY KEY, unit TEXT NOT NULL,
          unit_price REAL NOT NULL CHECK(unit_price>=0),
          price_date TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
    finally:
        conn.close()

migrate_v08()

def migrate_v09():
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS market_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL, unit TEXT NOT NULL,
            unit_price REAL NOT NULL CHECK(unit_price>=0),
            price_date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(item,unit,price_date)
        )''')
        # The previous version stored only the most recent quote. Preserve it as
        # one historical observation, without inventing earlier market prices.
        conn.execute('''INSERT OR IGNORE INTO market_price_history(item,unit,unit_price,price_date)
                        SELECT item,unit,unit_price,price_date FROM market_prices''')
        conn.commit()
    finally:
        conn.close()

migrate_v09()


def migrate_v1924_quotes():
    # Independent comparison-price records; never change stock or expense ledgers.
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS market_price_quotes_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL, item_detail TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL, price_date TEXT NOT NULL,
            unit_price REAL NOT NULL CHECK(unit_price>=0),
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(item,item_detail,unit,price_date)
        )""")
        conn.commit()
    finally: conn.close()

migrate_v1924_quotes()

def migrate_v106_units():
    """One-time lossless unit label normalization; create a full SQLite backup first."""
    import shutil
    conn=sqlite3.connect(DB_PATH)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        if conn.execute("SELECT 1 FROM app_migrations WHERE name='v106_units'").fetchone():
            conn.commit(); return
        conn.commit()
        backup=DB_PATH+'.v106_oncesi_yedek'
        if os.path.exists(DB_PATH) and not os.path.exists(backup):
            with sqlite3.connect(backup) as b: conn.backup(b)
        conn.execute('BEGIN IMMEDIATE')
        for table in ('operations','stock_purchases','market_prices','market_price_history'):
            for row in conn.execute(f'SELECT rowid,unit FROM {table}').fetchall():
                rid,old=row
                new=normalize_unit(old)
                if new != old:
                    # Market price history may have an existing same-date canonical entry.
                    # Do not silently merge or delete those price observations.
                    if table=='market_price_history':
                        clash=conn.execute('SELECT 1 FROM market_price_history WHERE item=(SELECT item FROM market_price_history WHERE rowid=?) AND unit=? AND price_date=(SELECT price_date FROM market_price_history WHERE rowid=?) AND rowid<>?',(rid,new,rid,rid)).fetchone()
                        if clash: continue
                    conn.execute(f'UPDATE {table} SET unit=? WHERE rowid=?',(new,rid))
        conn.execute("INSERT INTO app_migrations(name) VALUES ('v106_units')")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()

migrate_v106_units()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('logged_in'): return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        if secrets.compare_digest(request.form.get('password',''), APP_PASSWORD):
            session.clear(); session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Parola doğru değil. Tekrar deneyin.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    season = request.args.get('season', SEASONS[0])
    if season not in SEASONS: season = SEASONS[0]
    conn = db()
    # Dashboard totals: sales/other operation income + supports, operation expenses + maintenance.
    totals = conn.execute("SELECT COALESCE(SUM(CASE WHEN direction='Gelir' THEN amount ELSE 0 END),0) income, COALESCE(SUM(CASE WHEN direction='Gider' THEN amount ELSE 0 END),0) expense FROM operations WHERE is_cancelled=0 AND season=?",(season,)).fetchone()
    supports = float(conn.execute('SELECT COALESCE(SUM(amount),0) n FROM supports WHERE is_cancelled=0 AND season=?',(season,)).fetchone()['n'])
    maintenance = float(conn.execute('SELECT COALESCE(SUM(cost),0) n FROM machine_maintenance WHERE is_cancelled=0 AND season=?',(season,)).fetchone()['n'])
    parcels = conn.execute("""SELECT COUNT(*) n, COALESCE(SUM(area_m2),0) area,
       COALESCE(SUM(COALESCE(owned_area_da,area_m2/1000.0)),0) owned_area_da
       FROM parcels WHERE active=1""").fetchone()
    # A seasonal area setting is a CAP, not evidence of actual work.
    # Only parcels with a real field operation count; never multiply by passes.
    # Include tillage before sowing, but exclude harvest, sales and rent entries.
    field_parcels=conn.execute("""SELECT DISTINCT o.parcel_code FROM operations o
       JOIN parcels p ON p.code=o.parcel_code AND p.active=1
       WHERE o.is_cancelled=0 AND o.season=? AND o.parcel_code IS NOT NULL
         AND o.op_type NOT IN ('Satış','Hasat','İcar/Kiralama')
         AND o.direction='Gider'""",(season,)).fetchall()
    cultivated_da=sum(worked_area(conn,p['parcel_code'],season) for p in field_parcels)
    # The same land is counted once: owned share + seasonal leased share,
    # never exceeding the physical parcel size. Rent contracts represent
    # financial obligations and are deliberately not summed as land area.
    area_rows=conn.execute("""SELECT p.code,p.area_m2/1000.0 tapu_da,
        COALESCE(p.owned_area_da,p.area_m2/1000.0) owned_da,
        COALESCE(a.leased_area_da,0) leased_da
        FROM parcels p LEFT JOIN parcel_season_areas a
          ON a.parcel_code=p.code AND a.season=?
        WHERE p.active=1""",(season,)).fetchall()
    leased_da=sum(max(0,float(r['leased_da'])) for r in area_rows)
    # Total managed footprint: owned + leased within the parcel, plus
    # genuinely cultivated extension (e.g. reclaimed pasture) beyond that.
    # Only count extension when a real field operation exists this season.
    worked_codes={r['parcel_code'] for r in field_parcels}
    operating_da=0.0
    for r in area_rows:
        base=min(float(r['tapu_da']),float(r['owned_da'])+max(0.0,float(r['leased_da'])))
        actual=worked_area(conn,r['code'],season) if r['code'] in worked_codes else 0.0
        operating_da+=max(base,actual)

    area_warnings=[]
    for r in area_rows:
        if float(r['owned_da'])+float(r['leased_da'])>float(r['tapu_da'])+0.001:
            area_warnings.append(f"{r['code']}: mülkiyet ve icar alanı tapu alanını aşıyor; kullanım alanı tapu alanıyla sınırlandı.")
    # Distinct, active parcels with genuine field work. The seasonal area is
    # taken live from parcel_season_areas every time the dashboard is loaded.
    # Ownership and worked area are independent: leased land can be worked.
    worked_parcel_count=len(field_parcels)
    seasonal_area_count=conn.execute("""SELECT COUNT(*) n FROM parcel_season_areas a
       JOIN parcels p ON p.code=a.parcel_code AND p.active=1
       WHERE a.season=?""",(season,)).fetchone()['n']
    income_total=float(totals['income'])+supports
    expense_total=float(totals['expense'])+maintenance
    net=income_total-expense_total
    # Itemized sales, preserving the exact original income total and season filter.
    income_groups=conn.execute("""SELECT CASE WHEN op_type='Satış' THEN
         COALESCE(NULLIF(TRIM(item),''),'Ürünü belirtilmemiş satış') || ' satışı'
         ELSE COALESCE(NULLIF(TRIM(op_type),''),'Diğer gelir') END label,
         COALESCE(SUM(amount),0) amount
       FROM operations WHERE is_cancelled=0 AND season=? AND direction='Gelir'
       GROUP BY label ORDER BY amount DESC, label""",(season,)).fetchall()
    income_breakdown=[{'label':r['label'],'amount':float(r['amount'])} for r in income_groups]
    if supports:income_breakdown.append({'label':'Devlet destekleri','amount':supports})
    expense_groups=conn.execute("""SELECT CASE
      WHEN category IN ('Mazot','Motorin') OR item='Motorin' OR op_type='Yakıt' THEN 'Motorin'
      WHEN category='Tohum' THEN 'Tohum'
      WHEN category='Gübre' THEN 'Gübre'
      WHEN category='İcar/Kiralama' OR op_type='İcar/Kiralama' THEN 'İcar / Kira'
      WHEN category='İlaç' THEN 'İlaç'
      WHEN category='İşçilik' THEN 'İşçilik'
      WHEN category='Nakliye' THEN 'Nakliye'
      ELSE 'Diğer giderler' END label,COALESCE(SUM(amount),0) amount
      FROM operations WHERE is_cancelled=0 AND season=? AND direction='Gider'
      GROUP BY label""",(season,)).fetchall()
    expense_breakdown=[{'label':r['label'],'amount':float(r['amount'])} for r in expense_groups]
    if maintenance:expense_breakdown.append({'label':'Makine bakımı','amount':maintenance})
    income_breakdown.sort(key=lambda x:-x['amount'])
    expense_breakdown.sort(key=lambda x:-x['amount'])
    stock = conn.execute('''SELECT p.item,COALESCE(p.item_detail,'') item_detail, p.unit, SUM(p.quantity) bought,
      COALESCE((SELECT SUM(o.quantity) FROM operations o WHERE o.is_cancelled=0 AND o.item=p.item AND COALESCE(o.item_detail,'')=COALESCE(p.item_detail,'') AND o.unit=p.unit AND o.direction='Gider' AND o.op_type NOT IN ('Hasat','Satış')),0) used,
      CASE WHEN SUM(p.quantity)>0 THEN SUM(p.quantity*p.unit_price)/SUM(p.quantity) ELSE 0 END avg_cost
      FROM stock_purchases p WHERE p.is_cancelled=0 GROUP BY p.item,COALESCE(p.item_detail,''),p.unit ORDER BY p.item,p.item_detail''').fetchall()
    # Product balance is cumulative across seasons; no invented season opening inventory.
    product_rows=conn.execute("""SELECT item,unit,
      SUM(CASE WHEN op_type='Hasat' THEN quantity ELSE 0 END) harvested,
      SUM(CASE WHEN op_type='Satış' THEN quantity ELSE 0 END) sold
      FROM operations WHERE is_cancelled=0 AND op_type IN ('Hasat','Satış')
      GROUP BY item,unit ORDER BY item,unit""").fetchall()
    product_balances=[dict(item=r['item'],unit=r['unit'],harvested=float(r['harvested']),sold=float(r['sold']),remaining=float(r['harvested'])-float(r['sold'])) for r in product_rows]
    warnings=list(area_warnings)
    for r in product_balances:
        if r['remaining'] < -0.0001: warnings.append(f"{r['item']}: ürün satışları hasat miktarını aşıyor; ürün adlarını kontrol edin.")
    for s in stock:
        if s['bought']-s['used'] < -0.0001: warnings.append(f"{s['item']}: hesaplanan stok eksiye düşüyor.")
    def stock_order(r):
        name=str(r['item']).casefold()
        if 'motorin' in name or 'mazot' in name:return (0,name)
        if 'gübre' in name or 'gubre' in name:return (1,name)
        if name in ('arpa','buğday','bugday','tohum') or 'tohum' in name:return (2,name)
        return (3,name)
    stock=sorted(stock,key=stock_order)
    # V1.9.7: outstanding obligations are cash-flow balances, not new expenses.
    debt_rows=conn.execute("""SELECT 'İcar' kind, r.total_amount total,
        COALESCE((SELECT SUM(p.amount) FROM rent_payments p WHERE p.rent_contract_id=r.id),0) paid
      FROM rent_contracts r WHERE r.season=? AND r.is_cancelled=0
      UNION ALL
      SELECT c.service_type kind,c.total_amount total,
        COALESCE((SELECT SUM(p.amount) FROM field_service_payments p WHERE p.charge_id=c.id),0) paid
      FROM field_service_charges c WHERE c.season=? AND c.cancelled=0""",(season,season)).fetchall()
    debt_total=sum(float(r['total']) for r in debt_rows)
    debt_paid=sum(float(r['paid']) for r in debt_rows)
    debt_by_type={}
    for r in debt_rows:
        v=debt_by_type.setdefault(r['kind'],{'kind':r['kind'],'total':0.0,'paid':0.0,'remaining':0.0})
        v['total']+=float(r['total']);v['paid']+=float(r['paid']);v['remaining']+=max(0.0,float(r['total'])-float(r['paid']))
    debt_by_type=sorted(debt_by_type.values(),key=lambda x:-x['remaining'])
    debt_remaining=sum(max(0.0,float(r['total'])-float(r['paid'])) for r in debt_rows)
    return render_template('dashboard.html', season=season, seasons=SEASONS, totals=totals, supports=supports, maintenance=maintenance,
       parcels=parcels, operating_da=operating_da, leased_da=leased_da, cultivated_da=cultivated_da, worked_parcel_count=worked_parcel_count, seasonal_area_count=seasonal_area_count, income_total=income_total, expense_total=expense_total,
       net=net, net_per_da=(net/cultivated_da if cultivated_da else None),
       income_breakdown=income_breakdown, expense_breakdown=expense_breakdown,
       stock=stock, product_balances=product_balances, warnings=warnings,
       debt_total=debt_total,debt_paid=debt_paid,debt_remaining=debt_remaining,debt_by_type=debt_by_type)

def find_market_quote(conn,item,detail,unit,asof):
    # Exact product + variety first. Legacy history is used only for unvaried items.
    aliases=[item]
    if item=='Motorin': aliases.append('Motorin (Mazot)')
    elif item=='Motorin (Mazot)': aliases.append('Motorin')
    marks=','.join('?' for _ in aliases)
    found=conn.execute(f"""SELECT unit_price,price_date FROM market_price_quotes_v2
        WHERE item IN ({marks}) AND item_detail=? AND unit=? AND price_date<=?
        ORDER BY price_date DESC,id DESC LIMIT 1""",(*aliases,detail,unit,asof)).fetchone()
    if found is not None: return found
    if detail: return None
    return conn.execute(f"""SELECT unit_price,price_date FROM market_price_history
        WHERE item IN ({marks}) AND unit=? AND price_date<=?
        ORDER BY price_date DESC,id DESC LIMIT 1""",(*aliases,unit,asof)).fetchone()

def early_purchase_analysis(conn,season):
    """Compare recorded input costs with market quotes, without modifying ledgers.
    Recorded cost and market quote availability are two independent questions.
    """
    purchases=conn.execute("""SELECT id,item,COALESCE(item_detail,'') item_detail,unit,
        purchase_date,quantity,unit_price FROM stock_purchases
        WHERE is_cancelled=0 ORDER BY purchase_date,id""").fetchall()
    grouped={}
    for lot in purchases:
        key=(lot['item'],lot['item_detail'],lot['unit'])
        grouped.setdefault(key,[]).append(lot)
    results=[]
    details=[]
    for (item,detail,unit),lots in sorted(grouped.items()):
        aliases=[item]
        if item=='Motorin': aliases.append('Motorin (Mazot)')
        if item=='Motorin (Mazot)': aliases.append('Motorin')
        marks=','.join('?' for _ in aliases)
        uses=conn.execute("""SELECT id,op_date,quantity,unit_price,amount,season
            FROM operations WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=?
            AND unit=? AND direction='Gider'
            AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama')
            ORDER BY op_date,id""",(item,detail,unit)).fetchall()
        balances={lot['id']:float(lot['quantity']) for lot in lots}
        purchased_total=sum(float(lot['quantity']) for lot in lots)
        used_total=sum(float(op['quantity']) for op in uses)
        cost_known=0.; cost_missing=0.; quote_known=0.; quote_missing=0.
        compared=0.; used_gain=0.; used_cost=0.; used_market=0.
        fifo_missing=0.
        for op in uses:
            q=float(op['quantity'])
            # Allocate across dated purchase lots, earliest first.
            need=q; fifo_cost=0.; allocated=0.; allocations=[]
            for lot in lots:
                if lot['purchase_date']>op['op_date']: break
                take=min(need,balances[lot['id']])
                if take>0:
                    balances[lot['id']]-=take;need-=take;allocated+=take
                    fifo_cost+=take*float(lot['unit_price'])
                    allocations.append(dict(date=lot['purchase_date'],quantity=take,unit_price=float(lot['unit_price']),cost=take*float(lot['unit_price'])))
                if need<=1e-6:break
            # Ignore floating-point residue smaller than one millionth of a unit.
            need=max(0.,need) if need>1e-6 else 0.0
            fifo_missing+=need
            if op['season']!=season:continue
            # Recorded expense is authoritative; never overwrite it with a market quote.
            cost=(float(op['amount']) if op['amount'] is not None else
                  q*float(op['unit_price']) if op['unit_price'] is not None else
                  fifo_cost if need<=1e-6 else None)
            quote=find_market_quote(conn,item,detail,unit,op['op_date'])
            # One operation may consume several purchase lots; show each lot explicitly.
            details.append(dict(item=item,detail=detail,unit=unit,op_id=op['id'],
                op_date=op['op_date'],quantity=q,recorded_cost=cost,
                fifo_cost=fifo_cost if need<=1e-6 else None,
                missing_fifo=max(0.,need),allocations=allocations,
                quote_date=quote['price_date'] if quote else None,
                quote_price=float(quote['unit_price']) if quote else None,
                market_value=q*float(quote['unit_price']) if quote else None,
                difference=(q*float(quote['unit_price'])-cost if quote is not None and cost is not None else None)))
            if cost is None:cost_missing+=q
            else:cost_known+=q
            if quote is None:quote_missing+=q
            else:quote_known+=q
            if cost is not None and quote is not None:
                compared+=q;used_cost+=cost;used_market+=q*float(quote['unit_price'])
                used_gain+=q*float(quote['unit_price'])-cost
        remaining=max(0.,purchased_total-used_total) if purchased_total-used_total>1e-6 else 0.0
        stock_cost=sum((v if v>1e-6 else 0.0)*float(next(lot['unit_price'] for lot in lots if lot['id']==lid))
                       for lid,v in balances.items())
        latest=find_market_quote(conn,item,detail,unit,date.today().isoformat())
        # A historical deficit means remaining inventory cost cannot be reconciled.
        stock_gain=(remaining*float(latest['unit_price'])-stock_cost
                    if latest is not None and fifo_missing<=1e-6 else None)
        results.append(dict(item=item,detail=detail,unit=unit,
            cost_known=cost_known,cost_missing=cost_missing,
            quote_known=quote_known,quote_missing=quote_missing,
            compared=compared,used_cost=used_cost,used_market=used_market,
            used_gain=used_gain,remaining=remaining,stock_cost=stock_cost,
            stock_gain=stock_gain,latest_date=latest['price_date'] if latest else None,
            fifo_missing=fifo_missing))
    return results,details

@app.route('/raporlar/piyasa-fiyatlari',methods=['GET','POST'])
@login_required
def market_quotes_page():
    conn=db()
    if request.method=='POST':
        if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
        action=request.form.get('action','save')
        if action=='delete':
            try: quote_id=int(request.form.get('quote_id','0'))
            except (ValueError,TypeError):quote_id=0
            conn.execute('DELETE FROM market_price_quotes_v2 WHERE id=?',(quote_id,))
            conn.commit();flash('Piyasa fiyatı silindi. Stok ve gider kayıtları değişmedi.','success')
        else:
            item=request.form.get('item','').strip()
            detail=request.form.get('item_detail','').strip()
            unit=normalize_unit(request.form.get('unit',''))
            dt=request.form.get('price_date','').strip()
            source=request.form.get('source','').strip()[:250]
            try:price=float(request.form.get('unit_price','').replace(',','.'))
            except (ValueError,TypeError):price=float('nan')
            valid_date=False
            try:valid_date=datetime.strptime(dt,'%Y-%m-%d').strftime('%Y-%m-%d')==dt
            except ValueError:pass
            known=conn.execute('''SELECT 1 FROM stock_purchases
                WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=?
                LIMIT 1''',(item,detail,unit)).fetchone()
            if not known or not valid_date or not math.isfinite(price) or price<0:
                flash('Ürün/çeşit, birim, tarih veya fiyat geçersiz.','error')
            else:
                conn.execute('''INSERT INTO market_price_quotes_v2
                    (item,item_detail,unit,price_date,unit_price,source)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(item,item_detail,unit,price_date)
                    DO UPDATE SET unit_price=excluded.unit_price,source=excluded.source''',
                    (item,detail,unit,dt,price,source))
                conn.commit()
                flash('Piyasa fiyatı kaydedildi. Stok ve giderler değişmedi.','success')
        return redirect(url_for('market_quotes_page'))
    products=conn.execute('''SELECT DISTINCT item,COALESCE(item_detail,'') item_detail,unit
        FROM stock_purchases WHERE is_cancelled=0 ORDER BY item,item_detail,unit''').fetchall()
    quotes=conn.execute('''SELECT * FROM market_price_quotes_v2
        ORDER BY price_date DESC,item,item_detail,id DESC LIMIT 300''').fetchall()
    prefill_item=request.args.get('item','').strip()
    prefill_detail=request.args.get('detail','').strip()
    prefill_unit=normalize_unit(request.args.get('unit',''))
    prefill_date=request.args.get('price_date','').strip()
    if not any(x['item']==prefill_item and x['item_detail']==prefill_detail and x['unit']==prefill_unit for x in products):
        prefill_item=prefill_detail=prefill_unit=''
    try:
        if datetime.strptime(prefill_date,'%Y-%m-%d').strftime('%Y-%m-%d')!=prefill_date:prefill_date=''
    except ValueError:prefill_date=''

    return render_template('market_quotes.html',products=products,quotes=quotes,
                           csrf=v05_csrf(),today=date.today().isoformat(),
                           prefill_item=prefill_item,prefill_detail=prefill_detail,
                           prefill_unit=prefill_unit,prefill_date=prefill_date)

def stock_movement_audit(conn):
    """Read-only chronology; purchases on the same day precede uses.
    A historical shortage is retained even when later purchases replenish stock.
    """
    events={}
    for r in conn.execute("""SELECT id,item,COALESCE(item_detail,'') detail,unit,
            purchase_date movement_date,quantity,unit_price FROM stock_purchases
            WHERE is_cancelled=0 ORDER BY purchase_date,id"""):
        k=(r['item'],r['detail'],r['unit'])
        events.setdefault(k,[]).append(dict(date=r['movement_date'],priority=0,id=r['id'],
            kind='Alım',quantity=float(r['quantity']),unit_price=r['unit_price'],
            parcel='',op_type='',note=''))
    # Only physical inventory items are eligible for stock movement auditing.
    # Service charges (e.g. baling and combine-harvester work) are expenses,
    # never stock consumption, even if their operation has direction='Gider'.
    inventory_keys=set(events)
    for r in conn.execute("""SELECT id,item,COALESCE(item_detail,'') detail,unit,
            op_date movement_date,quantity,parcel_code,op_type,note FROM operations
            WHERE is_cancelled=0 AND direction='Gider'
              AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama')
            ORDER BY op_date,id"""):
        k=(r['item'],r['detail'],r['unit'])
        if k not in inventory_keys or 'hizmet' in (r['item'] or '').casefold():
            continue
        events.setdefault(k,[]).append(dict(date=r['movement_date'],priority=1,id=r['id'],
            kind='Kullanım',quantity=float(r['quantity']),unit_price=None,
            parcel=r['parcel_code'] or '',op_type=r['op_type'],note=r['note'] or ''))
    summary=[];movements=[];issues=[]
    for (item,detail,unit),rows in sorted(events.items()):
        rows.sort(key=lambda x:(x['date'],x['priority'],x['id']))
        balance=0.;total_in=0.;total_out=0.;worst=0.;first=None
        for e in rows:
            before=balance
            delta=e['quantity'] if e['kind']=='Alım' else -e['quantity']
            balance+=delta
            if abs(balance)<=1e-6:balance=0.0
            if delta>0:total_in+=delta
            else:total_out-=delta
            shortage=max(0.,-balance)
            if shortage>1e-6:
                worst=max(worst,shortage)
                if first is None:first=e['date']
            entry=dict(item=item,detail=detail,unit=unit,date=e['date'],kind=e['kind'],
                id=e['id'],quantity=e['quantity'],before=before,after=balance,
                shortage=shortage,parcel=e['parcel'],op_type=e['op_type'],
                unit_price=e['unit_price'])
            movements.append(entry)
            if e['kind']=='Kullanım' and shortage>1e-6:
                issues.append(entry)
        summary.append(dict(item=item,detail=detail,unit=unit,bought=total_in,
            used=total_out,remaining=balance,first_shortage=first,
            maximum_shortage=worst,has_issue=worst>1e-6))
    return summary,movements,issues

@app.route('/raporlar/stok-hareketleri-kontrolu')
@login_required
def stock_movement_audit_page():
    conn=db()
    summary,movements,issues=stock_movement_audit(conn)
    selected=request.args.get('item','').strip()
    keys={f"{r['item']}|{r['detail']}|{r['unit']}" for r in summary}
    if selected not in keys:selected=''
    shown=[r for r in movements if not selected or f"{r['item']}|{r['detail']}|{r['unit']}"==selected]
    return render_template('stock_movement_audit.html',summary=summary,
        movements=shown,issues=issues,selected=selected)

@app.route('/raporlar/erken-alim')
@login_required
def early_purchase_report():
    conn=db()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS:season=SEASONS[0]
    early_rows,early_details=early_purchase_analysis(conn,season)
    # Only priced, actually consumed quantities contribute to realized price differences.
    missing_quotes=[d for d in early_details if d['quote_date'] is None]
    missing_quotes.sort(key=lambda d:(d['item'],d['detail'],d['op_date'],d['op_id']))
    compared_details=[d for d in early_details if d['difference'] is not None]
    summary=dict(compared_count=len(compared_details),
        compared_qty_by_unit={},
        recorded_cost=sum(d['recorded_cost'] for d in compared_details),
        market_value=sum(d['market_value'] for d in compared_details),
        realized_difference=sum(d['difference'] for d in compared_details),
        missing_count=len(missing_quotes),
        remaining_stock_difference=sum(r['stock_gain'] for r in early_rows if r['stock_gain'] is not None),
        stock_valued_count=sum(1 for r in early_rows if r['stock_gain'] is not None))
    for d in compared_details:
        unit=d['unit']
        summary['compared_qty_by_unit'][unit]=summary['compared_qty_by_unit'].get(unit,0)+d['quantity']
    return render_template('early_purchase.html',season=season,seasons=SEASONS,
        early_rows=early_rows,early_details=early_details,
        missing_quotes=missing_quotes,early_summary=summary)

@app.route('/parseller', methods=['GET','POST'])
@login_required
def parcels_page():
    conn=db()
    if request.method=='POST':
        code=request.form.get('code','').strip().upper(); name=request.form.get('name','').strip()
        try: area=float(request.form.get('area_m2',''))
        except ValueError: area=0
        if not code or not name or area<=0:
            flash('Parsel kodu, adı ve sıfırdan büyük alan zorunludur.','error')
        elif conn.execute('SELECT 1 FROM parcels WHERE code=?',(code,)).fetchone():
            flash('Bu parsel kodu zaten kayıtlı. Mükerrer parsel oluşturulmadı.','error')
        else:
            conn.execute('INSERT INTO parcels(code,name,area_m2,property_type,soil_type,irrigation,neighborhood,ada,parcel_no,owner) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (code,name,area,request.form.get('property_type') or None,request.form.get('soil_type') or None,request.form.get('irrigation') or None,request.form.get('neighborhood') or None,request.form.get('ada') or None,request.form.get('parcel_no') or None,request.form.get('owner') or None))
            conn.commit(); flash('Parsel kaydedildi.','success'); return redirect(url_for('parcels_page'))
    rows=conn.execute('SELECT * FROM parcels ORDER BY code').fetchall()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS:season=SEASONS[0]
    season_rows=conn.execute('SELECT parcel_code,worked_area_da,leased_area_da FROM parcel_season_areas WHERE season=?',(season,)).fetchall()
    season_data={r['parcel_code']:dict(r) for r in season_rows}
    return render_template('parcels.html', parcels=rows,season=season,seasons=SEASONS,season_data=season_data)


def canonical_item(item, category='', op_type='', detail=''):
    """Conservative canonical names; keep unknown names untouched."""
    name=(item or '').strip()
    norm=name.casefold().replace('ı','i').replace('ğ','g').replace('ü','u').replace('ş','s').replace('ö','o').replace('ç','c')
    cat=(category or '').casefold()
    kind=(op_type or '').casefold()
    if norm in ('motorin','mazot','motorin (mazot)','mazot (motorin)') or kind=='yakit':
        return 'Motorin', (detail or '').strip()
    if norm in ('reis','yavuz','slobella'):
        crop='Arpa' if norm=='slobella' else 'Buğday'
        return crop,(detail or name).strip()
    if norm in ('arpa','bugday','buğday','gubre','gübre'):
        canonical={'arpa':'Arpa','bugday':'Buğday','buğday':'Buğday','gubre':'Gübre','gübre':'Gübre'}[norm]
        return canonical,(detail or '').strip()
    fertilizer=(cat=='gübre' or kind=='gübreleme' or
        bool(re.search(r'(?i)(?:^|\W)(?:dap|üre|ure|npk|20[ -]20|15[ -]15|18[ -]46)(?:\W|$)',name)))
    if fertilizer:
        return 'Gübre',(detail or name).strip()
    return name,(detail or '').strip()

def v131_preview(conn):
    result=[]
    for table in ('operations','stock_purchases'):
        rows=conn.execute(f"SELECT id,item,item_detail,category{',op_type' if table=='operations' else ''} FROM {table}").fetchall()
        for r in rows:
            item,detail=canonical_item(r['item'],r['category'],r['op_type'] if table=='operations' else '',r['item_detail'])
            if item!=r['item'] or detail!=(r['item_detail'] or ''):
                result.append((table,r['id'],r['item'],r['item_detail'] or '',item,detail))
    return result

@app.route('/veri-esitle',methods=['GET','POST'])
@login_required
def sync_item_names():
    conn=db()
    changes=v131_preview(conn)
    if request.method=='POST':
        if request.form.get('confirm')!='EVET':
            flash('Onay verilmedi; kayıtlar değiştirilmedi.','error')
        else:
            conn.execute('SAVEPOINT sync131')
            try:
                for table,rid,old_item,old_detail,new_item,new_detail in changes:
                    conn.execute(f'UPDATE {table} SET item=?,item_detail=? WHERE id=?',(new_item,new_detail,rid))
                conn.execute('RELEASE sync131')
                conn.commit()
                flash(f'{len(changes)} kaydın ürün ve çeşit alanı eşitlendi. Tutarlar değiştirilmedi.','success')
                return redirect(url_for('sync_item_names'))
            except Exception:
                conn.execute('ROLLBACK TO sync131');conn.execute('RELEASE sync131')
                raise
    return render_template('sync_items.html',changes=changes)

STOCK_OPERATION_TYPES = ('Ekim','Gübreleme','İlaçlama','Yakıt')

def depot_choices(conn):
    return conn.execute("""SELECT MIN(id) id,item,COALESCE(item_detail,'') item_detail,unit,category
        FROM stock_purchases WHERE is_cancelled=0
        GROUP BY item,COALESCE(item_detail,''),unit,category
        ORDER BY item,item_detail,unit""").fetchall()

def selected_depot_item(conn, form):
    try: purchase_id=int(form.get('depot_item_id',''))
    except (TypeError,ValueError): return None
    return conn.execute("SELECT item,COALESCE(item_detail,'') item_detail,unit,category FROM stock_purchases WHERE id=? AND is_cancelled=0",(purchase_id,)).fetchone()


# One field activity can consume multiple materials. Each material remains a
# separate operation for backwards-compatible stock, FIFO and reporting.
@app.route('/tarla-faaliyeti',methods=['POST'])
@login_required
def save_field_activity():
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
    conn=db()
    season=request.form.get('season','')
    dt=request.form.get('op_date','')
    parcel=request.form.get('parcel_code','')
    activity=request.form.get('activity_type','')
    note=request.form.get('note','').strip()
    errors=[]
    if season not in SEASONS:errors.append('Sezon geçersiz.')
    try:datetime.strptime(dt,'%Y-%m-%d')
    except (ValueError,TypeError):errors.append('Tarih geçersiz.')
    if activity not in ('Ekim','Gübreleme','İlaçlama','Pulluk Sürme','Kazayağı Sürme','Tırmık Sürme','Diğer'):
        errors.append('Tarla faaliyeti geçersiz.')
    p=conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel,)).fetchone()
    if not p:errors.append('Geçerli parsel seçin.')
    try:area=float(request.form.get('application_area',''))
    except (ValueError,TypeError):area=-1
    if not math.isfinite(area) or area<=0 or (p and season in SEASONS and area>worked_area(conn,parcel,season)+1e-6):
        errors.append('Uygulama alanı pozitif olmalı ve sezonluk işlenen alanı aşmamalı.')
    ids=request.form.getlist('depot_item_id[]')
    rates=request.form.getlist('rate_per_decare[]')
    if not ids or len(ids)!=len(rates) or len(ids)>12:
        errors.append('1–12 malzeme seçin; her malzemeye dönüm başına miktar girin.')
    lines=[]
    seen=set()
    if not errors:
        for raw_id,raw_rate in zip(ids,rates):
            try:
                purchase_id=int(raw_id)
                rate=float(raw_rate)
            except (ValueError,TypeError):
                errors.append('Malzeme ve doz bilgileri geçersiz.');continue
            purchase=conn.execute("SELECT item,COALESCE(item_detail,'') item_detail,unit,category FROM stock_purchases WHERE id=? AND is_cancelled=0",(purchase_id,)).fetchone()
            if not purchase or not math.isfinite(rate) or rate<=0:
                errors.append('Malzeme veya dönüm başına miktar geçersiz.');continue
            item,detail,unit,category=purchase['item'],purchase['item_detail'],purchase['unit'],purchase['category']
            key=(item,detail,unit)
            if key in seen:
                errors.append(f'{item} / {detail}: Aynı malzemeyi bir kez seçin; dozları birleştirin.');continue
            seen.add(key)
            qty=round(rate*area,3)
            if qty<=0:errors.append('Toplam tüketim sıfır olamaz.');continue
            lines.append(dict(item=item,detail=detail,unit=unit,category=category,qty=qty,rate=rate))
    if activity=='Ekim' and not any(infer_sown_crop(x['item']) for x in lines):
        errors.append('Ekim faaliyetinde en az bir tohum (Arpa/Buğday vb.) seçin.')
    if activity=='Gübreleme' and not any(x['item'].strip().casefold()=='gübre' or (x['category'] or '').strip().casefold()=='gübre' for x in lines):
        errors.append('Gübreleme faaliyetinde en az bir gübre seçin.')
    if not errors:
        for x in lines:
            if x['qty']>input_stock(conn,x['item'],x['detail'],x['unit'])+1e-6:
                errors.append(f"{x['item']} / {x['detail']}: depoda yeterli stok yok.")
            if fifo_later_use(conn,x['item'],x['unit'],dt,detail=x['detail']):
                errors.append(f"{x['item']} / {x['detail']}: sonraki tarihli tüketim bulunduğundan FIFO sırası bozulabilir.")
            price,err=fifo_unit_cost(conn,x['item'],x['unit'],dt,x['qty'],detail=x['detail'])
            if err:errors.append(f"{x['item']} / {x['detail']}: {err}")
            else:x['price']=price
    if errors:
        for e in errors:flash(e,'error')
        return redirect(url_for('operations_page'))
    # Transaction is all-or-nothing. No partial depot consumption is possible.
    try:
        conn.execute('BEGIN IMMEDIATE')
        # Recheck current stock while holding the write lock.
        for x in lines:
            if x['qty']>input_stock(conn,x['item'],x['detail'],x['unit'])+1e-6:
                raise ValueError(f"{x['item']} için stok değişmiş; işlem kaydedilmedi.")
        cur=conn.execute('INSERT INTO field_activities(season,activity_date,parcel_code,activity_type,area_da,note) VALUES(?,?,?,?,?,?)',
            (season,dt,parcel,activity,area,note))
        aid=cur.lastrowid
        for x in lines:
            detail_note=f"Faaliyet #{aid} · Uygulama alanı: {area:g} da; Doz: {x['rate']:g} {x['unit']}/da"
            if note:detail_note+=' | '+note
            conn.execute("""INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (season,dt,parcel,activity,x['item'],x['qty'],x['unit'],x['price'],round(x['qty']*x['price'],2),'Gider',x['category'],detail_note,x['detail'],aid))
        conn.commit()
    except Exception as e:
        conn.rollback();flash('Faaliyet kaydedilmedi: '+str(e),'error')
        return redirect(url_for('operations_page'))
    flash(f'Faaliyet #{aid} kaydedildi: {len(lines)} malzeme tek seferde stoktan düşüldü.','success')
    return redirect(url_for('operations_page'))



@app.route('/tarla-hasat', methods=['POST'])
@login_required
def save_field_harvest():
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
    conn=db()
    season=request.form.get('season','')
    dt=request.form.get('op_date','')
    parcel=request.form.get('parcel_code','')
    crop=request.form.get('crop','')
    try:
        area=float(request.form.get('application_area',''))
        yield_kg=float(request.form.get('harvest_kg',''))
        diesel_rate=float(request.form.get('diesel_rate','0') or 0)
        diesel=round(area*diesel_rate,3)
        service_rate=float(request.form.get('service_rate','0') or 0)
        service=round(area*service_rate,2)
        paid=float(request.form.get('paid_amount','0') or 0)
        provider=request.form.get('provider','').strip()[:120]
        payment_date=request.form.get('payment_date') or dt
    except (TypeError,ValueError):
        flash('Hasat miktarları geçersiz.','error');return redirect(url_for('operations_page'))
    valid_date=True
    try:datetime.strptime(dt,'%Y-%m-%d')
    except (ValueError,TypeError):valid_date=False
    if (season not in SEASONS or not valid_date or
        not conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel,)).fetchone() or
        crop not in ('Arpa','Buğday') or not all(math.isfinite(x) for x in (area,yield_kg,diesel_rate,service_rate,paid)) or
        area<=0 or area>worked_area(conn,parcel,season)+1e-6 or yield_kg<=0 or diesel_rate<0 or service_rate<0 or paid<0 or paid>service+0.001):
        flash('Hasat bilgilerini ve sezonluk işlenen alanı kontrol edin.','error')
        return redirect(url_for('operations_page'))
    try: datetime.strptime(payment_date,'%Y-%m-%d')
    except (TypeError,ValueError):
        flash('Ödeme tarihi geçersiz.','error');return redirect(url_for('operations_page'))
    price=0
    if diesel>0:
        if diesel>input_stock(conn,'Motorin','','L')+1e-6:
            flash('Motorin stoğu yetersiz.','error');return redirect(url_for('operations_page'))
        if fifo_later_use(conn,'Motorin','L',dt,detail=''):
            flash('Sonraki tarihli motorin tüketimi var; FIFO sırası bozulabilir.','error')
            return redirect(url_for('operations_page'))
        price,err=fifo_unit_cost(conn,'Motorin','L',dt,diesel,detail='')
        if err:flash(err,'error');return redirect(url_for('operations_page'))
    try:
        conn.execute('BEGIN IMMEDIATE')
        if diesel>input_stock(conn,'Motorin','','L')+1e-6:
            raise ValueError('Motorin stoğu işlem sırasında değişti.')
        cur=conn.execute("""INSERT INTO field_activities(season,activity_date,parcel_code,activity_type,area_da,note)
          VALUES(?,?,?,?,?,?)""",(season,dt,parcel,'Hasat',area,request.form.get('note','').strip()))
        aid=cur.lastrowid
        note=f'Faaliyet #{aid} · Hasat alanı: {area:g} da'
        conn.execute("""INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(season,dt,parcel,'Hasat',crop,yield_kg,'kg',0,0,'Nötr',None,note,'',aid))
        if diesel>0:
            conn.execute("""INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(season,dt,parcel,'Yakıt','Motorin',diesel,'L',price,round(diesel*price,2),'Gider','Mazot',note,'',aid))
        if service>0:
            expense=conn.execute("""INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(season,dt,parcel,'İşçilik','Biçerdöver Hizmeti',1,'adet',service,round(service,2),'Gider','Makine',note,'',aid))
            charge=conn.execute("""INSERT INTO field_service_charges(activity_id,season,parcel_code,service_type,provider,service_date,area_da,rate_da,total_amount,expense_operation_id)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",(aid,season,parcel,'Biçerdöver',provider,dt,area,service_rate,service,expense.lastrowid))
            if paid>0:
                conn.execute('INSERT INTO field_service_payments(charge_id,payment_date,amount,note) VALUES(?,?,?,?)',(charge.lastrowid,payment_date,paid,'Hasat sırasında ödeme'))
        conn.commit()
    except Exception as e:
        conn.rollback();flash('Hasat kaydedilmedi: '+str(e),'error')
        return redirect(url_for('operations_page'))
    flash('Hasat, motorin ve biçerdöver gideri tek faaliyet altında kaydedildi.','success')
    return redirect(url_for('operations_page'))



@app.route('/tarla-balya',methods=['POST'])
@login_required
def save_bale_activity():
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
    conn=db()
    season=request.form.get('season','');dt=request.form.get('service_date','');parcel=request.form.get('parcel_code','')
    item=request.form.get('bale_crop','');provider=request.form.get('provider','').strip()[:120]
    try:
        datetime.strptime(dt,'%Y-%m-%d')
        area=float(request.form.get('area_da',''));count=int(request.form.get('bale_count',''))
        weight=float(request.form.get('bale_weight','250'));rate=float(request.form.get('rate_da',''))
        total=round(count*rate,2)
        if season not in SEASONS or item not in ('Arpa Samanı','Buğday Samanı'):raise ValueError()
        if not conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel,)).fetchone():raise ValueError()
        if not all(math.isfinite(x) for x in (area,weight,rate)) or area<=0 or area>worked_area(conn,parcel,season)+1e-6 or count<=0 or weight<=0 or rate<0:raise ValueError()
        conn.execute('BEGIN IMMEDIATE')
        aid=conn.execute('INSERT INTO field_activities(season,activity_date,parcel_code,activity_type,area_da,note) VALUES(?,?,?,?,?,?)',
          (season,dt,parcel,'Balya',area,request.form.get('note','').strip())).lastrowid
        kg=round(count*weight,3)
        op=conn.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(season,dt,parcel,'Hasat',item,kg,'kg',0,0,'Nötr',None,f'{count} adet × {weight:g} kg balya','',aid))
        conn.execute('INSERT INTO bale_batches(activity_id,item,count,kg_per_bale,harvest_operation_id) VALUES(?,?,?,?,?)',(aid,item,count,weight,op.lastrowid))
        if total>0:
            expense=conn.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(season,dt,parcel,'İşçilik','Balya Hizmeti',1,'adet',total,total,'Gider','Makine',f'{count} balya × {rate:g} TL','',aid))
            conn.execute('''INSERT INTO field_service_charges(activity_id,season,parcel_code,service_type,provider,service_date,area_da,rate_da,total_amount,expense_operation_id)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',(aid,season,parcel,'Balya',provider,dt,area,total/area,total,expense.lastrowid))
        conn.commit();flash(f'{count} balya ({kg:g} kg) depoya girdi. Hizmet bedeli borçlara işlendi.','success')
    except (ValueError,TypeError):
        conn.rollback();flash('Balya alanlarını kontrol edin; miktar, ağırlık ve parsel geçerli olmalıdır.','error')
    except Exception:
        conn.rollback();raise
    return redirect(url_for('operations_page'))

@app.route('/urun-satis',methods=['POST'])
@login_required
def sell_warehouse_product():
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
    conn=db()
    item=request.form.get('item','');dt=request.form.get('sale_date','');season=request.form.get('season','')
    parcel=request.form.get('parcel_code','') or None
    try:
        datetime.strptime(dt,'%Y-%m-%d')
        price=float(request.form.get('unit_price',''))
        if season not in SEASONS or not math.isfinite(price) or price<=0:raise ValueError()
        if parcel and not conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel,)).fetchone():raise ValueError()
        conn.execute('BEGIN IMMEDIATE')
        if item in ('Arpa Samanı','Buğday Samanı'):
            count=int(request.form.get('bale_count',''))
            if count<=0:raise ValueError()
            batches=conn.execute('''SELECT b.id,b.count,b.kg_per_bale,o.op_date,
              COALESCE((SELECT SUM(bs.count) FROM bale_sales bs JOIN operations so ON so.id=bs.sale_operation_id
                 WHERE bs.batch_id=b.id AND so.is_cancelled=0),0) sold
              FROM bale_batches b JOIN operations o ON o.id=b.harvest_operation_id
              WHERE b.item=? AND o.is_cancelled=0 AND o.op_date<=? ORDER BY o.op_date,b.id''',(item,dt)).fetchall()
            if sum(b['count']-b['sold'] for b in batches)<count:raise ValueError('Yeterli balya stoğu yok.')
            remaining=count
            for b in batches:
                take=min(remaining,b['count']-b['sold'])
                if take<=0:continue
                qty=round(take*b['kg_per_bale'],3)
                op=conn.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(season,dt,parcel,'Satış',item,qty,'kg',price/b['kg_per_bale'],round(take*price,2),'Gelir',None,f'{take} balya × {price:g} TL/adet; parti #{b["id"]}',''))
                conn.execute('INSERT INTO bale_sales(batch_id,sale_operation_id,count) VALUES(?,?,?)',(b['id'],op.lastrowid,take))
                remaining-=take
                if not remaining:break
            flash(f'{count} balya satıldı, stoktan düşüldü.','success')
        elif item in ('Arpa','Buğday'):
            qty=float(request.form.get('quantity',''))
            if not math.isfinite(qty) or qty<=0:raise ValueError()
            balance=conn.execute('''SELECT COALESCE(SUM(CASE WHEN op_type='Hasat' THEN quantity ELSE -quantity END),0)
               FROM operations WHERE is_cancelled=0 AND item=? AND op_type IN ('Hasat','Satış') AND op_date<=?''',(item,dt)).fetchone()[0]
            if qty>balance+1e-6:raise ValueError('Satış miktarı mevcut ürün stoğunu aşıyor.')
            conn.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(season,dt,parcel,'Satış',item,qty,'kg',price,round(qty*price,2),'Gelir',None,request.form.get('note','').strip(),''))
            flash('Ürün satışı kaydedildi ve stoktan düşüldü.','success')
        else:raise ValueError('Önce ürün depoya girmelidir.')
        conn.commit()
    except (ValueError,TypeError) as e:
        conn.rollback();flash('Satış kaydedilemedi: '+str(e),'error')
    except Exception:
        conn.rollback();raise
    return redirect(url_for('product_warehouse_page'))

@app.route('/tarla-hizmetleri',methods=['GET','POST'])
@login_required
def field_services_page():
    conn=db()
    if request.method=='POST':
        if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
        kind=request.form.get('action')
        if kind=='payment':
            try:
                charge_id=int(request.form.get('charge_id','0'))
                amount=float(request.form.get('amount',''))
                dt=request.form.get('payment_date','')
                datetime.strptime(dt,'%Y-%m-%d')
                charge=conn.execute('SELECT * FROM field_service_charges WHERE id=? AND cancelled=0',(charge_id,)).fetchone()
                paid=conn.execute('SELECT COALESCE(SUM(amount),0) FROM field_service_payments WHERE charge_id=?',(charge_id,)).fetchone()[0]
                if not charge or not math.isfinite(amount) or amount<=0 or amount>charge['total_amount']-paid+0.001:raise ValueError()
                conn.execute('INSERT INTO field_service_payments(charge_id,payment_date,amount,note) VALUES(?,?,?,?)',
                             (charge_id,dt,amount,request.form.get('note','').strip()))
                conn.commit();flash('Ödeme kaydedildi; ikinci gider oluşmadı.','success')
            except (ValueError,TypeError):
                flash('Ödeme tutarı veya tarih geçersiz; kalan borcu aşamaz.','error')
        elif kind=='service':
            try:
                season=request.form.get('season','')
                dt=request.form.get('service_date','')
                datetime.strptime(dt,'%Y-%m-%d')
                parcel=request.form.get('parcel_code','')
                kindname=request.form.get('service_type','')
                area=float(request.form.get('area_da',''))
                rate=float(request.form.get('rate_da',''))
                paid=float(request.form.get('paid_amount','0') or 0)
                total=round(area*rate,2)
                if season not in SEASONS or kindname not in ('Balya','Nakliye','Biçerdöver') or not conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel,)).fetchone():raise ValueError()
                if not all(math.isfinite(x) for x in (area,rate,paid)) or area<=0 or rate<=0 or paid<0 or paid>total+0.001:raise ValueError()
                if area>worked_area(conn,parcel,season)+0.001:raise ValueError()
                provider=request.form.get('provider','').strip()[:120]
                conn.execute('BEGIN IMMEDIATE')
                activity=conn.execute('INSERT INTO field_activities(season,activity_date,parcel_code,activity_type,area_da,note) VALUES(?,?,?,?,?,?)',
                     (season,dt,parcel,kindname,area,request.form.get('note','').strip()))
                aid=activity.lastrowid
                expense=conn.execute("""INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail,activity_id)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(season,dt,parcel,'İşçilik',kindname+' Hizmeti',1,'adet',total,total,'Gider','Makine',f'Faaliyet #{aid}; hizmet gideri','',aid))
                charge=conn.execute("""INSERT INTO field_service_charges(activity_id,season,parcel_code,service_type,provider,service_date,area_da,rate_da,total_amount,expense_operation_id)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",(aid,season,parcel,kindname,provider,dt,area,rate,total,expense.lastrowid))
                if paid>0:conn.execute('INSERT INTO field_service_payments(charge_id,payment_date,amount,note) VALUES(?,?,?,?)',
                  (charge.lastrowid,dt,paid,'İlk ödeme'))
                conn.commit();flash('Hizmet ve ödeme durumu kaydedildi.','success')
            except (ValueError,TypeError):
                conn.rollback();flash('Hizmet alanlarını kontrol edin.','error')
            except Exception:
                conn.rollback();raise
        else:abort(400)
        return redirect(url_for('payments_page')) if kind=='payment' else redirect(url_for('operations_page',_anchor='faaliyet-listesi'))
    charges=conn.execute("""SELECT c.*,
      COALESCE((SELECT SUM(amount) FROM field_service_payments p WHERE p.charge_id=c.id),0) paid
      FROM field_service_charges c WHERE c.cancelled=0
      ORDER BY c.service_date DESC,c.id DESC""").fetchall()
    return render_template('field_services.html',charges=charges,seasons=SEASONS,
      parcels=conn.execute('SELECT code,name FROM parcels WHERE active=1 ORDER BY code').fetchall(),
      today=date.today().isoformat(),csrf=v05_csrf())

@app.route('/odemeler',methods=['GET','POST'])
@login_required
def payments_page():
    conn=db()
    if request.method=='POST':
        if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
        source=request.form.get('source','')
        try:
            ident=int(request.form.get('id','0'))
            amount=float(request.form.get('amount',''))
            paid_date=request.form.get('payment_date','')
            datetime.strptime(paid_date,'%Y-%m-%d')
            if not math.isfinite(amount) or amount<=0:raise ValueError()
            conn.execute('BEGIN IMMEDIATE')
            if source=='service':
                obj=conn.execute('SELECT total_amount FROM field_service_charges WHERE id=? AND cancelled=0',(ident,)).fetchone()
                old=conn.execute('SELECT COALESCE(SUM(amount),0) FROM field_service_payments WHERE charge_id=?',(ident,)).fetchone()[0]
                if not obj or amount>round(obj[0]-old,2)+0.001:raise ValueError()
                conn.execute('INSERT INTO field_service_payments(charge_id,payment_date,amount,note) VALUES(?,?,?,?)',
                             (ident,paid_date,amount,request.form.get('note','').strip()))
            elif source=='rent':
                obj=conn.execute('SELECT total_amount FROM rent_contracts WHERE id=?',(ident,)).fetchone()
                old=conn.execute('SELECT COALESCE(SUM(amount),0) FROM rent_payments WHERE rent_contract_id=?',(ident,)).fetchone()[0]
                if not obj or amount>round(obj[0]-old,2)+0.001:raise ValueError()
                conn.execute('INSERT INTO rent_payments(rent_contract_id,payment_date,amount,note) VALUES(?,?,?,?)',
                             (ident,paid_date,amount,request.form.get('note','').strip()))
            else:raise ValueError()
            conn.commit()
            flash('Ödeme kaydedildi; gider ikinci kez oluşturulmadı.','success')
        except (ValueError,TypeError):
            conn.rollback()
            flash('Ödeme kaydedilemedi. Tarihi, tutarı ve kalan borcu kontrol edin.','error')
        return redirect(url_for('payments_page'))
    service=conn.execute("""SELECT c.id,c.service_date dt,c.season,c.parcel_code,
      c.service_type kind,c.provider creditor,c.total_amount total,
      COALESCE((SELECT SUM(p.amount) FROM field_service_payments p WHERE p.charge_id=c.id),0) paid
      FROM field_service_charges c WHERE c.cancelled=0""").fetchall()
    rents=conn.execute("""SELECT r.id,COALESCE(r.start_date,'') dt,r.season,r.parcel_code,
      'İcar' kind,r.landlord creditor,r.total_amount total,
      COALESCE((SELECT SUM(p.amount) FROM rent_payments p WHERE p.rent_contract_id=r.id),0) paid
      FROM rent_contracts r WHERE r.is_cancelled=0""").fetchall()
    debts=[dict(r,source='service') for r in service]+[dict(r,source='rent') for r in rents]
    debts.sort(key=lambda r:(r['dt'] or '',r['source'],r['id']),reverse=True)
    total=sum(float(r['total']) for r in debts)
    paid=sum(float(r['paid']) for r in debts)
    history=conn.execute("""SELECT p.payment_date dt,p.amount,p.note,'Hizmet' kind,c.service_type detail,c.parcel_code
      FROM field_service_payments p JOIN field_service_charges c ON c.id=p.charge_id WHERE c.cancelled=0
      UNION ALL SELECT p.payment_date,p.amount,p.note,'İcar','İcar',r.parcel_code
      FROM rent_payments p JOIN rent_contracts r ON r.id=p.rent_contract_id
      ORDER BY dt DESC LIMIT 100""").fetchall()
    return render_template('payments.html',debts=debts,history=history,
      total=total,paid=paid,today=date.today().isoformat(),csrf=v05_csrf())

@app.route('/tarla-faaliyetleri')
@login_required
def field_activities_page():
    conn=db()
    season=request.args.get('season','').strip()
    parcel=request.args.get('parcel','').strip()
    where=[];params=[]
    if season in SEASONS:where.append('f.season=?');params.append(season)
    else:season=''
    if parcel:
        if conn.execute('SELECT 1 FROM parcels WHERE code=?',(parcel,)).fetchone():
            where.append('f.parcel_code=?');params.append(parcel)
        else:parcel=''
    clause=(' WHERE '+' AND '.join(where)) if where else ''
    records=conn.execute("""SELECT f.*,p.name parcel_name,
      (SELECT COUNT(*) FROM operations o WHERE o.activity_id=f.id AND o.is_cancelled=0) line_count,
      (SELECT COALESCE(SUM(o.amount),0) FROM operations o WHERE o.activity_id=f.id AND o.is_cancelled=0) total_cost
      FROM field_activities f LEFT JOIN parcels p ON p.code=f.parcel_code
    """+clause+' ORDER BY f.activity_date DESC,f.id DESC LIMIT 300',params).fetchall()
    parcels=conn.execute('SELECT code,name FROM parcels ORDER BY code').fetchall()
    return render_template('field_activities.html',records=records,seasons=SEASONS,
        season=season,parcel=parcel,parcels=parcels)

@app.route('/tarla-faaliyeti/<int:activity_id>',methods=['GET','POST'])
@login_required
def field_activity_detail(activity_id):
    conn=db()
    activity=conn.execute('SELECT * FROM field_activities WHERE id=?',(activity_id,)).fetchone()
    if not activity:abort(404)
    if request.method=='POST':
        if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()):abort(400)
        action=request.form.get('action','save')
        note=request.form.get('note','').strip()
        lines=conn.execute("""SELECT * FROM operations WHERE activity_id=? AND is_cancelled=0 ORDER BY id""",(activity_id,)).fetchall()
        if not lines:
            flash('Faaliyette aktif malzeme bulunamadı.','error')
            return redirect(url_for('field_activity_detail',activity_id=activity_id))
        if action not in ('save','cancel'):
            abort(400)
        if action=='cancel':
            paid=conn.execute('''SELECT COALESCE(SUM(p.amount),0) FROM field_service_payments p
               JOIN field_service_charges c ON c.id=p.charge_id WHERE c.activity_id=? AND c.cancelled=0''',(activity_id,)).fetchone()[0]
            if paid>0.001:
                flash('Bu faaliyete bağlı ödeme var. Önce ödeme düzeltme işlemi gereklidir; faaliyet iptal edilmedi.','error')
                return redirect(url_for('field_activity_detail',activity_id=activity_id))
        if activity['activity_type']=='Hasat' and action=='save':
            flash('Hasat duzenlemek icin once iptal edip yeniden kaydedin.','error')
            return redirect(url_for('field_activity_detail',activity_id=activity_id))
        edits=[]
        errors=[]
        if action=='save':
            for line in lines:
                try: rate=float(request.form.get(f'rate_{line["id"]}',''))
                except (ValueError,TypeError):rate=-1
                qty=round(rate*float(activity['area_da']),3)
                if not math.isfinite(rate) or rate<=0 or qty<=0:
                    errors.append(f'{line["item"]}: dönüm başına tüketim pozitif olmalı.')
                else:edits.append((line,qty,rate))
        if errors:
            for error in errors:flash(error,'error')
            return redirect(url_for('field_activity_detail',activity_id=activity_id))
        try:
            conn.execute('BEGIN IMMEDIATE')
            # Remove all original lines only within the transaction, so FIFO
            # and inventory can be checked against the proposed entire activity.
            conn.execute('UPDATE operations SET is_cancelled=1 WHERE activity_id=? AND is_cancelled=0',(activity_id,))
            conn.execute('UPDATE field_service_charges SET cancelled=1 WHERE activity_id=?',(activity_id,))
            if action=='save':
                for line,qty,rate in edits:
                    item,detail,unit=line['item'],line['item_detail'] or '',line['unit']
                    if qty>input_stock(conn,item,detail,unit)+1e-6:
                        raise ValueError(f'{item} / {detail}: yeterli depo stoğu yok.')
                    if fifo_later_use(conn,item,unit,activity['activity_date'],detail=detail):
                        raise ValueError(f'{item} / {detail}: sonraki tarihli tüketim var; FIFO kontrolü için önce onu düzeltin.')
                    price,error=fifo_unit_cost(conn,item,unit,activity['activity_date'],qty,detail=detail)
                    if error:raise ValueError(f'{item} / {detail}: {error}')
                    line_note=f"Faaliyet #{activity_id} · Uygulama alanı: {activity['area_da']:g} da; Doz: {rate:g} {unit}/da"
                    if note:line_note+=' | '+note
                    conn.execute("""UPDATE operations SET quantity=?,unit_price=?,amount=?,note=?,is_cancelled=0 WHERE id=?""",
                        (qty,price,round(qty*price,2),line_note,line['id']))
            conn.execute('UPDATE field_activities SET note=? WHERE id=?',(note,activity_id))
            error=v05_validate_balances(conn)
            if error:raise ValueError(error)
            conn.commit()
        except (ValueError,sqlite3.Error) as e:
            conn.rollback()
            flash('Değişiklik uygulanmadı; tüm kayıtlar korundu: '+str(e),'error')
            return redirect(url_for('field_activity_detail',activity_id=activity_id))
        flash('Faaliyet ve tüm malzemeleri birlikte iptal edildi.' if action=='cancel' else 'Tüm malzeme miktarları ve FIFO maliyetleri birlikte güncellendi.','success')
        return redirect(url_for('field_activities_page') if action=='cancel' else url_for('field_activity_detail',activity_id=activity_id))
    lines=conn.execute("""SELECT id,item,COALESCE(item_detail,'') item_detail,
      quantity,unit,unit_price,amount,category,note FROM operations
      WHERE activity_id=? AND is_cancelled=0 ORDER BY id""",(activity_id,)).fetchall()
    total=sum(float(x['amount']) for x in lines)
    return render_template('field_activity_detail.html',activity=activity,lines=lines,
        total=total,csrf=v05_csrf())

@app.route('/islemler', methods=['GET','POST'])
@login_required
def operations_page():
    conn=db()
    if request.method=='POST':
        season=request.form.get('season',''); op_date=request.form.get('op_date',''); parcel_code=request.form.get('parcel_code') or None
        op_type=request.form.get('op_type',''); item=request.form.get('item','').strip(); unit=normalize_unit(request.form.get('unit',''))
        direction=request.form.get('direction',''); category=request.form.get('category') or None; note=request.form.get('note','').strip(); item_detail=request.form.get('item_detail','').strip()
        item,item_detail=canonical_item(item,category,op_type,item_detail)
        if op_type=='Yakıt':
            work=request.form.get('field_work','').strip()
            if work:
                note=('Tarla işi: '+work+' | '+note).strip(' |')
        if op_type in STOCK_OPERATION_TYPES or op_type in ('Hasat','Satış'):
            flash('Tarla işlemlerini üstteki formdan, satışları Ürün Deposu ekranından kaydedin.','error')
            return redirect(url_for('operations_page'))
            selected=selected_depot_item(conn,request.form)
            if selected:
                item=selected['item']; item_detail=selected['item_detail'];unit=selected['unit'];category=selected['category'];direction='Gider'
                if op_type=='Ekim' and (item=='Gübre' or category=='Gübre'):
                    op_type='Gübreleme'
                if op_type=='Ekim' and item=='Motorin':
                    op_type='Yakıt'

            else:
                item='';item_detail=''

        try: qty=float(request.form.get('quantity','')); unit_price=float(request.form.get('unit_price') or 0)
        except ValueError: qty=-1; unit_price=-1
        errors=[]
        if op_type in STOCK_OPERATION_TYPES:
            parcel_row=conn.execute('SELECT area_m2 FROM parcels WHERE code=? AND active=1',(parcel_code,)).fetchone() if parcel_code else None
            try:
                rate=float(request.form.get('rate_per_decare',''))
                application_area=float(request.form.get('application_area',''))
            except (ValueError,TypeError):
                rate=-1; application_area=-1
            if not parcel_row:
                errors.append('Dönüm başına hesaplama için geçerli parsel seçin.')
            elif application_area<=0 or application_area>worked_area(conn,parcel_code,season)+1e-6:
                errors.append('Uygulama alanı sıfırdan büyük ve sezonluk işlenen alanı aşmamalıdır.')
            if rate<=0 or not math.isfinite(rate) or not math.isfinite(application_area):
                errors.append('Dönüm başına miktar geçerli ve sıfırdan büyük olmalıdır.')
            if not errors:
                qty=round(rate*application_area,3)
                if qty<=0: errors.append('Hesaplanan toplam miktar sıfırdan büyük olmalıdır.')
                # Preserve a record of the applied area for future partial-field reporting.
                note=(note+' | ' if note else '')+f'Uygulama alanı: {application_area:g} da; Doz: {rate:g} {unit}/da'
        if season not in SEASONS: errors.append('Geçerli bir üretim sezonu seçin.')
        try: datetime.strptime(op_date,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli bir tarih girin.')
        if parcel_code and not conn.execute('SELECT 1 FROM parcels WHERE code=? AND active=1',(parcel_code,)).fetchone(): errors.append('Seçilen parsel bulunamadı.')
        if op_type not in OP_TYPES: errors.append('İşlem türünü listeden seçin.')
        if op_type in STOCK_OPERATION_TYPES and not parcel_code: errors.append('Ekim, gübreleme, ilaçlama ve yakıt işlemleri için parsel seçin.')
        if not item: errors.append('Depoda tanımlı ürün ve çeşidi listeden seçin.' if op_type in STOCK_OPERATION_TYPES else 'Ürün/malzeme açıklaması zorunludur.')
        if qty<=0: errors.append('Miktar sıfırdan büyük olmalıdır.')
        if unit_price<0: errors.append('Birim fiyat negatif olamaz.')
        if unit not in UNITS: errors.append('Birimi listeden seçin.')
        if direction not in ['Gelir','Gider','Nötr']: errors.append('Gelir/gider türünü seçin.')
        if op_type=='Satış':
            if not parcel_code: errors.append('Satış için parsel seçin.')
            available=product_stock(conn,item)
            if qty>available+1e-6: errors.append(f'Satış miktarı mevcut ürün stoğunu aşıyor. Mevcut: {available:g} {unit}.')
            if unit_price<=0: errors.append('Satış için birim satış fiyatı sıfırdan büyük olmalıdır.')
            direction='Gelir'
        if op_type=='Hasat':
            if not parcel_code: errors.append('Hasat için parsel seçin.')
            direction='Nötr'; unit_price=0
        if op_type=='İcar/Kiralama': direction='Gider'
        if op_type not in ['Hasat','Satış','İcar/Kiralama'] and direction=='Gider' and not stock_item_exists(conn,item,item_detail) and conn.execute('SELECT 1 FROM stock_purchases WHERE is_cancelled=0 AND item=? LIMIT 1',(item,)).fetchone():
            errors.append('Bu ürünün seçilen çeşidi depoda bulunmuyor. Depodaki çeşit adını kontrol edin.')
        if op_type not in ['Hasat','Satış','İcar/Kiralama'] and direction=='Gider' and stock_item_exists(conn,item,item_detail):
            available=input_stock(conn,item,item_detail,unit)
            if qty>available+1e-6: errors.append(f'Depoda yeterli stok yok. Mevcut: {available:g} {unit}. Önce depo alımı kaydedin veya miktarı düzeltin.')
            if fifo_later_use(conn,item,unit,op_date,detail=item_detail):
                errors.append('Sonraki tüketimler varken geçmiş tarihli yeni tüketim eklenemez; FIFO sırası korunmalıdır.')
            else:
                price, fifo_error=fifo_unit_cost(conn,item,unit,op_date,qty,detail=item_detail)
                if fifo_error: errors.append(fifo_error)
                else: unit_price=price
        if op_type in ['Hasat','Satış'] and unit!='kg': errors.append('Hasat ve satış miktarı kg biriminde girilmelidir.')
        if errors:
            for e in errors: flash(e,'error')
        else:
            amount=round(qty*unit_price,2) if direction in ['Gelir','Gider'] else 0
            conn.execute('INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note,item_detail) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (season,op_date,parcel_code,op_type,item,qty,unit,unit_price,amount,direction,category,note,item_detail))
            conn.commit(); flash('İşlem kaydedildi; ilgili stok ve raporlar veritabanından güncellenecek.','success'); return redirect(url_for('operations_page'))
    # Server-side filtering: searches all records, not only the latest 150.
    filters={k:request.args.get(k,'').strip() for k in ('q','season_filter','parcel_filter','type_filter','date_from','date_to')}
    where=['o.is_cancelled=0','o.activity_id IS NULL']; params=[]
    if filters['q']:
        where.append("(o.item LIKE ? OR o.note LIKE ? OR o.op_type LIKE ? OR p.name LIKE ? OR o.parcel_code LIKE ?)")
        params.extend(['%'+filters['q']+'%']*5)
    for field,col in [('season_filter','o.season'),('parcel_filter','o.parcel_code'),('type_filter','o.op_type')]:
        if filters[field]: where.append(col+'=?'); params.append(filters[field])
    for field,operator in [('date_from','>='),('date_to','<=')]:
        if filters[field]:
            try: datetime.strptime(filters[field],'%Y-%m-%d')
            except ValueError: filters[field]=''
            else: where.append('o.op_date'+operator+'?'); params.append(filters[field])
    clause=' AND '.join(where)
    joins=' FROM operations o LEFT JOIN parcels p ON p.code=o.parcel_code WHERE '+clause
    total=conn.execute('SELECT COUNT(*)'+joins,params).fetchone()[0]
    try: page=max(1,int(request.args.get('page','1')))
    except ValueError: page=1
    page_size=50; pages=max(1,(total+page_size-1)//page_size); page=min(page,pages)
    rows=conn.execute('SELECT o.*,p.name parcel_name'+joins+' ORDER BY o.op_date DESC,o.id DESC LIMIT ? OFFSET ?',params+[page_size,(page-1)*page_size]).fetchall()
    activities=conn.execute("""SELECT f.*,p.name parcel_name,
      (SELECT COUNT(*) FROM operations o WHERE o.activity_id=f.id AND o.is_cancelled=0) line_count,
      (SELECT COALESCE(SUM(o.amount),0) FROM operations o WHERE o.activity_id=f.id AND o.is_cancelled=0 AND o.direction='Gider') total_cost
      FROM field_activities f LEFT JOIN parcels p ON p.code=f.parcel_code
      WHERE f.season=? AND EXISTS(SELECT 1 FROM operations o WHERE o.activity_id=f.id AND o.is_cancelled=0)
      ORDER BY f.activity_date DESC,f.id DESC LIMIT 300""",(request.args.get('season_filter') if request.args.get('season_filter') in SEASONS else SEASONS[0],)).fetchall()
    return render_template('operations.html', activities=activities, operations=rows, parcels=conn.execute('SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code').fetchall(), worked_areas={season:{r['code']:worked_area(conn,r['code'],season) for r in conn.execute('SELECT code FROM parcels WHERE active=1')} for season in SEASONS},
       seasons=SEASONS, op_types=[t for t in OP_TYPES if t not in STOCK_OPERATION_TYPES and t not in ('Pulluk Sürme','Kazayağı Sürme','Tırmık Sürme')], units=UNITS, categories=CATEGORIES, today=date.today().isoformat(),csrf=v05_csrf(),
       filters=filters,total=total,page=page,pages=pages,depot_choices=depot_choices(conn),stock_types=STOCK_OPERATION_TYPES,
       depot_balances=[dict(id=r['id'],remaining=input_stock(conn,r['item'],r['item_detail'],r['unit']),unit=r['unit']) for r in depot_choices(conn)])

def stock_item_exists(conn,item,detail=''):
    return conn.execute("SELECT 1 FROM stock_purchases WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? LIMIT 1",(item,detail or '')).fetchone() is not None

def input_stock(conn,item,detail='',unit=None):
    where=" AND unit=?" if unit else ""
    args=(item,detail or '')+((unit,) if unit else ())
    bought=conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM stock_purchases WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=?"+where,args).fetchone()['n']
    used=conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM operations WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=?"+where+" AND direction='Gider' AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama')",args).fetchone()['n']
    return bought-used

def product_stock(conn,item):
    # Product names can include varieties, e.g. Buğday (Reis); match the selected product family.
    family=item.split(' (')[0].strip()
    harvested=conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM operations WHERE is_cancelled=0 AND op_type='Hasat' AND (item=? OR item LIKE ?)",(item,family+'%')).fetchone()['n']
    sold=conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM operations WHERE is_cancelled=0 AND op_type='Satış' AND (item=? OR item LIKE ?)",(item,family+'%')).fetchone()['n']
    return harvested-sold


def depot_timeline_deficits(conn):
    events={}
    for r in conn.execute("SELECT item,COALESCE(item_detail,'') detail,unit,purchase_date d,quantity q FROM stock_purchases WHERE is_cancelled=0"):
        key=(r['item'],r['detail'],r['unit'],r['d'])
        events[key]=events.get(key,0.0)+float(r['q'])
    for r in conn.execute("""SELECT item,COALESCE(item_detail,'') detail,unit,op_date d,quantity q FROM operations
        WHERE is_cancelled=0 AND direction='Gider' AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama')"""):
        key=(r['item'],r['detail'],r['unit'],r['d'])
        events[key]=events.get(key,0.0)-float(r['q'])
    balances={}; deficits={}
    for (item,detail,unit,d),delta in sorted(events.items()):
        k=(item,detail,unit)
        balances[k]=balances.get(k,0.0)+delta
        deficits[(item,detail,unit,d)]=max(0.0,-balances[k])
    return deficits

def new_depot_deficit_error(before,after):
    for (item,detail,unit,d),new_deficit in sorted(after.items()):
        if new_deficit>before.get((item,detail,unit,d),0.0)+1e-6:
            return f'{item} / {detail or "Çeşit belirtilmemiş"}: {d} tarihinde bu değişiklik nedeniyle stok açığı oluşuyor veya büyüyor. İlgili tüketim kaydını kontrol edin.'
    return None

def fifo_unit_cost(conn,item,unit,on_date,qty,exclude_id=None,detail=''):
    lots=conn.execute("SELECT id,purchase_date,quantity,unit_price FROM stock_purchases WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=? AND purchase_date<=? ORDER BY purchase_date,id",(item,detail or '',unit,on_date)).fetchall()
    if not lots: return None, 'İşlem tarihinde uygun depo alımı bulunamadı.'
    balances={r['id']:float(r['quantity']) for r in lots}
    uses=conn.execute("SELECT id,op_date,quantity FROM operations WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=? AND direction='Gider' AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama') AND (op_date<? OR (op_date=? AND id<?)) ORDER BY op_date,id",(item,detail or '',unit,on_date,on_date,exclude_id or 999999999)).fetchall()
    for use in uses:
        need=float(use['quantity'])
        for lot in lots:
            if lot['purchase_date']>use['op_date']: break
            take=min(need,balances[lot['id']]); balances[lot['id']]-=take; need-=take
            if need<1e-7: break
        if need>1e-7: return None,'Eski tüketimler için tarih sırasıyla yeterli depo alımı bulunmuyor.'
    need=qty; cost=0
    for lot in lots:
        take=min(need,balances[lot['id']]); need-=take; cost+=take*lot['unit_price']
        if need<1e-7: break
    if need>1e-7: return None,'İşlem tarihinde FIFO stoğu yetersiz.'
    return cost/qty,None

def fifo_later_use(conn,item,unit,dt,exclude_id=None,detail=''):
    return conn.execute("SELECT 1 FROM operations WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=? AND op_date>? AND direction='Gider' AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama') AND (? IS NULL OR id<>?) LIMIT 1",(item,detail or '',unit,dt,exclude_id,exclude_id)).fetchone() is not None

def weighted_cost_at_date(conn,item,on_date,detail=''):
    r=conn.execute('''SELECT SUM(quantity*unit_price)/NULLIF(SUM(quantity),0) n
        FROM stock_purchases WHERE is_cancelled=0 AND item=? AND purchase_date<=?''',(item,on_date)).fetchone()
    return None if r['n'] is None else float(r['n'])

def weighted_cost(conn,item,detail=''):
    r=conn.execute('SELECT SUM(quantity*unit_price)/NULLIF(SUM(quantity),0) n FROM stock_purchases WHERE is_cancelled=0 AND item=?',(item,)).fetchone()
    return float(r['n'] or 0)


@app.route('/urun-deposu')
@login_required
def product_warehouse_page():
    conn=db()
    rows=conn.execute("""SELECT item,unit,
      SUM(CASE WHEN op_type='Hasat' THEN quantity ELSE 0 END) harvested,
      SUM(CASE WHEN op_type='Satış' THEN quantity ELSE 0 END) sold
      FROM operations WHERE is_cancelled=0 AND op_type IN ('Hasat','Satış')
      GROUP BY item,unit ORDER BY item,unit""").fetchall()
    balances=[dict(item=r['item'],unit=r['unit'],harvested=float(r['harvested']),
        sold=float(r['sold']),remaining=float(r['harvested'])-float(r['sold'])) for r in rows]
    bales=conn.execute('''SELECT b.item, SUM(b.count) produced, SUM(b.count-COALESCE((SELECT SUM(bs.count) FROM bale_sales bs JOIN operations so ON so.id=bs.sale_operation_id WHERE bs.batch_id=b.id AND so.is_cancelled=0),0)) remaining
       FROM bale_batches b JOIN operations o ON o.id=b.harvest_operation_id WHERE o.is_cancelled=0 GROUP BY b.item''').fetchall()
    allocations,fifo_issues=warehouse_fifo_allocations(conn)
    sales_history=[]
    for sale in conn.execute("""SELECT id,op_date,season,item,quantity,amount,unit_price,parcel_code
         FROM operations WHERE is_cancelled=0 AND op_type='Satış' ORDER BY op_date DESC,id DESC LIMIT 150"""):
        sales_history.append(dict(sale=dict(sale),sources=allocations.get(sale['id'],[])))
    return render_template('product_warehouse.html',sales_history=sales_history,fifo_issues=fifo_issues,balances=balances,bales=bales,
       seasons=SEASONS,parcels=conn.execute('SELECT code,name FROM parcels WHERE active=1 ORDER BY code').fetchall(),
       csrf=v05_csrf(),today=date.today().isoformat())

@app.route('/depo/piyasa-fiyati',methods=['POST'])
@login_required
def update_market_price():
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()): abort(400)
    conn=db()
    item=request.form.get('item','').strip()
    unit=normalize_unit(request.form.get('unit','')).strip()
    dt=request.form.get('price_date','').strip()
    try: price=float(request.form.get('unit_price',''))
    except (ValueError,TypeError): price=-1
    known=conn.execute('SELECT unit FROM stock_purchases WHERE is_cancelled=0 AND item=? LIMIT 1',(item,)).fetchone()
    if not known or known['unit']!=unit or price<0:
        flash('Malzeme, birim veya piyasa fiyatı geçersiz.','error')
    else:
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: flash('Geçerli fiyat tarihi girin.','error')
        else:
            conn.execute('''INSERT INTO market_price_history(item,unit,unit_price,price_date)
                VALUES(?,?,?,?) ON CONFLICT(item,unit,price_date) DO UPDATE SET
                unit_price=excluded.unit_price''',(item,unit,price,dt))
            conn.execute('''INSERT INTO market_prices(item,unit,unit_price,price_date)
                VALUES(?,?,?,?) ON CONFLICT(item) DO UPDATE SET
                unit=excluded.unit,unit_price=excluded.unit_price,
                price_date=excluded.price_date,updated_at=CURRENT_TIMESTAMP
                WHERE excluded.price_date >= market_prices.price_date''',(item,unit,price,dt))
            conn.commit()
            flash('Piyasa fiyatı güncellendi. Bu değer alış maliyetini değiştirmez.','success')
    return redirect(url_for('depot_page'))

@app.route('/depo', methods=['GET','POST'])
@login_required
def depot_page():
    conn=db()
    if request.method=='POST':
        season=request.form.get('season',''); dt=request.form.get('purchase_date',''); cat=request.form.get('category',''); item=request.form.get('item','').strip(); unit=normalize_unit(request.form.get('unit',''))
        item_detail=request.form.get('item_detail','').strip()
        item,item_detail=canonical_item(item,cat,'',item_detail)
        try: qty=float(request.form.get('quantity','')); price=float(request.form.get('unit_price',''))
        except ValueError: qty=-1; price=-1
        errors=[]
        if season not in SEASONS: errors.append('Geçerli sezon seçin.')
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli alım tarihi girin.')
        if cat not in CATEGORIES: errors.append('Kategori seçin.')
        if not item: errors.append('Malzeme adı zorunludur.')
        if qty<=0: errors.append('Alım miktarı sıfırdan büyük olmalıdır.')
        if price<0: errors.append('Alış fiyatı negatif olamaz.')
        if unit not in UNITS: errors.append('Birim seçin.')
        # Prevent same-item/unit mismatches that would corrupt stock math.
        old=conn.execute('SELECT unit FROM stock_purchases WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? LIMIT 1',(item,item_detail or '')).fetchone()
        if old and old['unit']!=unit: errors.append(f"Bu malzeme daha önce '{old['unit']}' birimiyle kaydedilmiş. Aynı malzeme için aynı birimi kullanın.")
        # A new purchase is always allowed, including the same date as prior use.
        # Previously saved consumption costs remain unchanged.
        if errors:
            for e in errors: flash(e,'error')
        else:
            conn.execute('INSERT INTO stock_purchases(season,purchase_date,category,item,quantity,unit,unit_price,supplier_note,item_detail) VALUES(?,?,?,?,?,?,?,?,?)',
              (season,dt,cat,item,qty,unit,price,request.form.get('supplier_note','').strip(),item_detail))
            conn.commit(); flash('Yeni depo alımı kaydedildi. Önceki tüketim maliyetleri değiştirilmedi.','success'); return redirect(url_for('depot_page'))
    summary=conn.execute('''SELECT item,COALESCE(item_detail,'') item_detail,category,unit,SUM(quantity) bought,
      COALESCE((SELECT SUM(o.quantity) FROM operations o WHERE o.is_cancelled=0 AND o.item=s.item AND COALESCE(o.item_detail,'')=COALESCE(s.item_detail,'') AND o.unit=s.unit AND o.direction='Gider' AND o.op_type NOT IN ('Hasat','Satış','İcar/Kiralama')),0) used,
      SUM(quantity*unit_price)/SUM(quantity) avg_cost FROM stock_purchases s WHERE s.is_cancelled=0 GROUP BY item,COALESCE(item_detail,''),category,unit ORDER BY item,item_detail''').fetchall()
    market_rows=conn.execute('''SELECT s.item,s.item_detail,s.unit,s.bought,s.used,s.avg_cost,
          m.unit_price market_price,m.price_date
          FROM (SELECT p.item,COALESCE(p.item_detail,'') item_detail,p.unit,SUM(p.quantity) bought,
                COALESCE((SELECT SUM(o.quantity) FROM operations o WHERE o.is_cancelled=0 AND o.item=p.item AND COALESCE(o.item_detail,'')=COALESCE(p.item_detail,'') AND o.unit=p.unit
                AND o.direction='Gider' AND o.op_type NOT IN ('Hasat','Satış','İcar/Kiralama')),0) used,
                SUM(p.quantity*p.unit_price)/SUM(p.quantity) avg_cost
                FROM stock_purchases p WHERE p.is_cancelled=0 GROUP BY p.item,COALESCE(p.item_detail,''),p.unit) s
          LEFT JOIN market_prices m ON m.item=s.item AND m.unit=s.unit
          ORDER BY s.item''').fetchall()
    # Show existing historical stock discrepancies without inventing purchases or editing records.
    deficits=depot_timeline_deficits(conn)
    stock_warnings=[]
    for (warn_item,warn_detail,warn_unit,warn_date),shortfall in sorted(deficits.items(),key=lambda x:(x[0][3],x[0][0])):
        if shortfall <= 0.000001: continue
        uses=conn.execute("""SELECT id,op_date,op_type,quantity,parcel_code FROM operations
            WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=? AND op_date=? AND direction='Gider'
            AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama') ORDER BY id""",(warn_item,warn_detail,warn_unit,warn_date)).fetchall()
        stock_warnings.append(dict(item=warn_item,item_detail=warn_detail,unit=warn_unit,day=warn_date,shortfall=shortfall,uses=uses))
        if len(stock_warnings)>=15:break
    purchases=conn.execute('SELECT * FROM stock_purchases WHERE is_cancelled=0 ORDER BY purchase_date DESC,id DESC LIMIT 100').fetchall()
    return render_template('depot.html', app_version='1.0.8', stock_warnings=stock_warnings, summary=summary, purchases=purchases, market_rows=market_rows, csrf=v05_csrf(), seasons=SEASONS, categories=CATEGORIES, units=UNITS, today=date.today().isoformat())

def leased_area(conn,code,season):
    row=conn.execute('SELECT leased_area_da FROM parcel_season_areas WHERE parcel_code=? AND season=?',(code,season)).fetchone()
    return float(row['leased_area_da']) if row else 0.0

@app.route('/kiralar', methods=['GET','POST'])
@login_required
def rents_page():
    conn=db()
    if request.method=='POST':
        landlord=request.form.get('landlord','').strip(); parcel=request.form.get('parcel_code',''); season=request.form.get('season','')
        start=request.form.get('start_date') or None; end=request.form.get('end_date') or None; due=request.form.get('due_note','').strip()
        try: rate=float(request.form.get('rate_per_da','')); area=leased_area(conn,parcel,season)
        except (ValueError,TypeError): rate=-1; area=0
        errors=[]
        if not landlord: errors.append('Kiraya veren zorunludur.')
        if not conn.execute('SELECT 1 FROM parcels WHERE code=?',(parcel,)).fetchone(): errors.append('Parsel seçin.')
        if season not in SEASONS: errors.append('Sezon seçin.')
        if not math.isfinite(rate) or rate<0: errors.append('Dönüm kirası geçersiz.')
        if area<=0: errors.append('Bu parsel ve sezon için Parseller bölümünde icar kullanım alanı tanımlayın.')
        if start and end and end<start: errors.append('Bitiş tarihi başlangıç tarihinden önce olamaz.')
        if errors:
            for e in errors: flash(e,'error')
        else:
            try:
                conn.execute('INSERT INTO rent_contracts(landlord,parcel_code,season,start_date,end_date,area_da,rate_per_da,total_amount,due_note) VALUES(?,?,?,?,?,?,?,?,?)',
                  (landlord,parcel,season,start,end,area,rate,round(area*rate,2),due)); conn.commit()
                flash('Kira sözleşmesi kaydedildi. Ödemeleri Ödemeler bölümünden takip edin.','success'); return redirect(url_for('rents_page'))
            except sqlite3.IntegrityError: flash('Aynı parsel, sezon, kiraya veren ve başlangıç tarihiyle sözleşme zaten var.','error')
    rows=conn.execute('''SELECT r.*,p.name parcel_name,
       COALESCE((SELECT SUM(pay.amount) FROM rent_payments pay WHERE pay.rent_contract_id=r.id),0) paid,
       COALESCE(a.leased_area_da,0) current_leased_area
       FROM rent_contracts r JOIN parcels p ON p.code=r.parcel_code
       LEFT JOIN parcel_season_areas a ON a.parcel_code=r.parcel_code AND a.season=r.season
       WHERE r.is_cancelled=0 ORDER BY r.id DESC''').fetchall()
    return render_template('rents.html', rents=rows, parcels=conn.execute('SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code').fetchall(),
      leased_areas={season:{r['code']:leased_area(conn,r['code'],season) for r in conn.execute('SELECT code FROM parcels WHERE active=1')} for season in SEASONS}, seasons=SEASONS)

@app.route('/destekler', methods=['GET','POST'])
@login_required
def supports_page():
    conn=db()
    if request.method=='POST':
        dt=request.form.get('payment_date',''); season=request.form.get('season',''); st=request.form.get('support_type','').strip(); desc=request.form.get('description','').strip(); crop=request.form.get('crop') or None
        try: amount=float(request.form.get('amount',''))
        except ValueError: amount=-1
        errors=[]
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli ödeme tarihi girin.')
        if season not in SEASONS: errors.append('Sezon seçin.')
        if not st or not desc: errors.append('Destek türü ve açıklama zorunludur.')
        if amount<=0: errors.append('Destek tutarı sıfırdan büyük olmalıdır.')
        if errors:
            for e in errors: flash(e,'error')
        else:
            conn.execute('INSERT INTO supports(payment_date,season,support_type,description,crop,amount) VALUES(?,?,?,?,?,?)',(dt,season,st,desc,crop,amount)); conn.commit()
            flash('Destek bir kez kaydedildi; işletme gelirine bir kez dahil edilecek.','success'); return redirect(url_for('supports_page'))
    rows=conn.execute('SELECT * FROM supports WHERE is_cancelled=0 ORDER BY payment_date DESC,id DESC').fetchall()
    return render_template('supports.html', supports=rows, seasons=SEASONS, today=date.today().isoformat())

@app.route('/bakim', methods=['GET','POST'])
@login_required
def maintenance_page():
    conn=db()
    if request.method=='POST':
        dt=request.form.get('service_date',''); season=request.form.get('season',''); machine=request.form.get('machine','').strip(); desc=request.form.get('description','').strip(); note=request.form.get('note','').strip()
        try:
            cost=float(request.form.get('cost','0')); hours=float(request.form.get('work_hours') or 0)
        except ValueError:
            cost=-1; hours=-1
        errors=[]
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli bakım tarihi girin.')
        if season not in SEASONS: errors.append('Geçerli sezon seçin.')
        if not machine or not desc: errors.append('Makine ve bakım açıklaması zorunludur.')
        if cost<0 or hours<0: errors.append('Tutar ve çalışma saati negatif olamaz.')
        if errors:
            for e in errors: flash(e,'error')
        else:
            conn.execute('INSERT INTO machine_maintenance(season,service_date,machine,work_hours,description,cost,note) VALUES(?,?,?,?,?,?,?)',(season,dt,machine,hours,desc,cost,note)); conn.commit()
            flash('Makine bakım kaydı eklendi.','success'); return redirect(url_for('maintenance_page'))
    rows=conn.execute('SELECT * FROM machine_maintenance WHERE is_cancelled=0 ORDER BY service_date DESC,id DESC').fetchall()
    return render_template('maintenance.html', rows=rows, seasons=SEASONS, today=date.today().isoformat())

def infer_sown_crop(item, category='', note=''):
    """Infer crop from existing sowing record, without a separate report input."""
    label=' '.join(str(x or '') for x in (item, category, note)).casefold()
    label=label.replace('ı','i').replace('ğ','g').replace('ü','u').replace('ş','s').replace('ö','o').replace('ç','c')
    found=[]
    for crop, terms in {'Arpa':('arpa','slobella'), 'Buğday':('bugday',), 'Yulaf':('yulaf',), 'Çavdar':('cavdar',)}.items():
        if any(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',label) for term in terms):
            found.append(crop)
    return found[0] if len(found)==1 else None


@app.route('/cesit-verim')
@login_required
def variety_yield_page():
    conn=db()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS: season=SEASONS[0]
    parcel_filter=request.args.get('parcel','').strip()
    parcel_options=conn.execute("SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code").fetchall()
    areas={r['code']:worked_area(conn,r['code'],season) for r in parcel_options}
    if parcel_filter not in areas: parcel_filter=''
    ops=conn.execute("""SELECT parcel_code,op_type,item,COALESCE(item_detail,'') item_detail,
        quantity,unit,amount,direction FROM operations
        WHERE is_cancelled=0 AND season=? AND parcel_code IS NOT NULL ORDER BY op_date,id""",(season,)).fetchall()
    by_parcel={}
    for o in ops:
        code=o['parcel_code']
        if code not in areas: continue
        entry=by_parcel.setdefault(code,dict(sowings={},harvest=0.0,harvest_count=0,expense=0.0,income=0.0))
        if o['direction']=='Gider': entry['expense']+=float(o['amount'])
        if o['direction']=='Gelir': entry['income']+=float(o['amount'])
        if o['op_type']=='Hasat' and o['unit']=='kg':
            entry['harvest']+=float(o['quantity']);entry['harvest_count']+=1
        if o['op_type']=='Ekim' and o['unit']=='kg':
            crop=infer_sown_crop(o['item'])
            if crop:
                key=(crop,o['item_detail'].strip() or 'Çeşit belirtilmemiş')
                entry['sowings'][key]=entry['sowings'].get(key,0.0)+float(o['quantity'])
    rows=[]
    for code,e in by_parcel.items():
        if parcel_filter and code!=parcel_filter: continue
        for (crop,variety),seed in e['sowings'].items():
            unique=len(e['sowings'])==1
            area=areas[code]
            harvest=e['harvest'] if unique and e['harvest_count'] else None
            rows.append(dict(parcel=code,crop=crop,variety=variety,area=area,seed=seed,
                seed_da=seed/area if area else None,harvest=harvest,
                yield_da=harvest/area if harvest is not None and area else None,
                difference=e['income']-e['expense'] if unique else None,mixed=not unique))
    rows.sort(key=lambda r:(r['crop'],r['variety'],r['parcel']))
    groups={}
    for r in rows:
        k=(r['crop'],r['variety'])
        g=groups.setdefault(k,dict(crop=r['crop'],variety=r['variety'],area=0.0,seed=0.0,
            harvest=0.0,harvest_area=0.0,harvest_parcels=0,parcels=0))
        g['area']+=r['area'];g['seed']+=r['seed'];g['parcels']+=1
        if r['harvest'] is not None:
            g['harvest']+=r['harvest'];g['harvest_area']+=r['area'];g['harvest_parcels']+=1
    summary=[]
    for g in groups.values():
        g['seed_da']=g['seed']/g['area'] if g['area'] else None
        g['yield_da']=g['harvest']/g['harvest_area'] if g['harvest_area'] else None
        summary.append(g)
    return render_template('variety_yield.html',season=season,seasons=SEASONS,
        parcel_filter=parcel_filter,parcel_options=parcel_options,rows=rows,summary=summary)


@app.route('/gubre-analizi')
@login_required
def fertilizer_analysis_page():
    conn=db()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS: season=SEASONS[0]
    parcel_options=conn.execute("SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code").fetchall()
    parcels={r['code']:r for r in parcel_options}
    selected=request.args.get('parcel','').strip()
    if selected not in parcels: selected=''
    records=conn.execute("""SELECT parcel_code,op_type,item,COALESCE(item_detail,'') detail,
        quantity,unit,amount,direction,COALESCE(category,'') category FROM operations
        WHERE season=? AND is_cancelled=0 AND parcel_code IS NOT NULL
        ORDER BY op_date,id""",(season,)).fetchall()
    sowings={}; harvest={}; fertilizers={}
    for o in records:
        code=o['parcel_code']
        if code not in parcels: continue
        if o['op_type']=='Ekim':
            crop=infer_sown_crop(o['item'])
            if crop: sowings.setdefault(code,set()).add((crop,o['detail'] or 'Çeşit belirtilmemiş'))
        if o['op_type']=='Hasat' and o['unit']=='kg':
            harvest[code]=harvest.get(code,0)+float(o['quantity'])
        # Fertilizer reporting follows the consumed material, not the field-work label.
        # Legacy records may have op_type='Ekim' even when fertilizer was used.
        item_norm=(o['item'] or '').strip().casefold()
        cat_norm=(o['category'] or '').strip().casefold()
        is_fertilizer=(item_norm=='gübre' or cat_norm=='gübre' or
            (o['op_type']=='Gübreleme' and item_norm not in ('motorin','mazot','buğday','arpa')))
        if is_fertilizer and o['direction']=='Gider':
            key=(code,o['item'],o['detail'] or 'Çeşit belirtilmemiş',o['unit'])
            v=fertilizers.setdefault(key,{'quantity':0.,'cost':0.,'count':0})
            v['quantity']+=float(o['quantity']);v['cost']+=float(o['amount']);v['count']+=1
    rows=[];groups={}
    for (code,item,detail,unit),v in fertilizers.items():
        if selected and code!=selected: continue
        area=worked_area(conn,code,season)
        crops=sowings.get(code,set())
        crop_label=next(iter(crops)) if len(crops)==1 else None
        yield_da=harvest[code]/area if crop_label and code in harvest and area else None
        row=dict(parcel=code,product=item,detail=detail,unit=unit,
            crop=crop_label[0] if crop_label else None,
            seed_variety=crop_label[1] if crop_label else None,
            area=area,quantity=v['quantity'],cost=v['cost'],count=v['count'],
            quantity_da=v['quantity']/area if area else None,
            cost_da=v['cost']/area if area else None,yield_da=yield_da)
        rows.append(row)
        key=(item,detail,unit)
        g=groups.setdefault(key,dict(product=item,detail=detail,unit=unit,
            quantity=0.,cost=0.,parcels=set(),count=0))
        g['quantity']+=v['quantity'];g['cost']+=v['cost'];g['parcels'].add(code);g['count']+=v['count']
    rows.sort(key=lambda x:(x['detail'],x['parcel']))
    summary=[]
    for g in groups.values():
        g['parcel_count']=len(g['parcels'])
        # Count each parcel only once within each fertilizer type.
        g['area']=sum(worked_area(conn,c,season) for c in g['parcels'])
        g['quantity_da']=g['quantity']/g['area'] if g['area'] else None
        g['cost_da']=g['cost']/g['area'] if g['area'] else None
        summary.append(g)
    summary.sort(key=lambda x:(x['product'],x['detail']))
    return render_template('fertilizer_analysis.html',season=season,seasons=SEASONS,
        parcel_options=parcel_options,selected=selected,rows=rows,summary=summary)


@app.route('/raporlar/uretim-ekonomisi')
@login_required
def production_economy_report():
    conn=db()
    seasons=list(SEASONS)
    # Historic seasons already in the database are shown as well.
    for table in ('operations','supports'):
        for r in conn.execute(f'SELECT DISTINCT season FROM {table} WHERE season IS NOT NULL'):
            if r['season'] not in seasons: seasons.append(r['season'])
    seasons.sort()
    rows=[]
    for season in seasons:
        expenses=conn.execute("""SELECT COALESCE(SUM(amount),0) total FROM operations
            WHERE season=? AND is_cancelled=0 AND direction='Gider'""",(season,)).fetchone()['total']
        income=conn.execute("""SELECT COALESCE(SUM(amount),0) total FROM operations
            WHERE season=? AND is_cancelled=0 AND direction='Gelir'""",(season,)).fetchone()['total']
        supports=conn.execute("""SELECT COALESCE(SUM(amount),0) total FROM supports
            WHERE season=? AND is_cancelled=0""",(season,)).fetchone()['total']
        breakdown=conn.execute("""SELECT CASE
            WHEN lower(COALESCE(category,'')) IN ('mazot','motorin') OR lower(item)='motorin' OR op_type='Yakıt' THEN 'Motorin'
            WHEN category='Gübre' THEN 'Gübre'
            WHEN category='Tohum' THEN 'Tohum'
            ELSE 'Diğer' END kind, SUM(amount) total
            FROM operations WHERE season=? AND is_cancelled=0 AND direction='Gider'
            GROUP BY kind""",(season,)).fetchall()
        parts={r['kind']:float(r['total']) for r in breakdown}
        # Use the area of distinct parcels actually worked, not the sum of operation passes.
        worked=conn.execute("""SELECT DISTINCT o.parcel_code FROM operations o
            JOIN parcels p ON p.code=o.parcel_code AND p.active=1
            WHERE o.season=? AND o.is_cancelled=0 AND o.direction='Gider'
            AND o.op_type NOT IN ('İcar/Kiralama')""",(season,)).fetchall()
        area=sum(float(worked_area(conn,r['parcel_code'],season)) for r in worked)
        harvest=conn.execute("""SELECT COALESCE(SUM(quantity),0) total FROM operations
            WHERE season=? AND is_cancelled=0 AND op_type='Hasat' AND lower(unit)='kg'""",(season,)).fetchone()['total']
        wheat_sales=conn.execute("""SELECT COALESCE(SUM(amount),0) revenue, COALESCE(SUM(quantity),0) kg
            FROM operations WHERE season=? AND is_cancelled=0 AND op_type='Satış'
            AND lower(unit)='kg' AND lower(item) LIKE '%buğday%'""",(season,)).fetchone()
        wheat_price=float(wheat_sales['revenue'])/float(wheat_sales['kg']) if wheat_sales['kg'] else None
        rows.append(dict(season=season,area=area,expenses=float(expenses),income=float(income),support=float(supports),
            cost_after=float(expenses)-float(supports),profit_before=float(income)-float(expenses),
            profit_after=float(income)+float(supports)-float(expenses),harvest=float(harvest),
            wheat_price=wheat_price,parts=parts,coverage=100*float(supports)/float(expenses) if expenses else None))
    selected=request.args.get('season',seasons[-1] if seasons else '')
    if selected not in seasons: selected=seasons[-1]
    current=next((r for r in rows if r['season']==selected),None)
    def positive_price(name):
        try:
            value=float(request.args.get(name,'').replace(',','.'))
            return value if value>0 else None
        except (ValueError,TypeError): return None
    prices={k:positive_price(k) for k in ('wheat','diesel','fertilizer')}
    return render_template('production_economy.html', rows=rows,current=current,selected=selected,prices=prices)

@app.route('/raporlar')
@login_required
def reports_page():
    conn=db(); season=request.args.get('season',SEASONS[0])
    if season not in SEASONS: season=SEASONS[0]
    parcel_filter=request.args.get('parcel','').strip()
    parcel_options=conn.execute('SELECT code,name FROM parcels WHERE active=1 ORDER BY code').fetchall()
    if parcel_filter not in [p['code'] for p in parcel_options]: parcel_filter=''
    params=(season,)
    parcels=conn.execute("""SELECT p.code,p.name,p.area_m2,
      COALESCE(SUM(CASE WHEN o.direction='Gelir' THEN o.amount ELSE 0 END),0) income,
      COALESCE(SUM(CASE WHEN o.direction='Gider' THEN o.amount ELSE 0 END),0) expense,
      COALESCE(SUM(CASE WHEN o.op_type='Hasat' AND o.unit='kg' THEN o.quantity ELSE 0 END),0) harvest_kg,
      COALESCE(SUM(CASE WHEN o.op_type='Satış' AND o.unit='kg' THEN o.quantity ELSE 0 END),0) sold_kg,
      COUNT(o.id) op_count
      FROM parcels p LEFT JOIN operations o ON o.parcel_code=p.code AND o.season=? AND o.is_cancelled=0
      WHERE p.active=1 GROUP BY p.code,p.name,p.area_m2 ORDER BY p.code""",params).fetchall()
    # Only use selected parcel for breakdowns. Whole-farm totals remain season-wide.
    clause=' AND parcel_code=?' if parcel_filter else ''
    op_params=(season,parcel_filter) if parcel_filter else (season,)
    expenses=conn.execute("SELECT COALESCE(NULLIF(category,''),'Diğer') label, SUM(amount) amount, COUNT(*) count FROM operations WHERE is_cancelled=0 AND season=? AND direction='Gider'"+clause+" GROUP BY COALESCE(NULLIF(category,''),'Diğer') ORDER BY amount DESC",op_params).fetchall()
    income_types=conn.execute("SELECT op_type label, SUM(amount) amount, COUNT(*) count FROM operations WHERE is_cancelled=0 AND season=? AND direction='Gelir'"+clause+" GROUP BY op_type ORDER BY amount DESC",op_params).fetchall()
    crops=conn.execute("""SELECT item, SUM(CASE WHEN op_type='Hasat' AND unit='kg' THEN quantity ELSE 0 END) harvested_kg,
      SUM(CASE WHEN op_type='Satış' AND unit='kg' THEN quantity ELSE 0 END) sold_kg,
      SUM(CASE WHEN op_type='Satış' THEN amount ELSE 0 END) sales_income
      FROM operations WHERE is_cancelled=0 AND season=? AND op_type IN ('Hasat','Satış')"""+clause+" GROUP BY item ORDER BY item",op_params).fetchall()
    sowings=conn.execute("SELECT parcel_code,item,item_detail,category,note,op_date FROM operations WHERE is_cancelled=0 AND season=? AND op_type='Ekim' AND parcel_code IS NOT NULL ORDER BY op_date DESC,id DESC",(season,)).fetchall()
    sowing_by_parcel={}
    for o in sowings: sowing_by_parcel.setdefault(o['parcel_code'],(o['item']+' / '+o['item_detail']) if o['item_detail'] else o['item'])
    # Determine crop directly from recorded sowing material, category and note.
    crop_by_parcel={}
    for o in sowings:
        inferred=infer_sown_crop(' '.join((o['item'],o['item_detail'] or '')),o['category'],o['note'])
        if inferred: crop_by_parcel.setdefault(o['parcel_code'],set()).add(inferred)
    crop_by_parcel={code:next(iter(values)) for code,values in crop_by_parcel.items() if len(values)==1}
    # Unrecognized or conflicting sowings are left unallocated rather than guessed.

    totals=conn.execute("SELECT COALESCE(SUM(CASE WHEN direction='Gelir' THEN amount ELSE 0 END),0) income, COALESCE(SUM(CASE WHEN direction='Gider' THEN amount ELSE 0 END),0) expense FROM operations WHERE is_cancelled=0 AND season=?",(season,)).fetchone()
    supports=conn.execute('SELECT COALESCE(SUM(amount),0) n FROM supports WHERE is_cancelled=0 AND season=?',(season,)).fetchone()['n']
    maintenance=conn.execute('SELECT COALESCE(SUM(cost),0) n FROM machine_maintenance WHERE is_cancelled=0 AND season=?',(season,)).fetchone()['n']
    rent=conn.execute('SELECT COALESCE(SUM(total_amount),0) n FROM rent_contracts WHERE is_cancelled=0 AND season=?',(season,)).fetchone()['n']
    parcel_rows=[dict(r) for r in parcels if not parcel_filter or r['code']==parcel_filter]
    for r in parcel_rows:
        r['area_da']=worked_area(conn,r['code'],season)
        r['difference']=r['income']-r['expense']
        r['difference_da']=r['difference']/r['area_da'] if r['area_da'] else 0
        r['sowing_label']=sowing_by_parcel.get(r['code'],'—')
        r['inferred_crop']=crop_by_parcel.get(r['code'],'Belirlenemedi')
    # V1.2: Allocate common machine-maintenance cost only across parcels
    # with a non-cancelled sowing in this season; each parcel counted once.
    cultivated_codes={o['parcel_code'] for o in sowings}
    cultivated_area=sum(worked_area(conn,r['code'],season) for r in parcels if r['code'] in cultivated_codes)
    unallocated_maintenance=maintenance if cultivated_area<=0 else 0.0
    for r in parcel_rows:
        r['cultivated']=r['code'] in cultivated_codes
        r['allocated_maintenance']=(maintenance*r['area_da']/cultivated_area
                                   if r['cultivated'] and cultivated_area>0 else 0.0)
        r['after_maintenance']=r['difference']-r['allocated_maintenance']
        r['after_maintenance_da']=r['after_maintenance']/r['area_da'] if r['area_da'] else 0
    # V1.2.1: Distribute general supports by cultivated area.
    # Crop-specific supports are only distributed when the sowing label
    # unambiguously contains the named crop. Otherwise keep unallocated.
    support_records=conn.execute('SELECT id,support_type,description,crop,amount FROM supports WHERE is_cancelled=0 AND season=? ORDER BY id',(season,)).fetchall()
    parcel_area={r['code']:worked_area(conn,r['code'],season) for r in parcels}
    support_by_parcel={code:0.0 for code in parcel_area}
    support_details=[]
    unallocated_supports=0.0
    for sp in support_records:
        crop_name=(sp['crop'] or '').strip().casefold()
        if not crop_name: crop_name=infer_sown_crop(sp['support_type'],sp['description']) or ''
        crop_name={'arpa':'Arpa','buğday':'Buğday','bugday':'Buğday','yulaf':'Yulaf','çavdar':'Çavdar','cavdar':'Çavdar'}.get(crop_name,crop_name)
        if crop_name in ('','genel','tümü','tum','tüm ürünler','tum urunler'):
            eligible=set(cultivated_codes)
            scope='Tüm işlenen parseller'
        else:
            eligible={code for code in cultivated_codes if crop_by_parcel.get(code,'').casefold()==crop_name.casefold()}
            scope='İşlemler / Ekim kaydından otomatik: '+str(crop_name)
        eligible_area=sum(parcel_area.get(code,0) for code in eligible)
        allocated=0.0
        if eligible_area>0:
            for code in eligible:
                portion=float(sp['amount'])*parcel_area[code]/eligible_area
                support_by_parcel[code]+=portion
                allocated+=portion
        else:
            unallocated_supports+=float(sp['amount'])
        support_details.append(dict(id=sp['id'],kind=sp['support_type'],crop=sp['crop'] or 'Genel',
            amount=float(sp['amount']),allocated=allocated,unallocated=float(sp['amount'])-allocated,scope=scope))
    for r in parcel_rows:
        r['allocated_support']=support_by_parcel.get(r['code'],0.0)
        r['after_support']=r['after_maintenance']+r['allocated_support']
        r['after_support_da']=r['after_support']/r['area_da'] if r['area_da'] else 0.0
    selected_support=sum(r['allocated_support'] for r in parcel_rows)
    selected_after_support=sum(r['after_support'] for r in parcel_rows)
    selected_maintenance=sum(r['allocated_maintenance'] for r in parcel_rows)
    selected_after_maintenance=sum(r['after_maintenance'] for r in parcel_rows)
    # All-parcel reconciliation uses unfiltered parcels; no duplicate maintenance
    # in company net because maintenance is already deducted there.
    allocated_maintenance_total=maintenance-unallocated_maintenance
    selected_income=sum(r['income'] for r in parcel_rows)
    selected_expense=sum(r['expense'] for r in parcel_rows)
    selected_area=sum(r['area_da'] for r in parcel_rows)
    # Season-to-season comparison: no extra allocation or double counting.
    season_comparison=[]
    for ss in SEASONS:
        r=conn.execute('''SELECT COALESCE(SUM(CASE WHEN direction='Gelir' THEN amount ELSE 0 END),0) income,
             COALESCE(SUM(CASE WHEN direction='Gider' THEN amount ELSE 0 END),0) expense
             FROM operations WHERE is_cancelled=0 AND season=?''',(ss,)).fetchone()
        sup=conn.execute('SELECT COALESCE(SUM(amount),0) n FROM supports WHERE is_cancelled=0 AND season=?',(ss,)).fetchone()['n']
        maint=conn.execute('SELECT COALESCE(SUM(cost),0) n FROM machine_maintenance WHERE is_cancelled=0 AND season=?',(ss,)).fetchone()['n']
        season_comparison.append(dict(season=ss,income=r['income'],expense=r['expense'],
            supports=sup,maintenance=maint,net=r['income']+sup-r['expense']-maint))
    max_season_value=max([max(r['income']+r['supports'],r['expense']+r['maintenance']) for r in season_comparison]+[1])
    for r in season_comparison:
        r['income_pct']=round(100*(r['income']+r['supports'])/max_season_value,1)
        r['expense_pct']=round(100*(r['expense']+r['maintenance'])/max_season_value,1)
    # Ranking by recorded parcel income minus recorded parcel expense only.
    ranked_parcels=sorted([dict(r) for r in parcel_rows if r['op_count']>0],
                          key=lambda r:r['difference_da'],reverse=True)
    max_abs_parcel=max([abs(r['difference_da']) for r in ranked_parcels]+[1])
    for r in ranked_parcels:
        r['bar_pct']=round(abs(r['difference_da'])/max_abs_parcel*100,1)
    profit_data=parcel_profitability_data(conn,season,parcel_filter)
    return render_template('reports.html',season=season,seasons=SEASONS,parcel_options=parcel_options,
      parcel_filter=parcel_filter,parcels=parcel_rows,crops=crops,expenses=expenses,income_types=income_types,
      totals=totals,supports=supports,maintenance=maintenance,rent_contract_total=rent,
      net=totals['income']+supports-totals['expense']-maintenance,
      selected_income=selected_income,selected_expense=selected_expense,selected_area=selected_area,
      season_comparison=season_comparison,ranked_parcels=ranked_parcels,
      cultivated_area=cultivated_area,selected_maintenance=selected_maintenance,
      selected_after_maintenance=selected_after_maintenance,
      support_details=support_details,unallocated_supports=unallocated_supports,
      selected_support=selected_support,selected_after_support=selected_after_support,
      allocated_maintenance_total=allocated_maintenance_total,
      unallocated_maintenance=unallocated_maintenance,profit_data=profit_data)


def warehouse_fifo_allocations(conn):
    """Read-only chronological allocation; keys are sale operation IDs.
    A sale's amount is apportioned across source harvest parcels, including bale batches.
    """
    from collections import defaultdict, deque
    alloc=defaultdict(list)
    issues=[]
    # Bale sales already record exact consumed batches; use those links.
    for r in conn.execute("""SELECT so.id sale_id,so.amount,so.quantity sale_kg,
           b.id batch_id,ho.parcel_code source_parcel,ho.season harvest_season,
           ho.op_date harvest_date,bs.count
           FROM bale_sales bs JOIN operations so ON so.id=bs.sale_operation_id
           JOIN bale_batches b ON b.id=bs.batch_id
           JOIN operations ho ON ho.id=b.harvest_operation_id
           WHERE so.is_cancelled=0 AND ho.is_cancelled=0"""):
        alloc[r['sale_id']].append(dict(parcel=r['source_parcel'],season=r['harvest_season'],
            quantity=float(r['sale_kg']),amount=float(r['amount']),batch=r['batch_id']))
    # Grain sales and grain harvests are allocated in date + operation-ID order.
    for item in ('Arpa','Buğday'):
        events=conn.execute("""SELECT id,op_date,op_type,parcel_code,season,quantity,amount
          FROM operations WHERE is_cancelled=0 AND item=? AND unit='kg'
          AND op_type IN ('Hasat','Satış') ORDER BY op_date,id""",(item,)).fetchall()
        lots=deque()
        for e in events:
            if e['op_type']=='Hasat':
                if float(e['quantity'] or 0)>0:
                    lots.append([e['parcel_code'],e['season'],float(e['quantity']),e['id']])
                continue
            remaining=float(e['quantity'] or 0)
            if remaining<=0:continue
            price=float(e['amount'] or 0)/remaining
            while remaining>0.000001 and lots:
                lot=lots[0]
                take=min(remaining,lot[2])
                alloc[e['id']].append(dict(parcel=lot[0],season=lot[1],quantity=take,
                    amount=take*price,batch=lot[3]))
                remaining-=take;lot[2]-=take
                if lot[2]<0.000001:lots.popleft()
            if remaining>0.000001:issues.append(dict(id=e['id'],item=item,quantity=remaining))
    return alloc,issues


def parcel_warehouse_remaining(conn, allocations, season):
    """Remaining physical stock by originating parcel and harvest season.
    All sales to date are deducted, including sales in later seasons.
    """
    from collections import defaultdict
    used=defaultdict(float)
    grain_sale_ids={r['id'] for r in conn.execute(
        "SELECT id FROM operations WHERE is_cancelled=0 AND op_type='Satış' AND item IN ('Arpa','Buğday')")}
    for sale_id,parts in allocations.items():
        if sale_id not in grain_sale_ids:continue
        for part in parts:
            # Grain allocation batch is harvest operation ID.
            used[part['batch']]+=float(part['quantity'])
    stock=defaultdict(lambda:dict(grain_kg=0.,bales=0.,bale_kg=0.))
    for h in conn.execute("""SELECT id,parcel_code,season,quantity FROM operations
          WHERE is_cancelled=0 AND op_type='Hasat' AND item IN ('Arpa','Buğday')
          AND unit='kg' AND season=?""",(season,)):
        if h['parcel_code']:
            stock[h['parcel_code']]['grain_kg']+=max(0.,float(h['quantity'] or 0)-used[h['id']])
    for b in conn.execute("""SELECT b.id,b.count,b.kg_per_bale,o.parcel_code FROM bale_batches b
          JOIN operations o ON o.id=b.harvest_operation_id
          WHERE o.is_cancelled=0 AND o.season=?""",(season,)):
        if not b['parcel_code']:continue
        sold=conn.execute("""SELECT COALESCE(SUM(bs.count),0) FROM bale_sales bs
             JOIN operations so ON so.id=bs.sale_operation_id
             WHERE bs.batch_id=? AND so.is_cancelled=0""",(b['id'],)).fetchone()[0]
        remaining=max(0.,float(b['count'] or 0)-float(sold or 0))
        stock[b['parcel_code']]['bales']+=remaining
        stock[b['parcel_code']]['bale_kg']+=remaining*float(b['kg_per_bale'] or 0)
    return stock


def parcel_profitability_data(conn,season,parcel_filter):
    parcels=conn.execute('SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code').fetchall()
    if parcel_filter not in {p['code'] for p in parcels}: parcel_filter=''
    allocations,fifo_issues=warehouse_fifo_allocations(conn)
    warehouse_remaining=parcel_warehouse_remaining(conn,allocations,season)
    ops=conn.execute("""SELECT id,parcel_code,op_type,item,COALESCE(item_detail,'') item_detail,
        quantity,unit,amount,direction FROM operations WHERE is_cancelled=0 AND season=?
        ORDER BY op_date,id""",(season,)).fetchall()
    facts={}; sowings={}; unassigned_sales=0.; unassigned_other_income=0.; unassigned_expense=0.
    for o in ops:
        # Warehouse sales are attributed by the harvest source, not by an optional
        # sale-form parcel selection. No new revenue/expense records are created.
        if o['op_type']=='Satış' and o['id'] in allocations:
            for part in allocations[o['id']]:
                code=part['parcel']; amount=part['amount']
                if not code:
                    unassigned_sales+=amount;continue
                f=facts.setdefault(code,dict(income=0.,expense=0.,harvest=0.,sales_kg=0.,grain_sales=0.,bale_sales=0.,other_sales=0.))
                f['income']+=amount
                if o['item'] in ('Arpa','Buğday'):f['grain_sales']+=amount
                elif o['item'] in ('Arpa Samanı','Buğday Samanı'):f['bale_sales']+=amount
                else:f['other_sales']+=amount
                f['sales_kg']+=part['quantity']
            continue
        code=o['parcel_code']; amount=float(o['amount'] or 0)
        if not code:
            if o['direction']=='Gelir':
                if o['op_type']=='Satış': unassigned_sales+=amount
                else: unassigned_other_income+=amount
            elif o['direction']=='Gider': unassigned_expense+=amount
            continue
        f=facts.setdefault(code,dict(income=0.,expense=0.,harvest=0.,sales_kg=0.,grain_sales=0.,bale_sales=0.,other_sales=0.))
        if o['direction']=='Gelir': f['income']+=amount
        if o['direction']=='Gider': f['expense']+=amount
        if o['op_type']=='Hasat' and o['unit']=='kg': f['harvest']+=float(o['quantity'] or 0)
        if o['op_type']=='Satış':
            if o['item'] in ('Arpa','Buğday'): f['grain_sales']+=amount
            elif o['item'] in ('Arpa Samanı','Buğday Samanı'): f['bale_sales']+=amount
            else: f['other_sales']+=amount
            if o['unit']=='kg': f['sales_kg']+=float(o['quantity'] or 0)
        if o['op_type']=='Ekim':
            crop=infer_sown_crop(' '.join((o['item'],o['item_detail'])))
            if crop:sowings.setdefault(code,set()).add((crop,o['item_detail'] or 'Çeşit belirtilmemiş'))
    support_rows=conn.execute("SELECT crop,amount FROM supports WHERE season=? AND is_cancelled=0",(season,)).fetchall()
    maintenance=float(conn.execute("SELECT COALESCE(SUM(cost),0) FROM machine_maintenance WHERE season=? AND is_cancelled=0",(season,)).fetchone()[0])
    area={p['code']:worked_area(conn,p['code'],season) for p in parcels}
    eligible={c for c in sowings if c in area}
    cultivated_area=sum(area[c] for c in eligible)
    support_alloc={c:0. for c in area}; unallocated_support=0.
    for sp in support_rows:
        crop=(sp['crop'] or '').strip()
        if crop and crop.casefold() not in ('genel','tümü','tüm ürünler'):
            match={c for c in eligible if len({v[0] for v in sowings[c]})==1 and next(iter({v[0] for v in sowings[c]})).casefold()==crop.casefold()}
        else: match=eligible
        denominator=sum(area[c] for c in match)
        if denominator:
            for c in match:support_alloc[c]+=float(sp['amount'])*area[c]/denominator
        else:unallocated_support+=float(sp['amount'])
    rents=conn.execute("""SELECT parcel_code,total_amount,id FROM rent_contracts
       WHERE season=? AND is_cancelled=0""",(season,)).fetchall()
    rent_due={c:0. for c in area}
    for rent in rents:
        paid=float(conn.execute("SELECT COALESCE(SUM(amount),0) FROM rent_payments WHERE rent_contract_id=?",(rent['id'],)).fetchone()[0])
        if rent['parcel_code'] in rent_due:rent_due[rent['parcel_code']]+=max(0.,float(rent['total_amount'])-paid)
    rows=[]
    for p in parcels:
        code=p['code']
        if parcel_filter and code!=parcel_filter:continue
        f=facts.get(code,dict(income=0.,expense=0.,harvest=0.,sales_kg=0.,grain_sales=0.,bale_sales=0.,other_sales=0.))
        varieties=sowings.get(code,set())
        crop=' / '.join('%s (%s)'%v for v in sorted(varieties)) if varieties else 'Ekim kaydı yok'
        maintenance_share=maintenance*area[code]/cultivated_area if code in eligible and cultivated_area else 0.
        cost=f['expense']+maintenance_share
        support=support_alloc[code]
        net=f['income']+support-cost
        rows.append(dict(code=code,name=p['name'],crop=crop,area=area[code],
            expense=f['expense'],maintenance=maintenance_share,support=support,
            income=f['income'],grain_sales=f['grain_sales'],bale_sales=f['bale_sales'],
            other_sales=f['other_sales'],other_income=f['income']-f['grain_sales']-f['bale_sales']-f['other_sales'],
            cost=cost,net=net,net_da=net/area[code] if area[code] else None,
            income_da=(f['income']+support)/area[code] if area[code] else None,
            cost_da=cost/area[code] if area[code] else None,
            grain_remaining=warehouse_remaining[code]['grain_kg'],
            bales_remaining=warehouse_remaining[code]['bales'],
            bale_kg_remaining=warehouse_remaining[code]['bale_kg'],
            harvest=f['harvest'],rent_due=rent_due.get(code,0.)))
    total={key:sum(r[key] for r in rows) for key in ('area','income','cost','support','net','harvest','grain_sales','bale_sales','other_sales','other_income','rent_due','grain_remaining','bales_remaining','bale_kg_remaining')}
    return dict(season=season,seasons=SEASONS,parcel_filter=parcel_filter,parcels=parcels,rows=rows,ranked_rows=sorted(rows,key=lambda r:r['net_da'] if r['net_da'] is not None else float('-inf'),reverse=True),total=total,
        unassigned_sales=unassigned_sales,unassigned_other_income=unassigned_other_income,
        unassigned_expense=unassigned_expense,unallocated_support=unallocated_support,
        unallocated_maintenance=maintenance if cultivated_area==0 else 0,
        fifo_issues=fifo_issues)


@app.route('/kar-zarar-analizi')
@login_required
def profitability_analysis_page():
    conn=db()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS:season=SEASONS[0]
    parcel_filter=request.args.get('parcel','').strip()
    data=parcel_profitability_data(conn,season,parcel_filter)
    return render_template('profitability_analysis.html',**data)

@app.route('/tahmini-basa-bas-verim')
@login_required
def forecast_breakeven_page():
    conn=db()
    season=request.args.get('season',SEASONS[0])
    if season not in SEASONS:season=SEASONS[0]
    try: price=float(request.args.get('price','12').replace(',','.'))
    except (ValueError,TypeError):price=12.
    if not 0 < price <= 100000:price=12.
    try: target=float(request.args.get('yield_da','300').replace(',','.'))
    except (ValueError,TypeError):target=300.
    if not 0 <= target <= 100000:target=300.
    def scenario_number(name,default=0):
        try: value=float(request.args.get(name,str(default)).replace(',','.'))
        except (ValueError,TypeError): value=float(default)
        return value if 0 <= value <= 100000 else float(default)
    future_cost_da=scenario_number('future_cost_da')
    expected_support_da=scenario_number('expected_support_da')
    support_mode=request.args.get('support_mode','recorded')
    if support_mode not in ('recorded','forecast'):support_mode='recorded'
    cost_mode=request.args.get('cost_mode','recorded')
    if cost_mode not in ('recorded','forecast'):cost_mode='recorded'
    parcels=conn.execute("SELECT code,name,area_m2 FROM parcels WHERE active=1 ORDER BY code").fetchall()
    area={p['code']:worked_area(conn,p['code'],season) for p in parcels}
    selected=request.args.get('parcel','').strip()
    if selected not in area:selected=''
    ops=conn.execute("""SELECT parcel_code,op_type,item,COALESCE(item_detail,'') item_detail,
       direction,amount FROM operations WHERE season=? AND is_cancelled=0
       AND parcel_code IS NOT NULL""",(season,)).fetchall()
    expenses={};non_sale_income={};sowings={}
    for o in ops:
        code=o['parcel_code']
        if code not in area:continue
        amount=float(o['amount'] or 0)
        if o['direction']=='Gider':expenses[code]=expenses.get(code,0.)+amount
        if o['direction']=='Gelir' and o['op_type']!='Satış':
            non_sale_income[code]=non_sale_income.get(code,0.)+amount
        if o['op_type']=='Ekim':
            crop=infer_sown_crop(' '.join((o['item'],o['item_detail'])))
            if crop:sowings.setdefault(code,set()).add((crop,o['item_detail'] or 'Çeşit belirtilmemiş'))
    eligible={c for c in sowings if area.get(c,0)>0}
    cultivated_area=sum(area[c] for c in eligible)
    maintenance=float(conn.execute("SELECT COALESCE(SUM(cost),0) n FROM machine_maintenance WHERE season=? AND is_cancelled=0",(season,)).fetchone()['n'])
    supports=conn.execute("SELECT crop,amount FROM supports WHERE season=? AND is_cancelled=0",(season,)).fetchall()
    support_alloc={c:0. for c in area};unallocated=0.
    for sp in supports:
        crop=(sp['crop'] or '').strip()
        if crop and crop.casefold() not in ('genel','tümü','tüm ürünler'):
            matching={c for c in eligible if len({x[0] for x in sowings[c]})==1 and next(iter({x[0] for x in sowings[c]})).casefold()==crop.casefold()}
        else:matching=eligible
        denominator=sum(area[c] for c in matching)
        if denominator:
            for c in matching:support_alloc[c]+=float(sp['amount'])*area[c]/denominator
        else:unallocated+=float(sp['amount'])
    rows=[]
    for p in parcels:
        c=p['code']
        if selected and c!=selected:continue
        a=area[c]
        if a<=0:continue
        maintenance_share=maintenance*a/cultivated_area if c in eligible and cultivated_area else 0.
        cost=expenses.get(c,0.)+maintenance_share
        support=support_alloc[c]
        # Forecast only: do not subtract bale revenue or unrelated income.
        # The entered cost is either additional (recorded mode) or complete (forecast mode).
        cost=(cost+future_cost_da*a) if cost_mode=='recorded' else future_cost_da*a
        if support_mode=='forecast':support=expected_support_da*a
        other_income=0.
        required=max(0.,cost-support)
        threshold=required/(a*price)
        expected_revenue=target*a*price
        expected_net=expected_revenue-required
        varieties=sowings.get(c,set())
        rows.append(dict(code=c,name=p['name'],area=a,crop=' / '.join('%s (%s)'%v for v in sorted(varieties)) if varieties else 'Ekim kaydı yok',
            cost=cost,support=support,other_income=other_income,required=required,
            cost_da=cost/a,threshold=threshold,threshold_total=required/price,
            target_total=target*a,expected_revenue=expected_revenue,expected_net=expected_net,
            has_sowing=c in eligible))
    return render_template('forecast_breakeven.html',season=season,seasons=SEASONS,
        parcels=parcels,selected=selected,price=price,target=target,rows=rows,
        unallocated=unallocated,unallocated_maintenance=maintenance if not cultivated_area else 0,
        future_cost_da=future_cost_da,expected_support_da=expected_support_da,
        support_mode=support_mode,cost_mode=cost_mode)

@app.route('/veri-kontrolu')
@login_required
def data_check_page():
    conn=db(); issues=[]
    for row in conn.execute("SELECT item,COALESCE(item_detail,'') item_detail,unit,SUM(quantity) bought FROM stock_purchases WHERE is_cancelled=0 GROUP BY item,COALESCE(item_detail,''),unit").fetchall():
        used=conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM operations WHERE is_cancelled=0 AND item=? AND COALESCE(item_detail,'')=? AND unit=? AND direction='Gider' AND op_type NOT IN ('Hasat','Satış','İcar/Kiralama')",(row['item'],row['item_detail'],row['unit'])).fetchone()['n']
        if used>row['bought']+0.0001: issues.append({'level':'Kritik','area':'Girdi deposu','detail':f"{row['item']} / {row['item_detail'] or 'Çeşit belirtilmemiş'}: tüketim {used:g} {row['unit']}, alım {row['bought']:g} {row['unit']}.",'fix':'Depo alımını veya tüketim kaydını kontrol edin.'})
    dup=conn.execute('SELECT op_date,parcel_code,op_type,item,quantity,COUNT(*) n FROM operations WHERE is_cancelled=0 GROUP BY op_date,parcel_code,op_type,item,quantity HAVING COUNT(*)>1').fetchall()
    for r in dup: issues.append({'level':'Kontrol','area':'Tarla işlemleri','detail':f"{r['op_date']} / {r['parcel_code'] or 'Parsel yok'} / {r['op_type']} / {r['item']} aynı miktarla {r['n']} kez kayıtlı.",'fix':'Tekrar kayıt olup olmadığını kontrol edin; aynı işlemin iki kez girilmesi şart değildir.'})
    for r in conn.execute("SELECT id,op_date,op_type,item FROM operations WHERE is_cancelled=0 AND parcel_code IS NULL AND op_type IN ('Ekim','Hasat','Satış')").fetchall():
        issues.append({'level':'Kontrol','area':'Tarla işlemleri','detail':f"#{r['id']} {r['op_date']} {r['op_type']} ({r['item']}) için parsel seçilmemiş.",'fix':'İlgili parseli belirleyin.'})
    return render_template('data_check.html',issues=issues)


# v0.3: Safe editing for operations and depot purchases.
@app.route('/duzenle/islem/<int:record_id>', methods=['GET','POST'])
@login_required
def edit_operation(record_id):
    conn=db(); old=conn.execute('SELECT * FROM operations WHERE id=?',(record_id,)).fetchone()
    if old is None: abort(404)
    if request.method=='POST':
        season=request.form.get('season',''); dt=request.form.get('op_date',''); parcel=request.form.get('parcel_code') or None
        kind=request.form.get('op_type',''); item=request.form.get('item','').strip(); unit=normalize_unit(request.form.get('unit',''))
        direction=request.form.get('direction',''); cat=request.form.get('category') or None; note=request.form.get('note','').strip(); item_detail=request.form.get('item_detail','').strip()
        item,item_detail=canonical_item(item,cat,kind,item_detail)
        if kind in STOCK_OPERATION_TYPES:
            selected=selected_depot_item(conn,request.form)
            if selected:
                item=selected['item'];item_detail=selected['item_detail'];unit=selected['unit'];cat=selected['category'];direction='Gider'
            else:
                item='';item_detail=''

        try: qty=float(request.form.get('quantity','')); price=float(request.form.get('unit_price') or 0)
        except (TypeError,ValueError): qty=-1; price=-1
        # Depot-priced consumables never require a manually supplied price.
        if kind not in ('Hasat','Satış','İcar/Kiralama') and direction=='Gider' and stock_item_exists(conn,item,item_detail):
            price=weighted_cost(conn,item)
        errors=[]
        if season not in SEASONS: errors.append('Geçerli sezon seçin.')
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli tarih girin.')
        if parcel and not conn.execute('SELECT 1 FROM parcels WHERE code=?',(parcel,)).fetchone(): errors.append('Parsel bulunamadı.')
        if kind not in OP_TYPES or not item or unit not in UNITS or direction not in ('Gelir','Gider','Nötr'): errors.append('Depo ürünü/çeşidi veya diğer zorunlu alanlar geçersiz.')
        if qty<=0 or price<0: errors.append('Miktar pozitif ve fiyat negatif olmayan bir sayı olmalı.')
        if kind in ('Hasat','Satış'):
            if not parcel or unit!='kg': errors.append('Hasat/satış için parsel ve kg birimi zorunlu.')
            if kind=='Hasat': direction='Nötr'; price=0
            else:
                direction='Gelir'
                if price<=0: errors.append('Satış fiyatı pozitif olmalı.')
        elif kind=='İcar/Kiralama': direction='Gider'
        # Check entire stock state as if the edited operation were removed.
        if not errors:
            conn.execute('SAVEPOINT edit_operation')
            try:
                conn.execute('UPDATE operations SET is_cancelled=1 WHERE id=?',(record_id,))
                if kind=='Satış' and qty>product_stock(conn,item)+1e-6: errors.append('Bu satış için yeterli hasat stoğu yok.')
                if kind not in ('Hasat','Satış','İcar/Kiralama') and direction=='Gider' and stock_item_exists(conn,item,item_detail):
                    if qty>input_stock(conn,item,item_detail,unit)+1e-6: errors.append('Bu tüketim için yeterli depo stoğu yok.')
                    else:
                        if fifo_later_use(conn,item,unit,dt,record_id,detail=item_detail):
                            errors.append('Sonraki tüketimler bulunduğu için FIFO sırası bozulmadan bu işlem düzenlenemiyor.')
                        else:
                            avg, fifo_error=fifo_unit_cost(conn,item,unit,dt,qty,record_id,detail=item_detail)
                            if fifo_error: errors.append(fifo_error)
                            else: price=avg
                amount=round(qty*price,2) if direction in ('Gelir','Gider') else 0
                if not errors:
                    conn.execute('UPDATE operations SET season=?,op_date=?,parcel_code=?,op_type=?,item=?,quantity=?,unit=?,unit_price=?,amount=?,direction=?,category=?,note=?,item_detail=?,is_cancelled=0 WHERE id=?',
                      (season,dt,parcel,kind,item,qty,unit,price,amount,direction,cat,note,item_detail,record_id))
                    for r in conn.execute("SELECT DISTINCT item FROM operations WHERE is_cancelled=0 AND op_type IN ('Hasat','Satış')"):
                        if product_stock(conn,r['item']) < -1e-6: errors.append('Değişiklik mevcut ürün satışlarını stoksuz bırakıyor.') ; break
                    for r in conn.execute("SELECT DISTINCT item,COALESCE(item_detail,'') detail,unit FROM stock_purchases WHERE is_cancelled=0"):
                        if input_stock(conn,r['item'],r['detail'],r['unit']) < -1e-6: errors.append('Değişiklik depo stokunu eksiye düşürüyor.'); break
                if errors: conn.execute('ROLLBACK TO edit_operation')
                conn.execute('RELEASE edit_operation')
            except Exception:
                conn.execute('ROLLBACK TO edit_operation');conn.execute('RELEASE edit_operation');raise
            if not errors:
                conn.commit(); flash('İşlem güvenli şekilde güncellendi.','success'); return redirect(url_for('operations_page'))
        for e in errors: flash(e,'error')
    return render_template('edit_operation.html',record=old,parcels=conn.execute('SELECT code,name FROM parcels ORDER BY code').fetchall(),seasons=SEASONS,op_types=OP_TYPES,units=UNITS,categories=CATEGORIES,depot_choices=depot_choices(conn),stock_types=STOCK_OPERATION_TYPES)

@app.route('/duzenle/depo/<int:record_id>', methods=['GET','POST'])
@login_required
def edit_purchase(record_id):
    conn=db(); old=conn.execute('SELECT * FROM stock_purchases WHERE id=?',(record_id,)).fetchone()
    if old is None: abort(404)
    if request.method=='POST':
        season=request.form.get('season',''); dt=request.form.get('purchase_date',''); cat=request.form.get('category','');item=request.form.get('item','').strip();unit=normalize_unit(request.form.get('unit',''))
        item_detail=request.form.get('item_detail','').strip()
        item,item_detail=canonical_item(item,cat,'',item_detail)
        try: qty=float(request.form.get('quantity',''));price=float(request.form.get('unit_price',''))
        except (TypeError,ValueError):qty=-1;price=-1
        errors=[]
        if season not in SEASONS or cat not in CATEGORIES or unit not in UNITS or not item: errors.append('Sezon, kategori, birim ve malzeme alanlarını kontrol edin.')
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError:errors.append('Geçerli tarih girin.')
        if qty<=0 or price<0:errors.append('Miktar pozitif, fiyat negatif olmayan bir sayı olmalı.')
        if not errors:
            before_deficits=depot_timeline_deficits(conn)
            conn.execute('SAVEPOINT edit_purchase')
            try:
                conn.execute('UPDATE stock_purchases SET season=?,purchase_date=?,category=?,item=?,quantity=?,unit=?,unit_price=?,supplier_note=?,item_detail=? WHERE id=?',
                  (season,dt,cat,item,qty,unit,price,request.form.get('supplier_note','').strip(),item_detail,record_id))
                for r in conn.execute('SELECT item,COALESCE(item_detail,'') detail,COUNT(DISTINCT unit) n FROM stock_purchases WHERE is_cancelled=0 GROUP BY item,COALESCE(item_detail,'')'):
                    if r['n']>1:errors.append('Aynı malzemede farklı ölçü birimleri olamaz.');break
                timeline_error=new_depot_deficit_error(before_deficits,depot_timeline_deficits(conn))
                if timeline_error:errors.append(timeline_error)
                if errors:conn.execute('ROLLBACK TO edit_purchase')
                conn.execute('RELEASE edit_purchase')
            except Exception:
                conn.execute('ROLLBACK TO edit_purchase');conn.execute('RELEASE edit_purchase');raise
            if not errors:
                conn.commit();flash('Depo alımı güncellendi. Geçmiş tüketim maliyetleri değiştirilmedi.','success');return redirect(url_for('depot_page'))
        for e in errors:flash(e,'error')
    return render_template('edit_purchase.html',record=old,seasons=SEASONS,categories=CATEGORIES,units=UNITS)

@app.route('/health')
def health(): return {'status':'ok','database':'sqlite','version':'1.1.0'}





@app.route('/duzenle/bakim/<int:record_id>', methods=['GET','POST'])
@login_required
def edit_maintenance(record_id):
    conn=db(); old=conn.execute('SELECT * FROM machine_maintenance WHERE id=?',(record_id,)).fetchone()
    if old is None: abort(404)
    if request.method=='POST':
        season=request.form.get('season',''); dt=request.form.get('service_date',''); machine=request.form.get('machine','').strip(); desc=request.form.get('description','').strip(); note=request.form.get('note','').strip()
        try: cost=float(request.form.get('cost','')); hours=float(request.form.get('work_hours') or 0)
        except (ValueError,TypeError): cost=-1; hours=-1
        errors=[]
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError: errors.append('Geçerli bakım tarihi girin.')
        if season not in SEASONS: errors.append('Geçerli sezon seçin.')
        if not machine or not desc: errors.append('Makine ve açıklama zorunlu.')
        if cost<0 or hours<0: errors.append('Tutar ve saat negatif olamaz.')
        if not errors:
            conn.execute('UPDATE machine_maintenance SET season=?,service_date=?,machine=?,work_hours=?,description=?,cost=?,note=? WHERE id=?',(season,dt,machine,hours,desc,cost,note,record_id));conn.commit()
            flash('Bakım kaydı güncellendi.','success');return redirect(url_for('maintenance_page'))
        for e in errors:flash(e,'error')
    return render_template('edit_maintenance.html',record=old,seasons=SEASONS)

@app.route('/duzenle/destek/<int:record_id>', methods=['GET','POST'])
@login_required
def edit_support(record_id):
    conn=db();old=conn.execute('SELECT * FROM supports WHERE id=?',(record_id,)).fetchone()
    if old is None:abort(404)
    if request.method=='POST':
        dt=request.form.get('payment_date','');season=request.form.get('season','');kind=request.form.get('support_type','').strip();desc=request.form.get('description','').strip();crop=request.form.get('crop') or None
        try: amount=float(request.form.get('amount',''))
        except (ValueError,TypeError):amount=-1
        errors=[]
        try:datetime.strptime(dt,'%Y-%m-%d')
        except ValueError:errors.append('Geçerli ödeme tarihi girin.')
        if season not in SEASONS:errors.append('Sezon seçin.')
        if not kind or not desc:errors.append('Tür ve açıklama zorunlu.')
        if amount<=0:errors.append('Destek tutarı pozitif olmalı.')
        if not errors:
            conn.execute('UPDATE supports SET payment_date=?,season=?,support_type=?,description=?,crop=?,amount=? WHERE id=?',(dt,season,kind,desc,crop,amount,record_id));conn.commit()
            flash('Destek güncellendi.','success');return redirect(url_for('supports_page'))
        for e in errors:flash(e,'error')
    return render_template('edit_support.html',record=old,seasons=SEASONS)

@app.route('/duzenle/kira/<int:record_id>', methods=['GET','POST'])
@login_required
def edit_rent(record_id):
    conn=db();old=conn.execute('SELECT * FROM rent_contracts WHERE id=?',(record_id,)).fetchone()
    if old is None:abort(404)
    if request.method=='POST':
        landlord=request.form.get('landlord','').strip();parcel=request.form.get('parcel_code','');season=request.form.get('season','');start=request.form.get('start_date') or None;end=request.form.get('end_date') or None;due=request.form.get('due_note','').strip()
        try:rate=float(request.form.get('rate_per_da',''))
        except (ValueError,TypeError):rate=-1
        par=conn.execute('SELECT area_m2 FROM parcels WHERE code=?',(parcel,)).fetchone()
        errors=[]
        if not landlord or not par:errors.append('Kiraya veren ve geçerli parsel zorunlu.')
        if season not in SEASONS:errors.append('Sezon seçin.')
        if rate<0:errors.append('Kira bedeli negatif olamaz.')
        if start and end and end<start:errors.append('Bitiş başlangıçtan önce olamaz.')
        area=leased_area(conn,parcel,season)
        if area<=0:errors.append('Parseller modülünde bu parsel ve sezon için icar kullanım alanı tanımlayın.')
        paid=conn.execute('SELECT COALESCE(SUM(amount),0) FROM rent_payments WHERE rent_contract_id=?',(record_id,)).fetchone()[0]
        if paid>0 and (parcel!=old['parcel_code'] or season!=old['season']):errors.append('Ödeme yapılmış sözleşmenin parseli veya sezonu değiştirilemez.')
        if math.isfinite(rate) and rate>=0 and paid>round(area*rate,2)+1e-6:errors.append('Yeni kira tutarı yapılmış ödemelerden az olamaz.')
        if not errors:
            try:
                conn.execute('UPDATE rent_contracts SET landlord=?,parcel_code=?,season=?,start_date=?,end_date=?,area_da=?,rate_per_da=?,total_amount=?,due_note=? WHERE id=?',
                  (landlord,parcel,season,start,end,area,rate,round(area*rate,2),due,record_id));conn.commit()
                flash('Kira sözleşmesi icar kullanım alanına göre güncellendi.','success');return redirect(url_for('rents_page'))
            except sqlite3.IntegrityError:conn.rollback();errors.append('Aynı sözleşme zaten mevcut.')
        for e in errors:flash(e,'error')
    return render_template('edit_rent.html',record=old,seasons=SEASONS,parcels=conn.execute('SELECT code,name FROM parcels ORDER BY code').fetchall(),leased_areas={season:{r['code']:leased_area(conn,r['code'],season) for r in conn.execute('SELECT code FROM parcels')} for season in SEASONS})


@app.route('/parsel-alan/<code>',methods=['POST'])
@login_required
def save_parcel_area(code):
    conn=db()
    p=conn.execute('SELECT area_m2 FROM parcels WHERE code=?',(code,)).fetchone()
    if not p:abort(404)
    season=request.form.get('season','')
    try:
        worked=float(request.form.get('worked_area_da',''))
        owned=float(request.form.get('owned_area_da',''))
        leased=float(request.form.get('leased_area_da','0'))
    except (TypeError,ValueError):
        flash('Alanlar sayı olmalıdır.','error');return redirect(url_for('edit_parcel',code=code))
    if season not in SEASONS or not all(math.isfinite(x) for x in (worked,owned,leased)) or worked<=0 or owned<0 or leased<0 or owned+leased>p['area_m2']/1000+0.00001 :
        flash('Alanlar geçersiz: mülkiyet ve icar toplamı tapu alanını aşamaz. İşlenen alan mera sürümü nedeniyle daha büyük olabilir.','error')
    else:
        conn.execute('INSERT INTO parcel_season_areas(parcel_code,season,worked_area_da,leased_area_da) VALUES(?,?,?,?) ON CONFLICT(parcel_code,season) DO UPDATE SET worked_area_da=excluded.worked_area_da,leased_area_da=excluded.leased_area_da',(code,season,worked,leased))
        conn.execute('UPDATE parcels SET owned_area_da=? WHERE code=?',(owned,code))
        conn.commit()
        flash('Mülkiyet, icarla kullanım ve sezonluk işlenen alan kaydedildi. İcar sözleşmeleri değiştirilmedi.','success')
    return redirect(url_for('edit_parcel',code=code))

@app.route('/toprak-analizi/<code>',methods=['GET','POST'])
@login_required
def soil_analysis_page(code):
    conn=db()
    parcel=conn.execute('SELECT code,name FROM parcels WHERE code=?',(code,)).fetchone()
    if not parcel:abort(404)
    if request.method=='POST':
        dt=request.form.get('analysis_date','')
        try: datetime.strptime(dt,'%Y-%m-%d')
        except ValueError:
            flash('Geçerli analiz tarihi girin.','error');return redirect(url_for('soil_analysis_page',code=code))
        values=[]
        for key in ('ph','organic_matter','phosphorus','potassium','lime','ec'):
            raw=request.form.get(key,'').strip()
            try: v=float(raw.replace(',','.')) if raw else None
            except ValueError: v=float('nan')
            values.append(v)
        if any(v is not None and (not math.isfinite(v) or v<0) for v in values):
            flash('Analiz değerleri sıfır veya pozitif sayı olmalı.','error')
        else:
            conn.execute('INSERT INTO soil_analyses(parcel_code,analysis_date,laboratory,ph,organic_matter,phosphorus,potassium,lime,ec,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (code,dt,request.form.get('laboratory','').strip(),*values,request.form.get('notes','').strip()))
            conn.commit();flash('Toprak analizi kaydedildi.','success')
            return redirect(url_for('soil_analysis_page',code=code))
    rows=conn.execute('SELECT * FROM soil_analyses WHERE parcel_code=? ORDER BY analysis_date DESC,id DESC',(code,)).fetchall()
    return render_template('soil_analysis.html',parcel=parcel,rows=rows,today=date.today().isoformat())

@app.route('/duzenle/parsel/<code>', methods=['GET','POST'])
@login_required
def edit_parcel(code):
    conn=db();old=conn.execute('SELECT * FROM parcels WHERE code=?',(code,)).fetchone()
    if old is None:abort(404)
    if request.method=='POST':
        name=request.form.get('name','').strip();property_type=request.form.get('property_type','');irrigation=request.form.get('irrigation','')
        try:area=float(request.form.get('area_m2',''))
        except (ValueError,TypeError):area=-1
        errors=[]
        if not name or area<=0:errors.append('Parsel adı ve pozitif alan zorunlu.')
        if property_type not in ('','Mülk','İcar','Ortak'):errors.append('Mülkiyet seçimini kontrol edin.')
        if irrigation not in ('','Kuru','Sulu'):errors.append('Sulama seçimini kontrol edin.')
        paid=conn.execute("SELECT COUNT(*) FROM operations WHERE is_cancelled=0 AND parcel_code=? AND op_type='İcar/Kiralama'",(code,)).fetchone()[0]
        if paid:
            for r in conn.execute('SELECT * FROM rent_contracts WHERE is_cancelled=0 AND parcel_code=?',(code,)):
                new_total=round(area/1000*r['rate_per_da'],2)
                old_paid=conn.execute("SELECT COALESCE(SUM(amount),0) FROM operations WHERE is_cancelled=0 AND parcel_code=? AND season=? AND op_type='İcar/Kiralama'",(code,r['season'])).fetchone()[0]
                if new_total+1e-6<old_paid:errors.append('Yeni parsel alanı kira ödemesinden düşük sözleşme tutarı oluşturuyor.');break
        if not errors:
            conn.execute('UPDATE parcels SET name=?,area_m2=?,property_type=?,soil_type=?,irrigation=?,neighborhood=?,ada=?,parcel_no=?,owner=? WHERE code=?',(name,area,property_type,request.form.get('soil_type',''),irrigation,request.form.get('neighborhood',''),request.form.get('ada',''),request.form.get('parcel_no',''),request.form.get('owner',''),code))
            conn.execute('UPDATE rent_contracts SET area_da=?,total_amount=ROUND(?*rate_per_da,2) WHERE parcel_code=?',(area/1000,area/1000,code))
            conn.commit();flash('Parsel ve bağlı kira alanları güncellendi.','success');return redirect(url_for('parcels_page'))
        for e in errors:flash(e,'error')
    season_areas=conn.execute('SELECT season,worked_area_da,leased_area_da FROM parcel_season_areas WHERE parcel_code=? ORDER BY season',(code,)).fetchall()
    return render_template('edit_parcel.html',record=old,season_areas=season_areas,seasons=SEASONS)



# v0.5: cancellation, restoration, and change history
from flask import render_template_string
from markupsafe import escape

V05_TABLES = {
    'islem': ('operations','İşlemler','op_date','item'),
    'depo': ('stock_purchases','Depo alımları','purchase_date','item'),
    'icar': ('rent_contracts','İcar sözleşmeleri','start_date','landlord'),
    'destek': ('supports','Destekler','payment_date','support_type'),
    'bakim': ('machine_maintenance','Makine bakım','service_date','machine'),
}

@app.before_request
def v05_block_cancelled_edits():
    endpoint = request.endpoint or ''
    names = {'edit_operation':'operations','edit_purchase':'stock_purchases',
             'edit_rent':'rent_contracts','edit_support':'supports','edit_maintenance':'machine_maintenance'}
    if endpoint in names:
        rid = (request.view_args or {}).get('record_id')
        if rid is not None:
            row = db().execute(f'SELECT is_cancelled FROM {names[endpoint]} WHERE id=?',(rid,)).fetchone()
            if row and row['is_cancelled']:
                flash('İptal edilmiş kayıt önce geri alınmalıdır.','error')
                return redirect(url_for('record_manager'))

MANAGER_HTML = '''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kayıt Yönetimi — Özcan Tarım</title>
<style>body{font:15px system-ui,sans-serif;background:#f5f7f5;color:#23352c;margin:0;padding:24px}main{max-width:1100px;margin:auto}h1{color:#176c50}a{color:#176c50}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}button{padding:7px 12px;cursor:pointer;border:0;border-radius:5px;background:#b04435;color:white}.restore{background:#176c50}.tabs a{display:inline-block;padding:8px 12px;margin:3px;background:white;border-radius:6px}.msg{padding:12px;background:#fff0d4;margin:8px 0}.muted{color:#667}input{max-width:150px}</style></head><body><main><a href="/">← Ana sayfa</a><h1>Kayıt Yönetimi</h1><p>İptal edilen kayıtlar silinmez. İptal/geri alma işlemleri raporlara ve stoklara yansır.</p>
{% for category,message in get_flashed_messages(with_categories=true) %}<div class="msg">{{ message }}</div>{% endfor %}
<nav class="tabs">{% for key, val in kinds.items() %}<a href="?tur={{ key }}">{{ val[1] }}</a>{% endfor %}<a href="/degisiklik-gecmisi">Değişiklik geçmişi</a></nav>
<h2>{{ title }}</h2><table><thead><tr><th>No</th><th>Tarih</th><th>Kayıt ayrıntıları</th><th>Durum</th><th>İşlem</th></tr></thead><tbody>
{% for r in rows %}<tr><td>{{ r['id'] }}</td><td>{{ r['date_value'] or '-' }}</td><td>{{ r['detail'] }}</td><td>{{ 'İptal' if r['is_cancelled'] else 'Aktif' }}</td><td><form method="post" action="{{ url_for('toggle_record', kind=kind, record_id=r['id']) }}" onsubmit="return confirm('Bu kaydın durumunu değiştirmek istiyor musunuz?')"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="{{ 'restore' if r['is_cancelled'] else '' }}">{{ 'Geri al' if r['is_cancelled'] else 'İptal et' }}</button></form></td></tr>
{% endfor %}</tbody></table><p class="muted">En son 150 kayıt gösterilir.</p></main></body></html>'''

@app.route('/kayit-merkezi')
@login_required
def records_hub():
    return render_template('records_hub.html')

@app.route('/kayit-yonetimi')
@login_required
def record_manager():
    kind=request.args.get('tur','islem')
    if kind not in V05_TABLES: kind='islem'
    table,title,date_col,label_col=V05_TABLES[kind]
    rows=db().execute(f'SELECT id, "{date_col}" AS date_value, "{label_col}" AS label_value, is_cancelled FROM {table} ORDER BY id DESC LIMIT 150').fetchall()
    details=[]
    for r in db().execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT 150').fetchall():
        if kind=='islem':
            label=f"{r['op_type']} | Parsel: {r['parcel_code'] or '-'} | {r['item']} | {r['quantity']:g} {r['unit']} | {r['amount']:,.2f} TL | Sezon: {r['season']}"
            if r['note']: label+=f" | Not: {r['note']}"
        elif kind=='depo': label=f"{r['category']} / {r['item']} | {r['quantity']:g} {r['unit']} × {r['unit_price']:,.2f} TL | Sezon: {r['season']}"
        elif kind=='icar': label=f"Parsel: {r['parcel_code']} | {r['landlord']} | {r['total_amount']:,.2f} TL | Sezon: {r['season']}"
        elif kind=='destek': label=f"{r['support_type']} | {r['description']} | {r['amount']:,.2f} TL | Sezon: {r['season']}"
        else: label=f"{r['machine']} | {r['description']} | {r['cost']:,.2f} TL | Sezon: {r['season']}"
        details.append(dict(id=r['id'],date_value=r[date_col],detail=label,is_cancelled=r['is_cancelled']))
    return render_template_string(MANAGER_HTML,rows=details,kinds=V05_TABLES,kind=kind,title=title,csrf=v05_csrf())

def v05_csrf():
    if '_v05_csrf' not in session: session['_v05_csrf']=secrets.token_urlsafe(24)
    return session['_v05_csrf']

def v05_validate_balances(conn):
    # Check both input and harvested product inventory after a tentative change.
    for r in conn.execute("SELECT DISTINCT item,COALESCE(item_detail,'') detail,unit FROM stock_purchases WHERE is_cancelled=0"):
        if input_stock(conn,r['item'],r['detail'],r['unit']) < -0.000001:
            return f"{r['item']}: depo stoğu eksiye düşecek. Önce tüketim kayıtlarını düzeltin."
    for r in conn.execute("SELECT DISTINCT item FROM operations WHERE is_cancelled=0 AND op_type IN ('Hasat','Satış')"):
        if product_stock(conn,r['item']) < -0.000001:
            return f"{r['item']}: ürün stoğu eksiye düşecek. Önce satış/hasat kayıtlarını düzeltin."
    return None

@app.route('/kayit-durumu/<kind>/<int:record_id>',methods=['POST'])
@login_required
def toggle_record(kind,record_id):
    if kind not in V05_TABLES: abort(404)
    if not secrets.compare_digest(request.form.get('csrf_token',''),v05_csrf()): abort(400)
    table=V05_TABLES[kind][0]
    conn=db()
    old=conn.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone()
    if old is None: abort(404)
    new_state=0 if old['is_cancelled'] else 1
    before_deficits=depot_timeline_deficits(conn) if table=='stock_purchases' else None
    conn.execute('SAVEPOINT v05_toggle')
    try:
        conn.execute(f'UPDATE {table} SET is_cancelled=? WHERE id=?',(new_state,record_id))
        err=None if table=='stock_purchases' else v05_validate_balances(conn)
        if not err and table=='stock_purchases': err=new_depot_deficit_error(before_deficits,depot_timeline_deficits(conn))
        if table=='rent_contracts' and new_state==1:
            paid=conn.execute("SELECT COALESCE(SUM(amount),0) FROM operations WHERE is_cancelled=0 AND op_type='İcar/Kiralama' AND parcel_code=? AND season=?",(old['parcel_code'],old['season'])).fetchone()[0]
            if paid>0: err='Ödeme bulunan kira sözleşmesi iptal edilemez. Önce ilgili kira ödemelerini iptal edin.'
        if err:
            conn.execute('ROLLBACK TO v05_toggle');flash(err,'error')
        else:
            flash('Kayıt iptal edildi.' if new_state else 'Kayıt yeniden etkinleştirildi.','success')
        conn.execute('RELEASE v05_toggle')
        if not err: conn.commit()
    except Exception:
        conn.execute('ROLLBACK TO v05_toggle');conn.execute('RELEASE v05_toggle');raise
    return redirect(url_for('record_manager',tur=kind))

@app.route('/degisiklik-gecmisi')
@login_required
def change_history():
    rows=db().execute('SELECT table_name,record_id,action,changed_at,old_data,new_data FROM change_log ORDER BY id DESC LIMIT 150').fetchall()
    return render_template_string('''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Değişiklik geçmişi</title><style>body{font:14px system-ui;margin:25px}details{max-width:1100px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f3f3;padding:12px}li{padding:8px;border-bottom:1px solid #ddd}</style><a href="/kayit-yonetimi">← Kayıt Yönetimi</a><h1>Değişiklik geçmişi</h1><p>Bu sürümden sonra yapılan değişiklikler kaydedilir; eski sürümlerin geçmişi geriye dönük oluşturulamaz.</p><ol>{% for r in rows %}<li><strong>{{r['changed_at']}} — {{r['table_name']}} #{{r['record_id']}} — {{r['action']}}</strong><details><summary>Önce / sonra</summary><pre>ÖNCE: {{r['old_data']}}
SONRA: {{r['new_data']}}</pre></details></li>{% endfor %}</ol></html>''',rows=rows)



# V1.9.29: Reports and safe SQLite backup (no database replacement).
from io import BytesIO
from flask import send_file
from pathlib import Path as _Path

_EXPORT_TABLES = {
    'islemler': ('İşlem Dökümü', 'operations', ['id','season','op_date','parcel_code','op_type','item','item_detail','quantity','unit','unit_price','amount','direction','category','note']),
    'stok': ('Girdi Alımları', 'stock_purchases', ['id','season','purchase_date','category','item','item_detail','quantity','unit','unit_price','supplier_note']),
    'destek': ('Devlet Destekleri', 'supports', ['id','season','payment_date','support_type','description','crop','amount','note']),
    'icar': ('İcar Sözleşmeleri', 'rent_contracts', ['id','season','parcel_code','landlord','area_da','rate_per_da','total_amount','due_note']),
    'bakim': ('Makine Bakımı', 'machine_maintenance', ['id','season','service_date','machine','description','cost','note']),
}

def _export_data(kind, season):
    if kind == 'ekonomi':
        headers=['Sezon','Gider (TL)','Gelir (TL)','Destek (TL)','Destek Öncesi Kâr','Destek Sonrası Kâr']
        sql="""SELECT s.season,
          COALESCE((SELECT SUM(amount) FROM operations o WHERE o.season=s.season AND o.direction='Gider' AND o.is_cancelled=0),0) gider,
          COALESCE((SELECT SUM(amount) FROM operations o WHERE o.season=s.season AND o.direction='Gelir' AND o.is_cancelled=0),0) gelir,
          COALESCE((SELECT SUM(amount) FROM supports d WHERE d.season=s.season AND d.is_cancelled=0),0) destek
          FROM (SELECT season FROM operations UNION SELECT season FROM supports) s
          WHERE (?='' OR s.season=?) ORDER BY s.season"""
        data=db().execute(sql,(season,season)).fetchall()
        rows=[[r['season'],r['gider'],r['gelir'],r['destek'],r['gelir']-r['gider'],r['gelir']+r['destek']-r['gider']] for r in data]
        return 'Üretim Ekonomisi',headers,rows
    if kind == 'parsel':
        headers=['Parsel','Ad','Alan (da)','Gelir (TL)','Gider (TL)','Fark (TL)']
        sql="""SELECT p.code,p.name,p.area_m2,
          COALESCE(SUM(CASE WHEN o.direction='Gelir' THEN o.amount ELSE 0 END),0) gelir,
          COALESCE(SUM(CASE WHEN o.direction='Gider' THEN o.amount ELSE 0 END),0) gider
          FROM parcels p LEFT JOIN operations o ON o.parcel_code=p.code AND o.is_cancelled=0 AND (?='' OR o.season=?)
          GROUP BY p.code,p.name,p.area_m2 ORDER BY p.code"""
        data=db().execute(sql,(season,season)).fetchall()
        rows=[[r['code'],r['name'],r['area_m2']/1000,r['gelir'],r['gider'],r['gelir']-r['gider']] for r in data]
        return 'Parsel İşlem Özeti',headers,rows
    if kind not in _EXPORT_TABLES: abort(404)
    title,table,fields=_EXPORT_TABLES[kind]
    available={r['name'] for r in db().execute('PRAGMA table_info('+table+')')}
    fields=[f for f in fields if f in available]
    where=" WHERE (? = '' OR season=?)"
    if 'is_cancelled' in available: where+=' AND is_cancelled=0'
    sql='SELECT '+','.join('"'+f+'"' for f in fields)+' FROM '+table+where+' ORDER BY id DESC'
    data=db().execute(sql,(season,season)).fetchall()
    return title,fields,[[r[f] for f in fields] for r in data]

@app.route('/raporlar/rapor-al')
@login_required
def export_page():
    return render_template('export.html')

@app.route('/raporlar/disari-aktar')
@login_required
def report_export():
    kind=request.args.get('tur','ekonomi')
    fmt=request.args.get('format','xlsx')
    if fmt != 'xlsx': abort(400, description='Yalnızca Excel raporu destekleniyor.')
    season=request.args.get('season','').strip()
    title,headers,rows=_export_data(kind,season)
    stamp=datetime.now().strftime('%Y%m%d_%H%M')
    if fmt=='xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill,Alignment
        from openpyxl.utils import get_column_letter
        wb=Workbook(); ws=wb.active;ws.title='Rapor'
        ws.append([title+' | Sezon: '+(season or 'Tümü')]);ws.append(headers)
        for r in rows: ws.append([v if v is not None else '' for v in r])
        ws.freeze_panes='A3';ws.auto_filter.ref=f'A2:{get_column_letter(len(headers))}{max(2,ws.max_row)}'
        for c in ws[2]: c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='245C41');c.alignment=Alignment(wrap_text=True)
        for i,h in enumerate(headers,1): ws.column_dimensions[get_column_letter(i)].width=min(42,max(15,len(str(h))+5))
        for row in ws.iter_rows(min_row=3):
            for cell in row:
                if isinstance(cell.value,float): cell.number_format='#,##0.00'
        buf=BytesIO();wb.save(buf);buf.seek(0)
        return send_file(buf,as_attachment=True,download_name=f'ozcan_{kind}_{stamp}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    abort(400)

def _safe_backup(destination):
    source=sqlite3.connect(DB_PATH)
    try:
        check=source.execute('PRAGMA integrity_check').fetchone()[0]
        if check!='ok': raise RuntimeError('Veritabanı bütünlük kontrolü başarısız: '+str(check))
        target=sqlite3.connect(str(destination))
        try: source.backup(target)
        finally: target.close()
        verified=sqlite3.connect(str(destination))
        try:
            check2=verified.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            verified.close()
        if check2!='ok': raise RuntimeError('Yedek bütünlük kontrolü başarısız')
    finally: source.close()

def _backup_dir():
    p=_Path(os.environ.get('OZCAN_TARIM_BACKUP_DIR',os.path.join(BASE_DIR,'yedekler')))
    p.mkdir(parents=True,exist_ok=True)
    return p

def automatic_backup():
    # Once per calendar day when app starts; also before any manual download.
    p=_backup_dir();day=date.today().isoformat();dest=p/('ozcan_tarim_'+day+'.db')
    if not dest.exists():
        temp=p/('ozcan_tarim_'+day+'.tmp')
        try: _safe_backup(temp);temp.replace(dest)
        finally:
            if temp.exists():temp.unlink()
    backups=sorted(p.glob('ozcan_tarim_????-??-??.db'),reverse=True)
    for old in backups[14:]:old.unlink()

def _backup_health(path):
    """Read-only verification on a separate SQLite connection."""
    try:
        conn=sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            return conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return False

@app.route('/yedekleme/kontrol', methods=['POST'])
@login_required
def backup_verify():
    # Never restore over the live DB. Test a verified backup in an isolated temp directory.
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as td:
            test_path=_Path(td)/'geri_yukleme_testi.db'
            _safe_backup(test_path)
            if not _backup_health(test_path):
                raise RuntimeError('Test kopyası açılamadı veya bütünlük kontrolünden geçemedi.')
        flash('Başarılı: Canlı veritabanından alınan bağımsız test kopyası açıldı ve bütünlüğü doğrulandı. Gerçek geri yükleme yapılmadı.', 'success')
    except Exception as exc:
        app.logger.exception('Yedek test hatası')
        flash('Yedek testi başarısız: '+str(exc), 'error')
    return redirect(url_for('backup_page'))

@app.route('/yedekleme/gunluk', methods=['POST'])
@login_required
def backup_daily_now():
    try:
        automatic_backup()
        flash('Günlük yedek kontrolü tamamlandı. Bugünün yedeği zaten varsa tekrar oluşturulmaz.', 'success')
    except Exception as exc:
        app.logger.exception('Günlük yedek hatası')
        flash('Günlük yedek oluşturulamadı: '+str(exc), 'error')
    return redirect(url_for('backup_page'))

@app.route('/yedekleme')
@login_required
def backup_page():
    backup_files=sorted(_backup_dir().glob('ozcan_tarim_????-??-??.db'),reverse=True)[:14]
    backups=[{'name':p.name,'ok':_backup_health(p),'size_kb':round(p.stat().st_size/1024,1)} for p in backup_files]
    return render_template('backup.html',backups=backups)

@app.route('/yedekleme/indir',methods=['POST'])
@login_required
def backup_download():
    # POST only; does not expose server-side backup paths.
    buf=BytesIO();source=sqlite3.connect(DB_PATH)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok': abort(500,description='Veritabanı bütünlük hatası')
        target=sqlite3.connect(':memory:')
        try:
            source.backup(target)
            with __import__('tempfile').TemporaryDirectory() as folder:
                path=os.path.join(folder,'backup.db');disk=sqlite3.connect(path)
                try:target.backup(disk)
                finally:disk.close()
                buf.write(open(path,'rb').read())
        finally:target.close()
    finally:source.close()
    buf.seek(0)
    return send_file(buf,as_attachment=True,download_name='ozcan_tarim_yedek_'+datetime.now().strftime('%Y%m%d_%H%M')+'.db',mimetype='application/octet-stream')

# Create the first verified backup at startup, without preventing startup on backup errors.
try:
    automatic_backup()
except Exception as _backup_error:
    app.logger.error('Otomatik yedekleme başarısız: %s',_backup_error)

@app.route('/wifi-test')
@login_required
def wifi_test():
    """Read-only connectivity check. Never returns farm data."""
    from flask import Response
    return Response('Özcan Tarım Wi-Fi bağlantısı başarılı. Bu sürüm henüz veri eşitlemez.', content_type='text/plain; charset=utf-8', headers={'Cache-Control':'no-store'})



# V3.3.2: read-only iPhone backup comparison. No database writes.
@app.route('/wifi-karsilastir', methods=['GET', 'POST'])
@login_required
def wifi_compare():
    from flask import render_template_string
    from collections import Counter
    import hashlib
    tables = {'parcels':'parcels','operations':'operations','inputs':'stock_purchases',
              'maintenance':'machine_maintenance','supports':'supports','rents':'rent_contracts',
              'rentPayments':'rent_payments','services':'field_service_charges',
              'servicePayments':'field_service_payments','bales':'bale_batches',
              'baleSales':'bale_sales','soilAnalyses':'soil_analyses'}
    results=[]; error=None; filename=None
    if request.method == 'POST':
        uploaded=request.files.get('backup')
        if not uploaded or not uploaded.filename.lower().endswith('.json'):
            error='Lütfen iPhone uygulamasından alınan JSON yedek dosyasını seçin.'
        else:
            raw=uploaded.stream.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:
                error='Dosya 8 MB sınırını aşıyor.'
            else:
                try:
                    mobile=json.loads(raw.decode('utf-8-sig'))
                    if not isinstance(mobile,dict): raise ValueError('JSON nesnesi bekleniyor')
                    filename=uploaded.filename
                    conn=sqlite3.connect(f'file:{DB_PATH}?mode=ro',uri=True)
                    conn.row_factory=sqlite3.Row
                    try:
                        available={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        for mobile_name,table_name in tables.items():
                            rows=mobile.get(mobile_name,[])
                            if not isinstance(rows,list): raise ValueError(mobile_name+' listesi geçersiz')
                            if table_name not in available:
                                results.append((mobile_name, len(rows), 'Yok', 'Tablo bulunamadı', ''))
                                continue
                            pc=[dict(x) for x in conn.execute('SELECT * FROM "'+table_name+'"')]
                            # Count-only first: record schemas and IDs may differ between the apps.
                            diff=len(rows)-len(pc)
                            status='Sayı eşit (içerik henüz doğrulanmadı)' if diff==0 else 'Kayıt sayısı farklı'
                            results.append((mobile_name,len(rows),len(pc),status,diff))
                    finally:conn.close()
                except (ValueError,UnicodeError,sqlite3.Error) as ex:
                    error='Yedek okunamadı: '+str(ex)[:160]
    return render_template_string('<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım - Wi-Fi Karşılaştırma</title><style>body{font:16px system-ui,sans-serif;background:#f4f7f3;color:#20352b;margin:0;padding:20px}main{max-width:880px;margin:auto;background:white;padding:24px;border-radius:15px}h1{font-size:1.6rem}label{display:block;margin:18px 0}input{max-width:100%}button{background:#19663d;color:white;border:0;padding:13px 20px;border-radius:8px;font-weight:700}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #ddd;text-align:left;padding:9px}section{overflow:auto}.warn{background:#fff4db;padding:12px;border-radius:8px}.err{color:#b00}small{color:#536358}</style></head><body><main><h1>🌾 Özcan Tarım · V3.3.2</h1><h2>iPhone – Bilgisayar veri karşılaştırması</h2><p class="warn">Bu ekran <strong>yalnızca okur</strong>. Bilgisayar veya iPhone verilerini değiştirmez. Sayı eşitliği, kayıtların aynı olduğunu kanıtlamaz.</p><form method="post" enctype="multipart/form-data"><label>iPhone uygulamasından dışa aktarılan <strong>JSON yedeği</strong><br><input type="file" name="backup" accept=".json,application/json" required></label><button type="submit">Kayıt sayılarını karşılaştır</button></form>{% if error %}<p class="err">{{error}}</p>{% endif %}{% if results %}<h2>Karşılaştırma sonucu</h2><p><small>Dosya: {{filename}}</small></p><section><table><thead><tr><th>Kayıt türü</th><th>iPhone</th><th>Bilgisayar</th><th>Durum</th></tr></thead><tbody>{% for key,mobile,pc,status,diff in results %}<tr><td>{{key}}</td><td>{{mobile}}</td><td>{{pc}}</td><td>{{status}}</td></tr>{% endfor %}</tbody></table></section><p class="warn">Sonraki aşama: kayıt kimlikleri ve alanları karşılaştırılarak gerçek fark listesi hazırlanacak. Bu sürüm hiçbir kayıt aktarmıyor.</p>{% endif %}<p><a href="/">Ana sayfaya dön</a></p></main></body></html>',results=results,error=error,filename=filename)

from wifi_detail import register as register_wifi_detail
register_wifi_detail(app, login_required, DB_PATH)
from wifi_transfer import register as register_wifi_transfer
register_wifi_transfer(app, login_required, DB_PATH)

from wifi_sync335 import register as register_wifi_sync335
register_wifi_sync335(app, login_required, DB_PATH)

from wifi_sync336 import register as register_wifi_sync336
register_wifi_sync336(app, login_required, DB_PATH)

from wifi_sim337 import register as register_wifi_sim337
register_wifi_sim337(app, login_required, DB_PATH)

from wifi_copy338 import register as register_wifi_copy338
register_wifi_copy338(app, login_required, DB_PATH)

from wifi_real339 import register as register_wifi_real339
register_wifi_real339(app, login_required, DB_PATH)

from iphone_yedek_raporu import register as register_iphone_yedek_raporu
register_iphone_yedek_raporu(app, login_required)
from tam_yedek_aktarim import register as register_tam_yedek
register_tam_yedek(app, login_required)

if __name__ == '__main__':
    lan_mode = os.environ.get('OZCAN_TARIM_LAN') == '1'
    if lan_mode and (APP_PASSWORD == 'Degistir123!' or len(APP_PASSWORD) < 10):
        raise SystemExit('Wi-Fi modunda en az 10 karakterlik, varsayilan olmayan parola gereklidir.')
    app.run(host='0.0.0.0' if lan_mode else '127.0.0.1', port=int(os.environ.get('PORT','5000')), debug=False)

