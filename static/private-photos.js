const privatePhotoCache=new Map();
async function privatePhoto(path){
 if(!path||!path.startsWith('/uploads/')||!token)return null;
 if(privatePhotoCache.has(path))return privatePhotoCache.get(path);
 const response=await fetch(path,{headers:{Authorization:'Bearer '+token},cache:'no-store'});
 if(!response.ok)return null;
 const url=URL.createObjectURL(await response.blob());
 privatePhotoCache.set(path,url);
 return url;
}
async function loadPrivatePhotos(root){
 const nodes=[...root.querySelectorAll('[data-photo]')];
 await Promise.all(nodes.map(async node=>{
  const path=node.dataset.photo;
  try{
   const url=await privatePhoto(path);
   if(url&&node.isConnected&&node.dataset.photo===path)node.style.backgroundImage='url("'+url+'")';
  }catch(error){console.warn('Unable to load private photo');}
 }));
}
function clearPrivatePhotos(){
 for(const url of privatePhotoCache.values())URL.revokeObjectURL(url);
 privatePhotoCache.clear();
}
