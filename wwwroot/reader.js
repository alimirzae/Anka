(() => {
let book=null,rendition=null,id=null,size=100,scroll=false,dark=false;
function applyTheme(){document.body.classList.toggle("dark",dark);if(rendition)rendition.themes.select(dark?"dark":"light");localStorage.setItem("anka-dark",dark?"1":"0");}
dark=localStorage.getItem("anka-dark")==="1";
window.ankaReader={
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
    if(text&&confirm("نشان‌گذاری متن انتخاب‌شده؟ / Highlight?")){
      rendition.annotations.highlight(cfi,{},()=>{},"anka-highlight",{fill:"#efd35b","fill-opacity":"0.4"});
      const key="anka-highlights-"+id;
      const rows=JSON.parse(localStorage.getItem(key)||"[]");rows.push({cfi,text});
      localStorage.setItem(key,JSON.stringify(rows));
    }
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
 close(){if(rendition){rendition.destroy();rendition=null;}if(book){book.destroy();book=null;}id=null;}
};
applyTheme();
})();
