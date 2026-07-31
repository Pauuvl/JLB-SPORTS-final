// ================================================================
// JLB Sports — JavaScript Principal
// ================================================================

// ── Sidebar móvil ────────────────────────────────────────────────
const sidebar  = document.querySelector('.sidebar');
const overlay  = document.querySelector('.sidebar-overlay');
const toggle   = document.querySelector('.menu-toggle');

if (toggle) {
  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('abierto');
    overlay.classList.toggle('visible');
  });
}
if (overlay) {
  overlay.addEventListener('click', () => {
    sidebar.classList.remove('abierto');
    overlay.classList.remove('visible');
  });
}

// ── Auto-ocultar alertas después de 5 segundos ───────────────────
document.querySelectorAll('.alerta').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
    el.style.opacity    = '0';
    el.style.transform  = 'translateY(-6px)';
    setTimeout(() => el.remove(), 400);
  }, 5500);
});

// ── Fecha en topbar ───────────────────────────────────────────────
const meses = ['enero','febrero','marzo','abril','mayo','junio',
                'julio','agosto','septiembre','octubre','noviembre','diciembre'];
const dias  = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
const d = new Date();
const elFecha = document.getElementById('topbar-fecha');
if (elFecha) {
  elFecha.textContent = `${dias[d.getDay()]}, ${d.getDate()} de ${meses[d.getMonth()]} de ${d.getFullYear()}`;
}

// ── Formateo de pesos colombianos ────────────────────────────────
function formatoPesos(valor) {
  const num = parseInt(valor) || 0;
  return '$' + num.toLocaleString('es-CO').replace(/,/g, '.');
}

// ── Constructor de ventas ─────────────────────────────────────────
let indiceItem = 0;

function agregarItem() {
  const contenedor = document.getElementById('items-lista');
  if (!contenedor) return;
  const idx = indiceItem++;

  const opcionesProducto = (window.PRODUCTOS || []).map(p => {
    const stockLabel = p.stock === 0
      ? ' — AGOTADO'
      : p.stock <= 5
        ? ` — Stock bajo: ${p.stock}`
        : ` — Stock: ${p.stock}`;
    const disabled = p.stock === 0 ? 'disabled' : '';
    return `<option value="${p.id}" data-precio="${p.precio}" data-stock="${p.stock}" ${disabled}>
              ${p.nombre}${stockLabel}
            </option>`;
  }).join('');

  const fila = document.createElement('div');
  fila.className = 'item-fila';
  fila.id = `item-${idx}`;
  fila.innerHTML = `
    <div class="form-grupo" style="margin:0">
      <label>Producto</label>
      <select name="product_id[]" required onchange="alSeleccionarProducto(this, ${idx})">
        <option value="">— Seleccionar —</option>
        ${opcionesProducto}
      </select>
    </div>
    <div class="form-grupo" style="margin:0">
      <label>Cantidad</label>
      <input type="number" name="quantity[]" id="cant-${idx}"
             value="1" min="1" required onchange="actualizarResumen()">
    </div>
    <div class="form-grupo" style="margin:0">
      <label>Precio Unit.</label>
      <input type="text" id="precio-display-${idx}" readonly placeholder="$0"
             style="background:var(--gris-fondo);font-weight:700;">
      <input type="hidden" id="precio-${idx}" value="0">
    </div>
    <div class="form-grupo" style="margin:0;justify-content:flex-end;">
      <label>&nbsp;</label>
      <button type="button" class="btn btn-outline btn-sm"
              onclick="quitarItem(${idx})" style="color:var(--rojo);border-color:var(--rojo);">✕</button>
    </div>
  `;
  contenedor.appendChild(fila);
  actualizarResumen();
}

function quitarItem(idx) {
  const fila = document.getElementById(`item-${idx}`);
  if (fila) {
    fila.style.opacity = '0';
    fila.style.transform = 'scale(0.95)';
    fila.style.transition = '0.15s ease';
    setTimeout(() => { fila.remove(); actualizarResumen(); }, 150);
  }
}

function alSeleccionarProducto(select, idx) {
  const opt   = select.options[select.selectedIndex];
  const multi = obtenerMultiplicadorCliente();
  const base  = parseFloat(opt.dataset.precio || 0);
  const precio = Math.round(base * multi);
  const stock  = parseInt(opt.dataset.stock || 0);

  document.getElementById(`precio-${idx}`).value          = precio;
  document.getElementById(`precio-display-${idx}`).value  = formatoPesos(precio);
  document.getElementById(`cant-${idx}`).max               = stock;

  actualizarResumen();
}

function obtenerMultiplicadorCliente() {
  const sel = document.getElementById('select-cliente');
  if (!sel) return 1;
  return parseFloat(sel.options[sel.selectedIndex]?.dataset?.multiplicador || 1);
}

function alCambiarCliente() {
  document.querySelectorAll('[name="product_id[]"]').forEach(sel => {
    if (sel.value) {
      const idx = sel.closest('.item-fila').id.replace('item-', '');
      alSeleccionarProducto(sel, idx);
    }
  });
}

function actualizarResumen() {
  let total = 0;
  let count = 0;
  document.querySelectorAll('.item-fila').forEach(fila => {
    const idx    = fila.id.replace('item-', '');
    const cant   = parseInt(document.getElementById(`cant-${idx}`)?.value || 0);
    const precio = parseInt(document.getElementById(`precio-${idx}`)?.value || 0);
    if (cant > 0 && precio > 0) { total += cant * precio; count++; }
  });

  const elTotal = document.getElementById('resumen-total');
  const elItems = document.getElementById('resumen-items');
  if (elTotal) elTotal.textContent = formatoPesos(total);
  if (elItems) elItems.textContent = document.querySelectorAll('.item-fila').length;
}

// Inicializar primera fila al cargar
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('items-lista')) {
    agregarItem();
  }
});
