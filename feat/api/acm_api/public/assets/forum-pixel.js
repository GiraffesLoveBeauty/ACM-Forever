(() => {
  const art=document.querySelector('.forum-pixel-art');
  if(!art)return;
  const grid=art.querySelector('.forum-pixel-grid');
  // Two 5-column glyphs, separated by one empty column.
  const rows=['01110001111','10001010000','10001010000','11111010000','10001010000','10001010000','10001001111'];
  for(const row of rows){
    for(const bit of row){
      const pixel=document.createElement('span');
      pixel.className=bit==='1'?'forum-pixel':'forum-pixel-empty';
      grid.appendChild(pixel);
    }
  }
  const pixels=[...grid.querySelectorAll('.forum-pixel')];
  const reducedMotion=window.matchMedia('(prefers-reduced-motion:reduce)');
  let pointer=null,frame=0;
  function reset(){
    pointer=null;
    if(frame){cancelAnimationFrame(frame);frame=0;}
    art.style.setProperty('--pixel-x','0px');
    art.style.setProperty('--pixel-y','0px');
    for(const pixel of pixels)pixel.style.setProperty('--pixel-near','0');
  }
  function draw(){
    frame=0;
    if(!pointer)return;
    const rect=art.getBoundingClientRect();
    if(!rect.width||!rect.height)return;
    const strength=reducedMotion.matches?0:.7;
    art.style.setProperty('--pixel-x',((pointer.x-rect.left)/rect.width-.5)*9*strength+'px');
    art.style.setProperty('--pixel-y',((pointer.y-rect.top)/rect.height-.5)*7*strength+'px');
    for(const pixel of pixels){
      const bounds=pixel.getBoundingClientRect();
      const distance=Math.hypot(bounds.x+bounds.width/2-pointer.x,bounds.y+bounds.height/2-pointer.y);
      pixel.style.setProperty('--pixel-near',String(Math.max(0,1-distance/64)));
    }
  }
  art.addEventListener('pointermove',event=>{
    if(event.pointerType==='touch')return;
    pointer={x:event.clientX,y:event.clientY};
    if(!frame)frame=requestAnimationFrame(draw);
  });
  art.addEventListener('pointerleave',reset);
  art.addEventListener('pointercancel',reset);
  reducedMotion.addEventListener('change',reset);
  window.addEventListener('blur',reset);
  window.addEventListener('scroll',reset,{passive:true});
  window.addEventListener('resize',reset);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)reset()});
})();
