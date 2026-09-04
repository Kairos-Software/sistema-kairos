// ═══════════════════════════════════════════════════════════
// CAJA.JS — Lógica de apertura/cierre de turno,
//            retiros y cierre diario.
// ═══════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    const URLS = window.cajaUrls || {};

    // ── CSRF ─────────────────────────────────────────────────
    function getCsrf() {
        return document.cookie.split(';')
            .map(c => c.trim())
            .find(c => c.startsWith('csrftoken='))
            ?.split('=')[1] || '';
    }

    async function ajax(url, body = null, method = 'POST') {
        const opts = {
            method,
            headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
        };
        if (body !== null) opts.body = JSON.stringify(body);
        const r = await fetch(url, opts);
        return r.json();
    }

    // ── FORMATO ───────────────────────────────────────────────
    function fmt(n) {
        return '$ ' + Number(n).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // ── ELEMENTOS ─────────────────────────────────────────────
    const panelCerrada = document.getElementById('panelCajaCerrada');
    const panelAbierta = document.getElementById('panelCajaAbierta');
    const subtitulo    = document.getElementById('cajaSubtitulo');

    let turnoActual = null;

    // ── ESTADO CAJA ──────────────────────────────────────────
    async function cargarEstado() {
        const data = await ajax(URLS.estado, null, 'GET');
        if (data.abierta) {
            turnoActual = data.turno;
            mostrarCajaAbierta(turnoActual);
        } else {
            turnoActual = null;
            mostrarCajaCerrada();
        }
    }

    function mostrarCajaCerrada() {
        panelCerrada.style.display = '';
        panelAbierta.style.display = 'none';
        subtitulo.textContent = 'Sin turno activo';
        document.getElementById('inputMontoInicial').value = '0';
        document.getElementById('abrirError').style.display = 'none';
        setTodayDates();
        actualizarIndicadorSidebar(false);
    }

    function mostrarCajaAbierta(t) {
        panelCerrada.style.display = 'none';
        panelAbierta.style.display = '';
        subtitulo.textContent = `Turno #${t.numero} abierto desde ${t.fecha_apertura}`;

        document.getElementById('badgeTurnoNumero').textContent            = '#' + t.numero;
        document.getElementById('turnoNombreCajero').textContent           = t.cajero;
        document.getElementById('turnoFechaApertura').textContent          = t.fecha_apertura;
        document.getElementById('turnoMontoInicial').textContent           = fmt(t.monto_inicial);
        document.getElementById('turnoCantCobros').textContent             = t.cant_cobros;
        document.getElementById('turnoEqFondo').textContent                = fmt(t.monto_inicial);
        document.getElementById('turnoTotEfectivo').textContent            = fmt(t.total_efectivo);
        document.getElementById('turnoTotTransferencia').textContent       = fmt(t.total_transferencia);
        document.getElementById('turnoTotDebito').textContent              = fmt(t.total_debito);
        document.getElementById('turnoTotCredito').textContent             = fmt(t.total_credito);
        document.getElementById('turnoTotQR').textContent                  = fmt(t.total_qr);
        document.getElementById('turnoTotRetiros').textContent             = fmt(t.total_retiros);
        document.getElementById('turnoTotIngresos').textContent            = fmt(t.total_ingresos);
        document.getElementById('turnoTotExtracciones').textContent        = fmt(t.total_extracciones);
        document.getElementById('turnoTotBoletas').textContent             = fmt(t.total_boletas);
        document.getElementById('turnoTotGeneral').textContent             = fmt(t.total_facturado);
        document.getElementById('turnoTotAdicionales').textContent         = fmt(t.total_adicionales);
        document.getElementById('turnoEfEsperado').textContent             = fmt(t.efectivo_esperado);

        Object.keys(retirosPorId).forEach(k => delete retirosPorId[k]);
        (t.retiros || []).forEach(r => { retirosPorId[r.id] = r; });
        editandoId = null;
        renderizarRetiros();

        // Pre-completar efectivo declarado con el esperado solo si está vacío
        const inputDecl = document.getElementById('inputEfectivoDeclarado');
        if (!inputDecl.value) {
            inputDecl.value = Number(t.efectivo_esperado).toFixed(2);
            actualizarDiferenciaPreview();
        }

        actualizarIndicadorSidebar(true);
    }

    // ── INDICADOR SIDEBAR ─────────────────────────────────────
    function actualizarIndicadorSidebar(abierta) {
        const ind = document.getElementById('navCajaIndicator');
        if (!ind) return;
        ind.style.display = '';
        ind.className = 'nav-caja-indicator ' + (abierta ? 'nav-caja-abierta' : 'nav-caja-cerrada');
        ind.title = abierta ? 'Caja abierta' : 'Caja cerrada';
    }

    // ── ABRIR CAJA ────────────────────────────────────────────
    document.getElementById('btnAbrirCaja').addEventListener('click', async () => {
        const montoInicial = parseFloat(document.getElementById('inputMontoInicial').value) || 0;
        const errEl = document.getElementById('abrirError');
        errEl.style.display = 'none';

        const btn = document.getElementById('btnAbrirCaja');
        btn.disabled = true;
        btn.textContent = 'Abriendo...';

        const data = await ajax(URLS.abrir, { monto_inicial: montoInicial });

        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="14" height="14">
            <rect x="2" y="7" width="12" height="8" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg> Abrir caja`;

        if (data.success) {
            turnoActual = data.turno;
            mostrarCajaAbierta(turnoActual);
            limpiarRetiros();
        } else {
            errEl.textContent = data.error || 'Error al abrir caja.';
            errEl.style.display = '';
        }
    });

    // ── MOVIMIENTOS (retiros e ingresos) ────────────────────────
    const retirosPorId = {};
    let movTipoActual = 'retiro';
    let editandoId = null;

    function escAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    document.querySelectorAll('.caja-tipo-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            movTipoActual = btn.dataset.tipo;
            document.querySelectorAll('.caja-tipo-btn').forEach(b => {
                b.classList.toggle('caja-tipo-btn-activo', b.dataset.tipo === movTipoActual);
            });
            const btnRegistrar = document.getElementById('btnRegistrarRetiro');
            btnRegistrar.textContent = movTipoActual === 'ingreso' ? '+ Registrar ingreso' : '+ Registrar retiro';
        });
    });

    function limpiarRetiros() {
        Object.keys(retirosPorId).forEach(k => delete retirosPorId[k]);
        renderizarRetiros();
        movTipoActual = 'retiro';
        document.querySelectorAll('.caja-tipo-btn').forEach(b => {
            b.classList.toggle('caja-tipo-btn-activo', b.dataset.tipo === 'retiro');
        });
        const btnRegistrar = document.getElementById('btnRegistrarRetiro');
        if (btnRegistrar) btnRegistrar.textContent = '+ Registrar retiro';
    }

    function renderizarRetiros() {
        const lista = document.getElementById('listaRetiros');
        const items = Object.values(retirosPorId);
        if (!items.length) {
            lista.innerHTML = '<p class="caja-sin-retiros">Sin movimientos registrados en este turno.</p>';
            return;
        }
        lista.innerHTML = items.map(r => {
            if (editandoId === r.id) {
                return `
                <div class="caja-retiro-item caja-retiro-item-editando" data-id="${r.id}">
                    <div class="caja-retiro-edit-form">
                        <div class="caja-tipo-toggle caja-retiro-edit-tipos">
                            <button type="button" class="caja-tipo-btn caja-retiro-edit-tipo ${r.tipo !== 'ingreso' ? 'caja-tipo-btn-activo' : ''}" data-tipo="retiro">Retiro</button>
                            <button type="button" class="caja-tipo-btn caja-retiro-edit-tipo ${r.tipo === 'ingreso' ? 'caja-tipo-btn-activo' : ''}" data-tipo="ingreso">Ingreso</button>
                        </div>
                        <input type="text" class="caja-input-text caja-retiro-edit-motivo" value="${escAttr(r.motivo)}" maxlength="200" placeholder="Motivo">
                        <div class="caja-input-wrap caja-retiro-edit-monto-wrap">
                            <span class="caja-signo">$</span>
                            <input type="number" class="caja-input caja-retiro-edit-monto" value="${r.monto}" min="0.01" step="0.01">
                        </div>
                    </div>
                    <p class="caja-retiro-edit-error" style="display:none;"></p>
                    <div class="caja-retiro-edit-acciones">
                        <button class="caja-retiro-guardar" data-id="${r.id}" title="Guardar cambios" aria-label="Guardar cambios"><i class="bi bi-check-lg" aria-hidden="true"></i></button>
                        <button class="caja-retiro-cancelar" data-id="${r.id}" title="Cancelar" aria-label="Cancelar edición"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
                    </div>
                </div>
            `;
            }
            const esIngreso = r.tipo === 'ingreso';
            return `
            <div class="caja-retiro-item ${esIngreso ? 'caja-mov-ingreso' : 'caja-mov-retiro'}" data-id="${r.id}">
                <span class="caja-mov-tipo-pill">${esIngreso ? 'Ingreso' : 'Retiro'}</span>
                <div class="caja-retiro-info">
                    <span class="caja-retiro-motivo">${r.motivo}</span>
                    <span class="caja-retiro-fecha">${r.fecha}</span>
                </div>
                <strong class="caja-retiro-monto">${esIngreso ? '+' : '−'}${fmt(r.monto)}</strong>
                <button class="caja-retiro-editar" data-id="${r.id}" title="Editar" aria-label="Editar movimiento"><i class="bi bi-pencil" aria-hidden="true"></i></button>
                <button class="caja-retiro-anular" data-id="${r.id}" title="Anular" aria-label="Anular movimiento"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
            </div>
        `;
        }).join('');
    }

    document.getElementById('btnRegistrarRetiro').addEventListener('click', async () => {
        const motivo = document.getElementById('retiroMotivo').value.trim();
        const monto  = parseFloat(document.getElementById('retiroMonto').value) || 0;
        const errEl  = document.getElementById('retiroError');
        errEl.style.display = 'none';

        if (!motivo) { errEl.textContent = 'El motivo es obligatorio.'; errEl.style.display = ''; return; }
        if (monto <= 0) { errEl.textContent = 'El monto debe ser mayor a cero.'; errEl.style.display = ''; return; }

        const data = await ajax(URLS.retiro, { tipo: movTipoActual, motivo, monto });
        if (data.success) {
            retirosPorId[data.retiro_id] = { id: data.retiro_id, tipo: data.tipo, motivo: data.motivo, monto: data.monto, fecha: data.fecha };
            renderizarRetiros();
            document.getElementById('retiroMotivo').value = '';
            document.getElementById('retiroMonto').value  = '';

            turnoActual.total_retiros     = data.total_retiros;
            turnoActual.total_ingresos    = data.total_ingresos;
            turnoActual.efectivo_esperado = data.efectivo_esperado;
            document.getElementById('turnoTotRetiros').textContent  = fmt(data.total_retiros);
            document.getElementById('turnoTotIngresos').textContent = fmt(data.total_ingresos);
            document.getElementById('turnoEfEsperado').textContent  = fmt(data.efectivo_esperado);
            actualizarDiferenciaPreview();
        } else {
            errEl.textContent = data.error || 'Error al registrar el movimiento.';
            errEl.style.display = '';
        }
    });

    document.getElementById('listaRetiros').addEventListener('click', async (e) => {
        const btnTipoEdit = e.target.closest('.caja-retiro-edit-tipo');
        if (btnTipoEdit) {
            btnTipoEdit.parentElement.querySelectorAll('.caja-retiro-edit-tipo').forEach(b => {
                b.classList.toggle('caja-tipo-btn-activo', b === btnTipoEdit);
            });
            return;
        }

        const btnEditar = e.target.closest('.caja-retiro-editar');
        if (btnEditar) {
            editandoId = parseInt(btnEditar.dataset.id);
            renderizarRetiros();
            return;
        }

        const btnCancelar = e.target.closest('.caja-retiro-cancelar');
        if (btnCancelar) {
            editandoId = null;
            renderizarRetiros();
            return;
        }

        const btnGuardar = e.target.closest('.caja-retiro-guardar');
        if (btnGuardar) {
            const id = parseInt(btnGuardar.dataset.id);
            const item = btnGuardar.closest('.caja-retiro-item-editando');
            const tipo = item.querySelector('.caja-retiro-edit-tipo.caja-tipo-btn-activo').dataset.tipo;
            const motivo = item.querySelector('.caja-retiro-edit-motivo').value.trim();
            const monto = parseFloat(item.querySelector('.caja-retiro-edit-monto').value) || 0;
            const errEl = item.querySelector('.caja-retiro-edit-error');

            if (!motivo) { errEl.textContent = 'El motivo es obligatorio.'; errEl.style.display = ''; return; }
            if (monto <= 0) { errEl.textContent = 'El monto debe ser mayor a cero.'; errEl.style.display = ''; return; }

            const data = await ajax(URLS.retiro, { id, tipo, motivo, monto }, 'PUT');
            if (data.success) {
                editandoId = null;
                retirosPorId[id] = { id, tipo: data.tipo, motivo: data.motivo, monto: data.monto, fecha: data.fecha };
                renderizarRetiros();
                turnoActual.total_retiros     = data.total_retiros;
                turnoActual.total_ingresos    = data.total_ingresos;
                turnoActual.efectivo_esperado = data.efectivo_esperado;
                document.getElementById('turnoTotRetiros').textContent  = fmt(data.total_retiros);
                document.getElementById('turnoTotIngresos').textContent = fmt(data.total_ingresos);
                document.getElementById('turnoEfEsperado').textContent  = fmt(data.efectivo_esperado);
                actualizarDiferenciaPreview();
            } else {
                errEl.textContent = data.error || 'Error al editar el movimiento.';
                errEl.style.display = '';
            }
            return;
        }

        const btnAnular = e.target.closest('.caja-retiro-anular');
        if (btnAnular) {
            const id = parseInt(btnAnular.dataset.id);
            if (!confirm('¿Anular este movimiento?')) return;

            const data = await ajax(URLS.retiro, { id }, 'DELETE');
            if (data.success) {
                delete retirosPorId[id];
                if (editandoId === id) editandoId = null;
                renderizarRetiros();
                turnoActual.total_retiros     = data.total_retiros;
                turnoActual.total_ingresos    = data.total_ingresos;
                turnoActual.efectivo_esperado = data.efectivo_esperado;
                document.getElementById('turnoTotRetiros').textContent  = fmt(data.total_retiros);
                document.getElementById('turnoTotIngresos').textContent = fmt(data.total_ingresos);
                document.getElementById('turnoEfEsperado').textContent  = fmt(data.efectivo_esperado);
                actualizarDiferenciaPreview();
            }
        }
    });

    // ── DIFERENCIA PREVIEW ────────────────────────────────────
    function actualizarDiferenciaPreview() {
        if (!turnoActual) return;
        const inputVal = parseFloat(document.getElementById('inputEfectivoDeclarado').value) || 0;
        const esperado = turnoActual.efectivo_esperado;
        const diff     = inputVal - esperado;

        const prevPanel = document.getElementById('diferenciaPrev');
        prevPanel.style.display = '';
        document.getElementById('difEsperado').textContent  = fmt(esperado);
        document.getElementById('difDeclarado').textContent = fmt(inputVal);

        const resEl = document.getElementById('difResultado');
        const label = document.getElementById('difLabel');
        const monto = document.getElementById('difMonto');

        resEl.className = 'caja-dif-resultado';
        if (diff > 0.005) {
            label.textContent = 'Sobrante';
            monto.textContent = fmt(diff);
            resEl.classList.add('caja-dif-sobrante');
        } else if (diff < -0.005) {
            label.textContent = 'Faltante';
            monto.textContent = fmt(Math.abs(diff));
            resEl.classList.add('caja-dif-faltante');
        } else {
            label.textContent = 'Sin diferencia';
            monto.textContent = '$ 0,00';
            resEl.classList.add('caja-dif-ok');
        }
    }

    document.getElementById('inputEfectivoDeclarado').addEventListener('input', actualizarDiferenciaPreview);

    // ── CERRAR TURNO ─────────────────────────────────────────
    document.getElementById('btnCerrarTurno').addEventListener('click', async () => {
        const efDecl = parseFloat(document.getElementById('inputEfectivoDeclarado').value) || 0;
        const errEl  = document.getElementById('cerrarError');
        errEl.style.display = 'none';

        if (!confirm(`¿Cerrar el turno #${turnoActual.numero}?\n\nEfectivo declarado: ${fmt(efDecl)}\nEsta acción no se puede deshacer.`)) return;

        const btn = document.getElementById('btnCerrarTurno');
        btn.disabled = true;
        btn.textContent = 'Cerrando...';

        const data = await ajax(URLS.cerrarTurno, { efectivo_declarado: efDecl });

        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="14" height="14">
            <rect x="2" y="7" width="12" height="8" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M6 11l1.5 1.5L10 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg> Cerrar turno`;

        if (data.success) {
            const diff  = data.diferencia;
            const signo = diff > 0 ? '+' : '';
            document.getElementById('cierreTurnoDetalle').innerHTML = `
                <div class="caja-modal-fila"><span>Turno</span><strong>#${data.numero}</strong></div>
                <div class="caja-modal-fila"><span>Boletas de terceros</span><strong>${fmt(data.total_boletas)}</strong></div>
                <div class="caja-modal-fila"><span>Nuestros adicionales (ganancia)</span><strong>${fmt(data.total_adicionales)}</strong></div>
                <div class="caja-modal-fila"><span>Total facturado</span><strong>${fmt(data.total_facturado)}</strong></div>
                <div class="caja-modal-fila caja-modal-sep"><span>Efectivo esperado en el cajón</span><strong>${fmt(data.efectivo_esperado)}</strong></div>
                <div class="caja-modal-fila"><span>Efectivo que contaste</span><strong>${fmt(data.efectivo_declarado)}</strong></div>
                <div class="caja-modal-fila caja-modal-dif ${diff > 0 ? 'sobrante' : diff < 0 ? 'faltante' : 'ok'}">
                    <span>Diferencia</span>
                    <strong>${signo}${fmt(Math.abs(diff))} — ${data.tipo_diferencia}</strong>
                </div>
            `;
            const modal = new bootstrap.Modal(document.getElementById('modalCierreTurno'));
            modal.show();
            turnoActual = null;
            limpiarRetiros();
            document.getElementById('inputEfectivoDeclarado').value = '';
            document.getElementById('diferenciaPrev').style.display = 'none';
            mostrarCajaCerrada();
        } else {
            errEl.textContent = data.error || 'Error al cerrar turno.';
            errEl.style.display = '';
        }
    });

    // Desde el modal, botón "Abrir nuevo turno"
    document.getElementById('btnAbrirNuevoTurno').addEventListener('click', () => {
        document.getElementById('inputMontoInicial').focus();
    });

    // ── CIERRE DIARIO ─────────────────────────────────────────
    function setTodayDates() {
        const now = new Date();
        const hoy = now.getFullYear() + '-'
            + String(now.getMonth() + 1).padStart(2, '0') + '-'
            + String(now.getDate()).padStart(2, '0');
        document.getElementById('cierreDesde').value = hoy;
        document.getElementById('cierreHasta').value = hoy;
    }

    document.getElementById('btnPrevisualizarCierre').addEventListener('click', async () => {
        const desde = document.getElementById('cierreDesde').value;
        const hasta = document.getElementById('cierreHasta').value;
        const errEl = document.getElementById('cierreError');
        errEl.style.display = 'none';
        document.getElementById('cierrePreviewPanel').style.display = 'none';
        document.getElementById('cierreExitoPanel').style.display   = 'none';

        const data = await ajax(URLS.cierrePrevisualizar, { desde, hasta });

        if (!data.success) {
            errEl.textContent = data.error || 'Error al previsualizar.';
            errEl.style.display = '';
            return;
        }

        const clsDif = d => d > 0.005 ? 'caja-dif-pos' : d < -0.005 ? 'caja-dif-neg' : '';
        const signo  = d => (d > 0 ? '+' : '');

        const filasT = data.turnos.map(t =>
            `<tr>
                <td>#${t.numero}</td>
                <td>${t.cajero}</td>
                <td>${t.fecha}</td>
                <td>${fmt(t.monto_inicial)}</td>
                <td>${fmt(t.ef_esperado)}</td>
                <td>${fmt(t.ef_decl)}</td>
                <td class="${clsDif(t.diferencia)}">${signo(t.diferencia)}${fmt(t.diferencia)}</td>
            </tr>`
        ).join('');

        const sumaDif = data.suma_diferencias_turnos || 0;

        document.getElementById('cierreResumen').innerHTML = `
            <div class="caja-cierre-bloques">

                <div class="caja-bloque caja-bloque-efectivo">
                    <div class="caja-bloque-titulo">Efectivo del período
                        <small>Lo que tiene que haber en el cajón</small></div>
                    <div class="caja-eq">
                        <div class="caja-eq-row"><span>Fondo inicial <em>(1er turno)</em></span><strong>${fmt(data.monto_inicial_dia)}</strong></div>
                        <div class="caja-eq-row caja-eq-mas"><span>Cobrado en efectivo</span><strong>${fmt(data.total_efectivo)}</strong></div>
                        <div class="caja-eq-row caja-eq-mas"><span>Ingresos de caja</span><strong>${fmt(data.total_ingresos)}</strong></div>
                        <div class="caja-eq-row caja-eq-menos"><span>Retiros de caja</span><strong>${fmt(data.total_retiros)}</strong></div>
                        <div class="caja-eq-row caja-eq-menos"><span>Extracciones entregadas</span><strong>${fmt(data.total_extracciones)}</strong></div>
                        <div class="caja-eq-row caja-eq-total"><span>Efectivo esperado</span><strong>${fmt(data.efectivo_esperado)}</strong></div>
                    </div>
                </div>

                <div class="caja-bloque caja-bloque-otros">
                    <div class="caja-bloque-titulo">Otros medios <small>No entran al cajón</small></div>
                    <div class="caja-mini-grid">
                        <div class="caja-total-row"><span>Transferencia</span><strong>${fmt(data.total_transferencia)}</strong></div>
                        <div class="caja-total-row"><span>Débito</span><strong>${fmt(data.total_debito)}</strong></div>
                        <div class="caja-total-row"><span>Crédito</span><strong>${fmt(data.total_credito)}</strong></div>
                        <div class="caja-total-row"><span>QR</span><strong>${fmt(data.total_qr)}</strong></div>
                    </div>
                </div>

                <div class="caja-bloque caja-bloque-factu">
                    <div class="caja-bloque-titulo">Facturación y ganancia</div>
                    <div class="caja-eq">
                        <div class="caja-eq-row"><span>Boletas de terceros</span><strong>${fmt(data.total_boletas)}</strong></div>
                        <div class="caja-eq-row caja-eq-mas caja-eq-ganancia"><span>Nuestros adicionales <em>(ganancia)</em></span><strong>${fmt(data.total_adicionales)}</strong></div>
                        <div class="caja-eq-row caja-eq-total"><span>Total facturado</span><strong>${fmt(data.total_boletas + data.total_adicionales)}</strong></div>
                    </div>
                </div>

            </div>

            <table class="caja-turnos-tabla">
                <thead><tr><th>#</th><th>Cajero</th><th>Fecha</th><th>Fondo</th><th>Esperado</th><th>Declarado</th><th>Dif.</th></tr></thead>
                <tbody>${filasT}</tbody>
                <tfoot><tr>
                    <td colspan="6">Suma de las diferencias que cada turno declaró al cerrar</td>
                    <td class="${clsDif(sumaDif)}">${signo(sumaDif)}${fmt(sumaDif)}</td>
                </tr></tfoot>
            </table>
            <p class="caja-bloque-hint" style="margin-top:.5rem;">
                Abajo ingresás el efectivo físico que contaste ahora. La diferencia del cierre
                debería coincidir con la <strong>suma de diferencias de los turnos</strong>
                (${signo(sumaDif)}${fmt(sumaDif)}). Si no coincide, revisá si entre turno y turno
                entró o salió efectivo sin registrarse.
            </p>
        `;

        document.getElementById('cierreEfectivoFisico').value = Number(data.efectivo_esperado).toFixed(2);
        document.getElementById('cierrePreviewPanel').style.display = '';
    });

    document.getElementById('btnEjecutarCierre').addEventListener('click', async () => {
        const desde    = document.getElementById('cierreDesde').value;
        const hasta    = document.getElementById('cierreHasta').value;
        const efFisico = parseFloat(document.getElementById('cierreEfectivoFisico').value) || 0;
        const errEl    = document.getElementById('cierreError');
        errEl.style.display = 'none';

        if (!confirm(`¿Ejecutar cierre diario?\nEfectivo físico declarado: ${fmt(efFisico)}\nEsta acción no se puede deshacer.`)) return;

        const btn = document.getElementById('btnEjecutarCierre');
        btn.disabled = true;
        btn.textContent = 'Ejecutando...';

        const data = await ajax(URLS.cierreEjecutar, { desde, hasta, efectivo_fisico: efFisico });

        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="14" height="14">
            <path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg> Ejecutar cierre diario`;

        if (data.success) {
            const diff  = data.diferencia_caja;
            const signo = diff > 0 ? '+' : '';
            // URL de historial cierres pasada desde el template via window.cajaUrls
            const urlHistorial = URLS.historialCierres || '#';
            document.getElementById('cierrePreviewPanel').style.display = 'none';
            document.getElementById('cierreExitoPanel').style.display   = '';
            document.getElementById('cierreExitoPanel').innerHTML = `
                <div class="caja-cierre-exito">
                    <div class="caja-cierre-exito-ico"><i class="bi bi-check-circle" aria-hidden="true"></i></div>
                    <h3>Cierre #${data.cierre_id} ejecutado</h3>
                    <div class="caja-modal-fila"><span>Turnos cerrados</span><strong>${data.cant_turnos}</strong></div>
                    <div class="caja-modal-fila"><span>Total recaudado</span><strong>${fmt(data.total_general)}</strong></div>
                    <div class="caja-modal-fila"><span>Adicionales (ganancia)</span><strong>${fmt(data.total_adicionales)}</strong></div>
                    <div class="caja-modal-fila"><span>Efectivo físico</span><strong>${fmt(data.efectivo_fisico)}</strong></div>
                    <div class="caja-modal-fila ${diff > 0 ? 'texto-sobrante' : diff < 0 ? 'texto-faltante' : 'texto-ok'}">
                        <span>Diferencia de caja</span>
                        <strong>${signo}${fmt(Math.abs(diff))}</strong>
                    </div>
                    <p style="margin-top:.8rem;font-size:.85rem;color:#888;">${data.fecha}</p>
                    <a href="${urlHistorial}" class="btn-caja-secundario" style="margin-top:.5rem;display:inline-flex;">
                        Ver historial de cierres
                    </a>
                </div>
            `;
        } else {
            errEl.textContent = data.error || 'Error al ejecutar cierre.';
            errEl.style.display = '';
        }
    });

    // ── INIT ─────────────────────────────────────────────────
    setTodayDates();
    cargarEstado();
    renderizarRetiros();
});
