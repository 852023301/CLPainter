'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {boot}=require('./frontend_switch_behavior.js');
const plain=value=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<120;i++)await Promise.resolve();};
const item=id=>({instrument_id:id,code:'S'+id,display_name:'Stock '+id,asset_class:'stock',market:'cn',url:'/chart?symbol=S'+id,change:null,change_pct:null});
const boards=()=>[{id:1,name:'First',items:[1,2,3].map(item)},{id:2,name:'Second',items:[]}];
const response=(payload,status=200)=>{const saved=plain(payload);return {ok:status>=200&&status<300,status,json:async()=>plain(saved)};};
const read=(p,code)=>vm.runInContext(code,p.context);
const order=p=>plain(read(p,'currentBoard()?.items.map(item=>item.instrument_id)||[]'));
const message=p=>p.document.getElementById('watchlistStatus')?.textContent||'';
const retry=p=>p.document.getElementById('watchlistRetry');
async function page(){
 const p=await boot('freq=1day',{},'available',{quiet:true,workspaceData:true});
 p.context.currentInstrumentId=1;p.context.prompt=()=> 'Renamed';p.context.confirm=()=>true;
 const create=p.document.createElement.bind(p.document);p.document.createElement=tag=>{const node=create(tag);node.scrollIntoView=()=>{};return node;};
 const server={boards:boards(),requests:[],pending:[],hold:null,mode:null,active:0,peak:0};
 const fallback=p.context.fetch;
 const perform=(url,method,body)=>{
  if(method==='GET')return response({boards:server.boards});
  if(method==='POST'&&url.endsWith('/watchlists')){const board={id:Math.max(0,...server.boards.map(row=>row.id))+1,name:body.name,items:[]};server.boards.push(board);return response(board,201);}
  const id=Number(url.split('/watchlists/')[1].split('/')[0]);const board=server.boards.find(row=>row.id===id);assert(board,'Fixture board must exist');
  if(url.endsWith('/items/order')){const items=new Map(board.items.map(row=>[row.instrument_id,row]));board.items=body.instrument_ids.map(value=>items.get(value));return response(board);}
  if(method==='PATCH'){board.name=body.name;return response(board);}
  if(method==='DELETE'&&!url.includes('/items/')){server.boards=server.boards.filter(row=>row.id!==id);return response(null,204);}
  if(method==='DELETE'){const removed=Number(url.split('/').pop());board.items=board.items.filter(row=>row.instrument_id!==removed);return response(null,204);}
  if(method==='POST'){if(!board.items.some(row=>row.instrument_id===body.instrument_id))board.items.push(item(body.instrument_id));return response(board);}
  throw new Error('Unexpected fixture request '+method+' '+url);
 };
 p.context.fetch=async(raw,options={})=>{
  const url=String(raw);if(!url.includes('/watchlists'))return fallback(raw,options);
  const method=options.method||'GET',body=options.body?JSON.parse(options.body):null;server.requests.push({url,method,body,signal:options.signal});
  const mode=server.mode;server.mode=null;
  if(mode==='http')return response({detail:'temporary watchlist failure'},503);
  if(mode==='unsafe')return response({detail:'<img src=x onerror=alert(1)>'},503);
  if(mode==='invalid')return response({unknown:[]});
  if(mode==='network')throw new TypeError('network unavailable');
  if(mode==='body'){const result=perform(url,method,body);return {...result,json:()=>new Promise(()=>{})};}
  if(server.hold===method||(server.hold==='order'&&url.endsWith('/items/order'))){
   server.hold=null;if(method!=='GET'){server.active++;server.peak=Math.max(server.peak,server.active);}
   return new Promise(resolve=>server.pending.push(()=>{if(method!=='GET')server.active--;resolve(perform(url,method,body));}));
  }
  return perform(url,method,body);
 };
 p.server=server;p.load=()=>read(p,'loadWatchlists()');
 p.move=(source,target,after=false)=>read(p,'reorderWatchlistItem(currentBoard(),'+source+','+target+','+after+')');
 await p.load();await flush();return p;
}
const cases=[
 ['sort_single_flight',async()=>{
  const p=await page();p.server.hold='order';const first=p.move(1,2,true);const second=p.move(3,2,false);await flush();
  assert.equal(p.server.requests.filter(row=>row.method==='PUT').length,1,'A second drag must not send a concurrent reorder');
  assert.deepEqual(order(p),[2,1,3]);p.server.pending.shift()();await first;await second;assert.equal(p.server.peak,1);
  assert.deepEqual(order(p),p.server.boards[0].items.map(row=>row.instrument_id));
 }],
 ['sort_busy_controls',async()=>{
  const p=await page();p.server.hold='order';const pending=p.move(1,2,true);await flush();
  assert(p.document.getElementById('watchlistCreateButton').disabled);assert(p.document.getElementById('watchlistDelete').disabled);
  for(const handle of p.document.getElementById('watchlistBoards').querySelectorAll('.watchlist-drag'))assert.equal(handle.draggable,false);
  assert(message(p).includes('保存'));p.server.pending.shift()();await pending;
  assert(!p.document.getElementById('watchlistCreateButton').disabled);
 }],
 ['sort_can_continue_after_success',async()=>{
  const p=await page();await p.move(1,2,true);await p.move(3,2,false);
  assert.deepEqual(order(p),[3,2,1]);assert.deepEqual(order(p),p.server.boards[0].items.map(row=>row.instrument_id));
 }],
 ['sort_failure_refresh_does_not_replay',async()=>{
  const p=await page();p.server.mode='http';await p.move(1,2,true);assert.deepEqual(order(p),[1,2,3]);
  assert(retry(p)&&!retry(p).hidden,'A write failure needs a visible refresh path');
  const count=p.server.requests.length;await p.move(3,1,false);assert.equal(p.server.requests.length,count,'Failed state must block further writes until resync');
  retry(p).dispatch('click');await flush();assert.equal(p.server.requests.filter(row=>row.method==='PUT').length,1);
  assert(!p.document.getElementById('watchlistCreateButton').disabled);
 }],
 ['sort_other_board_navigation_preserved',async()=>{
  const p=await page();p.server.hold='order';const pending=p.move(1,2,true);await flush();
  p.document.getElementById('watchlistTabs').children[1].dispatch('click');assert.equal(read(p,'currentBoard().id'),2);
  p.server.pending.shift()();await pending;assert.equal(read(p,'currentBoard().id'),2);
 }],
 ['initial_failure_visible_and_retryable',async()=>{
  let fail=true;const p=await boot('freq=1day',{},'available',{quiet:true,workspaceData:true,beforeResponse:async url=>{if(fail&&String(url).includes('/watchlists'))throw new Error('initial watchlist failure');}});await flush();
  assert(message(p).includes('失败'));assert(retry(p)&&!retry(p).hidden);assert(p.document.getElementById('watchlistCreateButton').disabled);
  fail=false;retry(p).dispatch('click');await flush();assert(!p.document.getElementById('watchlistCreateButton').disabled);
 }],
 ['loading_blocks_writes',async()=>{
  const p=await page();p.server.hold='GET';const loading=p.load();await flush();assert(p.document.getElementById('watchlistCreateButton').disabled);
  const before=p.server.requests.length;p.document.getElementById('watchlistNameInput').value='Ignored';p.document.getElementById('watchlistCreateButton').dispatch('click');await flush();
  assert.equal(p.server.requests.length,before);p.server.pending.shift()();await loading;
 }],
 ['read_timeout_releases_and_recovers',async()=>{
  const p=await page();p.server.hold='GET';let finished=false;const loading=p.load().then(()=>{finished=true;});await flush();p.runTimers();await flush();
  assert(finished,'A hanging read must respect the application timeout');await loading;assert(message(p).includes('超时'));assert(!retry(p).hidden);
  retry(p).dispatch('click');await flush();assert(!p.document.getElementById('watchlistCreateButton').disabled);
 }],
 ['read_body_timeout_is_bounded',async()=>{
  const p=await page();p.server.mode='body';let finished=false;const loading=p.load().then(()=>{finished=true;});await flush();p.runTimers();await flush();
  assert(finished,'Response body parsing must also time out');await loading;assert(message(p).includes('超时'));
 }],
 ['invalid_list_is_not_successful_empty',async()=>{
  const p=await page();p.server.mode='invalid';await p.load();assert(retry(p)&&!retry(p).hidden,'Invalid responses need a retry control');assert(message(p).includes('格式')||message(p).includes('失败'));
  assert(p.document.getElementById('watchlistCreateButton').disabled);assert.equal(read(p,'watchlists.length'),2,'Keep the last known list rather than accepting invalid data as empty');
 }],
 ['write_timeout_requires_explicit_resync',async()=>{
  const p=await page();p.server.hold='order';let finished=false;const pending=p.move(1,2,true).then(()=>{finished=true;});await flush();p.runTimers();await flush();
  assert(finished,'A hanging sort must release frontend waiting');await pending;assert(message(p).includes('可能已处理'));assert(!retry(p).hidden);
  const count=p.server.requests.length;await p.move(3,1,false);assert.equal(p.server.requests.length,count);
  retry(p).dispatch('click');await flush();const refreshed=order(p);p.server.pending.shift()();await flush();assert.deepEqual(order(p),refreshed,'A timed-out response must not overwrite refreshed UI');
 }],
 ['committed_write_body_timeout_is_not_repeated',async()=>{
  const p=await page();p.server.mode='body';p.document.getElementById('watchlistNameInput').value='Created despite lost response';
  p.document.getElementById('watchlistCreateButton').dispatch('click');await flush();assert.equal(p.server.boards.length,3);p.runTimers();await flush();
  assert(message(p).includes('可能已处理'));assert.equal(p.document.getElementById('watchlistNameInput').value,'Created despite lost response');
  retry(p).dispatch('click');await flush();assert.equal(read(p,'watchlists.length'),3);
  assert.equal(p.server.requests.filter(row=>row.method==='POST').length,1,'Refresh must never automatically replay a write');
 }],
 ['duplicate_create_is_blocked',async()=>{
  const p=await page();p.server.hold='POST';p.document.getElementById('watchlistNameInput').value='New board';
  p.document.getElementById('watchlistCreateButton').dispatch('click');p.document.getElementById('watchlistCreateButton').dispatch('click');await flush();
  assert.equal(p.server.requests.filter(row=>row.method==='POST').length,1);p.server.pending.shift()();await flush();assert.equal(read(p,'watchlists.length'),3);
 }],
 ['delete_204_and_controls_recover',async()=>{
  const p=await page();p.document.getElementById('watchlistDelete').dispatch('click');await flush();assert.equal(read(p,'watchlists.length'),1);
  assert(!p.document.getElementById('watchlistCreateButton').disabled);
 }],
 ['other_mutations_are_blocked_during_sort',async()=>{
  const p=await page();p.server.hold='order';const pending=p.move(1,2,true);await flush();const count=p.server.requests.length;
  for(const id of ['watchlistAddCurrent','watchlistRename','watchlistDelete'])p.document.getElementById(id).dispatch('click');await flush();
  assert.equal(p.server.requests.length,count);p.server.pending.shift()();await pending;
 }],
 ['feedback_is_accessible_and_read_only_retry',async()=>{
  const p=await page();const status=p.document.getElementById('watchlistStatus');assert(status);assert.equal(status.getAttribute('role'),'status');
  p.server.mode='http';await p.load();assert(!retry(p).hidden);retry(p).focus();retry(p).dispatch('click');await flush();
  assert.equal(p.document.activeElement,p.document.getElementById('watchlistCreateButton'),'Successful retry must move focus off the hidden retry control');
  assert(p.server.requests.every(row=>row.method==='GET'),'Read retries cannot issue mutations');
 }],
 ['error_detail_is_plain_text',async()=>{
  const p=await page();p.server.mode='unsafe';await p.load();assert(message(p).includes('<img'));assert.equal(p.document.getElementById('watchlistFeedback').querySelectorAll('img').length,0);
 }],
];
(async()=>{const results=[];for(const [id,run] of cases){try{await run();results.push({id,status:'passed'});}catch(error){results.push({id,status:'failed',message:error.stack||String(error)});}}console.log(JSON.stringify({results},null,2));if(results.some(row=>row.status!=='passed'))process.exitCode=1;})().catch(error=>{console.error(error);process.exitCode=1;});
