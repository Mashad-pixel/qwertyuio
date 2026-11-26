
const $=s=>document.querySelector(s),reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x)),lerp=(a,b,t)=>a+(b-a)*t;
const eo3=x=>1-Math.pow(1-clamp(x),3);
const eob=x=>{x=clamp(x);return 1+2.9*Math.pow(x-1,3)+1.9*Math.pow(x-1,2)};
const spring=x=>x<=0?0:1-Math.exp(-6*x)*Math.cos(16*x);

/* ---------- DOM: headline, tracker, buttons ---------- */
const h1=$('#h1');
['ORDER PLACED','SUCCESSFULLY!'].forEach((w,li)=>{const ln=document.createElement('span');ln.className='ln';
 [...w].forEach((ch,i)=>{const s=document.createElement('span');s.className='l';s.textContent=ch;s.style.setProperty('--i',i+li*8);ln.appendChild(s)});h1.appendChild(ln)});
const QS=new URLSearchParams(location.search),ORDER=QS.get('receipt')||'SO-'+(100000+Math.floor(Math.random()*899999));
const ORDER_ID=Number(QS.get('order_id'));
$('#copy').textContent=ORDER;
$('#copy').onclick=()=>{try{navigator.clipboard.writeText(ORDER)}catch(e){}$('#copied').textContent='Copied';setTimeout(()=>$('#copied').textContent='Tap to copy',1800)};
const IC=['<path d="M5 12.5l4.2 4.2L19 7"/>','<path d="M3 18h18M5 18a7 7 0 0114 0M12 8V6"/>','<circle cx="6" cy="17" r="2.8"/><circle cx="18" cy="17" r="2.8"/><path d="M6 17h5l3-7h3M9 10h3"/>','<path d="M4 11l8-7 8 7v9H4zM10 20v-5h4v5"/>'];
const NM=['Order confirmed','Preparing','Out for delivery','Delivered'];
const MSG=['Order confirmed. The kitchen has your ticket.','Our chefs are plating your meal.','Your rider is on the way, about 18 minutes out.','Delivered. Enjoy your meal.'];
$('#steps').innerHTML=NM.map((n,i)=>`<div class="st"><div class="ic"><svg viewBox="0 0 24 24">${IC[i]}</svg></div>${n}</div>`).join('');
const stEls=[...document.querySelectorAll('.st')];
function setStep(n){stEls.forEach((e,i)=>{e.classList.toggle('done',i<=n);e.classList.toggle('now',i===n&&n<3)});
 $('#fill').style.width=(n<0?0:n/3*100)+'%';$('#status').textContent=n<0?'':MSG[n]}
const timers=[];const later=(f,ms)=>timers.push(setTimeout(f,ms));
let tt;function toast(m){const e=$('#toast');e.textContent=m;e.classList.add('on');clearTimeout(tt);tt=setTimeout(()=>e.classList.remove('on'),2600)}
document.querySelectorAll('.btn').forEach(b=>b.addEventListener('click',e=>{const r=b.getBoundingClientRect(),d=Math.max(r.width,r.height)*2.2,s=document.createElement('span');
 s.className='rip';s.style.cssText=`width:${d}px;height:${d}px;left:${(e.clientX||r.left+r.width/2)-r.left-d/2}px;top:${(e.clientY||r.top+r.height/2)-r.top-d/2}px`;
 b.appendChild(s);s.onanimationend=()=>s.remove()}));
/* Both buttons leave the page. Track opens this order on the orders page; Continue goes to the menu. */
const goTo=(url,msg)=>{toast(msg);setTimeout(()=>{location.href=url},450)};
$('#trackBtn').addEventListener('click',()=>goTo(Number.isInteger(ORDER_ID)&&ORDER_ID>0?`./tracking.html?order_id=${ORDER_ID}`:'./tracking.html','Opening your orders…'));
$('#contBtn').addEventListener('click',()=>goTo('../index.html','Taking you back to the menu…'));
const rvs=[...document.querySelectorAll('.rv')];
function showTitle(){h1.classList.add('on')}
function showPanel(){rvs.forEach((e,i)=>setTimeout(()=>e.classList.add('on'),i*180));$('#hint').classList.add('on');
 later(()=>setStep(0),900);later(()=>setStep(1),5200);later(()=>setStep(2),11000)}

/* ---------- Three.js scene ---------- */
let R,S,cam,go=null,run=false;
try{
const stage=$('#stage'),canvas=$('#c');
R=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,powerPreference:'high-performance'});
R.setPixelRatio(Math.min(devicePixelRatio,2));R.outputEncoding=THREE.sRGBEncoding;R.toneMapping=THREE.ACESFilmicToneMapping;R.toneMappingExposure=1.15;
S=new THREE.Scene();cam=new THREE.PerspectiveCamera(35,1,.1,50);
S.add(new THREE.AmbientLight(0xffe2b8,.6));
const key=new THREE.DirectionalLight(0xfff0d6,1.7);key.position.set(3,6,5);S.add(key);
const rim=new THREE.DirectionalLight(0xe6bc63,1.3);rim.position.set(-4,3,-4);S.add(rim);
const glowL=new THREE.PointLight(0xffc766,0,7);glowL.position.set(0,1,.6);S.add(glowL);

const dot=(()=>{const c=document.createElement('canvas');c.width=c.height=64;const g=c.getContext('2d'),gr=g.createRadialGradient(32,32,0,32,32,32);
 gr.addColorStop(0,'rgba(255,255,255,1)');gr.addColorStop(.3,'rgba(255,255,255,.45)');gr.addColorStop(1,'rgba(255,255,255,0)');g.fillStyle=gr;g.fillRect(0,0,64,64);return new THREE.CanvasTexture(c)})();
const M=(c,r=.5,m=.1,o={})=>new THREE.MeshStandardMaterial(Object.assign({color:c,roughness:r,metalness:m},o));
const mChoc=M(0x3a2115,.5,.12),mGold=M(0xe0b25a,.28,.85),mBun=M(0xc98b4b,.45,.05,{side:THREE.DoubleSide});

/* halo ring + glow */
const halo=new THREE.Group();halo.position.set(0,1.45,-1.2);S.add(halo);
const ring=new THREE.Mesh(new THREE.TorusGeometry(2.45,.035,16,160),new THREE.MeshBasicMaterial({color:0xf1cd7a,transparent:true,opacity:0}));halo.add(ring);
const ring2=new THREE.Mesh(new THREE.TorusGeometry(2.72,.012,8,160),new THREE.MeshBasicMaterial({color:0xf1cd7a,transparent:true,opacity:0}));halo.add(ring2);
const gl=new THREE.Sprite(new THREE.SpriteMaterial({map:dot,color:0xffd98a,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false}));gl.scale.set(8,8,1);halo.add(gl);

/* shadow */
const sc=document.createElement('canvas');sc.width=sc.height=128;{const g=sc.getContext('2d'),gr=g.createRadialGradient(64,64,0,64,64,64);gr.addColorStop(0,'rgba(30,12,4,.6)');gr.addColorStop(1,'rgba(30,12,4,0)');g.fillStyle=gr;g.fillRect(0,0,128,128)}
const shadow=new THREE.Mesh(new THREE.PlaneGeometry(4.2,4.2),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(sc),transparent:true,depthWrite:false}));
shadow.rotation.x=-Math.PI/2;shadow.position.y=-.52;S.add(shadow);

/* delivery box */
const box=new THREE.Group();S.add(box);
box.add(new THREE.Mesh(new THREE.BoxGeometry(1.8,1,1.8),mChoc));
[.3,-.3].forEach(y=>{const b=new THREE.Mesh(new THREE.BoxGeometry(1.84,.08,1.84),mGold);b.position.y=y;box.add(b)});
const lc=document.createElement('canvas');lc.width=lc.height=256;{const g=lc.getContext('2d');g.strokeStyle='#e6bc63';g.fillStyle='#e6bc63';g.lineWidth=5;
 g.beginPath();g.arc(128,128,96,0,7);g.stroke();g.lineWidth=1.5;g.beginPath();g.arc(128,128,84,0,7);g.stroke();
 g.font='700 74px Georgia,serif';g.textAlign='center';g.textBaseline='middle';g.fillText('S&O',128,134)}
const label=new THREE.Mesh(new THREE.PlaneGeometry(.78,.78),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(lc),transparent:true}));label.position.z=.905;box.add(label);
const lid=new THREE.Group();lid.position.set(0,.5,-.9);box.add(lid);
const lm=new THREE.Mesh(new THREE.BoxGeometry(1.9,.14,1.9),mChoc);lm.position.set(0,.07,.95);lid.add(lm);
const ls=new THREE.Mesh(new THREE.BoxGeometry(.3,.02,1.92),mGold);ls.position.set(0,.15,.95);lid.add(ls);
const inner=new THREE.Mesh(new THREE.PlaneGeometry(1.6,1.6),new THREE.MeshBasicMaterial({color:0xf3c25f,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false}));
inner.rotation.x=-Math.PI/2;inner.position.y=.505;box.add(inner);

/* burger */
const burger=new THREE.Group(),bi=new THREE.Group();burger.add(bi);S.add(burger);
const half=(r,top)=>new THREE.SphereGeometry(r,40,20,0,Math.PI*2,top?0:Math.PI/2,Math.PI/2);
const bb=new THREE.Mesh(half(.88,false),mBun);bb.scale.y=.5;bi.add(bb);
const patty=new THREE.Mesh(new THREE.CylinderGeometry(.9,.88,.24,36),M(0x3a1f12,.8));patty.position.y=.16;bi.add(patty);
const cheese=new THREE.Mesh(new THREE.BoxGeometry(1.55,.04,1.55),M(0xe6b23a,.35));cheese.position.y=.32;cheese.rotation.y=Math.PI/4;bi.add(cheese);
const lg=new THREE.TorusGeometry(.8,.09,8,60),lp=lg.attributes.position;
for(let i=0;i<lp.count;i++){lp.setZ(i,lp.getZ(i)+Math.sin(Math.atan2(lp.getY(i),lp.getX(i))*9)*.05)}
const lettuce=new THREE.Mesh(lg,M(0x6f7d3f,.6));lettuce.rotation.x=Math.PI/2;lettuce.position.y=.38;bi.add(lettuce);
const tom=new THREE.Mesh(new THREE.CylinderGeometry(.72,.72,.08,32),M(0x9a2f22,.4));tom.position.y=.47;bi.add(tom);
const tb=new THREE.Mesh(half(.92,true),mBun);tb.scale.y=.78;tb.position.y=.5;bi.add(tb);
const mSes=M(0xf3e3c0,.5);
for(let i=0;i<18;i++){const ph=.2+(i*.37%1)*.85,th=i*2.4,x=.93*Math.sin(ph)*Math.cos(th),y=.5+.93*.78*Math.cos(ph),z=.93*Math.sin(ph)*Math.sin(th);
 const s=new THREE.Mesh(new THREE.SphereGeometry(1,8,6),mSes);s.scale.set(.07,.07,.035);s.position.set(x,y,z);s.lookAt(x*2,(y-.5)*2+.5,z*2);bi.add(s)}
burger.visible=false;

/* success badge */
const badge=new THREE.Group();S.add(badge);
const disc=new THREE.Mesh(new THREE.CylinderGeometry(.62,.62,.14,48),mChoc);disc.rotation.x=Math.PI/2;badge.add(disc);
const rimM=new THREE.Mesh(new THREE.TorusGeometry(.62,.05,12,48),mGold);badge.add(rimM);
const sh=new THREE.Shape();[[-.5,.02],[-.36,-.12],[-.14,.1],[.36,-.4],[.5,-.26],[-.14,.38]].forEach((p,i)=>i?sh.lineTo(p[0],p[1]):sh.moveTo(p[0],p[1]));
const chk=new THREE.Mesh(new THREE.ExtrudeGeometry(sh,{depth:.12,bevelEnabled:true,bevelSize:.025,bevelThickness:.025,bevelSegments:3}),mGold);chk.position.set(0,-.02,.08);badge.add(chk);
badge.position.set(1.5,3.15,.3);badge.visible=false;

/* ambient particles reacting to mouse */
const N=110,pp=new Float32Array(N*3),pv=new Float32Array(N*3),ph=[],home=[];
for(let i=0;i<N;i++){const h=[(Math.random()-.5)*7,-.3+Math.random()*4.8,-1+Math.random()*2.6];home.push(h);ph.push(Math.random()*6);pp.set(h,i*3)}
const pg=new THREE.BufferGeometry();pg.setAttribute('position',new THREE.BufferAttribute(pp,3));
const pm=new THREE.PointsMaterial({size:.11,map:dot,color:0xf1cd7a,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false});S.add(new THREE.Points(pg,pm));

/* sparkle burst */
const SN=90,sp=new Float32Array(SN*3),sv=new Float32Array(SN*3),scol=new Float32Array(SN*3),slife=new Float32Array(SN);
const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.BufferAttribute(sp,3));sg.setAttribute('color',new THREE.BufferAttribute(scol,3));
S.add(new THREE.Points(sg,new THREE.PointsMaterial({size:.16,map:dot,vertexColors:true,transparent:true,blending:THREE.AdditiveBlending,depthWrite:false})));
/* confetti */
const CN=90,cm=new THREE.InstancedMesh(new THREE.PlaneGeometry(.09,.17),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}),CN);
const cp=[],cv=[],cr=[],crv=[],cl=[],dm=new THREE.Object3D(),pal=[0xe6bc63,0xf6ead4,0xc98b4b,0x5a3422,0xf1cd7a];
for(let i=0;i<CN;i++){cp.push(new THREE.Vector3(0,-9,0));cv.push(new THREE.Vector3());cr.push(new THREE.Vector3());crv.push(new THREE.Vector3());cl.push(0);cm.setColorAt(i,new THREE.Color(pal[i%5]))}
cm.frustumCulled=false;S.add(cm);
function burst(){for(let i=0;i<SN;i++){const a=Math.random()*6.28,u=Math.random(),sp_=2+Math.random()*3.5;sp.set([(Math.random()-.5)*1.2,.6,(Math.random()-.5)*1.2],i*3);
 sv.set([Math.cos(a)*sp_*.7,1.5+u*4,Math.sin(a)*sp_*.5],i*3);slife[i]=.7+Math.random()*.9}
 for(let i=0;i<CN;i++){const a=Math.random()*6.28,s=1.5+Math.random()*3;cp[i].set((Math.random()-.5)*1.2,.6,(Math.random()-.5)*1.2);cv[i].set(Math.cos(a)*s,4+Math.random()*4.5,Math.sin(a)*s*.6);
 cr[i].set(Math.random()*6,Math.random()*6,0);crv[i].set((Math.random()-.5)*12,(Math.random()-.5)*12,(Math.random()-.5)*8);cl[i]=2.6+Math.random()*.9}}

/* interaction */
const ptr=new THREE.Vector2(9,9),ray=new THREE.Raycaster(),pl=new THREE.Plane(new THREE.Vector3(0,0,1),0),mw=new THREE.Vector3(99,99,0);
let hov=0,hovT=0,rx=0,ry=0;
addEventListener('pointermove',e=>{const r=stage.getBoundingClientRect();ptr.set((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height)*2+1)});
addEventListener('pointerleave',()=>ptr.set(9,9));
function resize(){const w=stage.clientWidth,h=stage.clientHeight;R.setSize(w,h,false);cam.aspect=w/h;
 const z=9*Math.max(1,.95/cam.aspect);cam.position.set(0,2.5+(z-9)*.2,z);cam.lookAt(0,1.55,0);cam.updateProjectionMatrix()}
new ResizeObserver(resize).observe(stage);resize();

/* ---------- Exploded burger: layers, labels, info card ---------- */
const DATA=[
['Bottom Bun','Butter-toasted brioche heel. Toasted on the flat top so it holds the juices without going soggy.',[['Bread','Potato brioche'],['Finish','Clarified butter'],['Role','Foundation']]],
['Wagyu Patty','Hand-formed smoked wagyu, seared hard for a caramelised crust, then finished over oak smoke.',[['Cut','Wagyu chuck and brisket'],['Weight','180 g'],['Cook','Medium']]],
['Aged Cheddar','Slow-melted under a steam dome so it drapes over the patty and binds the layers together.',[['Age','18 months'],['Flavour','Nutty and sharp'],['Role','Richness']]],
['Butterhead Lettuce','Crisp and cold, a fresh contrast to the warm patty and a barrier that protects the bun.',[['Source','Local farm'],['Served','Chilled'],['Role','Crunch']]],
['Vine Tomato','A thick slice seasoned with flaky salt, adding sweetness and the acidity that lifts the richness.',[['Cut','6 mm slice'],['Seasoning','Sea salt'],['Role','Acidity']]],
['Sesame Brioche Bun','Glazed with egg wash and topped with toasted sesame for aroma, shine and a gentle crown.',[['Topping','Toasted sesame'],['Glaze','Egg wash'],['Role','Crown']]]];
const EX=[-.55,-.2,.15,.5,.85,1.35],C=[.12,.16,.32,.38,.47,.85];
const seeds=bi.children.filter(o=>o.material===mSes);
const LAY=[[bb],[patty],[cheese],[lettuce],[tom],[tb,...seeds]].map((a,i)=>{const g=new THREE.Group();g.userData.i=i;bi.add(g);a.forEach(o=>g.add(o));return{g,s:0,r:0}});
const selG=new THREE.Group(),rA=new THREE.Mesh(new THREE.TorusGeometry(1.1,.02,12,120),new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:0,depthWrite:false})),
rB=new THREE.Mesh(new THREE.TorusGeometry(1.22,.008,8,120),new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:0,depthWrite:false})),
gw=new THREE.Sprite(new THREE.SpriteMaterial({map:dot,color:0xffffff,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false}));
rA.rotation.x=rB.rotation.x=Math.PI/2;gw.scale.set(3.8,3.8,1);selG.add(rA,rB,gw);selG.visible=false;burger.add(selG);selG.traverse(o=>{o.raycast=()=>{}});
const ov=document.createElement('div');ov.id='ov';
ov.innerHTML='<svg id="ln"><defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="rgba(43,23,16,.75)" stroke="none"/></marker><marker id="ah2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0L8 4L0 8z" fill="#fff7e6" stroke="none"/></marker></defs>'+DATA.map((_,i)=>`<g class="cn${i%2?' R':''}"><path/><circle r="3"/></g>`).join('')+'<g id="cc"><path class="t d"/><path class="t d"/><path class="t"/><path class="t"/><path/><path/><path/><path/><circle r="4"/><circle r="4"/></g></svg>'+DATA.map((d,i)=>`<button class="lb${i%2?' R':''}"><i>0${i+1}</i>${d[0]}</button>`).join('')+'<div id="card"></div><div id="tr"></div>';
stage.appendChild(ov);
const cn=[...ov.querySelectorAll('.cn')],lb=[...ov.querySelectorAll('.lb')],card=ov.querySelector('#card'),cc=ov.querySelector('#cc'),vv=new THREE.Vector3();
let isEx=false,sel=-1,lsel=0,exT=0,exK=0,selK=0;
function pick(i){sel=i;const tr=ov.querySelector('#tr');if(i>=0){lsel=i;const d=DATA[i];tr.innerHTML=`<div class="nd root" style="--i:0"><small>FIG. 0${i+1} · LAYER ANALYSIS</small>${d[0]}</div><div class="nd" style="--i:1"><b>A1 · About</b>${d[1]}</div>`+d[2].map((f,j)=>`<div class="nd" style="--i:${j+2}"><b>A${j+2} · ${f[0]}</b>${f[1]}</div>`).join('')}
 ov.classList.toggle('sel',i>=0);$('#blur').classList.toggle('on',i>=0);stage.classList.toggle('fx',i>=0);cn.forEach((e,j)=>e.classList.toggle('act',j===i));lb.forEach((e,j)=>e.classList.toggle('act',j===i))}
function pick0(i){sel=i;if(i>=0){lsel=i;const d=DATA[i];card.innerHTML=`<button class="x" aria-label="Close">×</button><small>LAYER 0${i+1} / 06</small><h3>${d[0]}</h3><p>${d[1]}</p><dl>${d[2].map(f=>`<div><dt>${f[0]}</dt><dd>${f[1]}</dd></div>`).join('')}</dl>`;card.querySelector('.x').onclick=()=>pick(-1)}
 card.classList.toggle('on',i>=0);ov.classList.toggle('sel',i>=0);$('#blur').classList.toggle('on',i>=0);stage.classList.toggle('fx',i>=0);
 cn.forEach((e,j)=>e.classList.toggle('act',j===i));lb.forEach((e,j)=>e.classList.toggle('act',j===i))}
lb.forEach((b,i)=>b.onclick=()=>pick(sel===i?-1:i));
$('#blur').onclick=()=>pick(-1);addEventListener('keydown',e=>{if(e.key==='Escape')pick(-1)});
$('#hint').textContent='Tap the burger to explore its layers';
canvas.addEventListener('click',e=>{if(!burger.visible)return;const r=stage.getBoundingClientRect();ptr.set((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height)*2+1);ray.setFromCamera(ptr,cam);
 const h=ray.intersectObject(burger,true)[0];let o=h&&h.object;while(o&&o.userData.i===undefined)o=o.parent;
 if(o){if(!isEx)isEx=true;else pick(sel===o.userData.i?-1:o.userData.i)}else if(sel>=0)pick(-1);else isEx=false});
function tree(r){const nd=[...ov.querySelector('#tr').children];if(nd.length<5)return;
 const g=cc.children,S=(i,d)=>g[i].setAttribute('d',d),vw=innerWidth,vh=innerHeight,pt=sx=>{vv.set(sx,C[sel],0);LAY[sel].g.localToWorld(vv).project(cam);return[r.left+(vv.x*.5+.5)*r.width,r.top+(.5-vv.y*.5)*r.height]};
 const [xl,y]=pt(-.95),[xr]=pt(.95),xc=(xl+xr)/2,put=(n,l,t,w)=>{n.style.left=l+'px';n.style.top=t+'px';n.style.width=w?w+'px':''};
 g[8].setAttribute('cx',xl);g[8].setAttribute('cy',y);g[9].setAttribute('cx',xr);g[9].setAttribute('cy',y);
 const rt=nd[0];put(rt,0,0,0);const rw=rt.offsetWidth,rh=rt.offsetHeight,rtop=Math.max(12,r.top+8),rcy=rtop+rh/2;put(rt,xc-rw/2,rtop,0);
 const gap=26,tL=xl-34,tR=xr+34,wL=Math.max(110,Math.min(250,tL-gap-8)),wR=Math.max(110,Math.min(250,vw-8-tR-gap)),nL=Math.max(8,tL-gap-wL),nR=tR+gap;
 const side=(ns,nx,w)=>{ns.forEach(n=>put(n,nx,0,w));const hs=ns.map(n=>n.offsetHeight),H=hs.reduce((a,b)=>a+b,0)+10*(ns.length-1),c=[];let ty=Math.max(rtop+rh+16,Math.min(y-H/2,vh-H-16));ns.forEach((n,k)=>{n.style.top=ty+'px';c.push(ty+hs[k]/2);ty+=hs[k]+10});return c};
 const cL=side([nd[1],nd[2]],nL,wL),cR=side([nd[3],nd[4]],nR,wR);
 S(0,`M${xl} ${y}H${tL}`);S(1,`M${xr} ${y}H${tR}`);
 S(2,`M${tL} ${Math.min(rcy,y)}V${Math.max(y,cL[1])}M${tL} ${rcy}H${xc-rw/2}`);S(3,`M${tR} ${Math.min(rcy,y)}V${Math.max(y,cR[1])}M${tR} ${rcy}H${xc+rw/2}`);
 cL.forEach((c,k)=>S(4+k,`M${tL} ${c}H${nL+wL+6}`));cR.forEach((c,k)=>S(6+k,`M${tR} ${c}H${nR-6}`))}
function lay(dt){
 exT=clamp(exT+(isEx?.9:-1.3)*dt);exK=eo3(exT);const k=1-Math.exp(-dt*5);
 if(exT>0)st.spin=lerp(st.spin,Math.round(st.spin/6.2832)*6.2832,(1-Math.exp(-dt*3))*exK);
 LAY.forEach((L,i)=>{const e=eo3(exT*1.4-i*.06);L.s=lerp(L.s,sel===i?1:0,k);L.g.position.y=EX[i]*e+L.s*.32;
  if(sel===i)L.r+=dt*.14;else L.r=lerp(L.r,Math.round(L.r/6.2832)*6.2832,1-Math.exp(-dt*3));L.g.rotation.y=L.r});
 selK=lerp(selK,sel>=0?1:0,k);selG.visible=selK>.01;selG.position.y=LAY[lsel].g.position.y+C[lsel];
 rA.material.opacity=selK*.95;rB.material.opacity=selK*.5;gw.material.opacity=selK*.5;
 ov.classList.toggle('on',isEx&&exT>.75);if(exT<.02)return;
 burger.updateMatrixWorld(true);const r=stage.getBoundingClientRect(),X=(v)=>r.left+(v.x*.5+.5)*r.width,Y=(v)=>r.top+(.5-v.y*.5)*r.height;
 const gp=innerWidth<880?30:48,P=LAY.map((L,i)=>{vv.set(i%2?.95:-.95,C[i],0);L.g.localToWorld(vv).project(cam);return[X(vv),Y(vv)]}),lx=Math.min(...P.filter((p,i)=>i%2==0).map(p=>p[0]))-gp,rx2=Math.max(...P.filter((p,i)=>i%2).map(p=>p[0]))+gp;
 P.forEach(([x,y],i)=>{const rt=i%2,ly=y+(i-2.5)*4,g=cn[i].children,e=rt?rx2:lx;g[0].setAttribute('d',`M${x} ${y}L${x+(rt?24:-24)} ${ly}H${e+(rt?-8:8)}`);g[1].setAttribute('cx',x);g[1].setAttribute('cy',y);lb[i].style.transform=rt?`translate(${e}px,${ly}px) translateY(-50%)`:`translate(${e}px,${ly}px) translate(-100%,-50%)`});
 if(sel>=0)tree(r);
 if(false){const nd=[...ov.querySelector('#tr').children],m=innerWidth<880,g=cc.children,S=(i,d)=>g[i].setAttribute('d',d),put=(n,l,t,w)=>{n.style.left=l+'px';n.style.top=t+'px';n.style.width=w?w+'px':''};
  if(nd.length<5)return;vv.set(m?-.95:.95,C[sel],0);LAY[sel].g.localToWorld(vv).project(cam);const x=X(vv),y=Y(vv),cy=[];g[1].setAttribute('cx',x);g[1].setAttribute('cy',y);
  if(m){const tx=14,w=innerWidth-tx-34;let ty=r.bottom+8;nd.forEach(n=>{put(n,tx+16,ty,w);cy.push(ty+n.offsetHeight/2);ty+=n.offsetHeight+8});
   S(0,`M${x} ${y}H${tx}V${cy[0]}H${tx+10}`);for(let j=1;j<5;j++)S(j+1,`M${tx} ${cy[j]}H${tx+10}`);S(6,`M${tx} ${cy[0]}V${cy[4]}`)}
  else{const rx=x+64;put(nd[0],rx,y-17,0);const rw=nd[0].offsetWidth,tx=rx+rw+30,nx=tx+26,w=Math.min(300,innerWidth-nx-20);
   const ch=nd.slice(1);ch.forEach(n=>put(n,nx,0,w));const hs=ch.map(n=>n.offsetHeight),H=hs.reduce((a,b)=>a+b,0)+10*3;let ty=Math.max(70,Math.min(y-H/2,innerHeight-H-20));
   ch.forEach((n,j)=>{n.style.top=ty+'px';cy[j+1]=ty+hs[j]/2;ty+=hs[j]+10});nd[0].style.top=(y-nd[0].offsetHeight/2)+'px';
   S(0,`M${x} ${y}H${rx-6}`);for(let j=1;j<5;j++)S(j+1,`M${tx} ${cy[j]}H${nx-6}`);S(6,`M${rx+rw} ${y}H${tx}M${tx} ${Math.min(y,cy[1])}V${Math.max(y,cy[4])}`)}}}

/* timeline */
let t0,st,last;
go=function(){timers.splice(0).forEach(clearTimeout);h1.classList.remove('on');rvs.forEach(e=>e.classList.remove('on'));$('#hint').classList.remove('on');setStep(-1);
 $('#veil').classList.add('off');run=true;
 st={y:7,vy:0,landed:false,landT:0,sq:0,lid:null,burst:false,title:false,panel:false,spin:0,time:0};
 for(let i=0;i<CN;i++)cl[i]=0;slife.fill(0);t0=performance.now();last=t0};
const speed=reduce?3:1;
R.setAnimationLoop(()=>{if(!run)return;const now=performance.now(),dt=Math.min(.05,(now-last)/1000)*speed;last=now;const t=(now-t0)/1000*speed;st.time+=dt;
 /* halo */
 const rp=eo3((t-.5)/1.3);ring.material.opacity=rp;ring2.material.opacity=rp*.4;gl.material.opacity=rp*.4;halo.scale.setScalar(lerp(.6,1,rp));ring2.rotation.z=t*.1;
 pm.opacity=eo3((t-.8)/1.5)*.85;
 /* box drop with bounce */
 box.visible=t>1.2;
 if(t>1.2&&!st.landed){st.vy-=22*dt;st.y+=st.vy*dt;if(st.y<=0){st.y=0;if(st.vy<-2){st.sq=Math.min(1,-st.vy*.06);st.vy=-st.vy*.36}else{st.vy=0;st.landed=true;st.landT=t}}}
 st.sq*=Math.pow(.02,dt);box.position.y=st.y;box.scale.set(1+st.sq*.1,1-st.sq*.16,1+st.sq*.1);
 shadow.material.opacity=box.visible?clamp(1-st.y/6)*.9:0;shadow.scale.setScalar(1+st.y*.08);
 /* lid, glow, burst */
 if(st.landed&&st.lid===null&&t>st.landT+.35)st.lid=t;
 if(st.lid!==null){const k=t-st.lid;lid.rotation.x=-1.95*eob(k/.85);inner.material.opacity=lerp(.95,.35,eo3((k-.4)/1.2))*eo3(k/.3);glowL.intensity=3.5*eo3(k/.5);
  if(!st.burst&&k>.15){st.burst=true;burst()}
  if(!st.title&&k>.25){st.title=true;showTitle()}
  if(!st.panel&&k>1.3){st.panel=true;showPanel()}
  /* burger */
  const kb=k-.3;burger.visible=kb>0;const p=eo3(kb/1.15),fl=eo3((kb-1)/1);
  const hf=hov;hovT=lerp(hovT,hf,.08);st.spin+=dt*lerp(.5,.05,hovT)*(1-exK);
  burger.position.y=lerp(.15,1.2,p)+Math.sin(st.time*1.7)*(.05+.08*hovT)*fl+hovT*.08;
  burger.scale.setScalar(lerp(.55,1,eob(kb/1.1))*(1+hovT*.07));
  ry=lerp(ry,ptr.x*.9*hovT,.08);rx=lerp(rx,-ptr.y*.45*hovT,.08);
  const q=1-exK;burger.rotation.y=st.spin+ry*q;bi.rotation.x=rx*q;bi.rotation.z=-ry*.25*q;lay(dt);
  /* badge */
  const kc=k-.95;badge.visible=kc>0&&exK<.98;if(kc>0){badge.scale.setScalar(Math.max(.001,spring(kc)*(1-exK)));badge.rotation.y=(1-clamp(kc/.9))*Math.PI*2+Math.sin(st.time*1.2)*.12;badge.position.y=3.15+Math.sin(st.time*1.5)*.06}
  /* hover test */
  ray.setFromCamera(ptr,cam);hov=(burger.visible&&ray.intersectObject(burger,true).length)?1:0;canvas.style.cursor=hov?'pointer':'default'}
 /* ambient particles */
 ray.setFromCamera(ptr,cam);if(!ray.ray.intersectPlane(pl,mw))mw.set(99,99,0);
 const f=dt*60;for(let i=0;i<N;i++){const j=i*3,h=home[i],tx=h[0]+Math.sin(st.time*.5+ph[i])*.2,ty=h[1]+Math.cos(st.time*.4+ph[i])*.25;
  pv[j]+=(tx-pp[j])*.012*f;pv[j+1]+=(ty-pp[j+1])*.012*f;pv[j+2]+=(h[2]-pp[j+2])*.012*f;
  const dx=pp[j]-mw.x,dy=pp[j+1]-mw.y,d=Math.hypot(dx,dy);if(d<1.5&&d>.001){const k=(1.5-d)*.07*f;pv[j]+=dx/d*k;pv[j+1]+=dy/d*k}
  pv[j]*=.93;pv[j+1]*=.93;pv[j+2]*=.93;pp[j]+=pv[j]*f;pp[j+1]+=pv[j+1]*f;pp[j+2]+=pv[j+2]*f}
 pg.attributes.position.needsUpdate=true;
 /* sparkles */
 for(let i=0;i<SN;i++){const j=i*3;if(slife[i]>0){slife[i]-=dt;sv[j+1]-=3*dt;sp[j]+=sv[j]*dt;sp[j+1]+=sv[j+1]*dt;sp[j+2]+=sv[j+2]*dt;const b=clamp(slife[i]*1.4)*(.6+.4*Math.sin(st.time*30+i));
  scol[j]=1*b;scol[j+1]=.8*b;scol[j+2]=.42*b}else{scol[j]=scol[j+1]=scol[j+2]=0}}
 sg.attributes.position.needsUpdate=sg.attributes.color.needsUpdate=true;
 /* confetti */
 for(let i=0;i<CN;i++){if(cl[i]>0){cl[i]-=dt;cv[i].y-=7*dt;cv[i].multiplyScalar(1-1.2*dt*.5);cp[i].addScaledVector(cv[i],dt);cr[i].addScaledVector(crv[i],dt);
  dm.position.copy(cp[i]);dm.rotation.set(cr[i].x,cr[i].y,cr[i].z);dm.scale.setScalar(clamp(cl[i]*2.5))}else{dm.position.set(0,-20,0);dm.scale.setScalar(.0001)}
  dm.updateMatrix();cm.setMatrixAt(i,dm.matrix)}
 cm.instanceMatrix.needsUpdate=true;
 R.render(S,cam)});
}catch(err){console.warn(err);$('#c').style.display='none'}
/* ---------- Intro: light gathers, impact frames, tick ---------- */
const intro=$('#intro'),ic=$('#ic'),ix=ic.getContext('2d'),isp=reduce?2:1;
let IW,IH,DPR,IR,ip,lines,sparks,spawned,rid,it0,fired;
const isz=()=>{DPR=Math.min(devicePixelRatio,2);IW=innerWidth;IH=innerHeight;ic.width=IW*DPR;ic.height=IH*DPR;IR=Math.min(Math.max(Math.min(IW,IH)*.13,64),120)};
addEventListener('resize',isz);
function seed(){const n=reduce?120:300,m=Math.hypot(IW,IH)*.6;ip=[];
 for(let i=0;i<n;i++)ip.push({a:Math.random()*6.283,r:m*(.25+Math.random()*.75),d:Math.random(),s:.8+Math.random()*1.8,w:(Math.random()<.5?-1:1)*(1.5+Math.random()*2)});
 lines=[];for(let i=0;i<30;i++)lines.push({a:i/30*6.283+Math.random()*.1,l:1.5+Math.random()*3.5,w:1+Math.random()*2.5});sparks=[];spawned=0}
function tick(cx,cy,s,p){const P=[[-.45,.02],[-.12,.34],[.5,-.34]],L1=.47,L2=.9,d=p*(L1+L2);ix.beginPath();ix.moveTo(cx+P[0][0]*s,cy+P[0][1]*s);
 const a=Math.min(d,L1)/L1;ix.lineTo(cx+(P[0][0]+(P[1][0]-P[0][0])*a)*s,cy+(P[0][1]+(P[1][1]-P[0][1])*a)*s);
 if(d>L1){const b=(d-L1)/L2;ix.lineTo(cx+(P[1][0]+(P[2][0]-P[1][0])*b)*s,cy+(P[1][1]+(P[2][1]-P[1][1])*b)*s)}}
function frame(now){if(fired)return;const T=(now-it0)/1000*isp,Ti=2.5,E=Ti+.13+1.7,cx=IW/2,cy=IH/2,k=T-Ti;
 if(T>=E){finish();return}
 rid=requestAnimationFrame(frame);
 ix.setTransform(DPR,0,0,DPR,0,0);ix.globalCompositeOperation='source-over';
 /* impact frame 1: full flash */
 if(k>=0&&k<.06){ix.fillStyle='#fff1cf';ix.fillRect(0,0,IW,IH);return}
 /* impact frame 2: inverted silhouette */
 if(k>=.06&&k<.13){ix.fillStyle='#f6ead4';ix.fillRect(0,0,IW,IH);ix.strokeStyle='#1a0d07';ix.lineWidth=IR*.5;ix.lineCap=ix.lineJoin='round';tick(cx,cy,IR*2.6,1);ix.stroke();return}
 const charge=k<0?clamp((T-1.9)/.6)*3:0,sh=k>=.13?Math.max(0,1-(k-.13)/.4)*16:charge;
 ix.setTransform(DPR,0,0,DPR,(Math.random()-.5)*sh*DPR,(Math.random()-.5)*sh*DPR);
 ix.fillStyle=k<0?'rgba(13,7,4,.22)':'rgba(13,7,4,.38)';ix.fillRect(-30,-30,IW+60,IH+60);
 ix.globalCompositeOperation='lighter';
 const p=clamp((T-.3)/2.2),kk=k-.13;
 if(k<0){
  const g=16+p*p*p*120+Math.sin(T*18)*charge*3,gr=ix.createRadialGradient(cx,cy,0,cx,cy,g);gr.addColorStop(0,`rgba(255,236,190,${.3+.7*p})`);gr.addColorStop(.35,`rgba(240,190,95,${.35*p+.05})`);gr.addColorStop(1,'rgba(230,188,99,0)');
  ix.fillStyle=gr;ix.beginPath();ix.arc(cx,cy,g,0,6.283);ix.fill();
  for(const s of ip){const pp=clamp((T-.3-s.d*.25)/1.9),e=Math.pow(pp,2.2),r=s.r*(1-e),a=s.a+e*s.w;
   ix.fillStyle=`rgba(255,214,130,${.2+.8*pp})`;ix.beginPath();ix.arc(cx+Math.cos(a)*r,cy+Math.sin(a)*r,s.s*(1+pp),0,6.283);ix.fill()}
 }else{
  const g=IR*4,gr=ix.createRadialGradient(cx,cy,0,cx,cy,g);gr.addColorStop(0,`rgba(255,225,160,${.5*clamp(1-kk/1.3)})`);gr.addColorStop(1,'rgba(230,188,99,0)');ix.fillStyle=gr;ix.fillRect(0,0,IW,IH);
  for(const d of [0,.12]){const q=(kk-d)/.9;if(q>0&&q<1){ix.strokeStyle=`rgba(255,220,150,${1-q})`;ix.lineWidth=2+(1-q)*7;ix.beginPath();ix.arc(cx,cy,IR+eo3(q)*Math.max(IW,IH)*.6,0,6.283);ix.stroke()}}
  const q=kk/.35;if(q<1){ix.lineCap='round';for(const l of lines){const r0=IR*1.35+IR*q*l.l*.9,r1=IR*1.35+IR*l.l*eo3(q)*1.6;ix.strokeStyle=`rgba(255,226,165,${1-q})`;ix.lineWidth=l.w;ix.beginPath();ix.moveTo(cx+Math.cos(l.a)*r0,cy+Math.sin(l.a)*r0);ix.lineTo(cx+Math.cos(l.a)*r1,cy+Math.sin(l.a)*r1);ix.stroke()}}
  if(!spawned){spawned=1;for(let i=0;i<90;i++){const a=Math.random()*6.283,v=250+Math.random()*650;sparks.push({x:cx,y:cy,vx:Math.cos(a)*v,vy:Math.sin(a)*v,l:.6+Math.random()*.8})}}
  for(const s of sparks)if(s.l>0){s.l-=.0167*isp;s.x+=s.vx*.0167;s.y+=s.vy*.0167;s.vx*=.95;s.vy*=.95;ix.fillStyle=`rgba(255,214,130,${clamp(s.l*1.5)})`;ix.beginPath();ix.arc(s.x,s.y,1.8,0,6.283);ix.fill()}
  ix.globalCompositeOperation='source-over';
  const sc=Math.max(.001,spring(kk));ix.save();ix.translate(cx,cy);ix.scale(sc,sc);ix.translate(-cx,-cy);
  ix.shadowColor='rgba(230,188,99,.9)';ix.shadowBlur=36;ix.fillStyle='#2b1710';ix.beginPath();ix.arc(cx,cy,IR,0,6.283);ix.fill();
  ix.strokeStyle='#e6bc63';ix.lineWidth=IR*.06;ix.stroke();ix.shadowBlur=18;ix.lineWidth=IR*.17;ix.lineCap=ix.lineJoin='round';tick(cx,cy,IR*1.15,eo3(kk/.35));ix.stroke();ix.restore();
  const ta=clamp((kk-.6)/.5);if(ta>0){ix.shadowBlur=0;ix.fillStyle=`rgba(246,234,212,${ta})`;ix.font=`600 ${Math.round(IR*.3)}px 'Cormorant Garamond',serif`;ix.textAlign='center';ix.fillText('Payment received',cx,cy+IR*1.9)}
 }
 /* closing flash into the page */
 const fa=clamp((T-(E-.3))/.3);if(fa>0){ix.setTransform(DPR,0,0,DPR,0,0);ix.globalCompositeOperation='source-over';ix.fillStyle=`rgba(255,241,207,${fa})`;ix.fillRect(0,0,IW,IH)}}
function finish(){if(fired)return;fired=1;cancelAnimationFrame(rid);intro.classList.add('out');if(go)go();else{showTitle();showPanel()}}
function startIntro(){timers.splice(0).forEach(clearTimeout);run=false;h1.classList.remove('on');rvs.forEach(e=>e.classList.remove('on'));$('#hint').classList.remove('on');setStep(-1);
 intro.classList.remove('out');fired=0;isz();seed();cancelAnimationFrame(rid);it0=performance.now();rid=requestAnimationFrame(frame)}
$('#skip').onclick=finish;$('#replay').onclick=startIntro;startIntro();
