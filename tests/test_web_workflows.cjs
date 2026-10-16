const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function run(script) {
  const elements = new Map();
  const context = vm.createContext({
    crypto: require('node:crypto').webcrypto, structuredClone, setTimeout, clearTimeout, URLSearchParams,
    window: {addEventListener() {}, scrollTo() {}},
    document: {addEventListener() {}, querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {addEventListener() {}, focus() {}, scrollIntoView() {}, open: false});
      return elements.get(selector);
    }},
  });
  const source = fs.readFileSync(path.join(__dirname, '../pligrim_bot/web/static/app.js'), 'utf8').replace(/\ninit\(\);\s*$/, '');
  vm.runInContext(source, context);
  return vm.runInContext(`(async()=>{render=()=>{};notify=()=>{};state.user={id:101};${script}})()`, context);
}

test('standalone flight skips rooms and hotels and supports back navigation', () => run(`
  loadCatalog=async()=>{};loadPreview=async()=>{};
  await start('flight');state.flightSource='manual';state.returnFlight=false;
  if(!state.flightEnabled)throw Error('Flight not enabled');
  state.flight.outbound={airline:'SCAT',number:'DV 499',origin:'ALA',destination:'MED',departure_date:'2026-10-20',arrival_date:'2026-10-20',departure_time:'05:30',arrival_time:'04:50'};
  await next();if(state.step!==4)throw Error('Rooms or hotels requested for flight');
  await next();if(state.step!==5)throw Error('Review not reached');
  const body=requestBody();
  if(body.document_type!=='flight'||body.voucher!==null||body.flight.inbound!==null)throw Error('Incorrect standalone request');
  back();if(state.step!==4)throw Error('Wrong return from review');
  back();if(state.step!==0)throw Error('Wrong return to source');
`));

test('bulk room changes affect only selected rooms without reclassifying adults', () => run(`
  state.voucher.people.rooms=[{kind:'DBL',people:['IVANOV IVAN','PETROVA ANNA'],adults:2,selected:true},{kind:'SGL',people:['SMIRNOV EGOR'],adults:1,selected:false}];
  inputChanged({dataset:{bind:'all-room-kind'},value:'QUAD'});
  if(state.voucher.people.rooms[0].kind!=='QUAD'||state.voucher.people.rooms[0].adults!==2)throw Error('Selected room changed incorrectly');
  if(state.voucher.people.rooms[1].kind!=='SGL')throw Error('Unselected room changed');
  if(requestBody().voucher.people.rooms.length!==1)throw Error('Unselected room submitted');
`));

test('schedule import fills flight data without changing the passenger package title', () => run(`
  state.mode='package';state.title='Passenger package';
  state.flightOptions=[{id:'route',title:'Flight package',flight:{outbound:{airline:'Air Astana',number:'KC263'},inbound:{airline:'Air Astana',number:'KC266'}}}];
  selectScheduledFlight('route',true);
  if(state.title!=='Passenger package'||!state.returnFlight||!state.flightEnabled||state.flight.outbound.number!=='KC263')throw Error('Attached import failed');
  state.mode='flight';selectScheduledFlight('route');
  if(state.title!=='Flight package'||state.flightOptionId!=='route')throw Error('Standalone import failed');
`));

test('saved standalone flight is editable without room data', () => run(`
  applySavedDraft({document_type:'flight',title:'Saved flight',voucher:null,flight:{outbound:{airline:'SCAT',number:'DV499'},inbound:null},deliver_to_chat:false,background:0},{key:'saved',index:0});
  if(state.mode!=='flight'||state.step!==4||state.returnFlight||state.deliver)throw Error('Wrong editor state');
  if(requestBody().voucher!==null||requestBody().flight.outbound.number!=='DV499')throw Error('Saved flight lost');
`));

test('a late job status response cannot replace another open job', () => run(`
  let resolve;api=()=>new Promise(done=>resolve=done);state.job={id:'old'};
  const waiting=pollJob();state.job={id:'new'};resolve({id:'old',status:'done'});await waiting;
  if(state.job.id!=='new')throw Error('Late response replaced active job');
`));

test('every website wizard renders and flight screens omit hotel steps', () => run(`
  for(const mode of ['manual','package','flight']){
    state.mode=mode;state.flightSource='sheet';state.flightOptions=[];
    for(const step of wizardSteps()){
      state.step=step;renderWizard();const html=$('#main').innerHTML;
      if(html.includes('undefined'))throw Error('Undefined content on '+mode+' step '+step);
      if(mode==='flight'&&html.includes('>Проживание<'))throw Error('Hotel step in standalone flight');
    }
  }
  renderHome();if(!$('#main').innerHTML.includes('start-flight')||!$('#main').innerHTML.includes('history'))throw Error('Missing home entry points');
  state.job={id:'job',status:'done',document_type:'flight',files:[{name:'flight.pdf',pages:1,download:'/file'}],sent:1,archive:'/zip'};
  renderJob();if(!$('#main').innerHTML.includes('1 страница')||!$('#main').innerHTML.includes('edit-document'))throw Error('Flight result not rendered');
`));
