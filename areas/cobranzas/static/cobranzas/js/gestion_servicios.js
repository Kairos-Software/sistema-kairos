document.addEventListener('DOMContentLoaded', function () {

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

    const modalEl     = document.getElementById('servicioModal');
    const modal       = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarModal');
    const elimModal   = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const form        = document.getElementById('formServicio');
    const btnNuevo    = document.getElementById('btnNuevoServicio');
    const btnGuardar  = document.getElementById('btnGuardarServicio');
    const formError   = document.getElementById('formError');
    let pkEliminar    = null;

    function ocultarError() {
        if (formError) formError.style.display = 'none';
    }

    /* Reset completo para nuevo servicio */
    function resetForm() {
        if (!form) return;
        form.reset();
        document.getElementById('servicioPk').value = '';
        document.getElementById('id_activo').checked = true;
        document.getElementById('id_monto').value = '';
        ocultarError();
    }

    /* Convierte un string de monto (ej: "200,50" o "200.50") a número con punto decimal */
    function parseMonto(valor) {
        if (!valor && valor !== 0) return '';
        // Si ya es número, lo formateamos
        if (typeof valor === 'number') return valor.toFixed(2);
        // Convertimos a string y reemplazamos coma por punto
        let str = String(valor).trim().replace(',', '.');
        let num = parseFloat(str);
        return isNaN(num) ? '' : num.toFixed(2);
    }

    /* Poblar formulario para edición (SÍNCRONO Y SEGURO) */
    function poblarFormulario(servicio) {
        // Asignar campos simples
        document.getElementById('servicioPk').value = servicio.id;
        document.getElementById('id_codigo').value = servicio.codigo;
        document.getElementById('id_descripcion').value = servicio.descripcion;
        document.getElementById('id_proveedor').value = servicio.proveedor || '';
        document.getElementById('id_activo').checked = servicio.activo === true;

        // Campo monto: usar el parseador para garantizar punto decimal
        const montoField = document.getElementById('id_monto');
        let montoValor = parseMonto(servicio.monto);
        montoField.value = montoValor;

        // Cambiar título del modal
        document.getElementById('servicioModalLabel').textContent = 'Editar servicio';
        ocultarError();
    }

    /* ── NUEVO SERVICIO ── */
    if (btnNuevo) {
        btnNuevo.addEventListener('click', () => {
            resetForm();
            document.getElementById('servicioModalLabel').textContent = 'Nuevo servicio';
            modal?.show();
        });
    }

    /* ── EDITAR SERVICIO ── */
    document.querySelectorAll('.btn-editar').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            const servicio = {
                id:          row.dataset.id,
                codigo:      row.dataset.codigo,
                descripcion: row.dataset.descripcion,
                monto:       row.dataset.monto,      // ya formateado con punto desde el template
                proveedor:   row.dataset.proveedor,
                activo:      row.dataset.activo === 'true'
            };
            poblarFormulario(servicio);
            modal?.show();
        });
    });

    /* ── GUARDAR ── */
    if (btnGuardar) {
        btnGuardar.addEventListener('click', async () => {
            if (!form) return;
            const fd = new FormData(form);
            ocultarError();
            btnGuardar.disabled    = true;
            btnGuardar.textContent = 'Guardando...';
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
            } catch (e) {
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

    /* ── ACTIVAR / DESACTIVAR ── */
    document.querySelectorAll('.btn-activar').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const activoActual = btn.dataset.activo === 'true';
            const nuevoActivo = !activoActual;
            const fd = new FormData();
            fd.append('pk', id);
            fd.append('activo', nuevoActivo);
            try {
                const resp = await postForm(window.servicioActivarUrl, fd);
                const data = await resp.json();
                if (data.success) location.reload();
                else alert('Error al cambiar estado.');
            } catch (e) {
                alert('Error de conexión.');
            }
        });
    });

    /* ── ELIMINAR ── */
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