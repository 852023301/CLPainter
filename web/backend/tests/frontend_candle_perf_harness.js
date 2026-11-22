'use strict';
const vm=require('node:vm');
function declaration(source,name){const at=new RegExp('\\bfunction\\s+'+name+'\\s*\\(').exec(source);if(!at)throw new Error('Missing source function '+name);for(let end=source.indexOf('}',at.index);end>=0;end=source.indexOf('}',end+1)){const value=source.slice(at.index,end+1);try{new vm.Script(value);return value;}catch(e){if(!(e instanceof SyntaxError))throw e;}}throw new Error('Incomplete '+name);}
function context(source,data,options={}){
 const state={calls:[],checksum:0,markers:[],range:null},series={};
 const record=(...entry)=>{if(options.record)state.calls.push(entry);state.checksum++;};
 const panel={chart:{subscribeCrosshairMove(fn){panel.crosshair=fn;}},valueLabel:{style:{}},labelRenderer:time=>record('panel-label',time),lookup:{},primarySeries:{}};
 const scope={candleData:data,candlestickSeries:series,panels:[panel],isSyncingCrosshair:false,currentPrecision:options.precision??3,gapMarkers:options.gaps||[],showGapsToggle:{checked:Boolean(options.showGaps)},chart:{setCrosshairPosition:(value,time)=>record('main-position',value,time),clearCrosshairPosition:()=>record('main-clear'),timeScale:()=>({getVisibleRange:()=>state.range})},syncSubCrosshairs:(time)=>record('sync',time),updateTooltip:param=>{const row=param.seriesData.get(series);state.lastRow=row;state.checksum+=row?.close||0;record('tooltip',row?JSON.stringify(row):null);},console};
 vm.createContext(scope);
 if(options.sameRealmData){scope.encodedCandles=JSON.stringify(data);vm.runInContext("candleData = JSON.parse(encodedCandles)",scope);delete scope.encodedCandles;}
 let access=null,buildMs=0;
 if(source.includes('function createCandleAccess(')){
  vm.runInContext(declaration(source,'createCandleAccess'),scope);
  const start=process.hrtime.bigint();access=scope.createCandleAccess(scope.candleData);buildMs=Number(process.hrtime.bigint()-start)/1e6;scope.candleAccess=access;
 }
 const start=source.indexOf('        // 各面板 -> 主图 + 其他面板'),end=source.indexOf('        // Tooltip 更新函数',start);if(start<0||end<start)throw new Error('Missing original crosshair segment');vm.runInContext(source.slice(start,end),scope);
 scope.candlestickSeries.setMarkers=markers=>{state.markers=markers;state.checksum+=markers.length;record('markers',JSON.stringify(markers));};
 vm.runInContext(declaration(source,'updateHighLowMarkers'),scope);
 return {scope,state,access,buildMs,crosshair:panel.crosshair,markers:range=>{state.range=range;scope.updateHighLowMarkers();}};
}
module.exports={context,declaration};
