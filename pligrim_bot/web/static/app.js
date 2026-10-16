'use strict';
const $=(selector,root=document)=>root.querySelector(selector);
const iconPaths={arrow:'M4 12h16m-6-6 6 6-6 6',back:'M20 12H4m6-6-6 6 6 6',user:'M20 21v-2a7 7 0 0 0-14 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',document:'M14 2H5v20h14V7zM14 2v6h5M8 12h8M8 16h8',edit:'m16 3 5 5-12 12-6 1 1-6zM13 6l5 5',shield:'m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6zm-4 10 3 3 5-6',plane:'m22 2-7 20-4-9-9-4zm0 0L11 13',check:'m5 12 4 4L20 5',calendar:'M4 5h16v16H4zM8 2v6m8-6v6M4 11h16',people:'M16 21v-2a5 5 0 0 0-10 0v2M11 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M19 8a3 3 0 0 1 0 6m3 7v-2a5 5 0 0 0-3-4',pin:'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0M15 10a3 3 0 1 0-6 0 3 3 0 0 0 6 0',download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',plus:'M12 5v14M5 12h14',trash:'M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',refresh:'M20 7a9 9 0 1 0 1 10M20 2v6h-6',lock:'M5 10h14v12H5zM8 10V6a4 4 0 0 1 8 0v4',chevron:'m9 5 7 7-7 7',close:'m6 6 12 12M6 18 18 6',globe:'M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18'};
const icon=(name)=>`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPaths[name]||iconPaths.document}"/></svg>`;
const esc=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const steps=['Пакет','Паломники','Проживание','Услуги','Перелёт','Проверка'];
const monthsRu=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
const monthsEn=['January','February','March','April','May','June','July','August','September','October','November','December'];
const monthLabel=m=>{const match=/^([A-Za-z]+) (20\d{2})$/.exec(m);return match&&monthsEn.includes(match[1])?`${monthsRu[monthsEn.indexOf(match[1])]} ${match[2]}`:m;};
const tg=window.Telegram?.WebApp;
let token='',loginTimer=null,loginExpires=0,resumeAction=null,toastTimer=null,jobTimer=null,previewCounter=0;
const defaults=()=>({city1:'Madinah',hotel1:'',dates1:'',checkin1:'16:00',city2:'Makkah',hotel2:'',dates2:'',checkin2:'16:00',service:'Виза и страховка',transfer:'Автобус',meal:'Завтрак и ужин',guide:'Групповой гид',excursions:'Мекка, Медина',tech_guide:'+966 56 328 0325',people:{rooms:[]}});
const serviceFields=[['service','Сервис','Виза и страховка'],['transfer','Трансфер','Поезд, Автобус'],['meal','Питание','Завтрак и ужин'],['guide','Сопровождение','Групповой гид'],['excursions','Экскурсии','Мекка, Медина']];
const serviceIncluded=value=>Boolean(String(value||'').trim())&&!/^(?:не включ[её]н[аоы]?|не предусмотрен[аоы]?|нет|not included|no|[-—–])$/i.test(String(value).trim());
const roomKinds=[{value:'SGL',label:'SGL · Одноместный',shortLabel:'SGL'},{value:'DBL',label:'DBL · Двухместный',shortLabel:'DBL'},{value:'TWIN',label:'TWIN · Отдельные кровати',shortLabel:'TWIN'},{value:'TRPL',label:'TRPL · Трёхместный',shortLabel:'TRPL'},{value:'QUAD',label:'QUAD · Четырёхместный',shortLabel:'QUAD'}];
const programDesigns=[
  {label:'Медина · автобус',description:'Первый город — Медина. Между Мединой и Меккой — автобус.'},
  {label:'Медина · поезд',description:'Прилёт в Джидду → Медина → Мекка на поезде → вылет из Джидды.'},
  {label:'Мекка · первый город',description:'Сначала проживание в Мекке, затем — в Медине.'}
];
function recommendedDesign(){
  const v=state.voucher,[first]=splitDates(v.dates1),[second]=splitDates(v.dates2);
  const city=String(state.secondCity&&first&&second&&second<first?v.city2:v.city1).trim().toLowerCase();
  if(/^(?:makkah|makka|mecca|mekka|мекка|макка)$/.test(city))return 2;
  if(!/^(?:madinah|medinah|medina|madina|медина|мадина)$/.test(city)||!serviceIncluded(v.transfer))return null;
  if(/поезд|train|жд/i.test(v.transfer))return 1;
  return /автобус|bus/i.test(v.transfer)?0:null;
}
function roomAdultLimit(room){return Math.min(4,room.people.length,({SGL:1,DBL:2,TWIN:2,TRPL:3,QUAD:4}[room.kind]||4));}
function roomCountLabel(room){return `Всего: ${room.people.length} · взрослых: ${room.adults} · детей: ${Math.max(0,room.people.length-room.adults)}`;}
function syncRoomCounts(index){
  const room=state.voucher.people.rooms[index];if(!room)return;
  const output=$(`[data-room-adults="${index}"]`),count=$(`[data-room-count="${index}"]`);
  if(output)output.textContent=room.adults;if(count)count.textContent=roomCountLabel(room);
  const minus=$(`[data-action="adult-minus"][data-index="${index}"]`),plus=$(`[data-action="adult-plus"][data-index="${index}"]`);
  if(minus)minus.disabled=room.adults<=0;if(plus)plus.disabled=room.adults>=roomAdultLimit(room);
}
function stepAdults(index,delta){
  const room=state.voucher.people.rooms[index];if(!room)return;
  if(delta>0&&room.adults>=roomAdultLimit(room))return;
  room.adults=delta<0?Math.max(0,room.adults-1):Math.min(roomAdultLimit(room),room.adults+1);
  dirty();syncRoomCounts(index);
}
let serviceDrafts={};
const legDefault=()=>({airline:'',number:'',origin:'',destination:'',departure_date:'',arrival_date:'',departure_time:'',arrival_time:''});
const state={user:null,config:{},view:'home',step:0,mode:'package',voucher:defaults(),title:'Индивидуальный ваучер',months:[],sheets:[],packages:[],month:'',sheet:'',selectedRow:null,includePast:false,loading:'',error:'',warnings:[],secondCity:true,flightEnabled:false,returnFlight:true,flight:{outbound:legDefault(),inbound:legDefault()},background:0,preview:'',deliver:true,requestId:crypto.randomUUID().replaceAll('-',''),job:null};

async function api(path,options={}){
  const headers={...(options.body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:`Bearer ${token}`}:{ }),...options.headers};
  let response;
  try{response=await fetch(path,{...options,headers,credentials:'same-origin'});}catch{throw new Error('Нет соединения с сервером. Проверьте интернет и попробуйте ещё раз.');}
  const type=response.headers.get('content-type')||'';
  const data=type.includes('json')?await response.json():null;
  if(!response.ok){
    if(response.status===401){state.user=null;updateAccount();}
    const detail=data?.detail;
    let text=Array.isArray(detail)?detail.map(e=>e.msg.replace('Value error, ','')).join('\n'):detail;
    throw new Error(text||(response.status===503?'Google Sheets временно недоступны. Можно создать ваучер вручную.':'Не удалось выполнить действие. Попробуйте ещё раз.'));
  }
  return data;
}
const post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data??{})});
function notify(text){clearTimeout(toastTimer);$('#toast').textContent=text;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,5000);}
function setError(text){state.error=text;const target=$('#step-error');if(target){target.innerHTML=`<div class="notice error form-error" role="alert">${esc(text).replaceAll('\n','<br>')}</div>`;target.focus({preventScroll:true});target.scrollIntoView({block:'nearest',behavior:'smooth'});}else notify(text);}
function dirty(){previewCounter++;state.preview='';state.requestId=crypto.randomUUID().replaceAll('-','');}
function updateAccount(){
  $('#account-name').textContent=state.user?(state.user.first_name||'Мой кабинет'):'Войти через Telegram';
  $('#account-icon').innerHTML=icon('user');
  let logout=$('#logout');if(!logout){logout=document.createElement('button');logout.id='logout';logout.className='logout';logout.dataset.action='logout';logout.textContent='Выйти';$('.header-inner').append(logout);}
  logout.hidden=!state.user;
}
function home(){
  if(jobTimer&&state.job&&['queued','rendering','sending'].includes(state.job.status)){notify('Документы формируются. Они будут доступны в разделе «Мои документы».');}
  state.view='home';render();tg?.BackButton?.hide();tg?.disableClosingConfirmation?.();window.scrollTo({top:0,behavior:'smooth'});
}
function render(){
  if(state.view==='home')renderHome();else if(state.view==='history')renderHistory();else if(state.view==='job')renderJob();else renderWizard();
}
function wizardSteps(){return state.mode==='flight'?[0,4,5]:[0,1,2,3,4,5];}
async function showHistory(){
  if(!state.user){resumeAction=showHistory;await showLogin();return;}
  const owner=state.user.id,history=await api('/api/jobs');if(state.user?.id!==owner)return;state.history=history.jobs;state.view='history';render();tg?.BackButton?.show();window.scrollTo(0,0);
}
function renderHistory(){
  const statuses={queued:'В очереди',rendering:'Формируется',sending:'Отправляется',done:'Готово',failed:'Нужно внимание'};
  $('#main').innerHTML=`<section class="container workspace"><div class="section-heading"><div><h1>Мои документы</h1><p>Последние 50 оформлений за 24 часа. Файлы в Telegram сохраняются в чате.</p></div></div><div class="history-list">${(state.history||[]).map(job=>`<button class="history-item" data-action="open-job" data-job="${esc(job.id)}"><span>${icon(job.document_type==='flight'?'plane':'document')}</span><span><strong>${esc(job.title)}</strong><small>${new Date(job.created*1000).toLocaleString('ru-RU')} · ${job.files} PDF · ${statuses[job.status]||job.status}</small></span>${icon('chevron')}</button>`).join('')||'<div class="notice">Документов пока нет. Создайте первый ваучер.</div>'}</div><button class="button secondary" data-action="home">${icon('back')}На главную</button></section>`;
}
async function openJob(key){
  clearTimeout(jobTimer);const owner=state.user?.id,job=await api(`/api/jobs/${key}`);if(state.user?.id!==owner)return;state.job=job;state.deliver=job.deliver_to_chat;state.view='job';render();tg?.BackButton?.show();window.scrollTo(0,0);if(['queued','rendering','sending'].includes(job.status))await pollJob();
}
function renderFlightSource(){
  return `<h2 id="step-heading">Ваучер на перелёт</h2><p class="panel-intro">Отдельный PDF с рейсами. Данные можно загрузить из расписания или заполнить вручную.</p><div class="selection-tabs"><button data-action="flight-source-sheet" class="${state.flightSource==='sheet'?'selected':''}">Из Google Sheets</button><button data-action="flight-source-manual" class="${state.flightSource==='manual'?'selected':''}">Вручную</button></div>${field('Название документа',state.title,'title',{full:true,maxlength:200})}${state.flightSource==='sheet'?`<div class="form-grid catalog-filters">${selectField('Месяц / таблица',state.month,'month',state.months.map(m=>({value:m,label:monthLabel(m)})),'Выберите таблицу')}${selectField('Группа / лист',state.sheet,'sheet',state.sheets,'Выберите лист')}</div><button class="button secondary small" data-action="refresh-catalog">${icon('refresh')}Обновить таблицы</button>${renderScheduleOptions(false)}`:'<div class="notice">На следующем шаге укажите авиакомпанию, маршрут, даты и время.</div>'}`;
}
function renderScheduleOptions(attached){
  return `<div class="schedule-options">${state.loading==='flights'?'<p class="loading-label"><span class="spinner"></span>Читаем расписание…</p>':''}${(state.flightOptions||[]).map(option=>`<button class="package-option ${state.flightOptionId===option.id?'selected':''}" data-action="${attached?'attach-schedule-flight':'select-schedule-flight'}" data-id="${esc(option.id)}"><h3>${esc(option.title)}</h3><p>${esc(option.label)}</p>${icon(state.flightOptionId===option.id?'check':'plane')}</button>`).join('')}${state.sheet&&!state.loading&&!(state.flightOptions||[]).length?'<p class="hint">Если подходящих рейсов нет, заполните перелёт вручную.</p>':''}</div>`;
}
async function loadScheduledFlights(){
  if(!state.month||!state.sheet)return;const month=state.month,sheet=state.sheet,mode=state.mode;state.loading='flights';state.flightOptions=[];state.flightOptionId=null;state.error='';render();
  try{const result=await api(`/api/flight-options?${new URLSearchParams({month,sheet})}`);if(state.month!==month||state.sheet!==sheet||state.mode!==mode)return;state.flightOptions=result.options;state.warnings=[result.notice];}
  catch(e){if(state.month===month&&state.sheet===sheet&&state.mode===mode)state.error=e.message;}finally{if(state.month===month&&state.sheet===sheet&&state.mode===mode){state.loading='';render();}}
}
function selectScheduledFlight(id,attached=false){
  const option=(state.flightOptions||[]).find(item=>item.id===id);if(!option)return;
  state.flight=structuredClone(option.flight);state.flightEnabled=true;state.returnFlight=Boolean(option.flight.inbound);state.flightOptionId=id;if(!attached)state.title=option.title.slice(0,200);
  dirty();render();notify('Рейсы загружены. Проверьте аэропорты, даты прилёта и местное время.');
}
function renderFlightReview(){
  const legs=[['Туда',state.flight.outbound],...(state.returnFlight?[['Обратно',state.flight.inbound]]:[])];
  return `<h2 id="step-heading">Проверка перелёта</h2><p class="panel-intro">Будет создан отдельный одностраничный PDF.</p><div class="review-line"><span>Документ</span><strong>${esc(state.title)}</strong></div>${legs.map(([label,leg])=>`<div class="flight-review"><h3>${label} · ${esc(leg.airline)} ${esc(leg.number)}</h3><p>${esc(leg.origin)} → ${esc(leg.destination)}</p><p>Вылет: ${esc(leg.departure_date)} ${esc(leg.departure_time)}<br>Прилёт: ${esc(leg.arrival_date)} ${esc(leg.arrival_time)}</p></div>`).join('')}<div class="preview-box" id="preview-box">${state.preview?`<img src="${state.preview}" alt="Предпросмотр ваучера на перелёт">`:'<span class="spinner"></span>'}</div><div class="deliver-choice"><label class="checkline"><input type="checkbox" data-bind="deliver" ${state.deliver?'checked':''}>Отправить готовый PDF в мой чат Telegram</label></div>`;
}
function renderHome(){
  $('#main').innerHTML=`<section class="container workspace app-home"><div class="section-heading"><div><h1>Ваучеры</h1><p>Выберите пакет или заполните данные вручную.</p></div></div>
  <div class="action-grid"><button class="action-card" data-action="start-package"><span class="card-content"><span class="card-number">01 / ИЗ ПАКЕТА</span><span class="card-title">Ваучеры<br>для паломников</span><span class="card-description">Выберите группу, проверьте данные и получите PDF в Telegram.</span><span class="card-link">Выбрать пакет ${icon('arrow')}</span></span><span class="card-art" aria-hidden="true"><span class="arch"></span><span class="paper-art back"></span><span class="paper-art"><b>HICKMET</b><i></i><i></i><i></i><i></i><i></i></span></span></button>
  <button class="action-card manual" data-action="start-manual"><span class="card-content"><span class="card-number">02 / ВРУЧНУЮ</span><span class="card-title">Индивидуальный<br>ваучер</span><span class="card-description">Добавьте паломников, отели и нужные услуги самостоятельно.</span><span class="card-link">Создать ваучер ${icon('arrow')}</span></span><span class="card-art" aria-hidden="true">${icon('edit')}</span></button><button class="action-card flight-card" data-action="start-flight"><span class="card-content"><span class="card-number">03 / ПЕРЕЛЁТ</span><span class="card-title">Ваучер на перелёт</span><span class="card-description">Загрузите рейсы из расписания или введите данные вручную.</span><span class="card-link">Оформить перелёт ${icon('arrow')}</span></span><span class="card-art" aria-hidden="true">${icon('plane')}</span></button></div><div class="home-tools"><button class="button secondary" data-action="history">${icon('document')}Мои документы</button></div><div class="home-delivery">${icon('document')}PDF придут в ваш чат Telegram. Данные перелёта можно включить или пропустить.</div></section>`;
}
async function start(mode){
  if(!state.user){resumeAction=()=>start(mode);await showLogin();return;}
  serviceDrafts={};clearTimeout(jobTimer);
  Object.assign(state,{view:'wizard',step:0,mode,voucher:defaults(),title:mode==='flight'?'Ваучер на перелёт':mode==='manual'?'Индивидуальный ваучер':'',selectedRow:null,warnings:[],error:'',loading:'',secondCity:true,flightEnabled:mode==='flight',flight:{outbound:legDefault(),inbound:legDefault()},background:0,preview:'',job:null,editSource:null,flightSource:'sheet',flightOptions:[],flightOptionId:null});
  dirty();render();window.scrollTo(0,0);tg?.enableClosingConfirmation?.();tg?.BackButton?.show();
  if(mode==='package'||mode==='flight')await loadCatalog();
}
function field(label,value,bind,options={}){
  const attrs=`data-bind="${bind}" ${options.required?'required':''} ${options.disabled?'disabled':''} ${options.min?`min="${esc(options.min)}"`:''} ${options.max?`max="${esc(options.max)}"`:''}`;
  return `<label class="field ${options.full?'full':''} ${options.className||''}"><span>${esc(label)}${options.required?' *':''}</span><input type="${options.type||'text'}" value="${esc(value)}" placeholder="${esc(options.placeholder||'')}" ${attrs} ${options.maxlength?`maxlength="${options.maxlength}"`:''}>${options.hint?`<small class="hint">${esc(options.hint)}</small>`:''}</label>`;
}
function selectField(label,value,bind,items,placeholder,searchable=true){
  const options=items.map(i=>typeof i==='string'?{value:i,label:i}:i),selected=options.find(i=>i.value===value);
  return `<div class="field catalog-field"><span id="picker-label-${bind}">${esc(label)}</span><details class="catalog-picker"><summary aria-labelledby="picker-label-${bind} picker-value-${bind}"><span class="picker-symbol">${icon(bind==='month'?'calendar':'people')}</span><span id="picker-value-${bind}" class="${selected?'':'picker-placeholder'}">${esc(selected?.shortLabel||selected?.label||placeholder)}</span>${icon('chevron')}</summary><div class="picker-menu">${searchable?`<div class="picker-search">${icon('globe')}<input type="search" data-picker-search placeholder="Найти ${bind==='month'?'таблицу':'группу'}" aria-label="Поиск: ${esc(label)}" autocomplete="off"></div>`:''}<div class="picker-options" role="listbox" aria-labelledby="picker-label-${bind}">${options.map(item=>`<button type="button" class="picker-option" role="option" aria-selected="${value===item.value}" data-action="picker-select" data-picker-bind="${bind}" data-picker-value="${esc(item.value)}" ${state.loading?'disabled':''}><span>${esc(item.label)}</span>${value===item.value?icon('check'):''}</button>`).join('')}</div><p class="picker-empty" ${options.length?'hidden':''}>${state.loading?'Загружаем список…':'Ничего не найдено'}</p></div></details></div>`;
}
function summary(){
  if(state.mode==='flight')return `<aside class="summary-card"><div class="summary-top"><h3>${esc(state.title)}</h3></div><div class="summary-details"><p>Ваучер на перелёт · 1 страница</p><p>${esc(state.flight.outbound.origin||'Откуда')} → ${esc(state.flight.outbound.destination||'Куда')}</p><p>${state.returnFlight?'С обратным рейсом':'Только рейс туда'}</p></div></aside>`;
  const rooms=state.voucher.people.rooms.filter(r=>r.selected!==false);const people=rooms.reduce((sum,r)=>sum+r.people.length,0);
  return `<aside class="summary-card" aria-label="Сводка ваучера"><div class="summary-top"><p class="eyebrow">ВАШЕ ПУТЕШЕСТВИЕ</p><h3>${esc(state.title||'Новый ваучер')}</h3></div><div class="summary-details"><div class="summary-row"><span>Оформление</span><strong>${state.mode==='manual'?'Индивидуальное':'Из пакета'}</strong></div><div class="summary-row"><span>Паломники</span><strong id="summary-people">${people||'—'} чел.</strong></div><div class="summary-row"><span>Комнаты</span><strong id="summary-rooms">${rooms.length||'—'}</strong></div><div class="summary-divider"></div><div class="summary-row"><span>Маршрут</span><strong>${esc(state.voucher.city1||'—')}${state.secondCity?' → '+esc(state.voucher.city2||'—'):''}</strong></div><div class="summary-row"><span>Данные перелёта</span><strong>${state.flightEnabled?'Включены':'Не включены'}</strong></div><div class="summary-row"><span>Формат</span><strong>PDF · ${state.flightEnabled?3:2} страницы</strong></div><p class="summary-note">${icon('lock')}Готовые документы доступны вам на сайте и отправляются в ваш чат Telegram.</p></div><div class="summary-illustration" aria-hidden="true"><span class="paper-art"><b>HICKMET</b><i></i><i></i><i></i></span></div></aside>`;
}
function renderWizard(){
  const sequence=wizardSteps(),position=sequence.indexOf(state.step);
  const content=state.mode==='flight'&&state.step===0?renderFlightSource():[renderPackage,renderPeople,renderHotels,renderServices,renderFlight,renderReview][state.step]();
  $('#main').innerHTML=`<div class="container wizard"><div class="breadcrumbs"><button data-action="home">Документы</button><span>/</span><span>Новый ваучер</span></div><div class="wizard-title"><div><h1>${state.editSource?'Изменить ваучер':state.mode==='flight'?'Ваучер на перелёт':'Новый ваучер'}</h1><p>Проверьте данные перед отправкой.</p></div><span class="draft-tag">${state.mode==='flight'?'Перелёт':state.mode==='manual'?'Индивидуально':'Из пакета'}</span></div><ol class="steps" aria-label="Шаги оформления">${sequence.map((step,i)=>`<li class="step ${i===position?'active':i<position?'done':''}" ${i===position?'aria-current="step"':''}><span class="step-number">${i<position?'✓':String(i+1).padStart(2,'0')}</span>${state.mode==='flight'&&step===0?'Источник':steps[step]}</li>`).join('')}</ol><div class="wizard-layout"><div><section class="panel" aria-labelledby="step-heading">${state.editSource?'<div class="notice edit-notice">Редактируется выбранный ваучер. При отправке будет создан новый PDF только для указанных здесь паломников.</div>':''}<div id="step-error" tabindex="-1">${state.error?`<div class="notice error form-error" role="alert">${esc(state.error).replaceAll('\n','<br>')}</div>`:''}</div>${content}</section><div class="wizard-actions"><button class="button secondary" data-action="back">${icon('back')} ${state.step===0?'На главную':'Назад'}</button><span class="step-counter">Шаг ${position+1} из ${sequence.length}</span><button class="button primary" data-action="${state.step===5?'generate':'next'}" ${state.loading?'disabled':''}>${state.loading?'<span class="spinner"></span>':''}${state.step===5?(state.deliver?'Создать и отправить':'Создать PDF'):'Продолжить'} ${icon(state.step===5?'document':'arrow')}</button></div></div>${summary()}</div></div>`;
  $('.step.active')?.scrollIntoView({block:'nearest',inline:'center'});
}
function renderPackage(){
  const tabs=`<div class="selection-tabs" role="group" aria-label="Способ оформления"><button data-action="mode-package" class="${state.mode==='package'?'selected':''}" aria-pressed="${state.mode==='package'}">Из Google Sheets</button><button data-action="mode-manual" class="${state.mode==='manual'?'selected':''}" aria-pressed="${state.mode==='manual'}">Заполнить вручную</button></div>`;
  if(state.mode==='manual')return `<h2 id="step-heading">Индивидуальный ваучер</h2><p class="panel-intro">Создайте индивидуальный ваучер. Все детали можно будет проверить перед отправкой.</p>${tabs}${field('Название тура',state.title,'title',{full:true,placeholder:'Например, Семейная умра · октябрь',maxlength:200})}<div class="notice">На следующем шаге добавьте паломников и выберите размещение для каждой комнаты.</div>`;
  return `<div class="panel-heading"><div><h2 id="step-heading">Выберите пакет</h2><p class="panel-intro">Найдём ваше путешествие в рабочих таблицах.</p></div><button class="icon-button" data-action="refresh-catalog" aria-label="Обновить таблицы">${icon('refresh')}</button></div>${tabs}<div class="form-grid catalog-filters">${selectField('Месяц / таблица',state.month,'month',state.months.map(m=>({value:m,label:monthLabel(m)})),'Выберите месяц')}${selectField('Группа / лист',state.sheet,'sheet',state.sheets,'Выберите группу')}</div><label class="checkline catalog-history" ><input type="checkbox" data-bind="includePast" ${state.includePast?'checked':''}>Показать также прошедшие поездки</label>${state.loading?'<div class="loading-label"><span class="spinner"></span>Читаем рабочие таблицы…</div><div class="skeleton"></div>':''}<div class="package-list"><div class="package-list-header"><h3>${state.packages.length?`Пакетов в выбранной группе: ${state.packages.length}`:'Доступные пакеты'}</h3></div>${state.packages.map(p=>`<button class="package-option ${state.selectedRow===p.row?'selected':''}" data-action="select-package" data-row="${p.row}" aria-pressed="${state.selectedRow===p.row}"><h3>${esc(p.title)}</h3><p>${p.people} паломников · ${p.rooms} комнат · ${p.ready?'данные заполнены':'понадобится уточнить детали'}</p>${icon(state.selectedRow===p.row?'check':'chevron')}</button>`).join('')}${!state.packages.length&&!state.loading?`<div class="empty-state">${icon('calendar')}${state.sheet?'На этом листе пакеты не найдены. Можно выбрать другую группу или заполнить ваучер вручную.':'Выберите месяц и группу — здесь появятся ваши пакеты.'}</div>`:''}</div>${state.warnings.length?`<div class="notice">${state.warnings.map(esc).join('<br>')}</div>`:''}`;
}
function renderPeople(){
  const rooms=state.voucher.people.rooms;
  return `<div class="panel-heading"><div><h2 id="step-heading">Паломники</h2><p class="panel-intro">Одна комната — один ваучер. Выберите нужные комнаты и проверьте имена.</p></div></div>${!rooms.length?'<div class="notice">Добавьте первую комнату и впишите имена паломников.</div>':''}${rooms.length?`<div class="room-tools"><div><button class="button secondary small" data-action="select-all-rooms">Выбрать все</button><button class="button secondary small" data-action="clear-rooms">Снять все</button></div>${selectField('Размещение для выбранных','','all-room-kind',roomKinds,'Применить ко всем',false)}</div>`:''}${rooms.map((r,i)=>`
  <article class="room-card"><div class="room-heading"><label class="checkline"><input type="checkbox" data-room-select="${i}" ${r.selected!==false?'checked':''}><h3>Комната ${i+1}</h3></label><button class="icon-button" data-action="remove-room" data-index="${i}" aria-label="Удалить комнату ${i+1}">${icon('trash')}</button></div>
  <div class="room-fields"><label class="field people-names"><span>Имена паломников *</span><textarea data-room-names="${i}" wrap="off" rows="${Math.max(3,Math.min(10,r.people.length+1))}" spellcheck="false" autocapitalize="characters" placeholder="IVANOV IVAN&#10;IVANOVA ANNA" aria-label="Имена паломников комнаты ${i+1}">${esc(r.people.join('\n'))}</textarea><small class="hint">Каждое полное имя с новой строки, как в паспорте</small></label>
  ${selectField('Размещение *',r.kind,`room-kind-${i}`,roomKinds,'Выберите',false)}
  <div class="field adult-field"><span id="adults-label-${i}">Взрослых *</span><div class="adult-stepper" role="group" aria-labelledby="adults-label-${i}"><button type="button" data-action="adult-minus" data-index="${i}" aria-label="Уменьшить число взрослых в комнате ${i+1}" ${r.adults<=0?'disabled':''}>−</button><output data-room-adults="${i}" aria-live="polite">${r.adults}</output><button type="button" data-action="adult-plus" data-index="${i}" aria-label="Увеличить число взрослых в комнате ${i+1}" ${r.adults>=roomAdultLimit(r)?'disabled':''}>+</button></div></div>
  <p class="room-occupancy-note" data-room-count="${i}">${esc(roomCountLabel(r))}</p></div></article>`).join('')}<button class="button secondary small" data-action="add-room">${icon('plus')}Добавить комнату</button>`;
}
function splitDates(value){const parts=String(value||'').split(/\s*–\s*/);return [0,1].map(i=>{const date=(parts[i]||'').match(/\d{2}\/\d{2}\/\d{4}/)?.[0];return date?date.split('/').reverse().join('-'):'';});}
function dateToISO(value){const d=String(value||'').split('-');return d.length===3?`${d[2]}/${d[1]}/${d[0]}`:'';}
function cityForm(i){
  const v=state.voucher,[start,end]=splitDates(v[`dates${i}`]);
  return `<section class="city-section"><div class="city-heading"><h3>${icon('pin')}Город ${i}</h3></div><div class="form-grid">${field('Город',v[`city${i}`],`voucher.city${i}`,{required:true,placeholder:'Медина / Мекка',maxlength:80})}${field('Отель',v[`hotel${i}`],`voucher.hotel${i}`,{required:true,placeholder:'Название отеля',maxlength:300})}${field('Дата заезда',start||'',`dates.${i}.start`,{required:true,type:'date'})}${field('Дата выезда',end||'',`dates.${i}.end`,{required:true,type:'date'})}${field('Время заселения',v[`checkin${i}`],`voucher.checkin${i}`,{required:true,type:'time'})}<div class="field"><span>Продолжительность</span><div class="stay-value" id="nights-${i}" role="status">${nightsLabel(start,end)}</div></div></div></section>`;
}
function nightsLabel(start,end){if(!start||!end)return 'Выберите даты';const n=Math.round((Date.parse(end)-Date.parse(start))/86400000);return n<0?'Проверьте порядок дат':`${n} ${n%100>=11&&n%100<=14?'ночей':n%10===1?'ночь':n%10>=2&&n%10<=4?'ночи':'ночей'}`;}
function renderHotels(){return `<h2 id="step-heading">Проживание</h2><p class="panel-intro">Проверьте отели, даты и время заселения.</p>${cityForm(1)}<div class="city-section"><label class="checkline"><input type="checkbox" data-bind="secondCity" ${state.secondCity?'checked':''}>Добавить проживание во втором городе</label></div>${state.secondCity?cityForm(2):''}`;}
function renderServices(){const v=state.voucher;return `<h2 id="step-heading">Услуги</h2><p class="panel-intro">Отключите услуги, которые не входят в пакет. В ваучере будет указано «Не включено».</p><div class="service-grid">${serviceFields.map(([key,label,placeholder])=>{const included=serviceIncluded(v[key]);return `<section class="service-card ${included?'':'excluded'}"><div class="service-card-heading"><h3>${esc(label)}</h3><label class="checkline"><input type="checkbox" data-service-toggle="${key}" ${included?'checked':''} aria-label="${esc(label)}: включено">Включено</label></div>${field('Описание',included?v[key]:'Не включено',`voucher.${key}`,{placeholder,maxlength:300,disabled:!included})}</section>`;}).join('')}</div><div class="service-contact">${field('Контакт технического гида',v.tech_guide,'voucher.tech_guide',{placeholder:'+966 …',maxlength:120,full:true})}</div>`;}
function flightForm(key,label){const leg=state.flight[key];return `<section class="flight-block"><h3>${icon('plane')}${label}</h3><div class="form-grid">${field('Авиакомпания',leg.airline,`flight.${key}.airline`,{required:true,placeholder:'Air Astana / SCAT / Turkish Airlines',maxlength:80})}${field('Номер рейса',leg.number,`flight.${key}.number`,{required:true,placeholder:'KC 263',maxlength:30})}${field('Откуда',leg.origin,`flight.${key}.origin`,{required:true,placeholder:'Алматы · ALA',maxlength:80})}${field('Куда',leg.destination,`flight.${key}.destination`,{required:true,placeholder:'Медина · MED',maxlength:80})}${field('Дата вылета',leg.departure_date,`flight.${key}.departure_date`,{required:true,type:'date',className:'date-half'})}${field('Время вылета',leg.departure_time,`flight.${key}.departure_time`,{required:true,type:'time',className:'date-half'})}${field('Дата прилёта',leg.arrival_date,`flight.${key}.arrival_date`,{required:true,type:'date',className:'date-half'})}${field('Время прилёта',leg.arrival_time,`flight.${key}.arrival_time`,{required:true,type:'time',className:'date-half'})}</div></section>`;}
function renderFlight(){
  if(state.mode==='flight')return `<h2 id="step-heading">Данные рейсов</h2><p class="panel-intro">Проверьте аэропорты и даты прилёта. Время указывается местное для каждого аэропорта.</p>${flightForm('outbound','Рейс туда')}<div class="city-section"><label class="checkline"><input type="checkbox" data-bind="returnFlight" ${state.returnFlight?'checked':''}>Добавить обратный рейс</label></div>${state.returnFlight?flightForm('inbound','Обратный рейс'):''}`;
  return `<h2 id="step-heading">Данные перелёта</h2><p class="panel-intro">Этот шаг необязательный. Вы решаете, что будет в документе.</p><div class="switch-card"><div><h3>Включить перелёт в ваучер</h3><p>Дополнительная страница с рейсами туда и обратно</p></div><label class="switch"><input type="checkbox" data-bind="flightEnabled" ${state.flightEnabled?'checked':''} aria-label="Включить данные перелёта"><span class="switch-track"></span></label></div>${state.flightEnabled?`<div class="notice">Указывайте местное время каждого аэропорта. Можно добавить рейсы любой авиакомпании.</div>${state.month&&state.sheet?`<div class="schedule-import"><button class="button secondary small" data-action="load-schedule">${icon('calendar')}Загрузить из расписания выбранной группы</button>${renderScheduleOptions(true)}</div>`:''}${flightForm('outbound','Путь к путешествию')}<div class="city-section"><label class="checkline"><input type="checkbox" data-bind="returnFlight" ${state.returnFlight?'checked':''}>Добавить обратный рейс</label></div>${state.returnFlight?flightForm('inbound','Дорога домой'):''}`:`<div class="no-flight">${icon('plane')}<h3>Только то, что нужно</h3><p>Ваучер будет содержать проживание и услуги.<br>Данные перелёта добавляться не будут.</p></div>`}`;}
function renderReview(){
  if(state.mode==='flight')return renderFlightReview();
  const v=state.voucher,rooms=v.people.rooms.filter(r=>r.selected!==false),people=rooms.reduce((s,r)=>s+r.people.length,0);
  return `<h2 id="step-heading">Проверка ваучера</h2><p class="panel-intro">Выберите оформление и убедитесь, что каждая деталь на своём месте.</p><h3 class="program-heading">Вторая страница · программа поездки</h3><div class="design-grid" role="group" aria-label="Дизайн программы">${programDesigns.map((program,i)=>`<button class="design-option ${state.background===i?'selected':''}" data-action="design" data-index="${i}" aria-pressed="${state.background===i}"><img src="/api/designs/${i}" alt="Программа ${program.label}" loading="lazy"><span>${program.label}</span></button>`).join('')}</div><div class="program-explanation"><p>${esc(programDesigns[state.background].description)}</p>${recommendedDesign()!==null?`<small>По указанному маршруту подходит: ${esc(programDesigns[recommendedDesign()].label)}.</small>`:'<small>Выберите программу по фактическому маршруту и транспорту.</small>'}<button class="button secondary small" data-action="preview-program">${icon('document')}Посмотреть вторую страницу</button></div><div class="review-layout"><div class="review-items"><div class="review-line"><span>Тур</span><strong>${esc(state.title)}</strong></div><div class="review-line"><span>Паломники</span><strong>${people} чел. · ${rooms.length} комнат</strong></div>${[1,...(state.secondCity?[2]:[])].map(i=>`<div class="review-line"><span>${esc(v[`city${i}`])}</span><strong>${esc(v[`hotel${i}`])}<br>${esc(v[`dates${i}`])}</strong></div>`).join('')}${serviceFields.map(([key,label])=>`<div class="review-line"><span>${esc(label)}</span><strong>${esc(serviceIncluded(v[key])?v[key]:'Не включено')}</strong></div>`).join('')}<div class="review-line"><span>Перелёт</span><strong>${state.flightEnabled?`${esc(state.flight.outbound.airline)} · ${esc(state.flight.outbound.number)}`:'Не включён'}</strong></div><div class="review-line"><span>Документы</span><strong>${rooms.length} PDF · по ${state.flightEnabled?3:2} страницы</strong></div>${rooms.map((r,i)=>`<div class="review-room"><b>Комната ${i+1} · ${esc(r.kind)}</b>${r.people.map(esc).join(', ')}</div>`).join('')}</div><div><div class="preview-box" id="preview-box">${state.preview?`<img src="${state.preview}" alt="Предпросмотр первой страницы ваучера">`:`<div class="preview-placeholder"><span class="spinner"></span><br>Готовим предпросмотр…</div>`}</div><p class="fine-print">Предпросмотр первой комнаты.<br>Для каждой комнаты будет отдельный PDF.</p></div></div><div class="deliver-choice"><label class="checkline"><input type="checkbox" data-bind="deliver" ${state.deliver?'checked':''}>Отправить готовые PDF в мой чат Telegram</label><p class="fine-print">Вы также сможете скачать документы на сайте.</p></div>`;
}
function validateStep(){
  if(state.mode==='flight'&&state.step===0&&state.flightSource==='sheet'&&!state.flightOptionId)throw new Error('Выберите рейсы из расписания или переключитесь на ручное заполнение.');
  const v=state.voucher,rooms=v.people.rooms.filter(r=>r.selected!==false);
  if(state.step===0){if(state.mode==='package'&&state.selectedRow===null)throw new Error('Выберите пакет из списка или перейдите к ручному оформлению.');if(!state.title.trim())throw new Error('Укажите название тура.');}
  if(state.step===1){if(!rooms.length)throw new Error('Добавьте или выберите хотя бы одну комнату.');for(const r of rooms){if(!r.people.length)throw new Error('Укажите имена паломников в каждой выбранной комнате.');if(!['SGL','DBL','TWIN','TRPL','QUAD'].includes(r.kind))throw new Error('Выберите размещение для каждой комнаты.');if(!Number.isInteger(r.adults)||r.adults<0||r.adults>r.people.length)throw new Error('Проверьте количество взрослых в комнатах.');if(r.adults>({SGL:1,DBL:2,TWIN:2,TRPL:3,QUAD:4}[r.kind]))throw new Error(`В комнате ${r.kind} слишком много взрослых. Разделите комнату или измените размещение.`);}}
  if(state.step===2){for(const i of [1,...(state.secondCity?[2]:[])]){const [a,b]=splitDates(v[`dates${i}`]);if(!v[`city${i}`]?.trim()||!v[`hotel${i}`]?.trim()||!a||!b)throw new Error(`Заполните город, отель и даты проживания для города ${i}.`);if(b<a)throw new Error('Дата выезда должна быть не раньше заезда.');if(!v[`checkin${i}`])throw new Error('Укажите время заселения.');}}
  if(state.step===4&&state.flightEnabled){for(const leg of [state.flight.outbound,...(state.returnFlight?[state.flight.inbound]:[])]){if(Object.values(leg).some(v=>!String(v).trim()))throw new Error('Заполните все поля включённых рейсов или отключите данные перелёта.');if(leg.arrival_date<leg.departure_date)throw new Error('Дата прилёта должна быть не раньше даты вылета.');}}
}
function requestBody(){
  if(state.mode==='flight')return {document_type:'flight',title:state.title.trim(),voucher:null,background:0,flight:{outbound:state.flight.outbound,inbound:state.returnFlight?state.flight.inbound:null},deliver_to_chat:state.deliver,request_id:state.requestId};
  const v=structuredClone(state.voucher);v.people.rooms=v.people.rooms.filter(r=>r.selected!==false).map(r=>({kind:r.kind,people:r.people,adults:r.adults}));
  for(const [key] of serviceFields)if(!serviceIncluded(v[key]))v[key]='Не включено';
  if(!state.secondCity){v.city2=null;v.hotel2=null;v.dates2=null;}
  const flight=state.flightEnabled?{outbound:state.flight.outbound,inbound:state.returnFlight?state.flight.inbound:null}:null;
  return {title:state.title.trim(),voucher:v,background:state.background,flight,deliver_to_chat:state.deliver,request_id:state.requestId};
}
async function next(){try{validateStep();state.error='';const sequence=wizardSteps();state.step=sequence[sequence.indexOf(state.step)+1];render();window.scrollTo(0,0);if(state.step===5)await loadPreview();}catch(e){setError(e.message);}}
function back(){const program=$('#program-dialog');if(program?.open){program.close();return;}if(state.view==='job'||state.view==='history'){home();return;}if(state.view==='home'){tg?.BackButton?.hide();return;}const sequence=wizardSteps(),position=sequence.indexOf(state.step);if(position<=0){home();return;}state.step=sequence[position-1];state.error='';render();window.scrollTo(0,0);}
async function loadCatalog(force=false){
  state.loading='catalog';state.error='';render();
  try{const data=await api(`/api/catalog?refresh=${force}`);state.months=data.months;const now=new Date();const suggested=`${monthsEn[now.getMonth()]} ${now.getFullYear()}`;state.month=state.months.includes(state.month)?state.month:state.months.includes(suggested)?suggested:state.months[0]||'';state.loading='';render();if(state.month)await loadSheets();}
  catch(e){state.loading='';setError(e.message);render();}
}
async function loadSheets(){
  state.loading='sheets';state.sheets=[];state.sheet='';state.packages=[];state.selectedRow=null;state.flightOptions=[];state.flightOptionId=null;state.error='';render();
  const month=state.month;
  try{const data=await api(`/api/sheets?month=${encodeURIComponent(month)}&include_past=${state.includePast}`);if(state.month!==month)return;state.sheets=data.sheets.filter(title=>state.mode!=='flight'||!/расписание/i.test(title));state.loading='';render();}
  catch(e){state.loading='';state.error=e.message;render();}
}
async function loadPackages(){
  if(state.mode==='flight'){await loadScheduledFlights();return;}
  state.loading='packages';state.packages=[];state.selectedRow=null;state.error='';render();
  const sheet=state.sheet;
  try{const data=await api(`/api/packages?month=${encodeURIComponent(state.month)}&sheet=${encodeURIComponent(sheet)}`);if(state.sheet!==sheet)return;state.packages=data.packages;state.loading='';render();}
  catch(e){state.loading='';state.error=e.message;render();}
}
async function selectPackage(row){
  serviceDrafts={};state.editSource=null;
  const p=state.packages.find(p=>p.row===row);if(!p)return;
  state.loading='selection';state.error='';render();
  try{const data=await post('/api/package',{month:state.month,sheet:state.sheet,row,title:p.title});state.selectedRow=row;state.title=data.title;state.voucher={...defaults(),...data.voucher};state.voucher.people.rooms=state.voucher.people.rooms.map(r=>({...r,selected:true}));state.secondCity=Boolean(state.voucher.city2);state.warnings=data.voucher.warnings||[];state.background=/мед|mad|med/i.test(state.voucher.city1||'')?(/поезд|train/i.test(state.voucher.transfer||'')?1:0):2;dirty();state.loading='';render();notify('Пакет выбран. Проверьте паломников и детали проживания.');}
  catch(e){state.loading='';state.error=e.message;render();}
}
async function loadPreview(){
  const id=++previewCounter;
  try{const data=await post('/api/preview',requestBody());if(id!==previewCounter)return;state.preview=data.image;if(state.step===5&&state.view==='wizard')$('#preview-box').innerHTML=`<img src="${data.image}" alt="Предпросмотр первой страницы ваучера">`;}
  catch(e){if(id!==previewCounter)return;setError(e.message);const box=$('#preview-box');if(box)box.innerHTML=`<div class="preview-placeholder">${icon('document')}Предпросмотр пока недоступен.<br>Проверьте заполненные поля.</div>`;}
}
async function generate(){
  if(state.loading)return;
  state.loading='generate';state.error='';render();
  try{const result=await post('/api/jobs',requestBody());state.loading='';state.job={id:result.id,status:'queued',files:[],sent:0,document_type:state.mode==='flight'?'flight':'voucher',title:state.title,deliver_to_chat:state.deliver};state.view='job';render();window.scrollTo(0,0);await pollJob();}
  catch(e){state.loading='';state.error=e.message;render();}
}
async function pollJob(){
  clearTimeout(jobTimer);if(!state.job)return;const key=state.job.id;
  try{const job=await api(`/api/jobs/${key}`);if(state.job?.id!==key)return;state.job=job;if(state.view==='job')renderJob();if(['queued','rendering','sending'].includes(job.status)){jobTimer=setTimeout(pollJob,1700);}else{tg?.disableClosingConfirmation?.();}}
  catch(e){if(state.job?.id!==key)return;if(state.view==='job')notify(e.message);jobTimer=setTimeout(pollJob,4000);}
}
function renderJob(){
  const job=state.job;if(!job){home();return;}
  const done=job.status==='done',failed=job.status==='failed';
  const messages={queued:'Принимаем данные…',rendering:'Формируем PDF…',sending:`Отправляем PDF в Telegram${job.files?.length?` · ${job.sent} из ${job.files.length}`:''}`};
  $('#main').innerHTML=`<div class="container wizard"><div class="breadcrumbs"><button data-action="home">Документы</button><span>/</span><span>Ваши ваучеры</span></div><section class="panel done-panel"><div class="done-icon">${done?icon('check'):failed?icon('document'):'<span class="spinner"></span>'}</div><h2>${done?'Документы готовы':failed?'Нужно немного внимания':'Формируем ваучеры'}</h2><p>${done?(state.deliver?'Готовые PDF отправлены в ваш личный чат Telegram. Также их можно скачать здесь.':'Готовые PDF можно скачать здесь.'):(failed?esc(job.error):`Оставьте страницу открытой или вернитесь в Telegram. ${job.document_type==='flight'?'Мы подготовим документ с данными рейсов.':'Мы подготовим отдельный ваучер для каждой комнаты.'}`)}</p>${!done&&!failed?`<div class="progress-label"><span class="spinner"></span>${messages[job.status]||'Готовим документы…'}</div>`:''}<div class="done-actions">${job.archive?`<button class="button primary" data-action="download" data-url="${esc(job.archive)}" data-name="Hickmet_vouchers.zip">${icon('download')}Скачать все документы</button>`:''}${done?`<button class="button secondary" data-action="home">Создать ещё ваучер ${icon('arrow')}</button>`:''}${failed&&job.files.length&&state.deliver?'<button class="button secondary" data-action="retry-send">Повторить отправку в Telegram</button>':''}${failed?'<button class="button secondary" data-action="edit-draft">Вернуться к данным</button>':''}</div><div class="file-list">${(job.files||[]).map((f,index)=>`<div class="file-item">${icon('document')}<span>${esc(f.name)}<br><small class="muted">${f.pages} ${f.pages===1?'страница':'страницы'} · PDF</small></span><div class="file-actions"><button class="button secondary small" data-action="edit-document" data-job="${esc(job.id)}" data-index="${index}" ${done||failed?'':'disabled'}>${icon('edit')}Изменить</button><button class="button secondary small" data-action="download" data-url="${esc(f.download)}" data-name="${esc(f.name)}">${icon('download')}Скачать</button></div></div>`).join('')}</div>${job.archive?'<p class="fine-print">Документы доступны на сайте в течение 24 часов.<br>Файлы в Telegram останутся в вашем чате.</p>':''}</section></div>`;
}
async function download(url,name){
  try{
    if(tg?.initData&&typeof tg.downloadFile==='function'&&tg.isVersionAtLeast?.('8.0')){
      const match=url.match(/^\/api\/jobs\/([a-f0-9]+)\/(?:files\/(\d+)|download)$/);
      if(!match)throw new Error('Неверная ссылка на документ');
      const link=await post(`/api/jobs/${match[1]}/download-link`,{index:match[2]===undefined?-1:Number(match[2])});
      tg.downloadFile(link);return;
    }
    const response=await fetch(url,{headers:token?{Authorization:`Bearer ${token}`}:{},credentials:'same-origin'});if(!response.ok)throw new Error('Не удалось скачать документ. Возможно, срок хранения истёк.');const blob=await response.blob(),href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),60000);}
  catch(e){notify(e.message);}
}
function applySavedDraft(draft,source){
  clearTimeout(jobTimer);serviceDrafts={};const flightOnly=draft.document_type==='flight';
  Object.assign(state,{view:'wizard',step:flightOnly?4:1,mode:flightOnly?'flight':'manual',title:draft.title,voucher:draft.voucher||defaults(),
    secondCity:Boolean(draft.voucher?.city2),flightEnabled:flightOnly||Boolean(draft.flight),returnFlight:Boolean(draft.flight?.inbound),
    flight:{outbound:draft.flight?.outbound||legDefault(),inbound:draft.flight?.inbound||legDefault()},
    deliver:draft.deliver_to_chat,background:draft.background,preview:'',job:null,selectedRow:null,warnings:[],error:'',loading:'',editSource:source,
    flightSource:'manual',flightOptions:[],flightOptionId:null});
  state.voucher.people.rooms=state.voucher.people.rooms.map(room=>({...room,selected:true}));
  dirty();render();window.scrollTo(0,0);tg?.enableClosingConfirmation?.();tg?.BackButton?.show();
}
async function editDocument(key,index){
  if(!state.user){resumeAction=()=>editDocument(key,index);await showLogin();return;}
  applySavedDraft(await api(`/api/jobs/${key}/files/${index}/draft`),{key,index});
}
async function editJobDraft(key){applySavedDraft(await api(`/api/jobs/${key}/draft`),{key,index:null});}
async function showLogin(){
  const dialog=$('#login-dialog');if(dialog.open)return;
  $('#login-status').innerHTML='<div class="loading-label"><span class="spinner"></span>Готовим безопасный вход…</div>';
  $('#telegram-login-link').hidden=true;dialog.showModal();
  try{const data=await post('/api/auth/challenge');$('#telegram-login-link').href=data.telegram_url;$('#telegram-login-link').hidden=false;$('#login-status').innerHTML='<div class="notice">В боте нажмите «Подтвердить вход на сайт».</div>';loginExpires=Date.now()+data.expires_in*1000;
    const check=async()=>{if(!dialog.open)return;if(Date.now()>loginExpires){$('#login-status').innerHTML='<div class="notice error">Время входа истекло. Закройте окно и попробуйте снова.</div>';return;}try{const result=await post('/api/auth/poll',{challenge:data.challenge,secret:data.secret});if(result.user){token=result.session_token;state.user=result.user;dialog.close();updateAccount();const action=resumeAction;resumeAction=null;if(action)await action();else notify('Вы вошли в Hickmet Workspace.');return;}}catch(e){$('#login-status').innerHTML=`<div class="notice error">${esc(e.message)}</div>`;return;}loginTimer=setTimeout(check,1500);};loginTimer=setTimeout(check,1500);
  }catch(e){$('#login-status').innerHTML=`<div class="notice error">${esc(e.message)}</div>`;}
}
function inputChanged(input){
  const bind=input.dataset.bind;
  if(input.dataset.serviceToggle){const key=input.dataset.serviceToggle;if(!serviceFields.some(([field])=>field===key))return;if(input.checked){state.voucher[key]=serviceDrafts[key]||defaults()[key];}else{serviceDrafts[key]=state.voucher[key];state.voucher[key]='Не включено';}dirty();render();$(`[data-service-toggle="${key}"]`)?.focus();return;}
  else if(input.dataset.roomNames!==undefined){const r=state.voucher.people.rooms[Number(input.dataset.roomNames)],old=r.people.length;const children=old-r.adults;r.people=input.value.split(/\n/).map(s=>s.trim()).filter(Boolean);r.adults=Math.max(0,r.people.length-Math.max(0,children));syncRoomCounts(Number(input.dataset.roomNames));input.rows=Math.max(3,Math.min(10,input.value.split(/\n/).length+1));}
  else if(input.dataset.roomKind!==undefined)state.voucher.people.rooms[Number(input.dataset.roomKind)].kind=input.value;
  else if(input.dataset.roomAdults!==undefined)state.voucher.people.rooms[Number(input.dataset.roomAdults)].adults=Number(input.value);
  else if(input.dataset.roomSelect!==undefined)state.voucher.people.rooms[Number(input.dataset.roomSelect)].selected=input.checked;
  else if(bind){
    if(bind==='all-room-kind'){state.voucher.people.rooms.filter(room=>room.selected!==false).forEach(room=>room.kind=input.value);dirty();render();return;}
    else if(bind.startsWith('room-kind-')){const index=Number(bind.slice('room-kind-'.length));state.voucher.people.rooms[index].kind=input.value;dirty();render();$(`#picker-value-${bind}`)?.parentElement?.focus();return;}
    else if(bind==='title')state.title=input.value;
    else if(bind.startsWith('voucher.'))state.voucher[bind.split('.')[1]]=input.value;
    else if(bind.startsWith('flight.')){const [,key,field]=bind.split('.');state.flight[key][field]=input.value;}
    else if(bind.startsWith('dates.')){const [,slot,kind]=bind.split('.'),[a,b]=splitDates(state.voucher[`dates${slot}`]);const start=kind==='start'?input.value:a||'',end=kind==='end'?input.value:b||'';state.voucher[`dates${slot}`]=`${dateToISO(start)} – ${dateToISO(end)}`;const n=$(`#nights-${slot}`);if(n)n.textContent=nightsLabel(start,end);}
    else if(bind==='month'){state.month=input.value;loadSheets();}
    else if(bind==='sheet'){state.sheet=input.value;loadPackages();}
    else if(bind==='includePast'){state.includePast=input.checked;loadSheets();}
    else if(['secondCity','flightEnabled','returnFlight','deliver'].includes(bind)){state[bind]=input.checked;render();}
  }
  dirty();
  const rooms=state.voucher.people.rooms.filter(r=>r.selected!==false);if($('#summary-people'))$('#summary-people').textContent=`${rooms.reduce((s,r)=>s+r.people.length,0)} чел.`;if($('#summary-rooms'))$('#summary-rooms').textContent=rooms.length;
}
document.addEventListener('input',event=>{
  if(event.target.matches('[data-picker-search]')){const picker=event.target.closest('.catalog-picker'),query=event.target.value.trim().toLocaleLowerCase();let count=0;picker.querySelectorAll('.picker-option').forEach(option=>{option.hidden=!option.textContent.toLocaleLowerCase().includes(query);if(!option.hidden)count++;});$('.picker-empty',picker).hidden=count>0;return;}
  if(event.target.matches('input:not([type=checkbox]),textarea'))inputChanged(event.target);
});
document.addEventListener('toggle',event=>{if(event.target.matches('.catalog-picker')&&event.target.open)document.querySelectorAll('.catalog-picker[open]').forEach(picker=>{if(picker!==event.target)picker.open=false;});},true);
document.addEventListener('keydown',event=>{const picker=event.target.closest('.catalog-picker');if(!picker)return;if(event.key==='Escape'){picker.open=false;$('summary',picker).focus();event.preventDefault();}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&!event.target.matches('input')){const options=[...picker.querySelectorAll('.picker-option:not([hidden]):not(:disabled)')];if(!options.length)return;picker.open=true;const index=options.indexOf(document.activeElement),next=event.key==='Home'?0:event.key==='End'?options.length-1:event.key==='ArrowDown'?(index+1)%options.length:(index-1+options.length)%options.length;options[next].focus();event.preventDefault();}else if(event.key==='ArrowDown'&&event.target.matches('[data-picker-search]')){picker.querySelector('.picker-option:not([hidden]):not(:disabled)')?.focus();event.preventDefault();}});
document.addEventListener('change',event=>{if(event.target.matches('select,input[type=checkbox]'))inputChanged(event.target);});
document.addEventListener('click',async event=>{
  document.querySelectorAll('.catalog-picker[open]').forEach(picker=>{if(!picker.contains(event.target))picker.open=false;});
  const button=event.target.closest('[data-action]');if(!button)return;const action=button.dataset.action;
  try{
    if(action==='picker-select'){const picker=button.closest('.catalog-picker');picker.open=false;$('summary',picker).focus();inputChanged({dataset:{bind:button.dataset.pickerBind},value:button.dataset.pickerValue});}
    else if(action==='home')home();else if(action==='start-package')await start('package');else if(action==='start-manual')await start('manual');else if(action==='start-flight')await start('flight');
    else if(action==='account'){if(state.user)notify(`Вы вошли как ${state.user.first_name||state.user.username}`);else await showLogin();}
    else if(action==='logout'){await post('/api/auth/logout');clearTimeout(jobTimer);token='';state.user=null;state.job=null;state.history=[];state.voucher=defaults();updateAccount();home();notify('Вы вышли из аккаунта.');}
    else if(action==='close-login')$('#login-dialog').close();
    else if(action==='mode-package'||action==='mode-manual'){state.editSource=null;state.mode=action==='mode-package'?'package':'manual';if(state.mode==='manual'){serviceDrafts={};state.title='Индивидуальный ваучер';state.voucher=defaults();state.selectedRow=null;state.warnings=[];}render();if(state.mode==='package'&&!state.months.length)await loadCatalog();}
    else if(action==='history')await showHistory();
    else if(action==='open-job')await openJob(button.dataset.job);
    else if(action==='flight-source-manual'){state.flightSource='manual';state.error='';dirty();render();}
    else if(action==='flight-source-sheet'){state.flightSource='sheet';state.error='';dirty();render();await loadCatalog();}
    else if(action==='load-schedule')await loadScheduledFlights();
    else if(action==='select-schedule-flight'||action==='attach-schedule-flight')selectScheduledFlight(button.dataset.id,action==='attach-schedule-flight');
    else if(action==='refresh-catalog')await loadCatalog(true);
    else if(action==='select-package')await selectPackage(Number(button.dataset.row));
    else if(action==='next')await next();else if(action==='back')back();
    else if(action==='select-all-rooms'||action==='clear-rooms'){state.voucher.people.rooms.forEach(room=>room.selected=action==='select-all-rooms');dirty();render();}
    else if(action==='adult-minus'||action==='adult-plus')stepAdults(Number(button.dataset.index),action==='adult-minus'?-1:1);
    else if(action==='add-room'){state.voucher.people.rooms.push({kind:'DBL',people:[],adults:0,selected:true});dirty();render();}
    else if(action==='remove-room'){state.voucher.people.rooms.splice(Number(button.dataset.index),1);dirty();render();}
    else if(action==='preview-program'){const dialog=$('#program-dialog');$('#program-title').textContent=programDesigns[state.background].label;$('#program-description').textContent=programDesigns[state.background].description;$('#program-image').src=`/api/designs/${state.background}`;dialog.showModal();}
    else if(action==='close-program')$('#program-dialog').close();
    else if(action==='design'){state.background=Number(button.dataset.index);state.preview='';dirty();render();await loadPreview();}
    else if(action==='generate')await generate();
    else if(action==='download')await download(button.dataset.url,button.dataset.name);
    else if(action==='edit-document')await editDocument(button.dataset.job,Number(button.dataset.index));
    else if(action==='retry-send'){await post(`/api/jobs/${state.job.id}/retry`);state.job.status='sending';renderJob();await pollJob();}
    else if(action==='edit-draft')await editJobDraft(state.job.id);
  }catch(e){if(state.view==='wizard')setError(e.message);else notify(e.message);}
});
$('#login-dialog').addEventListener('close',()=>clearTimeout(loginTimer));
window.addEventListener('beforeunload',event=>{if(state.view==='wizard'&&state.step>0){event.preventDefault();event.returnValue='';}});
async function init(){
  if(tg?.initData)document.body.classList.add('telegram-app');
  updateAccount();render();
  try{tg?.ready();tg?.expand();tg?.setHeaderColor?.('#f6f1e9');tg?.setBackgroundColor?.('#f6f1e9');tg?.BackButton?.onClick(back);}catch{}
  const configPromise=api('/api/config').then(config=>state.config=config).catch(()=>{});
  try{const result=tg?.initData?await post('/api/auth/telegram',{init_data:tg.initData}):await api('/api/me');state.user=result.user;if(result.session_token)token=result.session_token;updateAccount();}catch(e){if(tg?.initData)notify(e.message);}
  await configPromise;
  const edit=new URLSearchParams(window.location.search).get('edit');
  if(edit){const match=/^([a-f0-9]{32}):(\d+)$/.exec(edit);if(match){try{await editDocument(match[1],Number(match[2]));}catch(e){notify(e.message);}}else notify('Ссылка на ваучер некорректна.');}
}
init();
