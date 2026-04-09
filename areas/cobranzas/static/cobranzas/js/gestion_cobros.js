// ═══════════════════════════════════════════════════════════
// GESTIÓN DE COBROS — gestion_cobros.js  (híbrido)
//
// LÓGICA DE MONTOS (crítico — no modificar sin revisar todo):
//   Servicio.monto  = nuestro ADICIONAL (ganancia fija por cobro)
//   importe         = monto de la FACTURA del cliente (lo ingresa el usuario)
//   subtotal        = importe + adicional
//
// DOS MODOS DE BÚSQUEDA:
//   Tab 1 — Inteligente: prefijo + importe → backend detecta servicio automáticamente
//   Tab 2 — Texto:       búsqueda libre (código / descripción / proveedor) → selección manual
//
// Ambos modos usan el mismo endpoint /cobros/buscar-servicio/ pero con parámetros distintos:
//   Inteligente: ?prefijo=EX&valor=1500
//   Texto:       ?q=luz
// ═══════════════════════════════════════════════════════════

console.log("Módulo Gestión Cobros (híbrido) cargado.");

// ════════════════════════════════════════════════════════════
// ESTADO GLOBAL
// ════════════════════════════════════════════════════════════
const estado = {
    items:                    [],
    pagos:                    [],
    // Tab inteligente
    smartServicio:            null,   // servicio detectado automáticamente
    smartImporte:             0,      // importe confirmado para ese servicio
    // Tab texto
    textoServicioSeleccionado: null,
    // Secuencias
    pagoIdSeq:                0,
    itemIdSeq:                0,
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

// ════════════════════════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════════════════════════
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
// TABS
// ════════════════════════════════════════════════════════════
const panelInteligente = document.getElementById('panelTabInteligente');
const panelTexto       = document.getElementById('panelTabTexto');

document.querySelectorAll('.cobro-tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.cobro-tab').forEach(b => b.classList.remove('cobro-tab-active'));
        btn.classList.add('cobro-tab-active');

        const tab = btn.dataset.tab;
        panelInteligente.style.display = tab === 'inteligente' ? '' : 'none';
        panelTexto.style.display       = tab === 'texto'       ? '' : 'none';

        // Focus en el primer campo del tab activado
        if (tab === 'inteligente') {
            smartLimpiarResultado();
            document.getElementById('smartPrefijo').focus();
        } else {
            cerrarPanelCarga();
            document.getElementById('inputBuscarServicio').focus();
        }
    });
});


// ════════════════════════════════════════════════════════════
// TAB 1 — BÚSQUEDA INTELIGENTE (prefijo + importe)
// ════════════════════════════════════════════════════════════
const elSmartPrefijo       = document.getElementById('smartPrefijo');
const elSmartImporte       = document.getElementById('smartImporte');
const elSmartBuscando      = document.getElementById('smartBuscando');
const elSmartError         = document.getElementById('smartError');
const elSmartResultado     = document.getElementById('smartResultado');
const elSmartImporteConfirm = document.getElementById('smartImporteConfirm');

function smartMostrarError(msg) {
    elSmartError.textContent   = msg;
    elSmartError.style.display = '';
}
function smartOcultarError() {
    elSmartError.style.display = 'none';
}

function smartLimpiarResultado() {
    elSmartResultado.style.display = 'none';
    estado.smartServicio           = null;
    estado.smartImporte            = 0;
}

// Enter en prefijo → foco a importe
elSmartPrefijo.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); elSmartImporte.focus(); }
});

// Enter en importe → buscar
elSmartImporte.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('btnSmartBuscar').click(); }
});

// Limpiar resultado al editar los campos de búsqueda
elSmartPrefijo.addEventListener('input', () => {
    smartOcultarError();
    smartLimpiarResultado();
});
elSmartImporte.addEventListener('input', () => {
    smartOcultarError();
    smartLimpiarResultado();
});

// Botón buscar
document.getElementById('btnSmartBuscar').addEventListener('click', async () => {
    smartOcultarError();
    smartLimpiarResultado();

    const prefijo = elSmartPrefijo.value.trim().toUpperCase();
    const importe = parseFloat(elSmartImporte.value);

    if (!prefijo) {
        smartMostrarError('Ingresá el prefijo del servicio (ej: EX).');
        elSmartPrefijo.focus();
        return;
    }
    if (!importe || importe <= 0) {
        smartMostrarError('Ingresá un importe de factura válido.');
        elSmartImporte.focus();
        return;
    }

    elSmartBuscando.style.display = '';
    document.getElementById('btnSmartBuscar').disabled = true;

    try {
        const url  = `${window.cobroBuscarUrl}?prefijo=${encodeURIComponent(prefijo)}&valor=${encodeURIComponent(importe)}`;
        const res  = await fetch(url);
        const data = await res.json();

        if (!data.encontrado) {
            smartMostrarError(data.mensaje || 'No se encontró ningún servicio para ese prefijo e importe.');
            return;
        }

        // ── Servicio encontrado ──
        const s        = data.servicio;
        const adicional = parseFloat(s.monto);

        estado.smartServicio = s;
        estado.smartImporte  = importe;

        document.getElementById('smartSrvCodigo').textContent      = s.codigo;
        document.getElementById('smartSrvDescripcion').textContent = s.descripcion;
        document.getElementById('smartSrvProveedor').textContent   = s.proveedor || '';
        document.getElementById('smartSrvAdicional').textContent   =
            adicional.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        elSmartImporteConfirm.value = importe.toFixed(2);

        // Subtotal
        document.getElementById('smartSubtotalMonto').textContent = fmt(importe + adicional);

        elSmartResultado.style.display = '';

    } catch (err) {
        smartMostrarError('Error de red. Intentá de nuevo.');
        console.error(err);
    } finally {
        elSmartBuscando.style.display = 'none';
        document.getElementById('btnSmartBuscar').disabled = false;
    }
});

// Botón limpiar resultado
document.getElementById('btnSmartLimpiar').addEventListener('click', () => {
    smartLimpiarResultado();
    elSmartPrefijo.value  = '';
    elSmartImporte.value  = '';
    smartOcultarError();
    elSmartPrefijo.focus();
});

// Agregar boleta desde modo inteligente
document.getElementById('btnSmartAgregar').addEventListener('click', () => {
    const s       = estado.smartServicio;
    const importe = estado.smartImporte;
    if (!s || !importe || importe <= 0) return;

    const canal     = document.getElementById('smartCanal').value;
    const adicional = parseFloat(s.monto);

    estado.itemIdSeq++;
    estado.items.push({
        _id:             estado.itemIdSeq,
        servicio_id:     s.id,
        codigo:          s.codigo,
        descripcion:     s.descripcion,
        proveedor:       s.proveedor || '',
        monto_factura:   importe,
        monto_adicional: adicional,
        canal,
        _modo:           'inteligente',   // solo para trazabilidad interna, no se envía
    });

    renderCarrito();

    // Limpiar para la próxima boleta
    smartLimpiarResultado();
    elSmartPrefijo.value = '';
    elSmartImporte.value = '';
    elSmartPrefijo.focus();
});


// ════════════════════════════════════════════════════════════
// TAB 2 — BÚSQUEDA POR TEXTO (código / descripción / proveedor)
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
    if (!q) { mostrarEstadoBusqueda('placeholder'); return; }
    searchTimer = setTimeout(() => buscarServicios(q), 280);
});

btnLimpiar.addEventListener('click', () => {
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstadoBusqueda('placeholder');
    cerrarPanelCarga();
});

document.getElementById('btnDeseleccionar').addEventListener('click', () => {
    cerrarPanelCarga();
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstadoBusqueda('placeholder');
    inputBuscar.focus();
});

function mostrarEstadoBusqueda(cual) {
    elPlaceholder.style.display   = cual === 'placeholder' ? '' : 'none';
    elSinResultados.style.display = cual === 'vacio'       ? '' : 'none';
    elResultados.style.display    = cual === 'resultados'  ? '' : 'none';
}

async function buscarServicios(q) {
    try {
        const res  = await fetch(`${window.cobroBuscarUrl}?q=${encodeURIComponent(q)}`);
        const data = await res.json();

        if (!data.servicios || !data.servicios.length) {
            mostrarEstadoBusqueda('vacio');
            return;
        }

        // Nota: el "monto" del servicio es nuestro adicional
        listaResultados.innerHTML = data.servicios.map(s => `
            <div class="cobro-resultado-item" tabindex="0"
                 data-id="${s.id}"
                 data-codigo="${esc(s.codigo)}"
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

        mostrarEstadoBusqueda('resultados');

        listaResultados.querySelectorAll('.cobro-resultado-item').forEach(el => {
            const abrir = () => seleccionarServicio({
                id:          parseInt(el.dataset.id),
                codigo:      el.dataset.codigo,
                descripcion: el.dataset.descripcion,
                adicional:   parseFloat(el.dataset.adicional),
                proveedor:   el.dataset.proveedor,
            });
            el.addEventListener('click', abrir);
            el.addEventListener('keydown', e => { if (e.key === 'Enter') abrir(); });
        });

    } catch (err) {
        console.error('Error buscando servicios:', err);
    }
}

// ── Panel de carga manual ────────────────────────────────────
const agrImporte = document.getElementById('agrImporte');

function seleccionarServicio(s) {
    estado.textoServicioSeleccionado = s;

    document.getElementById('agrCodigo').textContent      = s.codigo;
    document.getElementById('agrDescripcion').textContent = s.descripcion;
    document.getElementById('agrProveedor').textContent   = s.proveedor || '';
    document.getElementById('agrAdicional').textContent   =
        parseFloat(s.adicional).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    agrImporte.value = '';
    document.getElementById('subtotalPreview').style.visibility = 'hidden';
    panelAgregar.style.display = '';

    // Marca el ítem seleccionado en la lista
    listaResultados.querySelectorAll('.cobro-resultado-item').forEach(el => {
        el.classList.toggle('cobro-resultado-selected', parseInt(el.dataset.id) === s.id);
    });

    setTimeout(() => agrImporte.focus(), 50);
}

function cerrarPanelCarga() {
    panelAgregar.style.display = 'none';
    estado.textoServicioSeleccionado = null;
}

// Subtotal en tiempo real
agrImporte.addEventListener('input', () => {
    const s = estado.textoServicioSeleccionado;
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

// Enter en importe → agregar
agrImporte.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btnAgregarItem').click();
});

document.getElementById('btnAgregarItem').addEventListener('click', () => {
    const s = estado.textoServicioSeleccionado;
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
        _id:             estado.itemIdSeq,
        servicio_id:     s.id,
        codigo:          s.codigo,
        descripcion:     s.descripcion,
        proveedor:       s.proveedor || '',
        monto_factura:   importe,
        monto_adicional: s.adicional,
        canal,
        _modo:           'texto',
    });

    renderCarrito();

    cerrarPanelCarga();
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstadoBusqueda('placeholder');
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
    carritoContenido.style.display = hay ? ''     : 'none';
    if (!hay) return;

    document.getElementById('badgeCount').textContent = estado.items.length;

    listaItems.innerHTML = estado.items.map(item => `
        <div class="cobro-item-row">
            <div class="cobro-item-header">
                <span class="codigo-badge">${esc(item.codigo)}</span>
                <span class="cobro-item-canal cobro-canal-${item.canal}">${CANALES[item.canal]}</span>
                <button class="cobro-item-remove" data-iid="${item._id}" title="Quitar boleta">×</button>
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
    const totFacturas  = estado.items.reduce((s, i) => s + i.monto_factura, 0);
    const totAdicional = estado.items.reduce((s, i) => s + i.monto_adicional, 0);
    const totGeneral   = totFacturas + totAdicional;

    document.getElementById('totalFacturas').textContent    = fmt(totFacturas);
    document.getElementById('totalAdicionales').textContent = fmt(totAdicional);
    document.getElementById('totalGeneral').textContent     = fmt(totGeneral);

    actualizarBalance();
}

function sincronizarPago() {
    // Si hay exactamente un método de pago, le auto-asigna el total
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
// CONFIRMAR COBRO
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

    // Payload — solo datos necesarios para el backend, sin campos internos (_id, _modo, etc.)
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
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body:    JSON.stringify(payload),
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
    estado.items                     = [];
    estado.pagos                     = [];
    estado.smartServicio             = null;
    estado.smartImporte              = 0;
    estado.textoServicioSeleccionado = null;
    estado.pagoIdSeq                 = 0;
    estado.itemIdSeq                 = 0;

    // Limpiar tab inteligente
    elSmartPrefijo.value  = '';
    elSmartImporte.value  = '';
    smartOcultarError();
    smartLimpiarResultado();

    // Limpiar tab texto
    inputBuscar.value = '';
    btnLimpiar.style.display = 'none';
    mostrarEstadoBusqueda('placeholder');
    cerrarPanelCarga();

    // Reiniciar carrito y pagos
    renderCarrito();
    renderPagos();
    agregarFilaPago('efectivo', 0);
    document.getElementById('cobroObservaciones').value = '';
    document.getElementById('cobroError').style.display = 'none';

    // Volver al tab inteligente y darle foco
    document.querySelectorAll('.cobro-tab').forEach(b => b.classList.remove('cobro-tab-active'));
    document.querySelector('[data-tab="inteligente"]').classList.add('cobro-tab-active');
    panelInteligente.style.display = '';
    panelTexto.style.display       = 'none';
    elSmartPrefijo.focus();
}


// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════
agregarFilaPago('efectivo', 0);
elSmartPrefijo.focus();