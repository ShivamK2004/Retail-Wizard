(() => {
  const clock = document.getElementById('live-clock');
  const updateClock = () => { if (clock) clock.textContent = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'medium' }).format(new Date()); };
  updateClock(); setInterval(updateClock, 1000);
  const menu = document.getElementById('sidebar');
  document.querySelector('[data-menu-toggle]')?.addEventListener('click', () => menu?.classList.toggle('open'));
  document.addEventListener('click', e => { if (menu?.classList.contains('open') && !menu.contains(e.target) && !e.target.closest('[data-menu-toggle]')) menu.classList.remove('open'); });

  const productSelect = document.getElementById('product-select');
  const qtyInput = document.getElementById('product-qty');
  const cartBody = document.querySelector('#cart-table tbody');
  const itemsField = document.getElementById('items-json');
  const cartTotalEl = document.getElementById('cart-total');
  const paymentMethod = document.getElementById('payment-method');
  const cashFields = document.getElementById('cash-fields');
  const upiFields = document.getElementById('upi-fields');
  const cart = [];
  const rupees = n => '₹' + Number(n || 0).toFixed(2);
  function renderCart() {
    if (!cartBody) return;
    cartBody.innerHTML = '';
    if (!cart.length) {
      const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 5; td.className = 'empty-cell'; td.textContent = 'Cart is empty.'; tr.append(td); cartBody.append(tr);
    }
    let total = 0;
    cart.forEach((item, index) => {
      const gross = item.quantity * item.price; const afterItemDiscount = gross * (1 - item.discount / 100); total += afterItemDiscount;
      const amount = gross;
      const tr = document.createElement('tr');
      [item.name, rupees(item.price), String(item.quantity), rupees(amount)].forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
      const td = document.createElement('td'); const button = document.createElement('button'); button.type = 'button'; button.className = 'btn small danger-btn'; button.textContent = 'Remove'; button.addEventListener('click', () => { cart.splice(index, 1); renderCart(); }); td.append(button); tr.append(td); cartBody.append(tr);
    });
    const orderDiscount = Number(document.querySelector('input[name="order_discount_percent"]')?.value || 0);
    const afterOrderDiscount = total * (1 - orderDiscount / 100);
    const taxTotal = cart.reduce((sum, item) => sum + item.quantity * item.price * (1 - item.discount / 100) * (1 - orderDiscount / 100) * item.tax / 100, 0);
    const displayedTotal = afterOrderDiscount + taxTotal;
    if (cartTotalEl) cartTotalEl.textContent = rupees(displayedTotal);
    if (itemsField) itemsField.value = JSON.stringify(cart.map(({product_id, quantity}) => ({product_id, quantity})));
    const tender = document.querySelector('input[name="amount_tendered"]'); if (tender && (!tender.dataset.touched || tender.value === '0')) tender.value = displayedTotal.toFixed(2);
  }
  document.getElementById('add-cart')?.addEventListener('click', () => {
    const option = productSelect?.selectedOptions[0]; if (!option?.value) { alert('Choose a product first.'); return; }
    const quantity = Number(qtyInput.value); const stock = Number(option.dataset.stock); if (!Number.isFinite(quantity) || quantity <= 0) { alert('Enter a valid quantity.'); return; }
    const product_id = Number(option.value); const existing = cart.find(x => x.product_id === product_id); const next = (existing?.quantity || 0) + quantity;
    if (next > stock) { alert(`Only ${stock} units are available.`); return; }
    if (existing) existing.quantity = next; else cart.push({product_id, quantity, name: option.dataset.name, price: Number(option.dataset.price), discount: Number(option.dataset.discount || 0), tax: Number(option.dataset.tax || 0)});
    renderCart();
  });
  document.querySelector('input[name="amount_tendered"]')?.addEventListener('input', e => { e.target.dataset.touched = '1'; });
  document.querySelector('input[name="order_discount_percent"]')?.addEventListener('input', renderCart);
  paymentMethod?.addEventListener('change', () => { const isUpi = paymentMethod.value === 'UPI'; if (cashFields) cashFields.hidden = isUpi; if (upiFields) upiFields.hidden = !isUpi; });
  document.getElementById('checkout-form')?.addEventListener('submit', e => { if (!cart.length) { e.preventDefault(); alert('Add at least one product to the cart.'); return; } if (!confirm('Complete this sale?')) e.preventDefault(); });

  const purchaseSelect = document.getElementById('purchase-product');
  const purchaseCost = document.getElementById('purchase-cost');
  const purchaseCart = [];
  const purchaseBody = document.querySelector('#purchase-table tbody');
  const purchaseField = document.getElementById('purchase-items-json');
  purchaseSelect?.addEventListener('change', () => { const o = purchaseSelect.selectedOptions[0]; if (o?.value && purchaseCost) purchaseCost.value = Number(o.dataset.cost || 0).toFixed(2); });
  function renderPurchase() {
    if (!purchaseBody) return; purchaseBody.innerHTML = '';
    if (!purchaseCart.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 5; td.className = 'empty-cell'; td.textContent = 'No items added.'; tr.append(td); purchaseBody.append(tr); }
    purchaseCart.forEach((item,index) => { const tr = document.createElement('tr'); [item.name,String(item.quantity),rupees(item.unit_cost),String(item.tax_percent)].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);}); const td=document.createElement('td');const b=document.createElement('button');b.type='button';b.className='btn small danger-btn';b.textContent='Remove';b.addEventListener('click',()=>{purchaseCart.splice(index,1);renderPurchase();});td.append(b);tr.append(td);purchaseBody.append(tr); });
    if (purchaseField) purchaseField.value = JSON.stringify(purchaseCart.map(({product_id, quantity, unit_cost, tax_percent})=>({product_id,quantity,unit_cost,tax_percent})));
  }
  document.getElementById('add-purchase-item')?.addEventListener('click',()=>{const o=purchaseSelect?.selectedOptions[0];if(!o?.value){alert('Choose a product.');return;}const item={product_id:Number(o.value),name:o.dataset.name,quantity:Number(document.getElementById('purchase-qty').value),unit_cost:Number(purchaseCost.value),tax_percent:Number(document.getElementById('purchase-tax').value)};if(!Number.isFinite(item.quantity)||item.quantity<=0||item.unit_cost<0){alert('Enter a valid quantity and unit cost.');return;}purchaseCart.push(item);renderPurchase();});
  document.getElementById('purchase-form')?.addEventListener('submit',e=>{if(!purchaseCart.length){e.preventDefault();alert('Add at least one purchase item.');}});
  document.querySelector('form[action*="/refund"]')?.addEventListener('submit', e => { if (!confirm('Record this refund? This app records the refund; it does not transfer money.')) e.preventDefault(); });
})();
