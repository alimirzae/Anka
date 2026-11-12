(() => {
 const allowed = new Set(["fa","tr","az-Latn","az-Arab"]);
 const safe = lang => allowed.has(lang) ? lang : "az-Arab";
 let keyHandler=null;
 window.ankaSite = {
  getLanguage() { return safe(localStorage.getItem("anka-ui-lang")); },
  setLanguage(lang) {
   lang=safe(lang);
   localStorage.setItem("anka-ui-lang", lang);
   document.documentElement.lang=lang;
   document.documentElement.dir=(lang==="fa"||lang==="az-Arab")?"rtl":"ltr";
  },
  getPage(id) {
    const n=Number(localStorage.getItem("anka-page-"+id));
    return Number.isFinite(n) ? Math.max(0,Math.floor(n)) : 0;
  },
  savePage(id,page) { localStorage.setItem("anka-page-"+id, String(page)); },
  bindKeys(dotnet) {
    if(keyHandler)document.removeEventListener("keydown",keyHandler);
    keyHandler=e=>{
      if(e.altKey||e.ctrlKey||e.metaKey||["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName))return;
      if(e.key==="ArrowRight" || e.key==="ArrowLeft"){
        e.preventDefault();
        dotnet.invokeMethodAsync(e.key==="ArrowRight"?"TurnForward":"TurnBackward").catch(()=>{});
      }
    };
    document.addEventListener("keydown",keyHandler);
  },
  unbindKeys() { if(keyHandler)document.removeEventListener("keydown",keyHandler);keyHandler=null; }
 };
 document.documentElement.lang=safe(localStorage.getItem("anka-ui-lang"));
 document.documentElement.dir=["fa","az-Arab"].includes(document.documentElement.lang)?"rtl":"ltr";
})();