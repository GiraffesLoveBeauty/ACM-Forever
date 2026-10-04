(() => {
  const artwork=[...document.querySelectorAll('.community-header-art')];
  if(!artwork.length)return;
  const reducedMotion=window.matchMedia('(prefers-reduced-motion:reduce)');
  function svgElement(tag,attributes,parent,text){
    const element=document.createElementNS('http://www.w3.org/2000/svg',tag);
    for(const [key,value]of Object.entries(attributes))element.setAttribute(key,String(value));
    if(text!==undefined)element.textContent=text;
    parent.appendChild(element);
    return element;
  }
  for(const art of artwork){
    const svg=art.querySelector('.header-art-scene');
    const anchors=[];
    function path(d,className){return svgElement('path',{d,class:className},svg)}
    function node(x,y,label){
      const group=svgElement('g',{class:'header-art-node'},svg);
      svgElement('circle',{cx:x,cy:y,r:21,class:'header-art-halo'},group);
      svgElement('circle',{cx:x,cy:y,r:7,class:'header-art-dot'},group);
      if(label)svgElement('text',{x,y:y-19},group,label);
      anchors.push({x,y,element:group});
    }
    if(svg.dataset.headerScene==='podium'){
      path('M26 141L141 172L301 140M53 126L166 153L280 128','header-art-floor');
      path('M93 83Q154 47 218 25','header-art-route');
      for(const [x,top,label]of [[79,96,'03'],[141,66,'02'],[210,38,'01']]){
        const group=svgElement('g',{class:'header-art-step'},svg);
        svgElement('path',{d:'M'+x+' '+top+'l41 -11 27 14 -40 12Z',class:'header-art-step-top'},group);
        svgElement('path',{d:'M'+x+' '+top+'l28 15v'+(137-top)+'l-28 -14Z',class:'header-art-step-front'},group);
        svgElement('path',{d:'M'+(x+28)+' '+(top+15)+'l40 -12v'+(137-top)+'l-40 12Z',class:'header-art-step-side'},group);
        svgElement('text',{x:x+24,y:top-21,class:'header-art-rank'},group,label);
        anchors.push({x:x+34,y:top+32,element:group});
      }
      node(218,25,'');
    }else if(svg.dataset.headerScene==='journey'){
      path('M44 143Q97 28 167 107T294 58M49 156Q97 41 168 120T294 71','header-art-traces');
      path('M44 128Q96 11 164 92T287 42','header-art-route');
      node(73,76,'think');node(164,92,'code');node(287,42,'AC');
      svgElement('text',{x:205,y:166,class:'header-art-note'},svg,'one step at a time');
    }
    let pointer=null,frame=0;
    function reset(){
      pointer=null;
      if(frame){cancelAnimationFrame(frame);frame=0;}
      art.style.setProperty('--header-art-x','0px');art.style.setProperty('--header-art-y','0px');
      for(const anchor of anchors)anchor.element.style.setProperty('--header-art-near','0');
    }
    function draw(){
      frame=0;
      if(!pointer)return;
      const bounds=art.getBoundingClientRect(),matrix=svg.getScreenCTM();
      if(!bounds.width||!bounds.height||!matrix)return;
      const strength=reducedMotion.matches?0:.7;
      art.style.setProperty('--header-art-x',((pointer.x-bounds.left)/bounds.width-.5)*10*strength+'px');
      art.style.setProperty('--header-art-y',((pointer.y-bounds.top)/bounds.height-.5)*8*strength+'px');
      for(const anchor of anchors){
        const point=new DOMPoint(anchor.x,anchor.y).matrixTransform(matrix);
        const distance=Math.hypot(point.x-pointer.x,point.y-pointer.y);
        anchor.element.style.setProperty('--header-art-near',String(Math.max(0,1-distance/70)));
      }
    }
    art.addEventListener('pointermove',event=>{
      if(event.pointerType==='touch')return;
      pointer={x:event.clientX,y:event.clientY};
      if(!frame)frame=requestAnimationFrame(draw);
    });
    art.addEventListener('pointerleave',reset);art.addEventListener('pointercancel',reset);
    reducedMotion.addEventListener('change',reset);window.addEventListener('blur',reset);
    window.addEventListener('scroll',reset,{passive:true});window.addEventListener('resize',reset);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)reset()});
  }
})();
