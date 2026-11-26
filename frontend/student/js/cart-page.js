
document.getElementById("app-header").innerHTML=trayComponents.header();
function escapeHtml(value){
 return String(value??"").replace(/[&<>"']/g,(character)=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[character]);
}
function renderCart(){
 const cart=trayStorage.getCart();
 const total=cart.reduce((n,i)=>n+i.price*i.qty,0);
 const cartCount=document.getElementById("cart-count");
 if(cartCount)cartCount.textContent=cart.reduce((sum,item)=>sum+item.qty,0);
 document.getElementById("cart-total").textContent="₹"+total.toLocaleString("en-IN");
 document.getElementById("cart-list").innerHTML=cart.length?cart.map(i=>{
  const id=escapeHtml(i.id);
  return `
 <div class="cart-item" style="background:#fff;padding:12px;border:1px solid var(--line);margin-bottom:8px;border-radius:10px">
 <img src="${escapeHtml(i.image)}" alt=""><div><strong>${escapeHtml(i.name)}</strong><span style="display:block;color:var(--muted);font-size:13px;margin:4px 0">₹${escapeHtml(i.price)} each</span>
 <div class="qty-control"><button type="button" data-delta="-1" data-id="${id}">−</button><span>${escapeHtml(i.qty)}</span><button type="button" data-delta="1" data-id="${id}">+</button></div></div>
 <div style="text-align:right"><strong>₹${escapeHtml(i.price*i.qty)}</strong><button type="button" data-remove="${id}" style="display:block;border:0;background:none;color:var(--danger);font-size:12px;margin:8px 0 0 auto;cursor:pointer">Remove</button></div>
 </div>`;
 }).join(""):`<div class="empty-state"><h3>Your cart is empty</h3><p><a href="../index.html" style="text-decoration:underline">Return to the menu</a></p></div>`;
}
document.getElementById("cart-list").addEventListener("click",e=>{
 const cart=trayStorage.getCart();
 const qtyButton=e.target.closest("[data-delta]");
 const removeButton=e.target.closest("[data-remove]");
 if(qtyButton){const item=cart.find(i=>i.id===Number(qtyButton.dataset.id));if(item){item.qty+=Number(qtyButton.dataset.delta);trayStorage.set("trayup-cart",cart.filter(i=>i.qty>0));renderCart();}}
 if(removeButton){trayStorage.set("trayup-cart",cart.filter(i=>i.id!==Number(removeButton.dataset.remove)));trayNotify("Item removed");renderCart();}
});
document.getElementById("clear-cart").addEventListener("click",()=>{
 trayStorage.remove("trayup-cart");
 trayNotify("Cart cleared");
 renderCart();
});
renderCart();
