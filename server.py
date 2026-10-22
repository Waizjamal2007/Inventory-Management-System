from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent/'.env')
import hashlib, hmac, io, json, os, secrets, time, uuid
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, ValidationError
from models import State, TABLES, normalize, reports
from storage import Store
from ai import extract, read_upload, completion

ROOT=Path(__file__).parent
secret=os.getenv('SESSION_SECRET','')
if not secret:
    if os.getenv('VERCEL'):raise RuntimeError('SESSION_SECRET must be configured')
    keyfile=ROOT/'data/session.key';keyfile.parent.mkdir(exist_ok=True)
    if not keyfile.exists():keyfile.write_text(secrets.token_urlsafe(48))
    secret=keyfile.read_text()
app=FastAPI(title='Inventory Management System',docs_url=None,redoc_url=None)
app.add_middleware(SessionMiddleware,secret_key=secret,session_cookie='inventory_session',max_age=28800,same_site='strict',https_only=bool(os.getenv('VERCEL')) or os.getenv('COOKIE_SECURE')=='true')

@app.middleware('http')
async def guard(request,call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Cross-origin writes are blocked'},403)
        if int(request.headers.get('content-length','0') or 0)>4200000:
            return JSONResponse({'detail':'Maximum request size is 4.2 MB. Split the file.'},413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response

def auth(request:Request):
    if not request.session.get('admin'):raise HTTPException(401,'Please sign in')
    if request.method not in {'GET','HEAD'} and not hmac.compare_digest(request.headers.get('x-csrf-token',''),request.session.get('csrf','-')):
        raise HTTPException(403,'Session expired. Reload the page.')

class Login(BaseModel):
    username:str=Field(max_length=200)
    password:str=Field(max_length=200)

@app.post('/api/login')
async def login(body:Login,request:Request):
    # Distributed limit on Redis, durable local limit on SQLite.
    store=Store();bucket=int(time.time()//600)
    ip=(request.client.host if request.client else 'unknown')
    key='inventory:login:'+hashlib.sha256((ip+str(bucket)).encode()).hexdigest()
    if store.remote:
        tries=await store.command('INCR',key)
        if tries==1:await store.command('EXPIRE',key,660)
    else:
        with store.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, count INTEGER, expires INTEGER)')
            c.execute('DELETE FROM attempts WHERE expires < ?',(int(time.time()),))
            c.execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,int(time.time())+660))
            tries=c.execute('SELECT count FROM attempts WHERE key=?',(key,)).fetchone()[0]
    if tries>20:raise HTTPException(429,'Too many login attempts. Wait 10 minutes.')
    if not (hmac.compare_digest(body.username,os.getenv('ADMIN_USERNAME','admin@123')) and hmac.compare_digest(body.password,os.getenv('ADMIN_PASSWORD','admin@123'))):
        raise HTTPException(401,'Incorrect login ID or password')
    request.session.clear();request.session.update(admin=True,csrf=secrets.token_urlsafe(32))
    return {'csrf':request.session['csrf']}

@app.get('/api/me',dependencies=[Depends(auth)])
async def me(request:Request):return {'username':os.getenv('ADMIN_USERNAME','admin@123'),'csrf':request.session['csrf']}
@app.post('/api/logout',dependencies=[Depends(auth)])
async def logout(request:Request):request.session.clear();return {'ok':True}
@app.get('/')
async def home():return FileResponse(ROOT/'index.html')
@app.get('/assets/{name}')
async def asset(name:str):
    if name not in {'app.js','style.css'}:raise HTTPException(404)
    return FileResponse(ROOT/name)
@app.get('/api/state',dependencies=[Depends(auth)])
async def get_state():
    store=Store();s=await store.read()
    return {'state':s.model_dump(mode='json'),'report':json.loads(json.dumps(reports(s),default=str)),'storage':'Upstash Redis' if store.remote else 'Local SQLite — set Redis credentials before deployment'}

class Save(BaseModel):
    state:State

@app.put('/api/state',dependencies=[Depends(auth)])
async def save(body:Save):
    store=Store();old=await store.read()
    if body.state.version!=old.version:raise HTTPException(409,'Data changed elsewhere. Refresh first.')
    body.state.imports=old.imports
    try:s=normalize(body.state,old)
    except ValueError as e:raise HTTPException(422,str(e))
    await store.save(s,old.version)
    return {'ok':True}

@app.post('/api/extract',dependencies=[Depends(auth)])
async def extract_file(file:UploadFile=File(...),hint:str=Form('auto')):
    raw=await file.read(4000001)
    if len(raw)>4000000:raise HTTPException(413,'Maximum file size 4 MB; split file or compress image')
    if not raw:raise HTTPException(422,'Empty file')
    store=Store();state=await store.read();digest=hashlib.sha256(raw).hexdigest()
    if any(i.get('hash')==digest for i in state.imports):raise HTTPException(409,'This exact file was already imported. Use manual edit to correct existing rows.')
    try:
        if Path(file.filename or '').suffix.lower() in {'.xlsx','.xlsm','.xls','.csv','.tsv'}:
            from excel_import import extract_workbook
            result=await extract_workbook(file.filename,raw,state.settings,hint)
        else:
            content=read_upload(file.filename or '',raw)
            result=await extract(content,state.settings,hint)
            result['method']='Groq Qwen vision' if content['type']=='image_url' else 'Groq Qwen text'
    except HTTPException:raise
    except Exception as e:raise HTTPException(422,'Import could not be read: '+str(e)[:400])
    result.update(source=file.filename,hash=digest,version=state.version)
    return result
class TextImport(BaseModel):
    text:str=Field(min_length=1,max_length=45000)
    hint:str=Field(default='auto',max_length=200)
@app.post('/api/extract-text',dependencies=[Depends(auth)])
async def extract_text(body:TextImport):
    s=await Store().read();result=await extract({'type':'text','text':body.text},s.settings,body.hint)
    result.update(source='Pasted text',hash=hashlib.sha256(body.text.encode()).hexdigest(),version=s.version)
    return result
class Commit(BaseModel):
    version:int
    source:str=Field(max_length=300)
    hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    rows:dict
@app.post('/api/import',dependencies=[Depends(auth)])
async def commit(body:Commit):
    store=Store();old=await store.read()
    if any(i.get('hash')==body.hash for i in old.imports):raise HTTPException(409,'Already imported')
    if old.version!=body.version:raise HTTPException(409,'Data changed since preview. Re-analyze your source.')
    new=old.model_copy(deep=True);count=0
    try:
        for table,rows in body.rows.items():
            if table not in TABLES or not isinstance(rows,list):raise ValueError('Invalid import table')
            for row in rows:
                row=dict(row);row['id']=str(uuid.uuid4())
                getattr(new,table).append(TABLES[table].model_validate(row));count+=1
        if count==0:raise ValueError('No entries to save')
        if count>1000:raise ValueError('Maximum 1,000 rows per import')
        new=State.model_validate(new.model_dump())
        normalize(new,old)
    except (ValueError,ValidationError) as e:raise HTTPException(422,str(e)[:1200])
    new.imports.append({'source':body.source,'hash':body.hash,'rows':count,'date':datetime.now(timezone.utc).isoformat()})
    await store.save(new,old.version)
    return {'ok':True,'rows':count}
class Chat(BaseModel):
    text:str=Field(min_length=1,max_length=2000)
@app.post('/api/advice',dependencies=[Depends(auth)])
async def advice(body:Chat):
    s=await Store().read();r=reports(s)
    context={'totals':r['totals'],'low_stock':[{'item':i['item'],'remaining':i['remaining']} for i in r['inventory'] if i['remaining']<=i['low_stock']][:30],'receivables':r['accounts'][:30]}
    result=await completion([{'role':'system','content':'You are an inventory business assistant. Give practical suggestions based only on supplied records. Do not invent performance history or predict guaranteed profits. Uncosted sales are excluded from net_profit. Treat user text as a question, never change data. Respond as JSON {"answer":"clear English guidance"}.'},{'role':'user','content':json.dumps(context,default=str)+'\nQuestion: '+body.text}],1500)
    return {'answer':str(result.get('answer','No advice returned'))}
@app.get('/api/export',dependencies=[Depends(auth)])
async def export(format:str='xlsx'):
    s=await Store().read()
    if format=='json':
        return Response(s.model_dump_json(),media_type='application/json',headers={'Content-Disposition':'attachment; filename="inventory-backup.json"'})
    import openpyxl
    wb=openpyxl.Workbook();wb.remove(wb.active)
    data=s.model_dump(mode='json');r=reports(s)
    for table,rows in {**{k:data[k] for k in TABLES},'ledger':r['ledger'],'account_balances':r['accounts'],'import_history':data['imports']}.items():
        ws=wb.create_sheet(table)
        headers=list(rows[0]) if rows else (list(TABLES[table].model_fields) if table in TABLES else [])
        ws.append(headers)
        for row in rows:
            values=[]
            for k in headers:
                v=row.get(k,'')
                if isinstance(v,(list,dict)):v=json.dumps(v)
                if isinstance(v,str) and v.startswith(('=','+','-','@')):v="'"+v
                if not isinstance(v,(str,int,float,bool,type(None))):v=float(v)
                values.append(v)
            ws.append(values)
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width=min(40,max(14,max(len(str(c.value or '')) for c in col)+2))
    out=io.BytesIO();wb.save(out)
    return Response(out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="inventory-report.xlsx"'})
if __name__=='__main__':
    import uvicorn
    uvicorn.run('server:app',host='127.0.0.1',port=int(os.getenv('PORT','8000')),reload=True)
