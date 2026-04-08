// ═══════════════════════════════════════════════════════════
// GESTIÓN DE COBROS — gestion_cobros.js
//
// LÓGICA DE MONTOS (importante):
//   monto del servicio (modelo) = nuestro ADICIONAL, precio fijo
//   importe que carga el usuario = monto de la FACTURA del cliente
//   total por boleta = factura + adicional
// ═══════════════════════════════════════════════════════════

console.log("Módulo Gestión Cobros cargado.");

// ── Estado ──────────────────────────────────────────────────
const estado = {
    items: [],
    pagos: [],
    servicioSeleccionado: null,
    pagoIdSeq: 0,
    itemIdSeq: 0,
};

const CANALES = {
    pagofacil: 'Pago Fácil',
    rapipago:  'Rapipago',
    otro:      'Otro',
};

const METODOS_PAGO = {
    efectivo:      'Efectivo',
    transferencia: 'Transferencia',
    debito:        'Débito',
    credito:       'Crédito',
    qr:            'QR',
};

// ── Helpers ─────────────────────────────────────────────────
function fmt(n) {
    return '$' + parseFloat(n || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2
    });
}

function getCsrf() {
    return document.cookie.split(';')
        .map(c => c.trim())
        .find(c => c.startsWith('csrftoken='))
        ?.split('=')[1] || '';
}

function esc(str) {
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ════════════════════════════════════════════════════════════
// BÚSQUEDA
// ════════════════════════════════════════════════════════════
const inputBuscar     = document.getElementById('inputBuscarServicio');
const btnLimpiar      = document.getElementById('btnLimpiarBusqueda');
const elPlaceholder   = document.getElementById('buscarPlaceholder');
const elSinResultados = document.getElementById('sinResultados');
const elResultados    = document.getElementById('resultadosBusqueda');
const listaResultados = document.getElementById('listaResultados');
const panelAgregar    = document.getElementById('panelAgregar');

let searchTimer = null;

inputBuscar.addEventListener('input', () => {
    const q = inputBuscar.value.trim();
    btnLimpiar.style.display = q ? '' : 'none';
    clearTimeout(searchTimer);
    if (!q) { mostrarEstado('placeholder'); return; }
    searchTimer = setTimeout(() => buscarServicios(q), 280);
});

btnLimpiar.addEventListener('click', () => {
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstado('placeholder');
    cerrarPanelCarga();
});

document.getElementById('btnDeseleccionar').addEventListener('click', () => {
    cerrarPanelCarga();
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstado('placeholder');
    inputBuscar.focus();
});

function mostrarEstado(cual) {
    elPlaceholder.style.display   = cual === 'placeholder' ? '' : 'none';
    elSinResultados.style.display = cual === 'vacio'       ? '' : 'none';
    elResultados.style.display    = cual === 'resultados'  ? '' : 'none';
}

async function buscarServicios(q) {
    try {
        const res  = await fetch(`${window.cobroBuscarUrl}?q=${encodeURIComponent(q)}`);
        const data = await res.json();

        if (!data.servicios.length) { mostrarEstado('vacio'); return; }

        // El "monto" del servicio = nuestro adicional fijo
        listaResultados.innerHTML = data.servicios.map(s => `
            <div class="cobro-resultado-item" tabindex="0"
                 data-id="${s.id}" data-codigo="${esc(s.codigo)}"
                 data-descripcion="${esc(s.descripcion)}"
                 data-adicional="${s.monto}"
                 data-proveedor="${esc(s.proveedor || '')}">
                <div class="cobro-resultado-top">
                    <span class="codigo-badge">${esc(s.codigo)}</span>
                    <span class="cobro-resultado-adicional">+${fmt(s.monto)} adicional</span>
                </div>
                <div class="cobro-resultado-desc">${esc(s.descripcion)}</div>
                ${s.proveedor ? `<div class="cobro-resultado-proveedor">${esc(s.proveedor)}</div>` : ''}
            </div>
        `).join('');

        mostrarEstado('resultados');

        listaResultados.querySelectorAll('.cobro-resultado-item').forEach(el => {
            const abrir = () => seleccionarServicio({
                id:          parseInt(el.dataset.id),
                codigo:      el.dataset.codigo,
                descripcion: el.dataset.descripcion,
                adicional:   parseFloat(el.dataset.adicional),   // ← esto es el adicional
                proveedor:   el.dataset.proveedor,
            });
            el.addEventListener('click', abrir);
            el.addEventListener('keydown', e => { if (e.key === 'Enter') abrir(); });
        });

    } catch (err) {
        console.error('Error buscando servicios:', err);
    }
}

// ════════════════════════════════════════════════════════════
// PANEL DE CARGA
// ════════════════════════════════════════════════════════════
const agrImporte = document.getElementById('agrImporte');

function seleccionarServicio(s) {
    estado.servicioSeleccionado = s;

    document.getElementById('agrCodigo').textContent      = s.codigo;
    document.getElementById('agrDescripcion').textContent = s.descripcion;
    document.getElementById('agrProveedor').textContent   = s.proveedor || '';
    // Mostramos el adicional fijo del servicio
    document.getElementById('agrAdicional').textContent   =
        parseFloat(s.adicional).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    agrImporte.value = '';
    document.getElementById('subtotalPreview').style.visibility = 'hidden';
    panelAgregar.style.display = '';

    // Resalta ítem seleccionado
    listaResultados.querySelectorAll('.cobro-resultado-item').forEach(el => {
        el.classList.toggle('cobro-resultado-selected', parseInt(el.dataset.id) === s.id);
    });

    setTimeout(() => agrImporte.focus(), 50);
}

function cerrarPanelCarga() {
    panelAgregar.style.display = 'none';
    estado.servicioSeleccionado = null;
}

// Subtotal en tiempo real mientras escribe el importe
agrImporte.addEventListener('input', () => {
    const s = estado.servicioSeleccionado;
    if (!s) return;
    const importe  = parseFloat(agrImporte.value) || 0;
    const subtotal = importe + s.adicional;
    const preview  = document.getElementById('subtotalPreview');
    const monto    = document.getElementById('subtotalPreviewMonto');
    if (importe > 0) {
        monto.textContent = fmt(subtotal);
        preview.style.visibility = '';
    } else {
        preview.style.visibility = 'hidden';
    }
});

// Enter en el campo de importe = agregar
agrImporte.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btnAgregarItem').click();
});

document.getElementById('btnAgregarItem').addEventListener('click', () => {
    const s = estado.servicioSeleccionado;
    if (!s) return;

    const importe = parseFloat(agrImporte.value);
    if (!importe || importe <= 0) {
        agrImporte.focus();
        agrImporte.classList.add('cobro-input-error');
        setTimeout(() => agrImporte.classList.remove('cobro-input-error'), 1200);
        return;
    }

    const canal = document.getElementById('agrCanal').value;

    estado.itemIdSeq++;
    estado.items.push({
        _id:            estado.itemIdSeq,
        servicio_id:    s.id,
        codigo:         s.codigo,
        descripcion:    s.descripcion,
        proveedor:      s.proveedor,
        monto_factura:  importe,      // lo que ingresó el usuario
        monto_adicional: s.adicional, // fijo del servicio
        canal,
    });

    renderCarrito();
    cerrarPanelCarga();
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstado('placeholder');
    inputBuscar.focus();
});

// ════════════════════════════════════════════════════════════
// CARRITO
// ════════════════════════════════════════════════════════════
const carritoVacio     = document.getElementById('carritoVacio');
const carritoContenido = document.getElementById('carritoContenido');
const listaItems       = document.getElementById('listaItems');

function renderCarrito() {
    const hay = estado.items.length > 0;
    carritoVacio.style.display     = hay ? 'none' : '';
    carritoContenido.style.display = hay ? '' : 'none';
    if (!hay) return;

    document.getElementById('badgeCount').textContent = estado.items.length;

    listaItems.innerHTML = estado.items.map(item => `
        <div class="cobro-item-row">
            <div class="cobro-item-header">
                <span class="codigo-badge">${esc(item.codigo)}</span>
                <span class="cobro-item-canal cobro-canal-${item.canal}">${CANALES[item.canal]}</span>
                <button class="cobro-item-remove" data-iid="${item._id}" title="Quitar">×</button>
            </div>
            <div class="cobro-item-desc">${esc(item.descripcion)}</div>
            <div class="cobro-item-montos">
                <div class="cobro-item-monto-col">
                    <span class="cobro-monto-label">Factura</span>
                    <span class="cobro-monto-val">${fmt(item.monto_factura)}</span>
                </div>
                <span class="cobro-monto-mas">+</span>
                <div class="cobro-item-monto-col">
                    <span class="cobro-monto-label">Adicional</span>
                    <span class="cobro-monto-val cobro-monto-adicional">${fmt(item.monto_adicional)}</span>
                </div>
                <span class="cobro-monto-mas">=</span>
                <div class="cobro-item-monto-col cobro-item-subtotal">
                    <span class="cobro-monto-label">Subtotal</span>
                    <span class="cobro-monto-val cobro-monto-total">${fmt(item.monto_factura + item.monto_adicional)}</span>
                </div>
            </div>
        </div>
    `).join('');

    listaItems.querySelectorAll('.cobro-item-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            estado.items = estado.items.filter(i => i._id !== parseInt(btn.dataset.iid));
            renderCarrito();
            actualizarBalance();
        });
    });

    actualizarTotales();
    sincronizarPago();
}

function actualizarTotales() {
    const totFacturas   = estado.items.reduce((s, i) => s + i.monto_factura, 0);
    const totAdicional  = estado.items.reduce((s, i) => s + i.monto_adicional, 0);
    const totGeneral    = totFacturas + totAdicional;

    document.getElementById('totalFacturas').textContent   = fmt(totFacturas);
    document.getElementById('totalAdicionales').textContent = fmt(totAdicional);
    document.getElementById('totalGeneral').textContent    = fmt(totGeneral);

    actualizarBalance();
}

// Si hay un solo método de pago, le sugiere automáticamente el total
function sincronizarPago() {
    if (estado.pagos.length === 1) {
        const total = estado.items.reduce((s, i) => s + i.monto_factura + i.monto_adicional, 0);
        estado.pagos[0].monto = total;
        const inp = document.querySelector(`[data-pago-id="${estado.pagos[0].id}"] .cobro-pago-monto`);
        if (inp) inp.value = total.toFixed(2);
        actualizarBalance();
    }
}

// ════════════════════════════════════════════════════════════
// PAGOS
// ════════════════════════════════════════════════════════════
const listaPagos = document.getElementById('listaPagos');

function agregarFilaPago(metodo, monto) {
    estado.pagoIdSeq++;
    estado.pagos.push({ id: estado.pagoIdSeq, metodo: metodo || 'efectivo', monto: monto || 0 });
    renderPagos();
}

function renderPagos() {
    listaPagos.innerHTML = estado.pagos.map(p => `
        <div class="cobro-pago-row" data-pago-id="${p.id}">
            <select class="cobro-select cobro-pago-metodo" data-pago-id="${p.id}">
                ${Object.entries(METODOS_PAGO).map(([val, lbl]) =>
                    `<option value="${val}" ${p.metodo === val ? 'selected' : ''}>${lbl}</option>`
                ).join('')}
            </select>
            <div class="cobro-pago-monto-wrap">
                <span class="cobro-pago-signo">$</span>
                <input type="number" class="cobro-input-monto cobro-pago-monto"
                       data-pago-id="${p.id}"
                       value="${p.monto > 0 ? p.monto.toFixed(2) : ''}"
                       placeholder="0,00" min="0" step="0.01">
            </div>
            ${estado.pagos.length > 1
                ? `<button class="cobro-pago-remove" data-pago-id="${p.id}">×</button>`
                : '<span></span>'}
        </div>
    `).join('');

    listaPagos.querySelectorAll('.cobro-pago-metodo').forEach(sel => {
        sel.addEventListener('change', () => {
            const p = estado.pagos.find(x => x.id === parseInt(sel.dataset.pagoId));
            if (p) p.metodo = sel.value;
        });
    });

    listaPagos.querySelectorAll('.cobro-pago-monto').forEach(inp => {
        inp.addEventListener('input', () => {
            const p = estado.pagos.find(x => x.id === parseInt(inp.dataset.pagoId));
            if (p) p.monto = parseFloat(inp.value) || 0;
            actualizarBalance();
        });
    });

    listaPagos.querySelectorAll('.cobro-pago-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            estado.pagos = estado.pagos.filter(x => x.id !== parseInt(btn.dataset.pagoId));
            renderPagos();
            actualizarBalance();
        });
    });
}

document.getElementById('btnAgregarPago').addEventListener('click', () => {
    agregarFilaPago('efectivo', 0);
});

function actualizarBalance() {
    const total     = estado.items.reduce((s, i) => s + i.monto_factura + i.monto_adicional, 0);
    const asignado  = estado.pagos.reduce((s, p) => s + p.monto, 0);
    const pendiente = total - asignado;

    document.getElementById('totalAsignado').textContent = fmt(asignado);

    const balMonto = document.getElementById('balanceMonto');
    const balLabel = document.getElementById('balanceLabel');

    if (Math.abs(pendiente) < 0.01) {
        balMonto.textContent = '✓ Cubierto';
        balMonto.className   = 'cobro-balance-ok';
        balLabel.textContent = 'Estado';
    } else if (pendiente > 0) {
        balMonto.textContent = `${fmt(pendiente)} faltan`;
        balMonto.className   = 'cobro-balance-pendiente';
        balLabel.textContent = 'Falta asignar';
    } else {
        balMonto.textContent = `${fmt(Math.abs(pendiente))} de más`;
        balMonto.className   = 'cobro-balance-exceso';
        balLabel.textContent = 'Excedente';
    }
}

// ════════════════════════════════════════════════════════════
// CONFIRMAR
// ════════════════════════════════════════════════════════════
document.getElementById('btnConfirmarCobro').addEventListener('click', async () => {
    document.getElementById('cobroError').style.display = 'none';

    if (!estado.items.length) {
        mostrarError('No hay boletas cargadas.');
        return;
    }
    const total    = estado.items.reduce((s, i) => s + i.monto_factura + i.monto_adicional, 0);
    const asignado = estado.pagos.reduce((s, p) => s + p.monto, 0);

    if (!asignado) {
        mostrarError('Ingresá al menos un monto de pago.');
        return;
    }
    if (Math.round(asignado * 100) < Math.round(total * 100)) {
        mostrarError(`Los pagos (${fmt(asignado)}) no cubren el total (${fmt(total)}).`);
        return;
    }

    // Enviamos: monto_servicio = factura, monto_adicional = adicional
    const payload = {
        items: estado.items.map(i => ({
            servicio_id:     i.servicio_id,
            monto_servicio:  i.monto_factura,
            monto_adicional: i.monto_adicional,
            canal:           i.canal,
        })),
        pagos: estado.pagos.filter(p => p.monto > 0).map(p => ({
            metodo: p.metodo,
            monto:  p.monto,
        })),
        observaciones: document.getElementById('cobroObservaciones').value.trim(),
    };

    const btn = document.getElementById('btnConfirmarCobro');
    btn.disabled    = true;
    btn.textContent = 'Guardando...';

    try {
        const res  = await fetch(window.cobroConfirmarUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.success) {
            mostrarExito(data);
        } else {
            mostrarError(data.error || 'Error al guardar.');
        }
    } catch (err) {
        mostrarError('Error de red. Intentá de nuevo.');
        console.error(err);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="14" height="14">
            <path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"/></svg> Confirmar cobro`;
    }
});

function mostrarError(msg) {
    const el = document.getElementById('cobroError');
    el.textContent   = msg;
    el.style.display = '';
}

// ════════════════════════════════════════════════════════════
// MODAL ÉXITO
// ════════════════════════════════════════════════════════════
function mostrarExito(data) {
    document.getElementById('exitoCobroId').textContent = `Cobro #${data.cobro_id}`;
    document.getElementById('exitoFecha').textContent   = data.fecha;

    document.getElementById('exitoTotales').innerHTML = `
        <div class="cobro-exito-fila"><span>Facturas</span><strong>${fmt(data.total_boletas)}</strong></div>
        <div class="cobro-exito-fila"><span>Adicionales</span><strong>${fmt(data.total_adicionales)}</strong></div>
        <div class="cobro-exito-fila cobro-exito-total"><span>Total cobrado</span><strong>${fmt(data.total_general)}</strong></div>
    `;
    document.getElementById('exitoPagos').innerHTML = Object.entries(data.pagos)
        .map(([m, v]) => `<div class="cobro-exito-fila"><span>${m}</span><strong>${fmt(v)}</strong></div>`)
        .join('');

    new bootstrap.Modal(document.getElementById('modalExito')).show();
}

document.getElementById('btnNuevoCobro').addEventListener('click', resetear);

function resetear() {
    estado.items = [];
    estado.pagos = [];
    estado.servicioSeleccionado = null;
    estado.pagoIdSeq = 0;
    estado.itemIdSeq = 0;

    renderCarrito();
    renderPagos();
    agregarFilaPago('efectivo', 0);
    document.getElementById('cobroObservaciones').value = '';
    document.getElementById('cobroError').style.display = 'none';
    inputBuscar.focus();
}

// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════
agregarFilaPago('efectivo', 0);
inputBuscar.focus();