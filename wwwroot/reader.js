(() => {
let book=null,rendition=null,id=null,size=100,scroll=false,dark=false,selection=null,toolbar=null;
function applyTheme(){document.body.classList.toggle("dark",dark);if(rendition)rendition.themes.select(dark?"dark":"light");localStorage.setItem("anka-dark",dark?"1":"0");}
dark=localStorage.getItem("anka-dark")==="1";
window.ankaReader={
 async upload(title,author,language){
   const input=document.getElementById("uploadFile");
   const file=input?.files?.[0];
   if(!file)return "ابتدا یک فایل EPUB انتخاب کنید.";
   if(!file.name.toLowerCase().endsWith(".epub")||file.size>50*1024*1024)return "فقط فایل EPUB تا حجم ۵۰ مگابایت مجاز است.";
   const form=new FormData();
   form.append("file",file);form.append("title",title);form.append("author",author);form.append("language",language);
   const response=await fetch("/api/books",{method:"POST",body:form});
   if(response.ok)return "ok";
   const result=await response.json().catch(()=>({}));
   return result.error||("Upload failed: "+response.status);
 },
 async open(bookId){
  this.close();id=bookId;
  if(typeof ePub!=="function"){throw new Error("EPUB.js is not available.");}
  book=ePub("/api/books/"+encodeURIComponent(id)+"/file");
  rendition=book.renderTo("epub",{width:"100%",height:"100%",spread:"none",flow:scroll?"scrolled-doc":"paginated",allowScriptedContent:false});
  rendition.themes.register("light",{body:{background:"#fff",color:"#1d2a43"}});
  rendition.themes.register("dark",{body:{background:"#192333",color:"#edf3ff"}});
  applyTheme();rendition.themes.fontSize(size+"%");
  rendition.on("relocated",loc=>{if(loc?.start?.cfi)localStorage.setItem("anka-progress-"+id,loc.start.cfi);});
  rendition.on("selected",(cfi,contents)=>{
    const text=contents.window.getSelection()?.toString().trim();
    if(!text)return;
    selection={cfi,text};
    showSelectionToolbar();
  });
  await book.ready;
  const last=localStorage.getItem("anka-progress-"+id);
  try{await rendition.display(last||undefined);}catch{await rendition.display();}
  for(const row of JSON.parse(localStorage.getItem("anka-highlights-"+id)||"[]")){
   try{rendition.annotations.highlight(row.cfi,{},()=>{},"anka-highlight",{fill:"#efd35b","fill-opacity":"0.4"});}catch{}
  }
 },
 next(){return rendition?.next();},prev(){return rendition?.prev();},
 font(delta){size=Math.max(70,Math.min(190,size+delta));rendition?.themes.fontSize(size+"%");},
 flow(){scroll=!scroll;if(rendition){rendition.flow(scroll?"scrolled-doc":"paginated");}},
 toggleTheme(){dark=!dark;applyTheme();},
 close(){hideSelectionToolbar();selection=null;if(rendition){rendition.destroy();rendition=null;}if(book){book.destroy();book=null;}id=null;}
};
function hideSelectionToolbar(){if(toolbar){toolbar.remove();toolbar=null;}}
function showSelectionToolbar(){
 hideSelectionToolbar();
 if(!selection)return;
 toolbar=document.createElement("div");
 toolbar.className="anka-selection-tools";
 toolbar.setAttribute("role","toolbar");
 toolbar.setAttribute("aria-label","Selected text actions");
 const snippet=document.createElement("span");
 snippet.className="anka-selection-text";
 snippet.textContent=selection.text.length>95?selection.text.slice(0,95)+"…":selection.text;
 toolbar.appendChild(snippet);
 const add=(label,fn)=>{
   const btn=document.createElement("button");
   btn.type="button";btn.textContent=label;
   btn.addEventListener("click",fn);toolbar.appendChild(btn);
 };
 add("✎ Highlight",()=>{
   if(!rendition||!selection)return;
   const {cfi,text}=selection;
   rendition.annotations.highlight(cfi,{},()=>{},"anka-highlight",{fill:"#efd35b","fill-opacity":"0.4"});
   const key="anka-highlights-"+id;
   let rows=[];try{rows=JSON.parse(localStorage.getItem(key)||"[]");}catch{}
   if(!rows.some(v=>v.cfi===cfi))rows.push({cfi,text});
   localStorage.setItem(key,JSON.stringify(rows));
   hideSelectionToolbar();
 });
 add("📖 Dictionary",()=>{
   if(!selection)return;
   const term=selection.text.split(/\\s+/).slice(0,5).join(" ");
   window.open("https://en.wiktionary.org/wiki/"+encodeURIComponent(term),"_blank","noopener,noreferrer");
 });
 const target=document.createElement("select");
 target.setAttribute("aria-label","Translation target");
 [["fa","فارسی"],["tr","Türkçe"],["az","Azərbaycanca"],["en","English"]].forEach(([value,label])=>{
  const opt=document.createElement("option");opt.value=value;opt.textContent=label;target.appendChild(opt);
 });
 target.value=localStorage.getItem("anka-translation-target")||"fa";
 target.addEventListener("change",()=>localStorage.setItem("anka-translation-target",target.value));
 toolbar.appendChild(target);
 add("🌐 Translate",()=>{
   if(!selection)return;
   // Text leaves this site only when the reader explicitly requests translation.
   window.open("https://translate.google.com/?sl=auto&tl="+encodeURIComponent(target.value)+"&text="+encodeURIComponent(selection.text)+"&op=translate","_blank","noopener,noreferrer");
 });
 add("×",hideSelectionToolbar);
 document.body.appendChild(toolbar);
}
applyTheme();
})();
