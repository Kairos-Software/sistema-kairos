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

    const modalEl    = document.getElementById('servicioModal');
    const modal      = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarServicioModal');
    const elimModal  = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const form       = document.getElementById('formServicio');
    const btnNuevo   = document.getElementById('btnNuevoServicio');
    const errores    = document.getElementById('servicioErrores');

    let pkEliminar = null;

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('servicioPk').value = '';
        document.getElementById('servicioActivo').checked = true;
        document.getElementById('servicioModalTitulo').textContent = 'Nuevo servicio';
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        document.getElementById('servicioPk').value = row.dataset.id;
        document.getElementById('servicioNombre').value = row.dataset.nombre;
        document.getElementById('servicioDescripcion').value = row.dataset.descripcion;
        document.getElementById('servicioActivo').checked = row.dataset.activo === 'true';
        document.getElementById('servicioModalTitulo').textContent = 'Editar servicio';
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
        fd.set('activo', document.getElementById('servicioActivo').checked ? 'true' : 'false');

        const resp = await postForm(window.softwareUrls.servicioAcciones, fd);
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
            document.getElementById('eliminarServicioNombre').textContent = btn.dataset.nombre;
            document.getElementById('eliminarServicioError').style.display = 'none';
            elimModal.show();
        });
    });

    document.getElementById('btnConfirmarEliminarServicio')?.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData();
        fd.set('pk', pkEliminar);
        const resp = await postForm(window.softwareUrls.servicioEliminar, fd);
        const data = await resp.json();
        if (data.success) {
            window.location.reload();
        } else {
            const err = document.getElementById('eliminarServicioError');
            err.style.display = 'block';
            err.textContent = data.error || 'No se pudo eliminar.';
        }
    });

});
