// ================================================================
// JLB Sports — Cliente Socket.IO (tiempo real)
// Conecta a todos los clientes con el servidor y refleja en vivo:
//   - alertas de stock bajo / agotado / venta inusual
//   - creación/edición/eliminación de productos y cambios de stock
//   - nuevas ventas y pedidos
// Sin esto, los cambios de un dispositivo no se ven en los demás
// hasta recargar la página.
// ================================================================

(function () {
  if (typeof io === 'undefined') return;

  const socket = io();
  const statusChip = document.getElementById('socket-status');
  const alertsWrap = document.getElementById('realtime-alerts-wrap');

  function setStatus(connected) {
    if (!statusChip) return;
    statusChip.textContent = connected ? '🟢 En vivo' : '🔴 Sin conexión';
  }

  socket.on('connect', () => setStatus(true));
  socket.on('disconnect', () => setStatus(false));
  socket.on('connect_error', () => setStatus(false));

  function showAlert(message, tipo) {
    if (!alertsWrap) return;
    const icono = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' }[tipo] || 'ℹ️';
    const div = document.createElement('div');
    div.className = `alerta alerta-${tipo}`;
    div.innerHTML = `
      <span>${icono}</span>
      <span>${message}</span>
      <button class="alerta-cerrar" onclick="this.parentElement.remove()">×</button>
    `;
    alertsWrap.prepend(div);
    setTimeout(() => {
      div.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      div.style.opacity = '0';
      div.style.transform = 'translateY(-6px)';
      setTimeout(() => div.remove(), 400);
    }, 7000);
  }

  socket.on('low_stock_alert', (data) => showAlert(data.message, 'warning'));
  socket.on('out_of_stock_alert', (data) => showAlert(data.message, 'error'));
  socket.on('unusual_sale_alert', (data) => showAlert(data.message, 'info'));

  socket.on('sale_created', (data) => {
    showAlert(`🧾 Nueva venta registrada — ${data.client} · ${formatoPesosRT(data.total_amount)}`, 'success');
    refreshLowStockBadge();
  });
  socket.on('sale_cancelled', () => refreshLowStockBadge());
  socket.on('stock_changed', () => refreshLowStockBadge());
  socket.on('product_created', (data) => showAlert(`📦 Producto agregado: ${data.name}`, 'info'));
  socket.on('product_deleted', (data) => showAlert(`🗑️ Producto eliminado: ${data.name}`, 'info'));
  socket.on('order_created', () => refreshLowStockBadge());

  // Cualquier evento de negocio dispara un refresco genérico del dashboard
  // (si la página actual lo escucha, ver dashboard.html).
  socket.on('dashboard_refresh', (payload) => {
    document.dispatchEvent(new CustomEvent('jlb:dashboard_refresh', { detail: payload }));
  });

  function formatoPesosRT(v) {
    const num = Math.round(parseFloat(v) || 0);
    return '$' + num.toLocaleString('es-CO').replace(/,/g, '.');
  }

  // Refresca el badge de "stock bajo" en el menú lateral sin recargar la página.
  let badgeTimer = null;
  function refreshLowStockBadge() {
    clearTimeout(badgeTimer);
    badgeTimer = setTimeout(() => {
      fetch('/dashboard/api/stats/')
        .then((r) => r.json())
        .then((data) => {
          const link = document.querySelector('a.nav-enlace[href*="products"]');
          if (!link) return;
          let badge = link.querySelector('.nav-badge');
          if (data.low_stock_count > 0) {
            if (!badge) {
              badge = document.createElement('span');
              badge.className = 'nav-badge';
              link.appendChild(badge);
            }
            badge.textContent = data.low_stock_count;
          } else if (badge) {
            badge.remove();
          }
        })
        .catch(() => {});
    }, 400);
  }
})();
