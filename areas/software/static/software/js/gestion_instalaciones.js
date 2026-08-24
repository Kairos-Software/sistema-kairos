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

    function resetPasswordUI() {
        const input = document.getElementById('instContrasenaAdmin');
        const btn   = document.getElementById('btnTogglePasswordInst');
        if (input) input.type = 'password';
        if (btn) btn.textContent = 'Ver';
    }

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('instPk').value = '';
        document.getElementById('instalacionModalTitulo').textContent = 'Nueva instalación';
        resetClienteUI();
        resetPasswordUI();
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        resetClienteUI();
        resetPasswordUI();
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
        document.getElementById('instComandos').value = row.dataset.comandos;
        document.getElementById('instUsuarioAdmin').value = row.dataset.usuarioAdmin;
        document.getElementById('instContrasenaAdmin').value = row.dataset.contrasenaAdmin;

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

    // ─── Comandos (ver / copiar) ──────────────────────────────────────────

    const comandosModalEl = document.getElementById('comandosModal');
    const comandosModal   = comandosModalEl ? new bootstrap.Modal(comandosModalEl) : null;

    document.querySelectorAll('.btn-ver-comandos').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            document.getElementById('comandosSubtitulo').textContent =
                `${row.dataset.servicioNombre} — ${row.dataset.vpsNombre}`;
            document.getElementById('comandosContenido').textContent = row.dataset.comandos || '';
            comandosModal.show();
        });
    });

    document.getElementById('btnCopiarComandos')?.addEventListener('click', async () => {
        const texto = document.getElementById('comandosContenido').textContent;
        try {
            await navigator.clipboard.writeText(texto);
            const btn = document.getElementById('btnCopiarComandos');
            const original = btn.textContent;
            btn.textContent = 'Copiado';
            setTimeout(() => { btn.textContent = original; }, 1500);
        } catch { /* clipboard no disponible */ }
    });

    // ─── QR (ver / imprimir / descargar) ─────────────────────────────────

    const qrModalEl = document.getElementById('qrModal');
    const qrModal   = qrModalEl ? new bootstrap.Modal(qrModalEl) : null;

    function urlQrPara(id) {
        return window.softwareUrls.instalacionQrBase.replace(/\/0\/qr\/$/, `/${id}/qr/`);
    }

    document.querySelectorAll('.btn-qr').forEach(btn => {
        btn.addEventListener('click', () => {
            const url = urlQrPara(btn.dataset.id);
            document.getElementById('qrDominio').textContent = btn.dataset.dominio;
            document.getElementById('qrImagen').src = url;
            const btnDescargar = document.getElementById('btnDescargarQr');
            btnDescargar.href = url;
            btnDescargar.setAttribute('download', `qr-${btn.dataset.dominio.replace(/[^a-z0-9.-]+/gi, '_')}.svg`);
            qrModal.show();
        });
    });

    // ─── Contraseña: mostrar/ocultar y copiar ────────────────────────────

    function wireTogglePassword(btn, input) {
        btn?.addEventListener('click', () => {
            const oculto = input.type === 'password';
            input.type = oculto ? 'text' : 'password';
            btn.textContent = oculto ? 'Ocultar' : 'Ver';
        });
    }

    function wireCopiar(btn, getTexto) {
        btn?.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(getTexto());
                const original = btn.textContent;
                btn.textContent = 'Copiado';
                setTimeout(() => { btn.textContent = original; }, 1500);
            } catch { /* clipboard no disponible */ }
        });
    }

    wireTogglePassword(document.getElementById('btnTogglePasswordInst'), document.getElementById('instContrasenaAdmin'));

    // ─── Credenciales (ver / copiar) ──────────────────────────────────────

    const credencialesModalEl = document.getElementById('credencialesModal');
    const credencialesModal   = credencialesModalEl ? new bootstrap.Modal(credencialesModalEl) : null;
    const inputCredUsuario    = document.getElementById('credencialesUsuario');
    const inputCredContrasena = document.getElementById('credencialesContrasena');
    const btnVerCredContrasena = document.getElementById('btnVerContrasenaAdmin');

    document.querySelectorAll('.btn-ver-credenciales').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            document.getElementById('credencialesSubtitulo').textContent =
                `${row.dataset.servicioNombre} — ${row.dataset.vpsNombre}`;
            inputCredUsuario.value = row.dataset.usuarioAdmin || '';
            inputCredContrasena.value = row.dataset.contrasenaAdmin || '';
            inputCredContrasena.type = 'password';
            btnVerCredContrasena.textContent = 'Ver';
            credencialesModal.show();
        });
    });

    wireTogglePassword(btnVerCredContrasena, inputCredContrasena);
    wireCopiar(document.getElementById('btnCopiarUsuarioAdmin'), () => inputCredUsuario.value);
    wireCopiar(document.getElementById('btnCopiarContrasenaAdmin'), () => inputCredContrasena.value);

    document.getElementById('btnImprimirQr')?.addEventListener('click', () => {
        const src    = document.getElementById('qrImagen').src;
        const titulo = document.getElementById('qrDominio').textContent;
        const ventana = window.open('', '_blank', 'width=420,height=520');
        if (!ventana) return;
        ventana.document.write(`
            <html>
                <head><title>QR — ${titulo}</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                             height:100vh;margin:0;font-family:sans-serif;">
                    <img src="${src}" style="width:300px;height:300px;" onload="window.print();">
                    <p style="margin-top:1rem;">${titulo}</p>
                </body>
            </html>
        `);
        ventana.document.close();
    });

});
