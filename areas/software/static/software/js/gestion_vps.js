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

    const modalEl    = document.getElementById('vpsModal');
    const modal      = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarVpsModal');
    const elimModal  = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const form       = document.getElementById('formVps');
    const btnNuevo   = document.getElementById('btnNuevoVps');
    const errores    = document.getElementById('vpsErrores');

    let pkEliminar = null;

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('vpsPk').value = '';
        document.getElementById('vpsActiva').checked = true;
        document.getElementById('vpsUsuarioSsh').value = 'root';
        document.getElementById('vpsModalTitulo').textContent = 'Nueva VPS';
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        document.getElementById('vpsPk').value = row.dataset.id;
        document.getElementById('vpsNombre').value = row.dataset.nombre;
        document.getElementById('vpsProveedor').value = row.dataset.proveedor;
        document.getElementById('vpsIp').value = row.dataset.ip;
        document.getElementById('vpsPlan').value = row.dataset.plan;
        document.getElementById('vpsFechaVencimiento').value = row.dataset.fechaVencimiento;
        document.getElementById('vpsNucleosCpu').value = row.dataset.nucleosCpu;
        document.getElementById('vpsMemoria').value = row.dataset.memoria;
        document.getElementById('vpsEspacioDisco').value = row.dataset.espacioDisco;
        document.getElementById('vpsAnchoBanda').value = row.dataset.anchoBanda;
        document.getElementById('vpsSistemaOperativo').value = row.dataset.sistemaOperativo;
        document.getElementById('vpsUsuarioSsh').value = row.dataset.usuarioSsh;
        document.getElementById('vpsAccesoSsh').value = row.dataset.accesoSsh;
        document.getElementById('vpsNotas').value = row.dataset.notas;
        document.getElementById('vpsActiva').checked = row.dataset.activa === 'true';
        document.getElementById('vpsModalTitulo').textContent = 'Editar VPS';
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
        fd.set('activa', document.getElementById('vpsActiva').checked ? 'true' : 'false');

        const resp = await postForm(window.softwareUrls.vpsAcciones, fd);
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

    document.querySelectorAll('.btn-eliminar').forEach(btn => {
        btn.addEventListener('click', () => {
            pkEliminar = btn.dataset.id;
            document.getElementById('eliminarVpsNombre').textContent = btn.dataset.nombre;
            document.getElementById('eliminarVpsError').style.display = 'none';
            elimModal.show();
        });
    });

    document.getElementById('btnConfirmarEliminarVps')?.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData();
        fd.set('pk', pkEliminar);
        const resp = await postForm(window.softwareUrls.vpsEliminar, fd);
        const data = await resp.json();
        if (data.success) {
            window.location.reload();
        } else {
            const err = document.getElementById('eliminarVpsError');
            err.style.display = 'block';
            err.textContent = data.error || 'No se pudo eliminar.';
        }
    });

});
