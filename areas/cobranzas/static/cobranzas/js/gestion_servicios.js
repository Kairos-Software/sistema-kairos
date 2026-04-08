document.addEventListener('DOMContentLoaded', function () {

    // ─── Helpers ────────────────────────────────────────────────────────────

    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => {
            const [k, val] = c.trim().split('=');
            if (k === name) v = decodeURIComponent(val);
        });
        return v;
    }

    async function postForm(url, fd) {
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: fd
        });
    }

    function parseMonto(valor) {
        if (!valor && valor !== 0) return '';
        if (typeof valor === 'number') return valor.toFixed(2);
        let str = String(valor).trim().replace(',', '.');
        let num = parseFloat(str);
        return isNaN(num) ? '' : num.toFixed(2);
    }

    // ─── Refs ────────────────────────────────────────────────────────────────

    const modalEl       = document.getElementById('servicioModal');
    const modal         = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl   = document.getElementById('eliminarModal');
    const elimModal     = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const form          = document.getElementById('formServicio');
    const btnNuevo      = document.getElementById('btnNuevoServicio');
    const btnGuardar    = document.getElementById('btnGuardarServicio');
    const formError     = document.getElementById('formError');

    // Código selector
    const selectPrefijo           = document.getElementById('selectPrefijo');
    const codigoPreview           = document.getElementById('codigoPreview');
    const codigoHint              = document.getElementById('codigoHint');
    const codigoSelectorRow       = document.getElementById('codigoSelectorRow');
    const codigoEditDisplay       = document.getElementById('codigoEditDisplay');
    const codigoEditBadge         = document.getElementById('codigoEditBadge');
    const nuevoPrefijoPannel      = document.getElementById('nuevoPrefijoPannel');
    const eliminarPrefijoPannel   = document.getElementById('eliminarPrefijoPannel');
    const inputNuevoPrefijo       = document.getElementById('inputNuevoPrefijo');
    const btnConfirmarPrefijo     = document.getElementById('btnConfirmarPrefijo');
    const btnCancelarPrefijo      = document.getElementById('btnCancelarPrefijo');
    const btnAgregarPrefijo       = document.getElementById('btnAgregarPrefijo');
    const btnEliminarPrefijo      = document.getElementById('btnEliminarPrefijo');
    const btnConfirmarElimPrefijo = document.getElementById('btnConfirmarEliminarPrefijo');
    const btnCancelarElimPrefijo  = document.getElementById('btnCancelarEliminarPrefijo');
    const eliminarPrefijoNombre   = document.getElementById('eliminarPrefijoNombre');
    const errorNuevoPrefijo       = document.getElementById('errorNuevoPrefijo');
    const errorEliminarPrefijo    = document.getElementById('errorEliminarPrefijo');
    const idCodigo                = document.getElementById('id_codigo');

    let pkEliminar = null;

    // ─── Último prefijo recordado ────────────────────────────────────────────
    const STORAGE_KEY_PREFIJO = 'cobranzas_ultimo_prefijo';

    function guardarUltimoPrefijo(prefijo) {
        try { localStorage.setItem(STORAGE_KEY_PREFIJO, prefijo); } catch {}
    }

    function leerUltimoPrefijo() {
        try { return localStorage.getItem(STORAGE_KEY_PREFIJO) || ''; } catch { return ''; }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ─── MÓDULO DE ORDENAMIENTO CLIENT-SIDE ─────────────────────────────
    //
    // Motivación: el ordenamiento en DB varía entre SQLite (dev) y
    // PostgreSQL/MySQL (prod) por diferencias de collation y soporte de
    // orden alfanumérico. Moverlo al cliente garantiza comportamiento
    // idéntico en todos los entornos y le da al usuario control total.
    //
    // Preferencia persistida en localStorage → sobrevive navegación y
    // recargas, sin necesidad de parámetros en la URL.
    // ═══════════════════════════════════════════════════════════════════════

    const STORAGE_KEY_ORDEN = 'cobranzas_orden_servicios';
    const tbody             = document.getElementById('tbodyServicios');
    const selectOrden       = document.getElementById('selectOrden');

    /**
     * Comparador alfanumérico natural.
     * "EX2" < "EX10" < "TR1"  (en lugar del léxico "EX10" < "EX2")
     */
    function cmpAlfaNum(a, b) {
        return a.localeCompare(b, 'es', { numeric: true, sensitivity: 'base' });
    }

    /**
     * Ordena las filas visibles del tbody según la clave indicada.
     * No toca filas sin data-id (ej: fila vacía).
     *
     * @param {string} clave  – formato "campo_direccion", ej: "codigo_asc"
     */
    function ordenarTabla(clave) {
        if (!tbody) return;

        const filas = [...tbody.querySelectorAll('tr[data-id]')];
        if (!filas.length) return;

        const [campo, dir] = clave.split('_');
        const asc = (dir !== 'desc');

        filas.sort((a, b) => {
            let va, vb;

            switch (campo) {
                case 'monto':
                    va = parseFloat(a.dataset.monto) || 0;
                    vb = parseFloat(b.dataset.monto) || 0;
                    return asc ? va - vb : vb - va;

                case 'activo':
                    // true=1, false=0
                    va = a.dataset.activo === 'true' ? 1 : 0;
                    vb = b.dataset.activo === 'true' ? 1 : 0;
                    // desc → activos (1) primero; asc → inactivos (0) primero
                    return asc ? va - vb : vb - va;

                case 'descripcion':
                    va = (a.dataset.descripcion || '').toLowerCase();
                    vb = (b.dataset.descripcion || '').toLowerCase();
                    return asc ? va.localeCompare(vb, 'es') : vb.localeCompare(va, 'es');

                case 'codigo':
                default:
                    va = a.dataset.codigo || '';
                    vb = b.dataset.codigo || '';
                    return asc ? cmpAlfaNum(va, vb) : cmpAlfaNum(vb, va);
            }
        });

        // Re-insertar en el nuevo orden (mantiene filas especiales al final)
        filas.forEach(tr => tbody.appendChild(tr));

        // Actualizar flechas en los headers
        actualizarFlechasHeader(campo, asc);
    }

    /** Dibuja ↑ / ↓ en el th activo y limpia los demás. */
    function actualizarFlechasHeader(campoActivo, asc) {
        document.querySelectorAll('.th-sort-arrow').forEach(el => {
            const col = el.dataset.col;
            if (col === campoActivo) {
                el.textContent = asc ? ' ↑' : ' ↓';
                el.closest('th')?.classList.add('th-sorted');
            } else {
                el.textContent = '';
                el.closest('th')?.classList.remove('th-sorted');
            }
        });
    }

    /** Guarda la preferencia y aplica el orden. */
    function aplicarOrden(clave) {
        try { localStorage.setItem(STORAGE_KEY_ORDEN, clave); } catch {}
        ordenarTabla(clave);
        if (selectOrden) selectOrden.value = clave;
    }

    // Inicialización: leer preferencia guardada (default: codigo_asc)
    const ordenGuardado = (() => {
        try { return localStorage.getItem(STORAGE_KEY_ORDEN) || 'codigo_asc'; } catch { return 'codigo_asc'; }
    })();
    aplicarOrden(ordenGuardado);

    // Cambio desde el select desplegable
    if (selectOrden) {
        selectOrden.addEventListener('change', () => aplicarOrden(selectOrden.value));
    }

    // Clic en cabecera de columna → alterna asc/desc
    document.querySelectorAll('.th-sortable').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            const [actualCampo, actualDir] = (selectOrden?.value || ordenGuardado).split('_');
            // Si ya estamos ordenados por esta columna, invertir; sino asc
            const nuevaDir = (col === actualCampo && actualDir === 'asc') ? 'desc' : 'asc';
            aplicarOrden(`${col}_${nuevaDir}`);
        });
    });

    // ─── 1. BUSCADOR EN VIVO ────────────────────────────────────────────────

    const inputBusqueda     = document.getElementById('inputBusqueda');
    const btnLimpiarBusq    = document.getElementById('btnLimpiarBusqueda');
    const paginacion        = document.getElementById('paginacion');
    const tmplSinResultados = document.getElementById('tmplSinResultados');
    let rowLiveEmpty        = null;

    function filtrarTabla(termino) {
        const t = termino.toLowerCase().trim();

        // Mostrar/ocultar botón limpiar
        if (btnLimpiarBusq) btnLimpiarBusq.style.display = t ? 'flex' : 'none';

        // Remover fila "sin resultados" anterior
        if (rowLiveEmpty) { rowLiveEmpty.remove(); rowLiveEmpty = null; }

        const filas = tbody ? [...tbody.querySelectorAll('tr[data-id]')] : [];
        let visibles = 0;

        filas.forEach(tr => {
            const hayMatch = !t || tr.dataset.search.includes(t);
            tr.style.display = hayMatch ? '' : 'none';
            if (hayMatch) visibles++;
        });

        // Ocultar paginación mientras se filtra en vivo (es client-side)
        if (paginacion) paginacion.style.display = t ? 'none' : '';

        // Fila vacía dinámica
        if (t && visibles === 0 && tmplSinResultados) {
            rowLiveEmpty = tmplSinResultados.content.cloneNode(true).querySelector('tr');
            rowLiveEmpty.querySelector('#terminoBusqueda').textContent = termino;
            tbody.appendChild(rowLiveEmpty);
        }
    }

    if (inputBusqueda) {
        // Filtrar mientras escribe (debounce leve)
        let debounce;
        inputBusqueda.addEventListener('input', () => {
            clearTimeout(debounce);
            debounce = setTimeout(() => filtrarTabla(inputBusqueda.value), 120);
        });

        // Enter → submit normal (server-side search)
        inputBusqueda.addEventListener('keydown', e => {
            if (e.key === 'Enter') document.getElementById('formFiltros').submit();
        });

        // Inicializar si ya hay un valor del servidor
        if (inputBusqueda.value) filtrarTabla(inputBusqueda.value);
    }

    if (btnLimpiarBusq) {
        btnLimpiarBusq.addEventListener('click', () => {
            if (inputBusqueda) inputBusqueda.value = '';
            filtrarTabla('');
            document.getElementById('formFiltros').submit();
        });
    }

    // ─── 2. SELECTOR DE CÓDIGO / AUTOINCREMENTO ─────────────────────────────

    async function cargarSiguienteCodigo(prefijo) {
        codigoPreview.textContent = '…';
        codigoHint.textContent    = '';
        try {
            const r = await fetch(`${window.servicioSiguienteUrl}?prefijo=${encodeURIComponent(prefijo)}`);
            const d = await r.json();
            if (d.codigo) {
                idCodigo.value            = d.codigo;
                codigoPreview.textContent = d.codigo;
                codigoHint.textContent    = '← código que se asignará';
            }
        } catch {
            codigoPreview.textContent = '—';
            codigoHint.textContent    = 'Error al obtener código';
        }
    }

    /** Muestra/oculta el botón "Eliminar prefijo" según si hay uno seleccionado */
    function actualizarBtnEliminar() {
        if (!btnEliminarPrefijo || !selectPrefijo) return;
        btnEliminarPrefijo.style.display = selectPrefijo.value ? 'inline-flex' : 'none';
    }

    /** Cierra ambos sub-paneles sin tocar el select */
    function cerrarPanelesPrefijo() {
        if (nuevoPrefijoPannel)    nuevoPrefijoPannel.style.display    = 'none';
        if (eliminarPrefijoPannel) eliminarPrefijoPannel.style.display = 'none';
        if (errorNuevoPrefijo)     errorNuevoPrefijo.style.display     = 'none';
        if (errorEliminarPrefijo)  errorEliminarPrefijo.style.display  = 'none';
        if (inputNuevoPrefijo)     inputNuevoPrefijo.value             = '';
    }

    if (selectPrefijo) {
        selectPrefijo.addEventListener('change', () => {
            cerrarPanelesPrefijo();
            actualizarBtnEliminar();
            const val = selectPrefijo.value;
            if (!val) {
                idCodigo.value            = '';
                codigoPreview.textContent = '—';
                codigoHint.textContent    = '';
                return;
            }
            guardarUltimoPrefijo(val);
            cargarSiguienteCodigo(val);
        });
    }

    // Botón externo: Agregar prefijo
    if (btnAgregarPrefijo) {
        btnAgregarPrefijo.addEventListener('click', () => {
            const yaAbierto = nuevoPrefijoPannel?.style.display === 'block';
            cerrarPanelesPrefijo();
            if (!yaAbierto) {
                nuevoPrefijoPannel.style.display = 'block';
                setTimeout(() => inputNuevoPrefijo?.focus(), 50);
            }
        });
    }

    // Botón externo: Eliminar prefijo seleccionado
    if (btnEliminarPrefijo) {
        btnEliminarPrefijo.addEventListener('click', () => {
            const prefijo = selectPrefijo?.value;
            if (!prefijo) return;
            const yaAbierto = eliminarPrefijoPannel?.style.display === 'block';
            cerrarPanelesPrefijo();
            if (!yaAbierto) {
                if (eliminarPrefijoNombre) eliminarPrefijoNombre.textContent = prefijo;
                eliminarPrefijoPannel.style.display = 'block';
            }
        });
    }

    // Confirmar agregar prefijo
    if (btnConfirmarPrefijo) {
        btnConfirmarPrefijo.addEventListener('click', async () => {
            const nuevo = (inputNuevoPrefijo?.value || '').trim().toUpperCase();
            if (!nuevo) { mostrarErrorPrefijo('Ingresá un prefijo.'); return; }
            if (!/^[A-Z]{1,10}$/.test(nuevo)) { mostrarErrorPrefijo('Solo letras, máximo 10 caracteres.'); return; }

            const fd = new FormData();
            fd.append('prefijo', nuevo);
            try {
                const r = await postForm(window.servicioPrefijosUrl, fd);
                const d = await r.json();
                if (d.error) { mostrarErrorPrefijo(d.error); return; }

                actualizarSelectPrefijos(d.prefijos, nuevo);
                cerrarPanelesPrefijo();
                actualizarBtnEliminar();
                guardarUltimoPrefijo(nuevo);
                cargarSiguienteCodigo(nuevo);
            } catch {
                mostrarErrorPrefijo('Error de conexión.');
            }
        });
    }

    if (btnCancelarPrefijo) {
        btnCancelarPrefijo.addEventListener('click', () => {
            cerrarPanelesPrefijo();
        });
    }

    // Confirmar eliminar prefijo
    if (btnConfirmarElimPrefijo) {
        btnConfirmarElimPrefijo.addEventListener('click', async () => {
            const prefijo = selectPrefijo?.value;
            if (!prefijo) return;

            const fd = new FormData();
            fd.append('prefijo', prefijo);
            fd.append('accion', 'eliminar');
            try {
                const r = await postForm(window.servicioPrefijosUrl, fd);
                const d = await r.json();
                if (d.error) {
                    if (errorEliminarPrefijo) {
                        errorEliminarPrefijo.textContent  = d.error;
                        errorEliminarPrefijo.style.display = 'block';
                    }
                    return;
                }
                actualizarSelectPrefijos(d.prefijos, '');
                cerrarPanelesPrefijo();
                idCodigo.value            = '';
                codigoPreview.textContent = '—';
                codigoHint.textContent    = '';
                actualizarBtnEliminar();
            } catch {
                if (errorEliminarPrefijo) {
                    errorEliminarPrefijo.textContent  = 'Error de conexión.';
                    errorEliminarPrefijo.style.display = 'block';
                }
            }
        });
    }

    if (btnCancelarElimPrefijo) {
        btnCancelarElimPrefijo.addEventListener('click', () => {
            cerrarPanelesPrefijo();
        });
    }

    // Enter en input nuevo prefijo → confirmar
    if (inputNuevoPrefijo) {
        inputNuevoPrefijo.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); btnConfirmarPrefijo?.click(); }
        });
        inputNuevoPrefijo.addEventListener('input', () => {
            inputNuevoPrefijo.value = inputNuevoPrefijo.value.toUpperCase();
        });
    }

    function mostrarErrorPrefijo(msg) {
        if (!errorNuevoPrefijo) return;
        errorNuevoPrefijo.textContent  = msg;
        errorNuevoPrefijo.style.display = 'block';
    }

    function actualizarSelectPrefijos(prefijos, seleccionado) {
        if (!selectPrefijo) return;
        selectPrefijo.innerHTML = '<option value="">— Prefijo —</option>';
        prefijos.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p; opt.textContent = p;
            selectPrefijo.appendChild(opt);
        });
        if (seleccionado) selectPrefijo.value = seleccionado;
    }

    // ─── 3. AUTOFOCUS ────────────────────────────────────────────────────────

    // Modal servicio: foco en el select de prefijo (nuevo) o descripción (editar)
    if (modalEl) {
        modalEl.addEventListener('shown.bs.modal', () => {
            const pk = document.getElementById('servicioPk')?.value;
            if (!pk) {
                // Nuevo: foco en selector de prefijo
                selectPrefijo?.focus();
            } else {
                // Editar: foco en descripción (primer campo editable)
                document.getElementById('id_descripcion')?.focus();
            }
        });
    }

    // Modal eliminar: foco en botón confirmar
    if (elimModalEl) {
        elimModalEl.addEventListener('shown.bs.modal', () => {
            document.getElementById('confirmarEliminarBtn')?.focus();
        });
    }

    // ─── 4. RESET Y POBLACIÓN DEL FORMULARIO ────────────────────────────────

    function ocultarError() {
        if (formError) formError.style.display = 'none';
    }

    function resetForm(mantenerPrefijo) {
        if (!form) return;
        form.reset();
        document.getElementById('servicioPk').value = '';
        document.getElementById('id_activo').checked = true;
        document.getElementById('id_monto').value    = '';
        document.getElementById('id_descripcion').value = '';
        document.getElementById('id_proveedor').value   = '';
        idCodigo.value = '';

        // Resetear selector de código: restaurar último prefijo si corresponde
        const ultimoPrefijo = mantenerPrefijo || leerUltimoPrefijo();
        if (selectPrefijo) {
            selectPrefijo.value = ultimoPrefijo || '';
        }
        if (ultimoPrefijo && selectPrefijo && selectPrefijo.value === ultimoPrefijo) {
            // Hay un prefijo recordado y existe en el select → cargar siguiente código
            cargarSiguienteCodigo(ultimoPrefijo);
        } else {
            if (codigoPreview) codigoPreview.textContent = '—';
            if (codigoHint)    codigoHint.textContent    = '';
        }
        cerrarPanelesPrefijo();
        actualizarBtnEliminar();

        // Mostrar selector, ocultar display edición
        if (codigoSelectorRow) codigoSelectorRow.style.display = '';
        if (codigoEditDisplay) codigoEditDisplay.style.display = 'none';

        ocultarError();
    }

    function poblarFormulario(servicio) {
        document.getElementById('servicioPk').value         = servicio.id;
        document.getElementById('id_descripcion').value     = servicio.descripcion;
        document.getElementById('id_proveedor').value       = servicio.proveedor || '';
        document.getElementById('id_activo').checked        = servicio.activo === true;
        document.getElementById('id_monto').value           = parseMonto(servicio.monto);

        // En edición el código no cambia: mostrar como badge, ocultar selector
        idCodigo.value = servicio.codigo;
        if (codigoEditBadge)    codigoEditBadge.textContent    = servicio.codigo;
        if (codigoSelectorRow)  codigoSelectorRow.style.display = 'none';
        if (codigoEditDisplay)  codigoEditDisplay.style.display = '';
        if (nuevoPrefijoPannel) nuevoPrefijoPannel.style.display = 'none';

        document.getElementById('servicioModalLabel').textContent = 'Editar servicio';
        ocultarError();
    }

    // ─── Helper: agregar fila a la tabla sin recargar ────────────────────────

    function agregarFilaTabla(servicio) {
        if (!tbody) return;

        // Quitar fila vacía si existe
        const rowEmpty = tbody.querySelector('#rowEmpty, #rowLiveEmpty');
        if (rowEmpty) rowEmpty.remove();

        const puedeEditar  = document.querySelector('.btn-editar')  !== null;
        const puedeEliminar= document.querySelector('.btn-eliminar') !== null;
        const tieneAcciones= puedeEditar || puedeEliminar;

        const estadoClass = servicio.activo ? 'estado-activo' : 'estado-inactivo';
        const estadoText  = servicio.activo ? 'Activo' : 'Inactivo';
        const montoFmt    = parseFloat(servicio.monto).toFixed(2);
        const proveedor   = servicio.proveedor || '—';

        const accionesHtml = tieneAcciones ? `
            <td>
                <div class="acciones-cell">
                    ${puedeEditar ? `
                    <button class="btn-accion btn-editar" data-id="${servicio.id}">Editar</button>
                    <button class="btn-accion btn-activar" data-id="${servicio.id}" data-activo="${servicio.activo}">
                        ${servicio.activo ? 'Desactivar' : 'Activar'}
                    </button>` : ''}
                    ${puedeEliminar ? `
                    <button class="btn-accion btn-eliminar" data-id="${servicio.id}" data-codigo="${servicio.codigo}">Eliminar</button>
                    ` : ''}
                </div>
            </td>` : '';

        const tr = document.createElement('tr');
        tr.dataset.id          = servicio.id;
        tr.dataset.codigo      = servicio.codigo;
        tr.dataset.descripcion = servicio.descripcion;
        tr.dataset.monto       = montoFmt;
        tr.dataset.proveedor   = servicio.proveedor || '';
        tr.dataset.activo      = servicio.activo ? 'true' : 'false';
        tr.dataset.search      = `${servicio.codigo.toLowerCase()} ${servicio.descripcion.toLowerCase()} ${(servicio.proveedor || '').toLowerCase()}`;

        tr.innerHTML = `
            <td><span class="codigo-badge">${servicio.codigo}</span></td>
            <td>${servicio.descripcion}</td>
            <td><strong>$${montoFmt}</strong></td>
            <td>${proveedor}</td>
            <td><span class="estado-badge ${estadoClass}">${estadoText}</span></td>
            ${accionesHtml}
        `;

        // Agregar la nueva fila y re-aplicar el orden actual
        tbody.appendChild(tr);
        ordenarTabla(selectOrden?.value || ordenGuardado);

        // Reenlazar eventos de la nueva fila
        tr.querySelector('.btn-editar')?.addEventListener('click', () => {
            poblarFormulario({
                id: servicio.id, codigo: servicio.codigo,
                descripcion: servicio.descripcion, monto: servicio.monto,
                proveedor: servicio.proveedor, activo: servicio.activo === true
            });
            modal?.show();
        });
        tr.querySelector('.btn-activar')?.addEventListener('click', async (e) => {
            const btn2 = e.currentTarget;
            const fd = new FormData();
            fd.append('pk', btn2.dataset.id);
            fd.append('activo', btn2.dataset.activo !== 'true');
            try {
                const resp = await postForm(window.servicioActivarUrl, fd);
                const data = await resp.json();
                if (data.success) location.reload();
                else alert('Error al cambiar estado.');
            } catch { alert('Error de conexión.'); }
        });
        tr.querySelector('.btn-eliminar')?.addEventListener('click', (e) => {
            const btn2 = e.currentTarget;
            pkEliminar = btn2.dataset.id;
            document.getElementById('nombreEliminar').textContent = btn2.dataset.codigo;
            elimModal?.show();
        });

        // Actualizar contador
        const contador = document.getElementById('contadorServicios');
        if (contador) {
            const totalFilas = tbody.querySelectorAll('tr[data-id]').length;
            contador.textContent = `${totalFilas} servicio${totalFilas !== 1 ? 's' : ''} registrado${totalFilas !== 1 ? 's' : ''}`;
        }
    }

    if (btnNuevo) {
        btnNuevo.addEventListener('click', () => {
            resetForm();
            document.getElementById('servicioModalLabel').textContent = 'Nuevo servicio';
            modal?.show();
        });
    }

    // ─── 6. BOTONES EDITAR ───────────────────────────────────────────────────

    document.querySelectorAll('.btn-editar').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            poblarFormulario({
                id:          row.dataset.id,
                codigo:      row.dataset.codigo,
                descripcion: row.dataset.descripcion,
                monto:       row.dataset.monto,
                proveedor:   row.dataset.proveedor,
                activo:      row.dataset.activo === 'true'
            });
            modal?.show();
        });
    });

    // ─── 7. GUARDAR ──────────────────────────────────────────────────────────

    if (btnGuardar) {
        btnGuardar.addEventListener('click', async () => {
            if (!form) return;

            // Validar que hay código seleccionado (solo en creación)
            const pk = document.getElementById('servicioPk')?.value;
            if (!pk && !idCodigo.value) {
                if (formError) {
                    formError.textContent  = '⚠ Seleccioná un prefijo para generar el código.';
                    formError.style.display = 'block';
                }
                return;
            }

            const fd = new FormData(form);
            ocultarError();
            btnGuardar.disabled    = true;
            btnGuardar.textContent = 'Guardando…';
            try {
                const resp = await postForm(window.servicioAccionesUrl, fd);
                const data = await resp.json();
                if (data.success) {
                    const pk = document.getElementById('servicioPk')?.value;
                    if (pk) {
                        // Edición: cerrar y recargar (comportamiento original)
                        modal?.hide();
                        location.reload();
                    } else {
                        // Creación: NO cerrar el modal, agregar fila y preparar siguiente
                        const prefijo = selectPrefijo?.value || leerUltimoPrefijo();
                        agregarFilaTabla(data.servicio);
                        resetForm(prefijo);
                        // Mostrar feedback breve sin cerrar
                        if (formError) {
                            formError.style.display = 'block';
                            formError.style.backgroundColor = '#d4edda';
                            formError.style.color = '#155724';
                            formError.style.borderColor = '#c3e6cb';
                            formError.textContent = `✓ Servicio ${data.servicio.codigo} guardado. Podés seguir cargando.`;
                            setTimeout(() => {
                                if (formError) formError.style.display = 'none';
                                formError.style.backgroundColor = '';
                                formError.style.color = '';
                                formError.style.borderColor = '';
                            }, 3000);
                        }
                        // Foco en descripción para agilizar la siguiente carga
                        setTimeout(() => document.getElementById('id_descripcion')?.focus(), 100);
                    }
                } else {
                    const err = Object.entries(data.errors || {})
                        .map(([k, v]) => `${k}: ${v.join(', ')}`)
                        .join(' | ');
                    if (formError) {
                        formError.textContent  = '⚠ ' + (err || 'Error al guardar.');
                        formError.style.display = 'block';
                    }
                }
            } catch {
                if (formError) {
                    formError.textContent  = 'Error de conexión.';
                    formError.style.display = 'block';
                }
            } finally {
                btnGuardar.disabled    = false;
                btnGuardar.textContent = 'Guardar servicio';
            }
        });
    }

    // ─── 8. ACTIVAR / DESACTIVAR ─────────────────────────────────────────────

    document.querySelectorAll('.btn-activar').forEach(btn => {
        btn.addEventListener('click', async () => {
            const fd = new FormData();
            fd.append('pk', btn.dataset.id);
            fd.append('activo', btn.dataset.activo !== 'true');
            try {
                const resp = await postForm(window.servicioActivarUrl, fd);
                const data = await resp.json();
                if (data.success) location.reload();
                else alert('Error al cambiar estado.');
            } catch { alert('Error de conexión.'); }
        });
    });

    // ─── 9. ELIMINAR ─────────────────────────────────────────────────────────

    document.querySelectorAll('.btn-eliminar').forEach(btn => {
        btn.addEventListener('click', () => {
            pkEliminar = btn.dataset.id;
            document.getElementById('nombreEliminar').textContent = btn.dataset.codigo;
            elimModal?.show();
        });
    });

    const confirmarElim = document.getElementById('confirmarEliminarBtn');
    if (confirmarElim) {
        confirmarElim.addEventListener('click', async () => {
            if (!pkEliminar) return;
            const fd = new FormData();
            fd.append('pk', pkEliminar);
            const resp = await postForm(window.servicioEliminarUrl, fd);
            const data = await resp.json();
            if (data.success) location.reload();
            else alert('Error al eliminar.');
        });
    }

});