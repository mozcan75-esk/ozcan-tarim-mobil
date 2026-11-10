import json, html, io, csv, re, os, tempfile, hashlib
from pathlib import Path
from datetime import datetime, timezone
from flask import request, render_template_string, Response, redirect, url_for, abort, send_file

MAX_BYTES=30*1024*1024
STORES=('parcels','operations','inputs','stockMoves','harvests','sales','rents','rentPayments','supports','maintenance','services','servicePayments','bales','baleSales','soilAnalyses','marketPrices','sourceRecords')

def _validate(data):
    if not isinstance(data,dict) or data.get('format') not in ('ozcan-mobile-test-v1','ozcan-mobile-test-v2','ozcan-mobile-test-v3'):
        raise ValueError('Tanınmayan mobil yedek biçimi')
    if not isinstance(data.get('parcels'),list) or not isinstance(data.get('operations'),list):
        raise ValueError('Parsel veya işlem listesi eksik')
    for k in STORES:
        if k in data:
            if not isinstance(data[k],list) or any(not isinstance(v,dict) for v in data[k]):
                raise ValueError(k+' kayıtları geçersiz')
            key='code' if k=='parcels' else 'id'
            ids=[str(v.get(key,'')) for v in data[k]]
            if any(not x for x in ids) or len(ids)!=len(set(ids)):
                raise ValueError(k+' kayıtlarında eksik/tekrarlanan kimlik')
    return data

def register(app, login_required):
    archive_dir=Path(app.root_path)/'mobil_yedek_arsivi'
    archive_dir.mkdir(exist_ok=True)
    def archive_path(): return archive_dir/'son_mobil_yedek.json'
    @app.route('/iphone-yedek-indir')
    @login_required
    def iphone_yedek_indir():
        p=archive_path()
        if not p.exists(): abort(404)
        return send_file(p,as_attachment=True,download_name='Ozcan_Tarim_Mobil_Arsiv.json',mimetype='application/json')
    @app.route('/iphone-yedek-arsiv')
    @login_required
    def iphone_yedek_arsiv():
        p=archive_path()
        if not p.exists(): return redirect(url_for('iphone_yedek_raporu'))
        return _report(_validate(json.loads(p.read_text(encoding='utf-8'))), 'Arşivlenmiş iPhone yedeği', 'Bu veri bilgisayarın canlı SQLite veritabanına aktarılmamıştır.')
    def _report(data,filename,note=''):
        rows=[(k,len(data.get(k,[]))) for k in STORES]
        details=[]
        for k in STORES:
            entries=data.get(k,[])
            if entries:
                cols=list(dict.fromkeys(str(c) for r in entries for c in r.keys()))[:35]
                details.append((k,cols,[[str(r.get(c,''))[:500] for c in cols] for r in entries[:500]],len(entries)))
        return render_template_string(TEMPLATE,rows=rows,details=details,error=None,data=data,note=note,filename=filename)

    @app.route('/iphone-yedek-raporu',methods=['GET','POST'])
    @login_required
    def iphone_yedek_raporu():
        if request.method=='GET':
            return render_template_string(TEMPLATE,rows=[],details=[],error=None,data=None,note='',filename='')
        f=request.files.get('backup')
        if not f or not f.filename.lower().endswith('.json'):
            return render_template_string(TEMPLATE,rows=[],details=[],error='JSON dosyası seçin.',data=None,note='',filename='')
        raw=f.read(MAX_BYTES+1)
        try:
            if len(raw)>MAX_BYTES: raise ValueError('30 MB sınırı aşıldı')
            data=_validate(json.loads(raw.decode('utf-8-sig')))
            if request.form.get('archive')=='yes':
                # Atomic archive write, no modification to main database.
                tmp=archive_dir/('tmp_'+os.urandom(8).hex()+'.json')
                try:
                    tmp.write_bytes(raw)
                    os.replace(tmp,archive_path())
                finally:
                    tmp.unlink(missing_ok=True)
                note='Mobil yedek ayrı arşive kaydedildi. Canlı bilgisayar veritabanı DEĞİŞMEDİ.'
            else: note='Yalnızca önizleme. Dosya kaydedilmedi.'
            return _report(data, f.filename,note)
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError) as exc:
            return render_template_string(TEMPLATE,rows=[],details=[],error=str(exc),data=None,note='',filename='')

TEMPLATE="""<!doctype html><html lang='tr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>iPhone Yedek Raporu · Özcan Tarım</title><style>body{font:15px system-ui,sans-serif;max-width:1200px;margin:25px auto;padding:0 15px;color:#173b2b}h1{color:#176c43}.box{background:#f1f7f3;padding:18px;border-radius:10px;margin:16px 0}button{background:#176c43;color:white;border:0;border-radius:6px;padding:12px;cursor:pointer}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #ddd;padding:7px;text-align:left;vertical-align:top}th{background:#eaf2ec}section{margin:20px 0}details{margin:10px 0;border:1px solid #ddd;border-radius:8px;padding:12px}.scroll{overflow:auto;max-height:500px}.warn{color:#a33928}input{margin:12px 0}</style></head><body><p><a href='/'>← Özcan Tarım</a></p><h1>iPhone Tam Yedek Raporu</h1><div class='box'>Bu ekran iPhone JSON yedeğini <b>incelemek ve ayrı arşive kaydetmek</b> içindir. Bilgisayardaki veritabanını değiştirmez. İki uygulama bağımsız olarak kullanılabilir.</div><p><a href='/iphone-yedek-arsiv'>Son kaydedilen mobil arşivi aç</a> · <a href='/iphone-yedek-indir'>Mobil arşivi indir</a></p><form method='post' enctype='multipart/form-data'><input type='file' name='backup' accept='.json,application/json' required><label><input type='checkbox' name='archive' value='yes' checked> Doğrulanmış yedeği bilgisayarda ayrı arşive kaydet</label><button type='submit'>Yedeği Aç / Arşivle</button></form>{% if note %}<p class='box'>{{note}}</p>{% endif %}{% if error %}<p class='warn'>{{error}}</p>{% endif %}{% if data %}<p><b>Yedek biçimi:</b> {{data.get('format')}} · <b>Alınma zamanı:</b> {{data.get('exportedAt','Belirtilmemiş')}}</p><h2>Kayıt özeti</h2><table><tr><th>Kayıt türü</th><th>Adet</th></tr>{% for name,count in rows %}<tr><td>{{name}}</td><td>{{count}}</td></tr>{% endfor %}</table><h2>Kayıt ayrıntıları</h2><p>Her türden ilk 500 kayıt görüntülenir. Dosyanın tamamı analiz edilerek sayılmıştır.</p>{% for name,cols,items,total in details %}<details><summary><b>{{name}}</b> — {{total}} kayıt</summary><div class='scroll'><table><tr>{% for c in cols %}<th>{{c}}</th>{% endfor %}</tr>{% for item in items %}<tr>{% for val in item %}<td>{{val}}</td>{% endfor %}</tr>{% endfor %}</table></div></details>{% endfor %}{% endif %}</body></html>"""
