'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {spawnSync}=require('node:child_process');
const {installStorage,declaration,readTemplate}=require('./frontend_storage_harness.js');
const args=process.argv.slice(2),template=args[0];
const option=name=>{const i=args.indexOf(name);return i<0?undefined:args[i+1];};
const html=readTemplate(template);
const historyFile=option('--history')||path.resolve(path.dirname(template),'../static/js/screener-history.js');
const historyCode=fs.readFileSync(historyFile,'utf8');
function world(mode='available',seed={}) {
    const values=new Map(Object.entries(seed));const faults={read:mode==='denied',write:mode==='denied'||mode==='quota',remove:mode==='denied'||mode==='delete',badKey:null};
    const fail=operation=>{const error=new Error(operation+' storage unavailable');error.name=operation==='write'?'QuotaExceededError':'SecurityError';throw error;};
    const native={getItem:key=>{if(faults.read)fail('read');return values.get(String(key))??null;},setItem:(key,value)=>{if(faults.write||key===faults.badKey)fail('write');values.set(String(key),String(value));},removeItem:key=>{if(faults.remove)fail('remove');values.delete(String(key));}};
    const target={localStorage:native,console,URL,URLSearchParams,requestAnimationFrame:callback=>callback()};
    if(mode==='getter')Object.defineProperty(target,'localStorage',{get(){return fail('access');}});
    if(mode==='missing')delete target.localStorage;
    const scope=vm.createContext(target);const storage=installStorage(scope,html);
    return {scope,storage,values,faults};
}
function call(h,expression) {
    let failure=null,value;
    try{value=vm.runInContext(expression,h.scope);}catch(error){failure={name:error.name,message:error.message};}
    assert.equal(failure,null,'Storage faults must not escape into application code: '+JSON.stringify(failure));return value;
}
function remove(h,key) {
    assert.equal(vm.runInContext('typeof lsRemove',h.scope),'function','Deletion must use the same resilient storage layer');
    h.scope.key=key;return call(h,'lsRemove(key)');
}
const flush=async()=>{for(let i=0;i<50;i++)await Promise.resolve();};
function history(h) {
    class Element {
        constructor(tag='div'){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.dataset={};this.hidden=false;this.disabled=false;this.scrollTop=0;this._text='';this._value='';this.classList={contains:()=>false};}
        set textContent(value){this._text=String(value);this.children=[];}
        get textContent(){return this._text+this.children.map(item=>item.textContent).join('');}
        set value(value){this._value=String(value);}
        get value(){return this._value;}
        get options(){return this.children;}
        append(...items){this.children.push(...items);}
        appendChild(item){this.children.push(item);}
        setAttribute(name,value){this.attributes[name]=String(value);}
        addEventListener(name,handler){(this.listeners[name]??=[]).push(handler);}
        focus(){}
    }
    const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
    const elements=Object.fromEntries(ids.map(id=>[id,new Element(/Preset$|Frequency$|Version$/.test(id)?'select':'div')]));
    const location={search:'',pathname:'/api/v1/test_api/lightweight_charts_demo'};
    const window={location,history:{replaceState(_a,_b,url){location.search=url.includes('?')?'?'+url.split('?')[1]:'';}}};
    Object.assign(h.scope,{window,document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)}});
    vm.runInContext(historyCode,h.scope);
    const row={code:'AAA',display_name:'Fixture',market:'cn',asset_class:'stock'};
    const detail={id:3,preset_id:1,preset_name:'Fixture',frequency:'1day',version_date:'2026-11-20',previous_version:'2026-11-19',comparison_available:true,count:1,results:[row],added:[],removed:[],retained:[row]};
    const request=async url=>url.endsWith('/presets')?{presets:[{id:1,name:'Fixture'}]}:url.includes('/runs?')?{total:1,runs:[detail]}:detail;
    const construct=()=>new window.ScreenerHistory({request,storage:h.storage,getChartContext:()=>({symbol:'AAA',market:'cn',asset_class:'stock',frequency:'1day'}),getPresetId:()=>1});
    return {construct,elements};
}
const cases=[
    {id:'storage_denied_defaults',async run(){const h=world('denied');assert.equal(call(h,"lsGetBool('x', true)"),true);assert.equal(call(h,"lsGetString('x', 'fallback')"),'fallback');call(h,"lsSetString('x', 'value')");assert.equal(call(h,"lsGetString('x', '')"),'value');}},
    {id:'storage_quota_latest_string',async run(){const h=world('quota',{x:'old'});call(h,"lsSetString('x', 'new')");assert.equal(call(h,"lsGetString('x', '')"),'new');assert.equal(h.values.get('x'),'old');}},
    {id:'storage_quota_false_zero_empty',async run(){const h=world('quota',{flag:'1',zero:'9',blank:'old'});call(h,"lsSetBool('flag', false); lsSetString('zero', 0); lsSetString('blank', '')");assert.equal(call(h,"lsGetBool('flag', true)"),false);assert.equal(call(h,"lsGetString('zero', '')"),'0');assert.equal(call(h,"lsGetString('blank', 'fallback')"),'');}},
    {id:'storage_delete_tombstone',async run(){const h=world('delete',{x:'old',other:'keep'});assert.equal(call(h,"lsGetString('x', '')"),'old');remove(h,'x');assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');assert.equal(h.values.get('x'),'old');assert.equal(call(h,"lsGetString('other', '')"),'keep');h.faults.remove=false;remove(h,'x');assert(!h.values.has('x'));}},
    {id:'storage_read_uses_last_known',async run(){const h=world('available',{x:'known'});call(h,"lsGetString('x', '')");h.faults.read=true;assert.equal(call(h,"lsGetString('x', 'fallback')"),'known');h.faults.read=false;h.values.delete('x');assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');h.faults.read=true;assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');}},
    {id:'storage_getter_denied',async run(){const h=world('getter');assert.equal(call(h,"lsGetString('x', 'fallback')"),'fallback');call(h,"lsSetBool('x', false)");assert.equal(call(h,"lsGetBool('x', true)"),false);remove(h,'x');assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');}},
    {id:'storage_native_absent',async run(){const h=world('missing');assert.equal(call(h,"lsGetBool('x', false)"),false);call(h,"lsSetString('x', 'memory')");assert.equal(call(h,"lsGetString('x', '')"),'memory');remove(h,'x');assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');}},
    {id:'control_storage_available',async run(){const h=world();call(h,"lsSetBool('flag', true); lsSetString('name', 'sample')");assert.equal(call(h,"lsGetBool('flag', false)"),true);assert.equal(call(h,"lsGetString('name', '')"),'sample');assert.equal(h.values.get('name'),'sample');}},
    {id:'control_external_updates_visible',async run(){const h=world('available',{x:'first'});assert.equal(call(h,"lsGetString('x', '')"),'first');h.values.set('x','second');assert.equal(call(h,"lsGetString('x', '')"),'second');h.values.delete('x');assert.equal(call(h,"lsGetString('x', 'missing')"),'missing');}},
    {id:'storage_failed_key_isolated',async run(){const h=world('available',{bad:'old'});h.faults.badKey='bad';call(h,"lsSetString('bad', 'new'); lsSetString('good', 'saved')");assert.equal(h.values.get('good'),'saved');assert.equal(call(h,"lsGetString('bad', '')"),'new');h.values.set('good','external');assert.equal(call(h,"lsGetString('good', '')"),'external');}},
    {id:'storage_explicit_write_recovers',async run(){const h=world('quota',{x:'old'});call(h,"lsSetString('x', 'memory')");h.faults.write=false;h.values.set('x','external');assert.equal(call(h,"lsGetString('x', '')"),'memory');call(h,"lsSetString('x', 'saved')");assert.equal(h.values.get('x'),'saved');h.values.set('x','new external');assert.equal(call(h,"lsGetString('x', '')"),'new external');}},
    {id:'storage_history_shared_fallback',async run(){const h=world('quota',{'screener:mode':'realtime'});const fixture=history(h);const first=fixture.construct();await flush();first.mode='history';Object.assign(first.state,{runId:3,presetId:1,frequency:'1day',view:'retained',scrollTop:40});first.store(false);assert.equal(call(h,"lsGetString('screener:mode', '')"),'history');const next=fixture.construct();await flush();assert.equal(next.mode,'history');assert.equal(next.state.runId,3);assert.equal(next.state.view,'retained');assert.equal(next.state.scrollTop,40);}},
    {id:'storage_search_navigation_survives',async run(){const h=world('quota',{'search:history':'{bad JSON'});const navigation=[];h.scope.window={location:{search:'',origin:'http://local',assign:url=>navigation.push(url)}};vm.runInContext("const SEARCH_HISTORY_KEY = 'search:history'; const SEARCH_HISTORY_LIMIT = 20;\n"+['readSearchHistory','rememberSearchResult','openSearchResult'].map(name=>declaration(html,name,true)).join('\n'),h.scope);h.scope.result={code:'AAA',display_name:'Fixture',asset_class:'stock',url:'/chart?symbol=AAA'};call(h,'openSearchResult(result)');assert.equal(navigation.length,1);const values=call(h,'readSearchHistory()');assert.equal(values[0].code,'AAA');}},
    ...['available','denied','quota','delete','getter'].map(mode=>({id:'storage_ui_boot_'+mode,async run(evidence){
        const bootTemplate=option('--boot-template')||template;
        const result=spawnSync(process.execPath,[path.join(__dirname,'frontend_switch_behavior.js'),bootTemplate,'--storage-probe',mode],{encoding:'utf8',timeout:15000});
        evidence.child_exit=result.status;evidence.stderr=result.stderr.slice(-700);
        assert.equal(result.status,0,'Full-page initialization/query/reset must work with '+mode+' storage:\n'+result.stdout+result.stderr);
        assert(result.stdout.includes('"ui_usable":true'));evidence.complete_page_usable=true;
    }})),
];
(async()=>{
    const selected=option('--case');const chosen=selected?cases.filter(item=>item.id===selected):cases;if(!chosen.length)throw new Error('Unknown case: '+selected);
    const results=[];
    for(const item of chosen){const evidence={};try{await item.run(evidence);results.push({id:item.id,status:'passed',evidence});}catch(error){results.push({id:item.id,status:error.name==='AssertionError'?'failed':'harness_error',message:error.message,evidence});}}
    process.stdout.write(JSON.stringify({template,results},null,2)+'\n');if(results.some(item=>item.status==='harness_error'))process.exitCode=2;else if(results.some(item=>item.status==='failed'))process.exitCode=1;
})().catch(error=>{console.error(error.stack||error);process.exitCode=2;});
