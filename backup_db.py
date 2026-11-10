"""Create a consistent SQLite backup of the Özcan Tarım database."""
import os, sqlite3, sys
from datetime import datetime
base=os.path.dirname(os.path.abspath(__file__))
src=os.environ.get('OZCAN_TARIM_DB',os.path.join(base,'ozcan_tarim.db'))
out=sys.argv[1] if len(sys.argv)>1 else os.path.join(base,'backups',f'ozcan_tarim_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
os.makedirs(os.path.dirname(os.path.abspath(out)),exist_ok=True)
if not os.path.exists(src): raise SystemExit(f'Veritabanı bulunamadı: {src}')
with sqlite3.connect(src) as source, sqlite3.connect(out) as target:
    source.backup(target)
print(f'Yedek oluşturuldu: {out}')
