"""V3.3.6 safe dry-run: inspect paired mobile operations and stock moves.
No business-table writes. No importing; source ID relationships must be verified first.
"""
import json, sqlite3, collections, hashlib
from flask import request, render_template_string

PAGE='''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Özcan Tarım V3.3.6</title><style>body{font:16px system-ui;background:#edf4ee;color:#173d2b;padding:16px}main{max-width:1000px;margin:auto;background:#fff;padding:24px;border-radius:12px}button{padding:12px;background:#17683e;color:white;border:0;border-radius:8px}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}.warn{background:#fff1d7;padding:14px;border-radius:6px}.ok{background:#e2f3e7;padding:14px;border-radius:6px}code{overflow-wrap:anywhere}</style><main><h2>🌾 Özcan Tarım V3.3.6 — Faaliyet + stok bağlantı denetimi</h2><p class="warn"><b>Salt okunur test.</b> Bu sayfa hiçbir faaliyeti veya stok hareketini ana veritabanına eklemez, silmez ya da değiştirmez. Çift yönlü eşitleme henüz hazır değildir. Yeni faaliyetlerin bağlı stok hareketleri olmadan aktarılmasını önlemek için hazırlanmıştır.</p><p>Önce <a href="/wifi-transfer">iPhone JSON yedeğini bekleme alanına yükleyin</a>.</p><form method="post"><button>Son yedekte bağlantıları denetle</button></form>{% if error %}<p class="warn">{{error}}</p>{% endif %}{% if stats %}<p class="ok">Yedek: <code>{{digest}}</code><br>Mobil faaliyet: <b>{{stats.operations}}</b> · Stok hareketi: <b>{{stats.moves}}</b> · PC kökenli faaliyet: <b>{{stats.pc_origin}}</b> · Mobil kökenli yeni faaliyet adayı: <b>{{stats.mobile_new}}</b></p><h3>Bağlantı incelemesi</h3><table><tr><th>Durum</th><th>Adet</th></tr>{% for k,v in summary %}<tr><td>{{k}}</td><td>{{v}}</td></tr>{% endfor %}</table><h3>Mobil kökenli yeni faaliyet adayları (en çok 100)</h3>{% if candidates %}<table><tr><th>Kimlik</th><th>Faaliyet</th><th>Stok hareketi</th><th>Karar</th></tr>{% for x in candidates %}<tr><td><code>{{x.id}}</code></td><td>{{x.kind}} · {{x.parcel}}</td><td>{{x.moves}}</td><td>{{x.reason}}</td></tr>{% endfor %}</table>{% else %}<p>Yeni mobil kökenli faaliyet adayı yok. Bu yedekle yazma testi yapılmaz.</p>{% endif %}<p class="warn">Önemli: Mobil <code>stockMoves</code> içindeki <code>source_operation_id</code> alanı PC kökenli kayıtlarda sayısal olabilir; yeni mobil kayıtlarda aynı ilişkiyi güvenilir biçimde kanıtlamadan aktarım yapılmayacaktır. Stok alımı, iptal, güncelleme ve çakışmalar ayrıca modellenmelidir.</p>{% endif %}<p><a href="/wifi-yeni-islemler">Önceki ekran</a> · <a href="/">Ana sayfa</a></p></main>'''

def inspect(data, pc_ids, imported_ids):
    ops=data.get('operations'); moves=data.get('stockMoves')
    if not isinstance(ops,list) or not isinstance(moves,list):
        raise ValueError('Yedekte operations veya stockMoves listesi eksik.')
    by_source=collections.defaultdict(list)
    bad_moves=0
    for m in moves:
        if not isinstance(m,dict): bad_moves+=1;continue
        if m.get('kind')=='use':
            source=m.get('source_operation_id')
            if source is None:bad_moves+=1
            else:by_source[str(source)].append(m)
    results=[]; counts=collections.Counter(); origin=0
    seen=set()
    for op in ops:
        if not isinstance(op,dict):counts['Bozuk faaliyet kaydı']+=1;continue
        mid=op.get('id')
        if not isinstance(mid,str) or not mid:counts['Geçersiz faaliyet kimliği']+=1;continue
        if mid in seen:counts['Tekrarlanan faaliyet kimliği']+=1;continue
        seen.add(mid)
        if mid.startswith('pc-op-') and mid[6:].isdigit():
            origin+=1
            if int(mid[6:]) not in pc_ids:counts['PC kökenli fakat PC’de bulunamayan']+=1
            continue
        if mid in imported_ids:counts['Daha önce aktarılmış mobil kimliği']+=1;continue
        # Mobile records may point to their own operation ID, or a PC integer source id.
        links=by_source.get(mid,[])
        if not links and op.get('source_id') is not None:
            links=by_source.get(str(op['source_id']),[])
        if not links:
            reason='Bağlı stok tüketimi bulunamadı veya ilişki çözümlenemedi; aktarım engelli'
        else:
            reason='Bağlı hareket bulundu; alan ve muhasebe doğrulaması yapılmadı, aktarım engelli'
        counts[reason]+=1
        results.append(dict(id=mid,kind=op.get('op_type','?'),parcel=op.get('parcel_code','?'),moves=len(links),reason=reason))
    counts['Kaynak faaliyet kimliği olmayan stok tüketimi']=bad_moves
    counts['Stok alımı (ayrı eşleme gerektirir)']=sum(isinstance(m,dict) and m.get('kind')=='purchase' for m in moves)
    return {'operations':len(ops),'moves':len(moves),'pc_origin':origin,'mobile_new':len(results)},results,counts

def register(app,login_required,db_path):
    @app.route('/wifi-stok-denetim',methods=['GET','POST'])
    @login_required
    def wifi_stock_audit():
        context={'stats':None,'digest':None,'summary':[],'candidates':[],'error':None}
        if request.method=='POST':
            try:
                with sqlite3.connect(db_path,timeout=15) as conn:
                    conn.row_factory=sqlite3.Row
                    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wifi_inbox'").fetchone():
                        raise ValueError('Önce /wifi-transfer sayfasından yedek yükleyin.')
                    inbox=conn.execute('SELECT sha256,payload FROM wifi_inbox ORDER BY id DESC LIMIT 1').fetchone()
                    if not inbox:raise ValueError('Henüz yedek yüklenmemiş.')
                    data=json.loads(inbox['payload'])
                    if not isinstance(data,dict) or data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'):
                        raise ValueError('Tanımlanmayan yedek biçimi.')
                    pc_ids={r[0] for r in conn.execute('SELECT id FROM operations')}
                    imported=set()
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wifi_import_map'").fetchone():
                        imported={r[0] for r in conn.execute('SELECT mobile_id FROM wifi_import_map')}
                    stats,items,counts=inspect(data,pc_ids,imported)
                    context.update(stats=stats,candidates=items[:100],summary=sorted(counts.items()),digest=inbox['sha256'])
            except (ValueError,TypeError,sqlite3.Error,KeyError) as exc:
                context['error']='Denetim yapılamadı: '+str(exc)[:240]
        return render_template_string(PAGE,**context)
