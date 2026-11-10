"""One-time import of the current Özcan Tarım Excel workbook into SQLite.
Run: python import_workbook.py /path/to/source.xlsx
Existing non-empty databases are not overwritten.
"""
import os, sys, sqlite3
from datetime import datetime, date
import openpyxl
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.environ.get('OZCAN_TARIM_DB', os.path.join(BASE_DIR, 'ozcan_tarim.db'))

def init_db():
    conn=sqlite3.connect(DB_PATH)
    conn.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS parcels (code TEXT PRIMARY KEY, name TEXT NOT NULL, area_m2 REAL NOT NULL CHECK(area_m2>0), property_type TEXT, soil_type TEXT, irrigation TEXT, neighborhood TEXT, ada TEXT, parcel_no TEXT, owner TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS operations (id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, op_date TEXT NOT NULL, parcel_code TEXT REFERENCES parcels(code), op_type TEXT NOT NULL, item TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity>0), unit TEXT NOT NULL, unit_price REAL CHECK(unit_price>=0), amount REAL NOT NULL CHECK(amount>=0), direction TEXT NOT NULL CHECK(direction IN ('Gelir','Gider','Nötr')), category TEXT, note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS stock_purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, purchase_date TEXT NOT NULL, category TEXT NOT NULL, item TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity>0), unit TEXT NOT NULL, unit_price REAL NOT NULL CHECK(unit_price>=0), supplier_note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS machine_maintenance (id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT NOT NULL, service_date TEXT NOT NULL, machine TEXT NOT NULL, work_hours REAL, description TEXT NOT NULL, cost REAL NOT NULL CHECK(cost>=0), note TEXT);
    CREATE TABLE IF NOT EXISTS supports (id INTEGER PRIMARY KEY AUTOINCREMENT, payment_date TEXT NOT NULL, season TEXT NOT NULL, support_type TEXT NOT NULL, description TEXT NOT NULL, crop TEXT, amount REAL NOT NULL CHECK(amount>=0), note TEXT);
    CREATE TABLE IF NOT EXISTS rent_contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, landlord TEXT NOT NULL, parcel_code TEXT NOT NULL REFERENCES parcels(code), season TEXT NOT NULL, start_date TEXT, end_date TEXT, area_da REAL NOT NULL CHECK(area_da>0), rate_per_da REAL NOT NULL CHECK(rate_per_da>=0), total_amount REAL NOT NULL CHECK(total_amount>=0), due_note TEXT, UNIQUE(parcel_code, season, landlord, start_date));
    CREATE INDEX IF NOT EXISTS idx_ops_season ON operations(season); CREATE INDEX IF NOT EXISTS idx_ops_item ON operations(item); CREATE INDEX IF NOT EXISTS idx_stock_item ON stock_purchases(item);
    '''); conn.commit(); conn.close()

source = sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.dirname(__file__), 'source_workbook.xlsx')
if not os.path.exists(source):
    raise SystemExit(f'Kaynak Excel bulunamadı: {source}')
init_db()
conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
if conn.execute('SELECT COUNT(*) FROM parcels').fetchone()[0] or conn.execute('SELECT COUNT(*) FROM operations').fetchone()[0]:
    raise SystemExit('Veritabanında zaten veri var; güvenlik için içe aktarma durduruldu. Yeni boş veritabanı kullanın.')
wb=openpyxl.load_workbook(source, data_only=True, read_only=False)
def val(ws,r,c): return ws.cell(r,c).value
def txt(v): return str(v).strip() if v is not None and str(v).strip() else None
def num(v, default=0):
    try: return float(v) if v is not None else default
    except (ValueError,TypeError): return default
def dstr(v):
    if isinstance(v,(datetime,date)): return v.strftime('%Y-%m-%d')
    if v:
        try: return datetime.fromisoformat(str(v)).strftime('%Y-%m-%d')
        except ValueError: return None
    return None
# Parcels: only genuine rows with a code, name, and positive area are imported.
ws=wb['02_Parseller']; parcel_count=0
for r in range(4,ws.max_row+1):
    code,name,area=txt(val(ws,r,1)),txt(val(ws,r,2)),num(val(ws,r,5))
    if not code or not name or area<=0: continue
    conn.execute('''INSERT INTO parcels(code,name,ada,parcel_no,area_m2,neighborhood,property_type,soil_type,irrigation,owner)
      VALUES(?,?,?,?,?,?,?,?,?,?)''',(code,name,txt(val(ws,r,3)),txt(val(ws,r,4)),area,txt(val(ws,r,6)),txt(val(ws,r,7)),txt(val(ws,r,8)),txt(val(ws,r,11)),txt(val(ws,r,13))))
    parcel_count+=1
# Operations: only real rows, not the preformatted empty worksheet rows.
ws=wb['03_Islemler']; op_count=0
for r in range(4,ws.max_row+1):
    season=txt(val(ws,r,2)); dt=dstr(val(ws,r,3)); parcel=txt(val(ws,r,4)); op=txt(val(ws,r,7)); item=txt(val(ws,r,8)); qty=num(val(ws,r,9),-1); unit=txt(val(ws,r,10)); amount=num(val(ws,r,12)); direction=txt(val(ws,r,13))
    if not any([season,dt,parcel,op,item]): continue
    if not season or not dt or not op or not item or qty<=0: continue
    if parcel and not conn.execute('SELECT 1 FROM parcels WHERE code=?',(parcel,)).fetchone(): parcel=None
    if direction not in ('Gelir','Gider','Nötr'): direction='Nötr'
    unit_price=num(val(ws,r,21),num(val(ws,r,11),0))
    conn.execute('''INSERT INTO operations(season,op_date,parcel_code,op_type,item,quantity,unit,unit_price,amount,direction,category,note)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(season,dt,parcel,op,item,qty,unit or 'adet',max(unit_price,0),max(amount,0),direction,txt(val(ws,r,17)),txt(val(ws,r,14))))
    op_count+=1
# Depot purchase lots: only rows with date, item, quantity and price.
ws=wb['04_Depo_Stok']; stock_count=0
for r in range(24,ws.max_row+1):
    season=txt(val(ws,r,2)); dt=dstr(val(ws,r,3)); cat=txt(val(ws,r,4)); item=txt(val(ws,r,5)); qty=num(val(ws,r,6),-1); unit=txt(val(ws,r,7)); price=num(val(ws,r,8),-1)
    if not season or not dt or not item or qty<=0 or price<0: continue
    conn.execute('INSERT INTO stock_purchases(season,purchase_date,category,item,quantity,unit,unit_price,supplier_note) VALUES(?,?,?,?,?,?,?,?)',
      (season,dt,cat or 'Diğer',item,qty,unit or 'adet',price,txt(val(ws,r,12))))
    stock_count+=1
# Machine maintenance rows.
ws=wb['05_Makine_Bakim']; maint_count=0
for r in range(4,ws.max_row+1):
    season=txt(val(ws,r,2)); dt=dstr(val(ws,r,3)); machine=txt(val(ws,r,4)); desc=txt(val(ws,r,6)); cost=num(val(ws,r,7),-1)
    if not season or not dt or not machine or not desc or cost<0: continue
    conn.execute('INSERT INTO machine_maintenance(season,service_date,machine,work_hours,description,cost,note) VALUES(?,?,?,?,?,?,?)',
      (season,dt,machine,num(val(ws,r,5),0),desc,cost,txt(val(ws,r,8))))
    maint_count+=1
# Support payments.
ws=wb['10_Gelir_Destekler']; support_count=0
for r in range(4,ws.max_row+1):
    dt=dstr(val(ws,r,2)); season=txt(val(ws,r,4)); st=txt(val(ws,r,5)); desc=txt(val(ws,r,6)); crop=txt(val(ws,r,7)); amount=num(val(ws,r,8),-1)
    if not dt or not season or not st or not desc or amount<=0: continue
    conn.execute('INSERT INTO supports(payment_date,season,support_type,description,crop,amount) VALUES(?,?,?,?,?,?)',(dt,season,st,desc,crop,amount)); support_count+=1
# Rent contracts: import contracts, never import payment rows separately.
ws=wb['11_Kira_Takip']; rent_count=0
for r in range(5,ws.max_row+1):
    landlord=txt(val(ws,r,2)); parcel=txt(val(ws,r,3)); season=txt(val(ws,r,5)); start=dstr(val(ws,r,6)); end=dstr(val(ws,r,7)); rate=num(val(ws,r,9),-1); area=num(val(ws,r,8),0); total=num(val(ws,r,10),-1)
    if not landlord or not parcel or not season or rate<0 or total<0 or not conn.execute('SELECT 1 FROM parcels WHERE code=?',(parcel,)).fetchone(): continue
    try:
        conn.execute('INSERT INTO rent_contracts(landlord,parcel_code,season,start_date,end_date,area_da,rate_per_da,total_amount,due_note) VALUES(?,?,?,?,?,?,?,?,?)',
          (landlord,parcel,season,start,end,area,rate,total,txt(val(ws,r,11))))
        rent_count+=1
    except sqlite3.IntegrityError: pass
conn.commit(); conn.close()
print('İçe aktarma tamamlandı:')
print(f'Parseller: {parcel_count}; İşlemler: {op_count}; Depo alımları: {stock_count}; Makine bakımı: {maint_count}; Destek: {support_count}; Kira sözleşmesi: {rent_count}')
