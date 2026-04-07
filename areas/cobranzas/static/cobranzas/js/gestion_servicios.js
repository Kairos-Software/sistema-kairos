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

    // ─── 1. BUSCADOR EN VIVO ────────────────────────────────────────────────

    const inputBusqueda     = document.getElementById('inputBusqueda');
    const btnLimpiarBusq    = document.getElementById('btnLimpiarBusqueda');
    const tbody             = document.getElementById('tbodyServicios');
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

    function resetForm() {
        if (!form) return;
        form.reset();
        document.getElementById('servicioPk').value = '';
        document.getElementById('id_activo').checked = true;
        document.getElementById('id_monto').value    = '';
        document.getElementById('id_descripcion').value = '';
        document.getElementById('id_proveedor').value   = '';
        idCodigo.value = '';

        // Resetear selector de código
        if (selectPrefijo) selectPrefijo.value = '';
        if (codigoPreview) codigoPreview.textContent = '—';
        if (codigoHint)    codigoHint.textContent    = '';
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

    // ─── 5. BOTÓN NUEVO ──────────────────────────────────────────────────────

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
                    modal?.hide();
                    location.reload();
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