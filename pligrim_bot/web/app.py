import asyncio
import base64
import io
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,Request,Depends
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from pligrim_bot.config import settings
from pligrim_bot.config.constants import bot,TTF_REGULAR
from pligrim_bot.core.google_sheets import get_palm_sheet_names,find_worksheet_by_title
from pligrim_bot.core.parsers.package_parser import find_palm_packages,collect_voucher_by_package
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.voucher.render import AVAILABLE_BACKGROUNDS,render_voucher_page1_png
from pligrim_bot.core.voucher.validation import voucher_errors
from . import auth,service
from .models import GenerateRequest

STATIC=Path(__file__).parent/'static'
logger=logging.getLogger(__name__)
_refreshed=0
_username=None


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(service.cleanup)
    yield
    if service.TASKS:
        done,pending=await asyncio.wait(service.TASKS,timeout=20)
        for task in pending:task.cancel()
    await bot.session.close()

app=FastAPI(title='Hickmet Workspace',lifespan=lifespan,docs_url=None,redoc_url=None)


@app.middleware('http')
async def secure_requests(request,call_next):
    if request.method in {'POST','PUT','PATCH','DELETE'}:
        origin=request.headers.get('origin')
        if origin:
            allowed={str(request.base_url).rstrip('/'),os.getenv('WEBAPP_URL','').rstrip('/')}
            if origin not in allowed:return JSONResponse({'detail':'Запрос с другого сайта запрещён'},status_code=403)
        if int(request.headers.get('content-length','0') or 0)>512000:
            return JSONResponse({'detail':'Слишком большой запрос'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self' blob:; frame-ancestors https://web.telegram.org https://*.telegram.org; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)


async def user(request:Request):
    authorization=request.headers.get('authorization','')
    token=authorization[7:] if authorization.startswith('Bearer ') else request.cookies.get('hickmet_session')
    try:result=await asyncio.to_thread(auth.session_user,token)
    except ValueError as exc:raise HTTPException(403,str(exc)) from None
    if not result:raise HTTPException(401,'Войдите через Telegram, чтобы продолжить')
    return result


def signed_in(request,person):
    token=auth.new_session(person)
    response=JSONResponse({'user':person,'session_token':token})
    secure=request.url.scheme=='https' or os.getenv('WEBAPP_URL','').startswith('https://')
    # Bearer auth also supports Telegram Web on browsers that block third-party cookies.
    response.set_cookie('hickmet_session',token,httponly=True,secure=secure,samesite='lax',max_age=86400)
    return response


async def bot_username():
    global _username
    if not _username:_username=os.getenv('BOT_USERNAME') or (await bot.get_me(request_timeout=15)).username
    return _username


@app.get('/health')
def health():return {'status':'ok'}


@app.get('/api/config')
async def config():
    try:name=await bot_username()
    except Exception:name=os.getenv('BOT_USERNAME','')
    return {'bot_username':name,'webapp_url':os.getenv('WEBAPP_URL',''),'brand':'Hickmet'}


class InitData(BaseModel):init_data:str=Field(min_length=1,max_length=16384)
class Poll(BaseModel):challenge:str=Field(max_length=80);secret:str=Field(max_length=100)


@app.post('/api/auth/telegram')
async def telegram_auth(data:InitData,request:Request):
    try:person=auth.verify_init_data(data.init_data)
    except ValueError as exc:raise HTTPException(401,str(exc)) from None
    return signed_in(request,person)


@app.post('/api/auth/challenge')
async def challenge():
    name=await bot_username();key,secret=await asyncio.to_thread(auth.new_challenge)
    return {'challenge':key,'secret':secret,'telegram_url':f'https://t.me/{name}?start=web_{key}','expires_in':300}


@app.post('/api/auth/poll')
async def poll(data:Poll,request:Request):
    person=await asyncio.to_thread(auth.consume_challenge,data.challenge,data.secret)
    return signed_in(request,person) if person else {'pending':True}


@app.get('/api/me')
async def me(person=Depends(user)):return {'user':person}


@app.post('/api/auth/logout')
async def logout(request:Request):
    token=request.headers.get('authorization','').removeprefix('Bearer ') or request.cookies.get('hickmet_session')
    if token:
        with auth.database() as db:db.execute('DELETE FROM sessions WHERE token=?',(auth.digest(token),))
    response=JSONResponse({'ok':True});response.delete_cookie('hickmet_session');return response


def refresh_catalog(force=False):
    global _refreshed
    with settings._lock:
        if force or not settings.PALM_SHEETS or time.monotonic()-_refreshed>300:
            settings.refresh_sheets();_refreshed=time.monotonic()
        months='January February March April May June July August September October November December'.split()
        keys=sorted(settings.PALM_SHEETS,key=lambda k:(int(k.split()[-1]),months.index(k.split()[0])))
        return keys


@app.get('/api/catalog')
async def catalog(refresh:bool=False,person=Depends(user)):
    try:return {'months':await asyncio.to_thread(refresh_catalog,refresh)}
    except Exception:
        logger.exception('Google catalog unavailable');raise HTTPException(503,'Не удалось прочитать Google Sheets. Можно создать ваучер вручную.') from None


@app.get('/api/sheets')
async def sheets(month:str,include_past:bool=False,person=Depends(user)):
    await asyncio.to_thread(refresh_catalog)
    if month not in settings.PALM_SHEETS:raise HTTPException(404,'Месяц не найден')
    def load():
        with settings._lock:return get_palm_sheet_names(month,include_past=include_past)
    return {'sheets':await asyncio.to_thread(load)}


def snapshot(month,title):
    with settings._lock:
        if month not in settings.PALM_SHEETS:raise ValueError('Месяц не найден. Обновите таблицы.')
        ss=settings.get_google_client().open_by_key(settings.PALM_SHEETS[month])
        ws=find_worksheet_by_title(ss,title);rows=ws.get_all_values()
        class Snapshot:
            def get_all_values(self):return rows
        result=Snapshot();result.title=ws.title;result.spreadsheet=ss
        return result


@app.get('/api/packages')
async def packages(month:str,sheet:str,person=Depends(user)):
    def load():
        ws=snapshot(month,sheet);result=[]
        for p in find_palm_packages(ws):
            v=collect_voucher_by_package(ws,p['row']);errors=voucher_errors(v)
            result.append({'row':p['row'],'title':p['title'],'people':len(v['_people_flat']),
                           'rooms':len(v['room_groups']),'ready':not errors,'warnings':v.get('warnings',[])})
        return result
    return {'packages':await asyncio.to_thread(load)}


class PackageSelection(BaseModel):
    month:str=Field(max_length=80)
    sheet:str=Field(max_length=300)
    row:int=Field(ge=0)
    title:str=Field(max_length=500)


@app.post('/api/package')
async def select_package(data:PackageSelection,person=Depends(user)):
    def load():
        ws=snapshot(data.month,data.sheet)
        selected=next((p for p in find_palm_packages(ws) if p['row']==data.row and p['title']==data.title),None)
        if not selected:raise ValueError('Пакет изменился. Обновите список и выберите его заново.')
        return collect_voucher_by_package(ws,data.row)
    v=await asyncio.to_thread(load)
    return {'voucher':v,'title':data.title,'errors':voucher_errors(v)}


@app.get('/api/designs/{index}')
async def design(index:int):
    if index not in range(3):raise HTTPException(404)
    return FileResponse(AVAILABLE_BACKGROUNDS[index],media_type='image/png',headers={'Cache-Control':'public, max-age=86400'})


@app.post('/api/preview')
async def preview(data:GenerateRequest,person=Depends(user)):
    def render():
        v=service.prepared(data);room=v['people']['rooms'][0]
        payload=base_payload_from(v);payload['pilgrims']=room['people']
        from pligrim_bot.core.parsers.people_parser import human_room
        for i in (1,2):
            if payload.get(f'city{i}'):payload[f'room{i}']=human_room(room['kind'])
        png=render_voucher_page1_png(payload)
        try:
            from PIL import Image
            with Image.open(png) as image:
                image.thumbnail((700,1100));buf=io.BytesIO();image.convert('RGB').save(buf,'JPEG',quality=85)
            return base64.b64encode(buf.getvalue()).decode()
        finally:Path(png).unlink(missing_ok=True)
    return {'image':'data:image/jpeg;base64,'+await asyncio.to_thread(render),'pages':3 if data.flight else 2}


@app.post('/api/jobs')
async def create(data:GenerateRequest,person=Depends(user)):
    key,created=await asyncio.to_thread(service.create_job,person['id'],data)
    if created:service.launch_job(key,person['id'],data)
    return {'id':key}


@app.get('/api/jobs/{key}')
async def job_status(key:str,person=Depends(user)):
    job=await asyncio.to_thread(service.get_job,key,person['id'])
    if not job:raise HTTPException(404,'Документы не найдены')
    return {'id':key,'status':job['status'],'sent':job['sent'],'error':job['error'],
            'files':[{'name':f['name'],'pages':f['pages'],'download':f'/api/jobs/{key}/files/{i}'} for i,f in enumerate(job['files'])],
            'archive':f'/api/jobs/{key}/download' if job['files'] else None}


@app.post('/api/jobs/{key}/retry')
async def retry(key:str,person=Depends(user)):
    await service.retry_delivery(key,person['id']);return {'ok':True}


class DownloadLink(BaseModel):
    index:int=Field(default=-1,ge=-1)


@app.post('/api/jobs/{key}/download-link')
async def native_download_link(key:str,data:DownloadLink,person=Depends(user)):
    import secrets
    job=await asyncio.to_thread(service.get_job,key,person['id'])
    if not job or not job['files'] or data.index>=len(job['files']):raise HTTPException(404)
    grant=secrets.token_urlsafe(32)
    with auth.database() as db:
        db.execute('DELETE FROM downloads WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO downloads VALUES(?,?,?,?,?)',(auth.digest(grant),key,person['id'],data.index,time.time()+90))
    origin=os.getenv('WEBAPP_URL','').rstrip('/')
    if not origin.startswith('https://'):raise HTTPException(400,'Для скачивания внутри Telegram нужен HTTPS')
    name='Hickmet_vouchers.zip' if data.index==-1 else job['files'][data.index]['name']
    return {'url':f'{origin}/api/download/{grant}','file_name':name}


@app.api_route('/api/download/{grant}',methods=['GET','HEAD'])
async def native_download(grant:str,request:Request):
    with auth.database() as db:
        row=db.execute('SELECT * FROM downloads WHERE token=? AND expires>?',(auth.digest(grant),time.time())).fetchone()
        if not row:raise HTTPException(410,'Ссылка для скачивания устарела. Нажмите «Скачать» ещё раз.')
        # Telegram's downloader may retry or request byte ranges within this window.
    job=await asyncio.to_thread(service.get_job,row['job'],row['owner'])
    if not job:raise HTTPException(410)
    index=row['file_index']
    if index==-1:path=auth.state_dir()/'jobs'/job['id']/'vouchers.zip';name='Hickmet_vouchers.zip';media='application/zip'
    else:path=Path(job['files'][index]['path']);name=job['files'][index]['name'];media='application/pdf'
    if not path.exists():raise HTTPException(410)
    return FileResponse(path,media_type=media,filename=name,headers={'Access-Control-Allow-Origin':'https://web.telegram.org'})


@app.get('/api/jobs/{key}/download')
async def download(key:str,person=Depends(user)):
    job=await asyncio.to_thread(service.get_job,key,person['id'])
    if not job or not job['files']:raise HTTPException(404)
    path=auth.state_dir()/'jobs'/job['id']/'vouchers.zip'
    if not path.exists():raise HTTPException(410,'Срок хранения файлов истёк')
    return FileResponse(path,media_type='application/zip',filename='Hickmet_vouchers.zip')


@app.get('/api/jobs/{key}/files/{index}')
async def download_one(key:str,index:int,person=Depends(user)):
    job=await asyncio.to_thread(service.get_job,key,person['id'])
    if not job or not 0<=index<len(job['files']):raise HTTPException(404)
    file=job['files'][index]
    if not Path(file['path']).exists():raise HTTPException(410,'Срок хранения файла истёк')
    return FileResponse(file['path'],media_type='application/pdf',filename=file['name'])


@app.get('/assets/brand-font.ttf')
async def font():return FileResponse(TTF_REGULAR,media_type='font/ttf',headers={'Cache-Control':'public, max-age=86400'})

app.mount('/assets',StaticFiles(directory=STATIC/'assets'),name='assets')


@app.get('/')
async def index():return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-cache'})


@app.get('/app.js')
async def javascript():return FileResponse(STATIC/'app.js',media_type='application/javascript')


@app.get('/style.css')
async def css():return FileResponse(STATIC/'style.css',media_type='text/css')
