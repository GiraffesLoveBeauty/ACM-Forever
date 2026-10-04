(() => {
  const art=document.querySelector('.forum-algorithm-art');
  if(!art)return;
  const graph=art.querySelector('.algorithm-graph');
  const points=[{id:'s',x:50,y:151},{id:'u',x:114,y:83},{id:'a',x:177,y:47},{id:'b',x:248,y:63},{id:'c',x:323,y:96},{id:'t',x:348,y:174},{id:'v',x:198,y:130},{id:'d',x:256,y:167},{id:'e',x:285,y:232},{id:'f',x:155,y:215},{id:'g',x:84,y:227},{id:'h',x:312,y:32}];
  const edges=[['s','u',7],['s','v',3],['s','g',10],['u','a',4],['u','v',6],['a','b',8],['a','h',13],['b','c',7],['b','v',9],['c','t',8],['c','h',3],['v','d',2],['v','f',6],['d','t',4],['d','e',7],['f','e',8],['f','g',4],['g','e',16],['e','t',9],['b','d',9],['h','t',16]];
  const byId=Object.fromEntries(points.map(point=>[point.id,point]));
  const distances=Object.fromEntries(points.map(point=>[point.id,Infinity]));
  const previous={},remaining=new Set(points.map(point=>point.id));
  distances.s=0;
  while(remaining.size){
    const current=[...remaining].sort((a,b)=>distances[a]-distances[b])[0];
    remaining.delete(current);
    for(const [a,b,weight]of edges){
      const next=a===current?b:b===current?a:null;
      if(next&&remaining.has(next)&&distances[current]+weight<distances[next]){
        distances[next]=distances[current]+weight;
        previous[next]=current;
      }
    }
  }
  const segmentKey=(a,b)=>[a,b].sort().join(':');
  function svgElement(tag,attributes,parent,text){
    const element=document.createElementNS('http://www.w3.org/2000/svg',tag);
    for(const [key,value]of Object.entries(attributes))element.setAttribute(key,String(value));
    if(text!==undefined)element.textContent=text;
    parent.appendChild(element);
    return element;
  }
  const defs=svgElement('defs',{},graph);
  const pathGradient=svgElement('linearGradient',{id:'forum-graph-path',x1:0,y1:0,x2:1,y2:.2},defs);
  for(const [offset,color]of [[0,'#a9c88c'],[.6,'#d8ed9a'],[1,'#b9e3c3']])svgElement('stop',{offset,'stop-color':color},pathGradient);
  const nodeGradient=svgElement('radialGradient',{id:'forum-graph-node',cx:.34,cy:.2,r:.9},defs);
  for(const [offset,color]of [[0,'#f0f4ca'],[.55,'#cada96'],[1,'#7fa575']])svgElement('stop',{offset,'stop-color':color},nodeGradient);
  const glow=svgElement('filter',{id:'forum-graph-glow',x:'-30%',y:'-80%',width:'160%',height:'260%'},defs);
  svgElement('feGaussianBlur',{stdDeviation:3.2},glow);
  const floor=svgElement('g',{class:'graph-floor',transform:'translate(0,20)'},graph);
  const network=svgElement('g',{},graph);
  const routeGroup=svgElement('g',{},graph);
  const nodesGroup=svgElement('g',{},graph);
  const labelsGroup=svgElement('g',{},graph);
  const edgeViews=[],nodeViews=new Map(),secondaryWeights=[];
  for(const [a,b,weight]of edges){
    const p=byId[a],q=byId[b],key=segmentKey(a,b);
    const attributes={x1:p.x,y1:p.y,x2:q.x,y2:q.y};
    svgElement('line',{...attributes,class:'graph-floor-edge'},floor);
    const line=svgElement('line',{...attributes,class:'graph-edge'},network);
    edgeViews.push({a,b,weight,key,line});
    if(['u:a','b:c','c:h','e:f'].includes(key)){
      const label=svgElement('text',{x:(p.x+q.x)/2,y:(p.y+q.y)/2-7,class:'graph-weight graph-weight-secondary'},network,String(weight));
      secondaryWeights.push({key,label});
    }
  }
  const haze=svgElement('path',{class:'graph-path-haze'},routeGroup);
  const core=svgElement('path',{class:'graph-path-core'},routeGroup);
  for(const point of points){
    const floorDot=svgElement('circle',{cx:point.x,cy:point.y,r:3,class:'graph-floor-node'},floor);
    svgElement('line',{x1:point.x,y1:point.y+7,x2:point.x,y2:point.y+19,class:'graph-stem'},network);
    const group=svgElement('g',{class:'graph-node','data-node':point.id},nodesGroup);
    svgElement('circle',{cx:point.x,cy:point.y,r:20,class:'graph-node-halo'},group);
    svgElement('circle',{cx:point.x,cy:point.y,r:14,class:'graph-node-ring'},group);
    const sphere=svgElement('circle',{cx:point.x,cy:point.y,r:6,class:'graph-node-back'},group);
    const label=svgElement('text',{x:point.x,y:point.y-14,class:'graph-node-label-secondary'},group,point.id);
    nodeViews.set(point.id,{group,sphere,label,floorDot});
  }
  svgElement('path',{class:'graph-ring-arc',d:'M320 127A46 46 0 0 1 380 185'},graph);
  svgElement('path',{class:'graph-callout-line',d:'M348 184L343 208L310 208'},graph);
  svgElement('rect',{class:'graph-callout-surface',x:300,y:202,width:67,height:23,rx:5},graph);
  svgElement('text',{class:'graph-callout-text',x:313,y:218},graph,'✓ AC');
  const distanceCaption=svgElement('text',{class:'graph-trace-caption',x:81,y:274},graph);
  const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let target='',hovered=null,lastPointer=null,pointerFrame=0;
  function showRoute(nextTarget){
    if(nextTarget===target)return;
    target=nextTarget;
    const route=[];
    for(let node=target;node;node=previous[node])route.unshift(node);
    const active=new Set(route);
    const routeKeys=new Set(route.slice(1).map((id,index)=>segmentKey(route[index],id)));
    const path=route.map((id,index)=>{const point=byId[id];return(index?'L':'M')+point.x+' '+point.y}).join('');
    haze.setAttribute('d',path);core.setAttribute('d',path);
    for(const point of points){
      const selected=active.has(point.id),view=nodeViews.get(point.id);
      view.group.classList.toggle('is-path',selected);
      view.sphere.setAttribute('r',selected?9:6);
      view.sphere.setAttribute('class',selected?'graph-node-front':'graph-node-back');
      view.label.setAttribute('y',selected?point.y:point.y-14);
      view.label.setAttribute('class',selected?'graph-node-label':'graph-node-label-secondary');
      view.floorDot.setAttribute('r',selected?5:3);
    }
    labelsGroup.replaceChildren();
    for(const {a,b,weight,key}of edgeViews){
      if(!routeKeys.has(key))continue;
      const p=byId[a],q=byId[b];
      svgElement('text',{x:(p.x+q.x)/2,y:(p.y+q.y)/2-7,class:'graph-weight'},labelsGroup,String(weight));
    }
    for(const {key,label}of secondaryWeights)label.style.display=routeKeys.has(key)?'none':'';
    distanceCaption.textContent='dist['+target+'] = '+distances[target]+';';
    graph.setAttribute('aria-label','十二个节点的加权图，最短路径 '+route.join(' → ')+'，总权重 '+distances[target]);
  }
  function highlightNode(id){
    if(id===hovered)return;
    if(hovered)nodeViews.get(hovered).group.classList.remove('is-hover');
    hovered=id;
    if(hovered)nodeViews.get(hovered).group.classList.add('is-hover');
    showRoute(hovered||'t');
  }
  function distanceToSegment(pointer,p,q){
    const dx=q.x-p.x,dy=q.y-p.y,length=dx*dx+dy*dy;
    const amount=length?Math.max(0,Math.min(1,((pointer.x-p.x)*dx+(pointer.y-p.y)*dy)/length)):0;
    return Math.hypot(pointer.x-p.x-amount*dx,pointer.y-p.y-amount*dy);
  }
  function drawPointer(){
    pointerFrame=0;
    if(!lastPointer)return;
    const rect=art.getBoundingClientRect(),matrix=graph.getScreenCTM();
    if(!rect.width||!rect.height||!matrix)return;
    const pointer={x:lastPointer.x,y:lastPointer.y};
    const localX=Math.max(0,Math.min(1,(pointer.x-rect.left)/rect.width));
    const localY=Math.max(0,Math.min(1,(pointer.y-rect.top)/rect.height));
    const screenPoints=Object.fromEntries(points.map(point=>[point.id,new DOMPoint(point.x,point.y).matrixTransform(matrix)]));
    let nearest=null,nearestDistance=Infinity;
    for(const point of points){
      const screen=screenPoints[point.id],distance=Math.hypot(screen.x-pointer.x,screen.y-pointer.y);
      nodeViews.get(point.id).group.style.setProperty('--node-near',String(Math.max(0,1-distance/64)));
      if(distance<nearestDistance){nearest=point.id;nearestDistance=distance;}
    }
    // A slightly larger exit radius keeps nodes stable as the parallax settles.
    if(hovered){
      const screen=screenPoints[hovered],distance=Math.hypot(screen.x-pointer.x,screen.y-pointer.y);
      if(distance<=24&&distance<nearestDistance+6){nearest=hovered;nearestDistance=distance;}
    }
    highlightNode(nearestDistance<=(nearest===hovered?24:18)?nearest:null);
    for(const edge of edgeViews){
      const distance=distanceToSegment(pointer,screenPoints[edge.a],screenPoints[edge.b]);
      edge.line.style.setProperty('--edge-near',String(Math.max(0,1-distance/58)));
    }
    const strength=reducedMotion.matches?0:.75;
    art.style.setProperty('--graph-x',((localX*2-1)*7*strength).toFixed(2)+'px');
    art.style.setProperty('--graph-y',((localY*2-1)*5*strength).toFixed(2)+'px');
    art.style.setProperty('--graph-roll',((localX*2-1)*1.4*strength).toFixed(2)+'deg');
    art.style.setProperty('--pointer-x',(localX*100).toFixed(2)+'%');
    art.style.setProperty('--pointer-y',(localY*100).toFixed(2)+'%');
    art.style.setProperty('--pointer-active','1');
  }
  function queuePointer(){if(lastPointer&&!pointerFrame)pointerFrame=requestAnimationFrame(drawPointer)}
  function followPointer(event){
    if(event.pointerType==='touch')return;
    lastPointer={x:event.clientX,y:event.clientY};queuePointer();
  }
  function resetPointer(){
    lastPointer=null;
    if(pointerFrame){cancelAnimationFrame(pointerFrame);pointerFrame=0;}
    art.style.setProperty('--graph-x','0px');art.style.setProperty('--graph-y','0px');
    art.style.setProperty('--graph-roll','0deg');art.style.setProperty('--pointer-active','0');
    for(const view of nodeViews.values())view.group.style.setProperty('--node-near','0');
    for(const edge of edgeViews)edge.line.style.setProperty('--edge-near','0');
    highlightNode(null);showRoute('t');
  }
  showRoute('t');
  art.addEventListener('pointerenter',followPointer);
  art.addEventListener('pointermove',followPointer);
  art.addEventListener('pointerleave',resetPointer);
  art.addEventListener('pointercancel',resetPointer);
  reducedMotion.addEventListener('change',queuePointer);
  window.addEventListener('blur',resetPointer);
  window.addEventListener('scroll',resetPointer,{passive:true});
  window.addEventListener('resize',resetPointer);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)resetPointer()});
})();
