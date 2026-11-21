'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(process.argv[2],'utf8');
const ids=['screenerPanel','screenerRealtimeTab','screenerHistoryTab','screenerRealtimePanel','screenerHistoryPanel','screenerHistoryLink','screenerHistoryPreset','screenerHistoryFrequency','screenerHistoryVersion','screenerHistoryRefresh','screenerHistoryPage','screenerHistoryStatus','screenerHistoryChartHint','screenerHistorySummary','screenerHistoryResults','screenerHistoryViewResults','screenerHistoryViewAdded','screenerHistoryViewRemoved','screenerHistoryViewRetained','screenerExpand'];
for(const id of ids) assert(html.includes('id="'+id+'"'),'Missing workspace control '+id);
const script=fs.readFileSync(path.join(path.dirname(process.argv[2]),'../static/js/screener-history.js'),'utf8');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.attributes={};this._text='';this._value='';this.hidden=false;this.disabled=false;this.scrollTop=0;this.className='';this.classList={contains:name=>this.className.split(' ').includes(name)};}
 set textContent(value){this._text=String(value);this.children=[];if(this.tagName==='select')this._value='';}
 get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}
 set value(value){this._value=String(value);if(this.tagName==='select'&&!this.options.some(item=>item.value===this._value))this._value='';}
 get value(){return this._value;}
 get options(){return this.children;}
 append(...nodes){this.children.push(...nodes);}
 appendChild(node){this.children.push(node);}
 setAttribute(name,value){this.attributes[name]=String(value);}
 addEventListener(type,handler){(this.listeners[type]||=[]).push(handler);}
 focus(){this.focused=true;}
 async emit(type,extra={}){const event={target:this,button:0,preventDefault(){this.prevented=true;},...extra};for(const handler of this.listeners[type]||[])await handler(event);}
 async click(){if(!this.disabled)await this.emit('click');}
}
const item=code=>({code,display_name:code,market:'cn',asset_class:'stock'});
const detail3={id:3,preset_id:1,preset_name:'Example',frequency:'1day',version_date:'2026-11-20',previous_version:'2026-11-19',comparison_available:true,count:2,results:[item('AAA'),item('BBB')],added:[item('BBB')],removed:[item('CCC')],retained:[item('AAA')]};
const detail1={...detail3,id:1,version_date:'2026-11-19',previous_version:null,comparison_available:false,count:1,results:[item('AAA')],added:[],removed:[],retained:[]};
const clone=value=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
function server(){
 const data={details:{1:detail1,3:detail3},requests:[],failDetail:false,hold:false};
 data.request=async url=>{
  data.requests.push(url);const parsed=new URL(url,'http://local');
  if(parsed.pathname.endsWith('/presets'))return {presets:[{id:1,name:'Example'}]};
  if(parsed.pathname.endsWith('/runs'))return data.listOverride?data.listOverride(parsed.searchParams):{total:Object.keys(data.details).length,runs:Object.values(data.details).sort((a,b)=>b.id-a.id).map(({results,added,removed,retained,...meta})=>clone(meta))};
  const id=Number(parsed.pathname.split('/').pop());
  if(data.failDetail)throw new Error('detail unavailable');
  if(data.hold&&id===3){data.hold=false;await new Promise(resolve=>data.release=resolve);}
  return clone(data.details[id]);
 };return data;
}
async function boot(data,{storage=new Map(),search='',symbol='AAA'}={}){
 const elements=Object.fromEntries(ids.map(id=>[id,new Element(/Preset$|Frequency$|Version$/.test(id)?'select':'div')]));
 elements.appShell=new Element();
 const navigation=[];const location={pathname:'/api/v1/test_api/lightweight_charts_demo',search,assign:value=>navigation.push(value)};
 const window={location,history:{replaceState(a,b,target){location.search=target.includes('?')?'?'+target.split('?')[1]:'';}}};
 const context={window,console,URLSearchParams,document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)},localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value))},requestAnimationFrame:callback=>callback()};
 vm.createContext(context);vm.runInContext(script,context);
 const controller=new window.ScreenerHistory({request:data.request,getChartContext:()=>({symbol,market:'cn',asset_class:'stock',frequency:'1day'}),getPresetId:()=>1});
 await flush();return {controller,elements,navigation,storage,location};
}
(async()=>{
 const data=server();const page=await boot(data);
 assert.equal(data.requests.length,0,'Realtime startup must not fetch history');
 await page.elements.screenerHistoryTab.click();await flush();
 assert.equal(page.elements.screenerHistoryPanel.hidden,false);
 assert.equal(page.elements.screenerPanel.dataset.mode,'history');
 assert.equal(page.elements.screenerRealtimePanel.hidden,true);
 assert(page.elements.screenerHistoryChartHint.textContent.includes('最新完整行情'));
 assert(page.elements.screenerHistorySummary.textContent.includes('2026-11-20'));
 assert.equal(page.elements.screenerHistoryResults.children.filter(node=>node.tagName==='a').length,2);
 await page.elements.screenerHistoryViewAdded.click();
 assert.equal(page.elements.screenerHistoryResults.children.filter(node=>node.tagName==='a').length,1);
 page.elements.screenerHistoryResults.scrollTop=120;await page.elements.screenerHistoryResults.emit('scroll');
 await page.elements.screenerHistoryResults.children.find(node=>node.tagName==='a').click();
 const target=new URL(page.navigation[0],'http://local');
 assert.equal(target.pathname,'/api/v1/test_api/lightweight_charts_demo');
 assert.equal(target.searchParams.get('symbol'),'BBB');
 assert.equal(target.searchParams.get('frequency'),'1day');
 assert.equal(target.searchParams.get('history_run_id'),'3');
 assert.equal(target.searchParams.get('history_view'),'added');
 assert.equal(target.searchParams.get('history_scroll'),'120');
 for(const name of ['as_of','end_date','version_date'])assert(!target.searchParams.has(name));
 const reload=await boot(data,{storage:page.storage,search:target.search,symbol:'BBB'});
 assert.equal(reload.elements.screenerHistoryResults.scrollTop,120);
 assert.equal(reload.elements.screenerHistoryPanel.hidden,false);
 const realtimeState=JSON.stringify({filters:{frequency:'1week'},results:{count:5}});
 reload.storage.set('screener:state',realtimeState);
 await reload.elements.screenerHistoryTab.emit('keydown',{key:'Home'});
 assert.equal(reload.elements.screenerRealtimeTab.focused,true);
 await reload.elements.screenerRealtimeTab.click();
 assert.equal(reload.storage.get('screener:state'),realtimeState);
 assert.equal(reload.elements.screenerRealtimePanel.hidden,false);
 await reload.elements.screenerHistoryTab.click();await flush();
 reload.elements.screenerHistoryVersion.value='1';await reload.elements.screenerHistoryVersion.emit('change');await flush();
 assert(reload.elements.screenerHistorySummary.textContent.includes('2026-11-19'));
 assert.equal(reload.elements.screenerHistoryViewAdded.disabled,true,'No baseline must not invent additions');
 data.failDetail=true;await reload.elements.screenerHistoryRefresh.click();
 assert(reload.elements.screenerHistoryStatus.textContent.includes('detail unavailable'));
 assert.equal(reload.elements.screenerHistoryResults.children.filter(node=>node.tagName==='a').length,0,'Failure must not show stale results');
 data.failDetail=false;await reload.elements.screenerHistoryRefresh.click();
 assert.equal(reload.elements.screenerHistoryResults.children.filter(node=>node.tagName==='a').length,1);
 reload.controller.state.runId=3;data.hold=true;const slow=reload.controller.refresh({detailOnly:true});await flush();
 reload.controller.state.runId=1;await reload.controller.refresh({detailOnly:true});data.release();await slow;
 assert.equal(reload.controller.detail.id,1,'A late response must not replace the newest selected version');
 const empty=server();empty.details={};const emptyPage=await boot(empty,{search:'?screener_mode=history'});
 assert(emptyPage.elements.screenerHistoryStatus.textContent.includes('暂无'));
 assert.equal(emptyPage.elements.screenerHistoryVersion.disabled,true);
 const zero=server();zero.details={3:{...detail3,count:0,results:[],added:[],removed:[item('AAA')],retained:[]}};
 const zeroPage=await boot(zero,{search:'?screener_mode=history&history_run_id=3'});
 assert(zeroPage.elements.screenerHistoryResults.textContent.includes('本期没有命中'));
 await zeroPage.elements.screenerHistoryViewRemoved.click();
 assert.equal(zeroPage.elements.screenerHistoryResults.children.filter(node=>node.tagName==='a').length,1);
 const recent=server();recent.details=Object.fromEntries(Array.from({length:7},(_,i)=>[i+1,{...detail3,id:i+1,version_date:'2026-11-'+String(i+10).padStart(2,'0')}]));
 recent.listOverride=params=>{
  assert.equal(params.get('limit'),'5','History must request only the latest five versions');
  assert.equal(params.get('offset'),'0','Legacy pagination must not fetch older versions');
  return {total:7,runs:Object.values(recent.details).sort((a,b)=>b.id-a.id)};
 };
 const recentStorage=new Map([['screener:history-state',JSON.stringify({runId:1,offset:50,scrollTop:120})]]);
 const recentPage=await boot(recent,{storage:recentStorage,search:'?screener_mode=history&history_run_id=1&history_offset=50'});
 assert.deepEqual(Array.from(recentPage.elements.screenerHistoryVersion.options,option=>Number(option.value)),[7,6,5,4,3]);
 assert.equal(recentPage.controller.detail.id,7,'An expired version must fall back to the latest available version');
 assert.equal(recentPage.controller.state.offset,0);
 assert.equal(recentPage.elements.screenerHistoryResults.scrollTop,0,'Expired-version scroll state must not leak into another version');
 assert(recentPage.elements.screenerHistoryStatus.textContent.includes('5'));
 assert(!recent.requests.some(url=>url.endsWith('/runs/1')),'An older linked version must not bypass the five-version limit');
 assert.equal(Object.keys(recent.details).length,7,'Display limits must not delete archive data');
 recentPage.elements.screenerHistoryVersion.value='3';await recentPage.elements.screenerHistoryVersion.emit('change');await flush();
 assert.equal(recentPage.controller.detail.id,3);
 assert.equal(recentPage.elements.screenerHistoryVersion.options.length,5);
 recentPage.controller.state.runId=1;await recentPage.controller.refresh({detailOnly:true});
 assert.equal(recentPage.controller.detail.id,7,'A forged selection must not append a sixth option');
 assert.equal(recentPage.elements.screenerHistoryVersion.options.length,5);
 const unsafe=server();unsafe.details={3:{...detail3,results:[{...item('BBB'),display_name:'<img src=x onerror=alert(1)>'}]}};
 const unsafePage=await boot(unsafe,{search:'?screener_mode=history'});
 assert(unsafePage.elements.screenerHistoryResults.textContent.includes('<img src=x onerror=alert(1)>'));
 assert(!unsafePage.elements.screenerHistoryResults.children.some(node=>node.tagName==='img'));
 console.log('History workspace behavior passed: latest-chart navigation, state, scroll, tabs, errors, races, empty results and latest-five history');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
