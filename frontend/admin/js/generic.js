(function(){
const nav=[["Overview","dashboard.html"],["Menu","menu.html"],["Categories","categories.html"],["Orders","orders.html"],["Staff","staff.html"],["Reports","reports.html"],["Refunds","refunds.html"],["Settings","settings.html"]];
const active=document.body.dataset.page;
document.getElementById("admin-nav").innerHTML=nav.map(([name,file])=>`<a class="${file===active?"active":""}" href="./${file}">${name}</a>`).join("");
document.getElementById("logout")?.addEventListener("click",async()=>{try{await trayAuth.logout()}catch(_){}window.location.href="./login.html";});
})();
