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

    const modalEl     = document.getElementById('instalacionModal');
    const modal       = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarInstalacionModal');
    const elimModal   = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const form        = document.getElementById('formInstalacion');
    const btnNuevo    = document.getElementById('btnNuevaInstalacion');
    const errores     = document.getElementById('instErrores');

    // ─── Autocomplete de cliente ───────────────────────────────────────
    const inputBuscar = document.getElementById('instClienteBuscar');
    const lista       = document.getElementById('instClienteLista');
    const chip        = document.getElementById('instClienteChip');
    const chipTexto   = document.getElementById('instClienteChipTexto');
    const chipQuitar  = document.getElementById('instClienteChipQuitar');
    const inputCliId  = document.getElementById('instClienteId');
    const inputCliTxt = document.getElementById('instClienteTexto');

    let debounceTimer = null;

    function seleccionarCliente(id, label) {
        inputCliId.value = id;
        chipTexto.textContent = label;
        chip.style.display = 'block';
        inputBuscar.value = '';
        inputBuscar.style.display = 'none';
        lista.style.display = 'none';
        inputCliTxt.value = '';
        inputCliTxt.disabled = true;
    }

    function quitarCliente() {
        inputCliId.value = '';
        chip.style.display = 'none';
        inputBuscar.style.display = 'block';
        inputCliTxt.disabled = false;
    }

    chipQuitar?.addEventListener('click', quitarCliente);

    inputBuscar?.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = inputBuscar.value.trim();
        if (q.length < 2) {
            lista.style.display = 'none';
            return;
        }
        debounceTimer = setTimeout(async () => {
            try {
                const resp = await fetch(`${window.softwareUrls.clienteBuscar}?q=${encodeURIComponent(q)}`);
                const data = await resp.json();
                const clientes = data.clientes || [];
                lista.innerHTML = '';
                if (!clientes.length) {
                    lista.style.display = 'none';
                    return;
                }
                clientes.forEach(c => {
                    const item = document.createElement('div');
                    item.className = 'autocomplete-item';
                    item.textContent = c.label;
                    item.addEventListener('click', () => seleccionarCliente(c.id, c.label));
                    lista.appendChild(item);
                });
                lista.style.display = 'block';
            } catch {
                lista.style.display = 'none';
            }
        }, 250);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.autocomplete-wrap')) lista.style.display = 'none';
    });

    // ─── Alta / edición ─────────────────────────────────────────────────

    function resetClienteUI() {
        quitarCliente();
        inputCliTxt.disabled = false;
    }

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('instPk').value = '';
        document.getElementById('instalacionModalTitulo').textContent = 'Nueva instalación';
        resetClienteUI();
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        resetClienteUI();
        document.getElementById('instPk').value = row.dataset.id;
        document.getElementById('instVps').value = row.dataset.vps;
        document.getElementById('instServicio').value = row.dataset.servicio;
        document.getElementById('instDominio').value = row.dataset.dominio;
        document.getElementById('instPuerto').value = row.dataset.puerto;
        document.getElementById('instRutaProyecto').value = row.dataset.rutaProyecto;
        document.getElementById('instRutaService').value = row.dataset.rutaService;
        document.getElementById('instRutaConf').value = row.dataset.rutaConf;
        document.getElementById('instEstado').value = row.dataset.estado;
        document.getElementById('instDescripcion').value = row.dataset.descripcion;

        if (row.dataset.clienteId) {
            seleccionarCliente(row.dataset.clienteId, row.dataset.clienteNombre);
        } else if (row.dataset.clienteTexto) {
            inputCliTxt.value = row.dataset.clienteTexto;
        }

        document.getElementById('instalacionModalTitulo').textContent = 'Editar instalación';
        errores.style.display = 'none';
        modal.show();
    }

    btnNuevo?.addEventListener('click', abrirNuevo);

    document.querySelectorAll('.btn-editar').forEach(btn => {
        btn.addEventListener('click', () => abrirEditar(btn.closest('tr')));
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(form);

        const resp = await postForm(window.softwareUrls.instalacionAcciones, fd);
        const data = await resp.json();

        if (data.success) {
            window.location.reload();
        } else {
            errores.style.display = 'block';
            errores.textContent = data.errors
                ? Object.values(data.errors).flat().join(' ')
                : (data.error || 'Ocurrió un error al guardar.');
        }
    });

    // ─── Eliminar ───────────────────────────────────────────────────────

    let pkEliminar = null;

    document.querySelectorAll('.btn-eliminar').forEach(btn => {
        btn.addEventListener('click', () => {
            pkEliminar = btn.dataset.id;
            document.getElementById('eliminarInstalacionNombre').textContent = btn.dataset.nombre;
            document.getElementById('eliminarInstalacionError').style.display = 'none';
            elimModal.show();
        });
    });

    document.getElementById('btnConfirmarEliminarInstalacion')?.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData();
        fd.set('pk', pkEliminar);
        const resp = await postForm(window.softwareUrls.instalacionEliminar, fd);
        const data = await resp.json();
        if (data.success) {
            window.location.reload();
        } else {
            const err = document.getElementById('eliminarInstalacionError');
            err.style.display = 'block';
            err.textContent = data.error || 'No se pudo eliminar.';
        }
    });

});
