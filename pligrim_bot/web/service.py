import asyncio
import json
import logging
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from aiogram.types import FSInputFile
from pligrim_bot.config.constants import bot
from pligrim_bot.core.voucher.builder import base_payload_from,ensure_chronological_city_order
from pligrim_bot.core.voucher.render import render_voucher_page1_png,build_voucher_pdf,build_filename_from_payload
from pligrim_bot.core.voucher.validation import require_valid_voucher
from pligrim_bot.core.parsers.people_parser import human_room
from .auth import database,state_dir

logger=logging.getLogger(__name__)
TASKS=set()


def prepared(request):
    v=request.voucher.model_dump()
    v['people']['flat']=[n for r in v['people']['rooms'] for n in r['people']]
    for room in v['people']['rooms']:room['count']=len(room['people'])
    ensure_chronological_city_order(v);require_valid_voucher(v)
    return v


def create_job(owner,request):
    prepared(request)
    key=uuid.uuid4().hex
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT id FROM jobs WHERE owner=? AND request_key=?',(owner,request.request_id)).fetchone()
        if existing:return existing['id'],False
        active=db.execute("SELECT COUNT(*) FROM jobs WHERE owner=? AND status IN ('queued','rendering','sending')",(owner,)).fetchone()[0]
        if active>=2:raise ValueError('Уже формируются два набора документов. Дождитесь завершения.')
        db.execute('INSERT INTO jobs(id,owner,request_key,status,payload,created) VALUES(?,?,?,?,?,?)',(key,owner,request.request_id,'queued',request.model_dump_json(),time.time()))
    return key,True


def get_job(key,owner):
    with database() as db:
        row=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(key,owner)).fetchone()
    if not row or row['created']<time.time()-86400:return None
    result=dict(row);result['files']=json.loads(result['files'])
    return result


def update_job(key,**fields):
    if not fields or set(fields)-{'status','files','sent','error'}:raise ValueError('Invalid job update')
    if 'files' in fields:fields['files']=json.dumps(fields['files'],ensure_ascii=False)
    with database() as db:
        db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),key))


def render_documents(key,request):
    voucher=prepared(request)
    folder=state_dir()/'jobs'/key;folder.mkdir(parents=True,exist_ok=True)
    files=[]
    try:
        for index,room in enumerate(voucher['people']['rooms'],1):
            payload=base_payload_from(voucher);payload['pilgrims']=room['people']
            for slot in (1,2):
                if payload.get(f'city{slot}'):payload[f'room{slot}']=human_room(room['kind'])
            png=render_voucher_page1_png(payload)
            try:
                path=folder/f'{index}.pdf'
                build_voucher_pdf(png,payload.get('city1'),payload.get('transfer'),str(path),request.background,
                                  request.flight.model_dump(mode='json') if request.flight else None)
            finally:
                if os.path.exists(png):os.unlink(png)
            name=f'{index:02d}_{build_filename_from_payload(payload)}.pdf'
            files.append({'name':name,'path':str(path),'pages':3 if request.flight else 2,'people':len(room['people'])})
        with zipfile.ZipFile(folder/'vouchers.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for file in files:archive.write(file['path'],arcname=file['name'])
    except Exception:
        shutil.rmtree(folder,ignore_errors=True);raise
    return files


async def run_job(key,owner,request):
    try:
        update_job(key,status='rendering')
        files=await asyncio.to_thread(render_documents,key,request)
        update_job(key,files=files,status='sending' if request.deliver_to_chat else 'done')
        if request.deliver_to_chat:
            for i,file in enumerate(files,1):
                await bot.send_document(chat_id=owner,document=FSInputFile(file['path'],filename=file['name']),
                                        caption=f'{request.title}\nВаучер {i} из {len(files)} · {file["people"]} чел.'[:1000])
                update_job(key,sent=i)
                if i<len(files):await asyncio.sleep(.08)
            update_job(key,status='done')
    except Exception as exc:
        logger.exception('Voucher job failed: %s',key)
        text=str(exc) if isinstance(exc,ValueError) else 'Не удалось завершить отправку. Готовые PDF можно скачать; повторите отправку оставшихся документов.'
        update_job(key,status='failed',error=text[:500])


def launch_job(key,owner,request):
    task=asyncio.create_task(run_job(key,owner,request));TASKS.add(task);task.add_done_callback(TASKS.discard)


async def retry_delivery(key,owner):
    job=get_job(key,owner)
    if not job or job['status']!='failed' or not job['files']:raise ValueError('Нет документов для повторной отправки')
    with database() as db:
        changed=db.execute("UPDATE jobs SET status='sending',error=NULL WHERE id=? AND owner=? AND status='failed'",(key,owner)).rowcount
    if not changed:raise ValueError('Отправка уже выполняется')
    async def send():
        try:
            for i,file in enumerate(job['files'][job['sent']:],job['sent']+1):
                await bot.send_document(chat_id=owner,document=FSInputFile(file['path'],filename=file['name']))
                update_job(key,sent=i)
            update_job(key,status='done')
        except Exception:
            logger.exception('Retry delivery failed');update_job(key,status='failed',error='Не удалось отправить документ. Проверьте, что бот не заблокирован, и повторите попытку.')
    task=asyncio.create_task(send());TASKS.add(task);task.add_done_callback(TASKS.discard)


def cleanup():
    with database() as db:
        old=db.execute('SELECT id FROM jobs WHERE created<?',(time.time()-86400,)).fetchall()
        for row in old:
            if len(row['id'])==32 and all(c in '0123456789abcdef' for c in row['id']):shutil.rmtree(state_dir()/'jobs'/row['id'],ignore_errors=True)
        db.execute('DELETE FROM jobs WHERE created<?',(time.time()-86400,))
        db.execute("UPDATE jobs SET status='failed',error='Сервис перезапущен. Скачайте готовые файлы или создайте документы заново.' WHERE status IN ('queued','rendering','sending')")
