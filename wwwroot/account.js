(() => {
 async function post(url,body) {
  const response=await fetch(url,{
   method:"POST",credentials:"same-origin",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(body)
  });
  const result=await response.json().catch(()=>({}));
  return response.ok ? {...result,ok:true} : {ok:false,error:result.error||("HTTP "+response.status)};
 }
 window.ankaAccount={
  register:(email,password,name)=>post("/api/account/register",{email,password,name}),
  login:(email,password,name)=>post("/api/account/login",{email,password,name}),
  logout:()=>post("/api/account/logout",{}),
  async getShelfDetails(){
   const me=await this.me();
   if(!me.authenticated)return {authenticated:false,books:[]};
   const [shelfResponse,booksResponse]=await Promise.all([
     fetch("/api/me/shelf",{credentials:"same-origin"}),
     fetch("/api/books",{credentials:"same-origin"})
   ]);
   if(!shelfResponse.ok||!booksResponse.ok)return {authenticated:true,books:[]};
   const ids=await shelfResponse.json(),books=await booksResponse.json();
   const keys=new Set(ids);
   return {authenticated:true,books:books.filter(b=>keys.has(b.id))};
  },
  async addShelf(bookId){const r=await fetch("/api/me/shelf/"+encodeURIComponent(bookId),{method:"POST",credentials:"same-origin"});return {ok:r.ok,status:r.status};},
  async me(){const r=await fetch("/api/account/me",{credentials:"same-origin"});return r.ok?await r.json():{authenticated:false};}
 };
})();