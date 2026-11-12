(() => {
 let element=null, start=null, callback=null, pointerId=null;
 const isInput=target=>!!target?.closest?.('button,a,input,textarea,select,[contenteditable="true"]');
 function down(event) {
  if(event.button!==0 || isInput(event.target))return;
  start={x:event.clientX,y:event.clientY,time:Date.now(),target:event.target};
  pointerId=event.pointerId;
 }
 function up(event) {
  if(!start || pointerId!==event.pointerId)return;
  const dx=event.clientX-start.x,dy=event.clientY-start.y;
  const valid=Math.abs(dx)>=65 && Math.abs(dx)>Math.abs(dy)*1.3 && Date.now()-start.time<1200;
  start=null;pointerId=null;
  if(!valid || window.getSelection()?.toString().trim())return;
  const rtl=element?.getAttribute('dir')==='rtl';
  const next=rtl?dx>0:dx<0;
  callback?.invokeMethodAsync(next?'TurnForward':'TurnBackward').catch(()=>{});
 }
 function cancel(){start=null;pointerId=null;}
 const key=(id,type)=>'anka-reader-'+type+'-'+id;
 function selectedRangeInside(id){
  const root=document.getElementById(id),selection=window.getSelection();
  if(!root || !selection || selection.isCollapsed || !selection.rangeCount)return null;
  const range=selection.getRangeAt(0);
  if(!root.contains(range.commonAncestorContainer))return null;
  return {root,range,selection};
 }
 function readHighlights(id,page){
  try {const rows=JSON.parse(localStorage.getItem(key(id,'highlights'))||'[]');
   return Array.isArray(rows)?rows.filter(r=>r.page===page):[];
  }catch{return [];}
 }
 function applyHighlight(paragraph,start,end){
  if(!paragraph || start<0 || end<=start)return;
  const walker=document.createTreeWalker(paragraph,NodeFilter.SHOW_TEXT);
  const nodes=[];let node,offset=0;
  while((node=walker.nextNode())){nodes.push({node,start:offset,end:offset+node.length});offset+=node.length;}
  for(const item of nodes.filter(x=>x.end>start && x.start<end).reverse()){
   const from=Math.max(start-item.start,0),to=Math.min(end-item.start,item.node.length);
   if(to<=from)continue;
   const r=document.createRange();r.setStart(item.node,from);r.setEnd(item.node,to);
   const mark=document.createElement('mark');mark.className='anka-book-highlight';
   try{r.surroundContents(mark)}catch{}
  }
 }
 window.ankaReading={
  bind(dotnet,id){
   this.unbind();callback=dotnet;element=document.getElementById(id);
   element?.addEventListener('pointerdown',down,{passive:true});
   element?.addEventListener('pointerup',up,{passive:true});
   element?.addEventListener('pointercancel',cancel,{passive:true});
  },
  unbind(){
   element?.removeEventListener('pointerdown',down);
   element?.removeEventListener('pointerup',up);
   element?.removeEventListener('pointercancel',cancel);
   element=null;callback=null;cancel();
  },
  resetScroll(id){const el=document.getElementById(id);if(el)el.scrollTop=0;},
  getBookmark(id){const value=localStorage.getItem(key(id,'bookmark'));return value===null?null:Number(value);},
  setBookmark(id,page){if(page===null)localStorage.removeItem(key(id,'bookmark'));else localStorage.setItem(key(id,'bookmark'),String(page));},
  highlightSelection(rootId,id,page){
   const selection=selectedRangeInside(rootId);if(!selection)return;
   const paragraph=selection.range.startContainer.parentElement?.closest('p');
   if(!paragraph || !selection.range.endContainer.parentElement?.closest('p')?.isSameNode(paragraph))return;
   const paragraphs=[...selection.root.querySelectorAll('p')],index=paragraphs.indexOf(paragraph);
   if(index<0)return;
   const before=document.createRange();before.selectNodeContents(paragraph);before.setEnd(selection.range.startContainer,selection.range.startOffset);
   const start=before.toString().length, length=selection.range.toString().length;
   const rows=readHighlights(id,page);rows.push({page,index,start,end:start+length});
   let all=[];try{all=JSON.parse(localStorage.getItem(key(id,'highlights'))||'[]')}catch{}
   all.push({page,index,start,end:start+length});
   localStorage.setItem(key(id,'highlights'),JSON.stringify(all.slice(-300)));
   selection.selection.removeAllRanges();this.restoreHighlights(rootId,id,page);
  },
  restoreHighlights(rootId,id,page){
   const root=document.getElementById(rootId);if(!root)return;
   // Rendered paragraphs are fresh on every Blazor page change.
   const paragraphs=[...root.querySelectorAll('p')];
   for(const row of readHighlights(id,page).reverse()){
    const p=paragraphs[row.index];
    if(p && !p.querySelector('mark'))applyHighlight(p,row.start,row.end);
   }
  },
  translateSelection(rootId){
   const sel=selectedRangeInside(rootId);if(!sel)return;
   const target=localStorage.getItem('anka-translation-target')||'fa';
   const text=sel.selection.toString().trim().slice(0,3000);
   if(text)window.open('https://translate.google.com/?sl=auto&tl='+encodeURIComponent(target)+'&text='+encodeURIComponent(text)+'&op=translate','_blank','noopener,noreferrer');
  }
 };
})();