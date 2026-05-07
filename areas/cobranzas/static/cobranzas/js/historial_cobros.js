// ════════════════════════════════════════════════════════════
// HISTORIAL DE COBROS — JS
// ════════════════════════════════════════════════════════════

const CANALES_HIST      = { pagofacil: 'Pago Fácil', rapipago: 'Rapipago', otro: 'Otro' };
const METODOS_EDIT      = { efectivo:'Efectivo', transferencia:'Transferencia', debito:'Débito', credito:'Crédito', qr:'QR' };
const ELIMINAR_URL      = "{% url 'cobranzas:cobros_eliminar' %}";
const LIMPIEZA_URL      = "{% url 'cobranzas:cobros_limpieza_automatica' %}";
const PREVISUALIZAR_URL = "{% url 'cobranzas:cobros_previsualizar_filtro' %}";
// ↓ Ajustá el nombre de la URL según lo que pongas en urls.py
const EDITAR_BASE_URL = "{% url 'cobranzas:cobro_editar' cobro_id=0 %}".replace('0/editar/', '');

function fmt(n) {
    return '$' + parseFloat(n || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2
    });
}
function getCsrf() {
    return document.cookie.split(';').map(c => c.trim())
        .find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
}
async function postJSON(url, body) {
    return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify(body),
    });
}
const el = id => document.getElementById(id);

document.addEventListener('DOMContentLoaded', () => {

    // ── Resumen totales ──────────────────────────────────────
    let sumBoletas = 0, sumAdicionales = 0, sumGeneral = 0;
    document.querySelectorAll('.hist-fila').forEach(f => {
        sumBoletas     += parseFloat(f.dataset.totalBoletas     || 0);
        sumAdicionales += parseFloat(f.dataset.totalAdicionales || 0);
        sumGeneral     += parseFloat(f.dataset.totalGeneral     || 0);
    });
    if (el('resumenFacturas'))    el('resumenFacturas').textContent    = fmt(sumBoletas);
    if (el('resumenAdicionales')) el('resumenAdicionales').textContent = fmt(sumAdicionales);
    if (el('resumenGeneral'))     el('resumenGeneral').textContent     = fmt(sumGeneral);

    // ── Modal detalle ────────────────────────────────────────
    document.querySelectorAll('.hist-btn-detalle').forEach(btn => {
        btn.addEventListener('click', () => {
            const items = btn.dataset.items ? btn.dataset.items.split(';;') : [];
            const pagos = btn.dataset.pagos ? btn.dataset.pagos.split(';;') : [];
            el('detalleTitle').textContent    = `Cobro #${btn.dataset.id}`;
            el('detalleSubtitle').textContent = `${items.length} boleta${items.length !== 1 ? 's' : ''}`;
            el('detalleItems').innerHTML = items.map(raw => {
                const [cod, desc, factura, adicional, canal] = raw.split('|');
                return `<div class="cobro-item-row">
                    <div class="cobro-item-header">
                        <span class="codigo-badge">${cod}</span>
                        <span class="cobro-item-canal cobro-canal-${canal}">${CANALES_HIST[canal] || canal}</span>
                    </div>
                    <div class="cobro-item-desc">${desc}</div>
                    <div class="cobro-item-montos">
                        <div class="cobro-item-monto-col"><span class="cobro-monto-label">Factura</span><span class="cobro-monto-val">${fmt(factura)}</span></div>
                        <span class="cobro-monto-mas">+</span>
                        <div class="cobro-item-monto-col"><span class="cobro-monto-label">Adicional</span><span class="cobro-monto-val cobro-monto-adicional">${fmt(adicional)}</span></div>
                        <span class="cobro-monto-mas">=</span>
                        <div class="cobro-item-monto-col cobro-item-subtotal"><span class="cobro-monto-label">Subtotal</span><span class="cobro-monto-val cobro-monto-total">${fmt(parseFloat(factura)+parseFloat(adicional))}</span></div>
                    </div>
                </div>`;
            }).join('');
            el('detallePagos').innerHTML = pagos.map(raw => {
                const [metodo, monto] = raw.split('|');
                return `<div class="cobro-pago-row" style="background:#f8f9fb;border-radius:6px;padding:.4rem .7rem;">
                    <span style="font-size:.83rem;font-weight:600;">${metodo}</span>
                    <span style="font-size:.83rem;font-weight:700;margin-left:auto;">${fmt(monto)}</span>
                </div>`;
            }).join('');
            const obs = btn.dataset.obs || '';
            el('detalleObs').style.display = obs ? '' : 'none';
            if (obs) el('detalleObsTexto').textContent = obs;
            new bootstrap.Modal(el('modalDetalle')).show();
        });
    });

    // ════════════════════════════════════════════════════════
    // SELECCIÓN MASIVA
    // ════════════════════════════════════════════════════════
    const checkTodos = el('checkTodos');

    function getIdsSeleccionados() {
        return [...document.querySelectorAll('.check-cobro:checked')].map(c => parseInt(c.dataset.id));
    }
    function actualizarBarra() {
        const ids   = getIdsSeleccionados();
        const barra = el('barraAccionesMasivas');
        if (!barra) return;
        barra.style.display = ids.length > 0 ? 'flex' : 'none';
        el('selCount').textContent = `${ids.length} seleccionado${ids.length !== 1 ? 's' : ''}`;
        if (checkTodos) {
            const total = document.querySelectorAll('.check-cobro').length;
            checkTodos.indeterminate = ids.length > 0 && ids.length < total;
            checkTodos.checked = ids.length === total && total > 0;
        }
    }
    checkTodos?.addEventListener('change', () => {
        document.querySelectorAll('.check-cobro').forEach(c => c.checked = checkTodos.checked);
        actualizarBarra();
    });
    document.querySelectorAll('.check-cobro').forEach(c => c.addEventListener('change', actualizarBarra));

    el('btnDeseleccionarTodo')?.addEventListener('click', () => {
        document.querySelectorAll('.check-cobro').forEach(c => c.checked = false);
        if (checkTodos) checkTodos.checked = false;
        actualizarBarra();
    });

    // ════════════════════════════════════════════════════════
    // ELIMINACIÓN INDIVIDUAL + MASIVA
    // ════════════════════════════════════════════════════════
    let idsAEliminar = [];
    const modalElim = new bootstrap.Modal(el('modalEliminarCobros'));

    function abrirEliminar(ids) {
        idsAEliminar = ids;
        el('elimTexto').textContent = ids.length === 1
            ? `¿Eliminás el cobro #${ids[0]}?`
            : `¿Eliminás los ${ids.length} cobros seleccionados?`;
        el('elimError').style.display = 'none';
        el('btnConfirmarElimCobros').disabled    = false;
        el('btnConfirmarElimCobros').textContent = 'Eliminar';
        modalElim.show();
    }

    document.querySelectorAll('.btn-eliminar-cobro').forEach(btn => {
        btn.addEventListener('click', () => abrirEliminar([parseInt(btn.dataset.id)]));
    });
    el('btnEliminarSeleccionados')?.addEventListener('click', () => {
        const ids = getIdsSeleccionados();
        if (ids.length) abrirEliminar(ids);
    });

    el('btnConfirmarElimCobros')?.addEventListener('click', async () => {
        const btn = el('btnConfirmarElimCobros');
        btn.disabled = true; btn.textContent = 'Eliminando…';
        el('elimError').style.display = 'none';
        try {
            const res  = await postJSON(ELIMINAR_URL, { ids: idsAEliminar });
            const data = await res.json();
            if (data.success) {
                idsAEliminar.forEach(id => document.querySelector(`.hist-fila[data-id="${id}"]`)?.remove());
                modalElim.hide();
                actualizarBarra();
                const n = document.querySelectorAll('.hist-fila').length;
                const sub = el('subtituloHistorial');
                if (sub) sub.textContent = `${n} cobro${n !== 1 ? 's' : ''} registrado${n !== 1 ? 's' : ''}`;
            } else {
                el('elimError').textContent = data.error || 'No se pudo eliminar.';
                el('elimError').style.display = '';
                btn.disabled = false; btn.textContent = 'Eliminar';
            }
        } catch {
            el('elimError').textContent = 'Error de conexión.';
            el('elimError').style.display = '';
            btn.disabled = false; btn.textContent = 'Eliminar';
        }
    });

    // ════════════════════════════════════════════════════════
    // MODAL ELIMINAR POR FILTROS
    // ════════════════════════════════════════════════════════
    const modalFiltros = el('modalEliminarFiltros')
        ? new bootstrap.Modal(el('modalEliminarFiltros')) : null;

    el('btnEliminarPorFiltros')?.addEventListener('click', () => {
        el('elimFiltroPreview').style.display = 'none';
        el('elimFiltroError').style.display   = 'none';
        el('btnConfirmarElimFiltro').disabled  = true;
        ['efDesde','efHasta','efUsuario','efCodigo','efMontoMin','efMontoMax']
            .forEach(id => { if (el(id)) el(id).value = ''; });
        if (el('efMetodo')) el('efMetodo').value = '';
        modalFiltros?.show();
    });

    function getFiltros() {
        return {
            desde:     el('efDesde')?.value    || '',
            hasta:     el('efHasta')?.value    || '',
            usuario:   el('efUsuario')?.value.trim()  || '',
            metodo:    el('efMetodo')?.value   || '',
            codigo:    el('efCodigo')?.value.trim()   || '',
            monto_min: el('efMontoMin')?.value || '',
            monto_max: el('efMontoMax')?.value || '',
        };
    }

    el('btnPrevisualizarElim')?.addEventListener('click', async () => {
        const btn = el('btnPrevisualizarElim');
        btn.disabled = true; btn.textContent = 'Consultando…';
        el('elimFiltroError').style.display  = 'none';
        el('elimFiltroPreview').style.display = 'none';
        el('btnConfirmarElimFiltro').disabled = true;
        try {
            const res  = await postJSON(PREVISUALIZAR_URL, getFiltros());
            const data = await res.json();
            if (data.error) {
                el('elimFiltroError').textContent = data.error;
                el('elimFiltroError').style.display = '';
            } else {
                el('elimFiltroCount').textContent = data.count;
                el('elimFiltroPreview').style.display = '';
                el('btnConfirmarElimFiltro').disabled = data.count === 0;
            }
        } catch {
            el('elimFiltroError').textContent = 'Error de conexión.';
            el('elimFiltroError').style.display = '';
        } finally {
            btn.disabled = false; btn.textContent = 'Previsualizar';
        }
    });

    el('btnConfirmarElimFiltro')?.addEventListener('click', async () => {
        const btn = el('btnConfirmarElimFiltro');
        btn.disabled = true; btn.textContent = 'Eliminando…';
        el('elimFiltroError').style.display = 'none';
        try {
            const res  = await postJSON(ELIMINAR_URL, { filtros: getFiltros() });
            const data = await res.json();
            if (data.success) {
                modalFiltros?.hide();
                setTimeout(() => location.reload(), 300);
            } else {
                el('elimFiltroError').textContent = data.error || 'No se pudo eliminar.';
                el('elimFiltroError').style.display = '';
                btn.disabled = false; btn.textContent = 'Eliminar registros';
            }
        } catch {
            el('elimFiltroError').textContent = 'Error de conexión.';
            el('elimFiltroError').style.display = '';
            btn.disabled = false; btn.textContent = 'Eliminar registros';
        }
    });

    // ════════════════════════════════════════════════════════
    // LIMPIEZA AUTOMÁTICA
    // ════════════════════════════════════════════════════════
    el('btnLimpiezaAuto')?.addEventListener('click', () => {
        el('limpiezaError').style.display = 'none';
        el('limpiezaExito').style.display = 'none';
        el('btnConfirmarLimpieza').disabled    = false;
        el('btnConfirmarLimpieza').textContent = 'Ejecutar limpieza';
        new bootstrap.Modal(el('modalLimpieza')).show();
    });

    el('btnConfirmarLimpieza')?.addEventListener('click', async () => {
        const btn = el('btnConfirmarLimpieza');
        btn.disabled = true; btn.textContent = 'Procesando…';
        el('limpiezaError').style.display = 'none';
        el('limpiezaExito').style.display = 'none';
        try {
            const res  = await postJSON(LIMPIEZA_URL, {});
            const data = await res.json();
            if (data.success) {
                el('limpiezaExito').textContent = `✓ Se eliminaron ${data.eliminados} cobro(s) de ${data.periodo}.`;
                el('limpiezaExito').style.display = '';
                btn.textContent = 'Hecho';
                setTimeout(() => location.reload(), 2000);
            } else {
                el('limpiezaError').textContent = data.error || 'No se pudo ejecutar.';
                el('limpiezaError').style.display = '';
                btn.disabled = false; btn.textContent = 'Ejecutar limpieza';
            }
        } catch {
            el('limpiezaError').textContent = 'Error de conexión.';
            el('limpiezaError').style.display = '';
            btn.disabled = false; btn.textContent = 'Ejecutar limpieza';
        }
    });


    // ════════════════════════════════════════════════════════
    // MODAL EDITAR COBRO
    // ════════════════════════════════════════════════════════

    let editState = { cobroId: null, items: [], pagos: [], pagoSeq: 0 };
    const modalEditar = new bootstrap.Modal(el('modalEditarCobro'));

    // ── Abrir modal edición ──────────────────────────────────
    document.querySelectorAll('.hist-btn-editar').forEach(btn => {
        btn.addEventListener('click', () => {
            editState.cobroId = parseInt(btn.dataset.id);
            editState.pagoSeq = 0;

            // Parsear items: srvId|codigo|desc|montoSrv|montoAd|canal
            const itemsRaw = btn.dataset.itemsFull ? btn.dataset.itemsFull.split(';;') : [];
            editState.items = itemsRaw.map(raw => {
                const [srvId, codigo, desc, montoSrv, montoAd, canal] = raw.split('|');
                return {
                    servicio_id:     parseInt(srvId),
                    codigo,
                    desc,
                    monto_servicio:  parseFloat(montoSrv)  || 0,
                    monto_adicional: parseFloat(montoAd)   || 0,
                    canal:           canal || 'pagofacil',
                };
            });

            // Parsear pagos: metodo|monto
            const pagosRaw = btn.dataset.pagosFull ? btn.dataset.pagosFull.split(';;') : [];
            editState.pagos = pagosRaw.map(raw => {
                const [metodo, monto] = raw.split('|');
                return { id: ++editState.pagoSeq, metodo, monto: parseFloat(monto) || 0 };
            });

            el('editTitle').textContent    = `Editar cobro #${editState.cobroId}`;
            el('editSubtitle').textContent = `${editState.items.length} boleta${editState.items.length !== 1 ? 's' : ''}`;
            el('editFecha').value          = btn.dataset.fecha || '';
            el('editObs').value            = btn.dataset.obs   || '';
            el('editError').style.display  = 'none';

            renderEditItems();
            renderEditPagos();
            actualizarEditBalance();
            modalEditar.show();
        });
    });

    // ── Render items editables ───────────────────────────────
    function renderEditItems() {
        el('editItemsLista').innerHTML = editState.items.map((it, idx) => `
            <div class="edit-item-row" data-idx="${idx}">
                <div class="edit-item-header">
                    <span class="codigo-badge">${it.codigo}</span>
                    <select class="edit-canal-sel" data-idx="${idx}" data-field="canal">
                        <option value="pagofacil" ${it.canal==='pagofacil'?'selected':''}>Pago Fácil</option>
                        <option value="rapipago"  ${it.canal==='rapipago' ?'selected':''}>Rapipago</option>
                        <option value="otro"      ${it.canal==='otro'     ?'selected':''}>Otro</option>
                    </select>
                </div>
                <div class="edit-item-desc">${it.desc}</div>
                <div class="edit-item-montos">
                    <div>
                        <span class="edit-monto-label">Factura $</span>
                        <input type="number" class="edit-input-monto" min="0" step="0.01"
                               data-idx="${idx}" data-field="monto_servicio"
                               value="${it.monto_servicio.toFixed(2)}">
                    </div>
                    <span style="color:#aaa;font-size:.9rem;">+</span>
                    <div>
                        <span class="edit-monto-label">Adicional $</span>
                        <input type="number" class="edit-input-monto" min="0" step="0.01"
                               data-idx="${idx}" data-field="monto_adicional"
                               value="${it.monto_adicional.toFixed(2)}">
                    </div>
                    <span style="color:#aaa;font-size:.9rem;">=</span>
                    <div>
                        <span class="edit-monto-label">Subtotal</span>
                        <span class="edit-input-monto" style="display:inline-flex;align-items:center;
                              justify-content:flex-end;background:#f0f0f0;border-color:#e0e0e0;
                              font-weight:700;" id="editSubt${idx}">
                            ${fmt(it.monto_servicio + it.monto_adicional)}
                        </span>
                    </div>
                </div>
            </div>
        `).join('');

        // Listeners montos
        el('editItemsLista').querySelectorAll('[data-field="monto_servicio"],[data-field="monto_adicional"]')
            .forEach(inp => {
                inp.addEventListener('input', () => {
                    const idx = parseInt(inp.dataset.idx);
                    editState.items[idx][inp.dataset.field] = parseFloat(inp.value) || 0;
                    const it = editState.items[idx];
                    const subtEl = document.getElementById(`editSubt${idx}`);
                    if (subtEl) subtEl.textContent = fmt(it.monto_servicio + it.monto_adicional);
                    actualizarEditBalance();
                });
            });

        // Listeners canal
        el('editItemsLista').querySelectorAll('[data-field="canal"]').forEach(sel => {
            sel.addEventListener('change', () => {
                editState.items[parseInt(sel.dataset.idx)].canal = sel.value;
            });
        });
    }

    // ── Render pagos editables ───────────────────────────────
    function renderEditPagos() {
        const lista = el('editPagosLista');
        lista.innerHTML = editState.pagos.map(p => `
            <div class="edit-pago-row" data-pago-id="${p.id}">
                <select class="edit-pago-metodo" data-pago-id="${p.id}">
                    ${Object.entries(METODOS_EDIT).map(([val, lbl]) =>
                        `<option value="${val}" ${p.metodo===val?'selected':''}>${lbl}</option>`
                    ).join('')}
                </select>
                <span style="font-size:.85rem;color:#777;">$</span>
                <input type="number" class="edit-pago-monto" min="0" step="0.01"
                       data-pago-id="${p.id}"
                       value="${p.monto > 0 ? p.monto.toFixed(2) : ''}">
                ${editState.pagos.length > 1
                    ? `<button class="edit-pago-remove" data-pago-id="${p.id}">×</button>`
                    : '<span></span>'}
            </div>
        `).join('');

        lista.querySelectorAll('.edit-pago-metodo').forEach(sel => {
            sel.addEventListener('change', () => {
                const p = editState.pagos.find(x => x.id === parseInt(sel.dataset.pagoId));
                if (p) p.metodo = sel.value;
            });
        });
        lista.querySelectorAll('.edit-pago-monto').forEach(inp => {
            inp.addEventListener('input', () => {
                const p = editState.pagos.find(x => x.id === parseInt(inp.dataset.pagoId));
                if (p) p.monto = parseFloat(inp.value) || 0;
                actualizarEditBalance();
            });
        });
        lista.querySelectorAll('.edit-pago-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                editState.pagos = editState.pagos.filter(x => x.id !== parseInt(btn.dataset.pagoId));
                renderEditPagos();
                actualizarEditBalance();
            });
        });
    }

    el('editBtnAddPago')?.addEventListener('click', () => {
        editState.pagos.push({ id: ++editState.pagoSeq, metodo: 'efectivo', monto: 0 });
        renderEditPagos();
        actualizarEditBalance();
    });

    // ── Balance ──────────────────────────────────────────────
    function actualizarEditBalance() {
        const total    = editState.items.reduce((s, i) => s + i.monto_servicio + i.monto_adicional, 0);
        const asignado = editState.pagos.reduce((s, p) => s + p.monto, 0);
        const diff     = asignado - total;
        const balEl    = el('editBalanceMonto');
        if (Math.abs(diff) < 0.01) {
            balEl.textContent = '✓ Cubierto';
            balEl.className = 'edit-balance-ok';
        } else if (diff < 0) {
            balEl.textContent = `Faltan ${fmt(Math.abs(diff))}`;
            balEl.className = 'edit-balance-faltan';
        } else {
            balEl.textContent = `Sobran ${fmt(diff)}`;
            balEl.className = 'edit-balance-sobra';
        }
    }

    // ── Guardar edición ──────────────────────────────────────
    el('btnGuardarEdicion')?.addEventListener('click', async () => {
        el('editError').style.display = 'none';

        // Validar balance
        const total    = editState.items.reduce((s, i) => s + i.monto_servicio + i.monto_adicional, 0);
        const asignado = editState.pagos.reduce((s, p) => s + p.monto, 0);
        if (Math.round(asignado * 100) < Math.round(total * 100)) {
            el('editError').textContent = `Los pagos (${fmt(asignado)}) no cubren el total (${fmt(total)}).`;
            el('editError').style.display = '';
            return;
        }

        const payload = {
            items: editState.items.map(i => ({
                servicio_id:     i.servicio_id,
                monto_servicio:  i.monto_servicio,
                monto_adicional: i.monto_adicional,
                canal:           i.canal,
            })),
            pagos: editState.pagos.filter(p => p.monto > 0).map(p => ({
                metodo: p.metodo,
                monto:  p.monto,
            })),
            observaciones: el('editObs').value.trim(),
            fecha_cierre:  el('editFecha').value || null,
        };

        const btn = el('btnGuardarEdicion');
        btn.disabled = true; btn.textContent = 'Guardando…';

        try {
            const url = EDITAR_BASE_URL + editState.cobroId + '/editar/';
            const res  = await postJSON(url, payload);
            const data = await res.json();

            if (data.success) {
                // Actualizar fila en la tabla sin recargar la página
                const fila = document.querySelector(`.hist-fila[data-id="${editState.cobroId}"]`);
                if (fila) {
                    fila.dataset.totalBoletas     = data.total_boletas;
                    fila.dataset.totalAdicionales = data.total_adicionales;
                    fila.dataset.totalGeneral     = data.total_general;

                    // Celda fecha
                    const fechaSplit = data.fecha.split(' ');
                    const tdFecha = fila.querySelector('.hist-fecha');
                    const tdHora  = fila.querySelector('.hist-hora');
                    if (tdFecha) tdFecha.textContent = fechaSplit[0] || '';
                    if (tdHora)  tdHora.textContent  = fechaSplit[1] || '';

                    // Celda totales
                    const tds = fila.querySelectorAll('td');
                    // Buscamos por strong dentro de la celda de total cobrado
                    fila.querySelectorAll('.hist-total').forEach(el => {
                        el.textContent = fmt(data.total_general);
                    });
                    // Celda adicional
                    fila.querySelectorAll('.hist-adicional').forEach(el => {
                        el.textContent = fmt(data.total_adicionales);
                    });

                    // Recalcular resumen de cabecera
                    sumBoletas = sumAdicionales = sumGeneral = 0;
                    document.querySelectorAll('.hist-fila').forEach(f => {
                        sumBoletas     += parseFloat(f.dataset.totalBoletas     || 0);
                        sumAdicionales += parseFloat(f.dataset.totalAdicionales || 0);
                        sumGeneral     += parseFloat(f.dataset.totalGeneral     || 0);
                    });
                    if (el('resumenFacturas'))    el('resumenFacturas').textContent    = fmt(sumBoletas);
                    if (el('resumenAdicionales')) el('resumenAdicionales').textContent = fmt(sumAdicionales);
                    if (el('resumenGeneral'))     el('resumenGeneral').textContent     = fmt(sumGeneral);
                }
                modalEditar.hide();
                // Pequeño toast de éxito visual sin alert()
                mostrarToastExito(`Cobro #${data.cobro_id} actualizado correctamente.`);
            } else {
                el('editError').textContent = data.error || 'No se pudo guardar.';
                el('editError').style.display = '';
            }
        } catch {
            el('editError').textContent = 'Error de conexión. Intentá de nuevo.';
            el('editError').style.display = '';
        } finally {
            btn.disabled = false; btn.textContent = 'Guardar cambios';
        }
    });

    // ── Toast éxito ──────────────────────────────────────────
    function mostrarToastExito(msg) {
        const t = document.createElement('div');
        t.textContent = msg;
        Object.assign(t.style, {
            position:'fixed', bottom:'1.5rem', right:'1.5rem', zIndex:9999,
            background:'#16a34a', color:'#fff', borderRadius:'8px',
            padding:'.65rem 1.1rem', fontWeight:'600', fontSize:'.85rem',
            boxShadow:'0 4px 16px rgba(0,0,0,.18)', transition:'opacity .4s',
        });
        document.body.appendChild(t);
        setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 3000);
    }

});