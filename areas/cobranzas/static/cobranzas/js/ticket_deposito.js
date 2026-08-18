(function () {
    'use strict';

    let modalTicketInstance = null;
    let depositoActualId    = null;
    let tipoActual          = null;
    let botonActivador      = null;

    const TIPO_LABELS = {
        efectivo_fisico:  'Efectivo físico',
        ya_en_banco:      'Transferencia al banco',
        saldo_plataforma: 'Corrección de saldo a favor',
        ticket_1:         'Ticket 1',
        ticket_2:         'Ticket 2',
    };

    function getCsrf() {
        return document.cookie.split(';')
            .map(c => c.trim())
            .find(c => c.startsWith('csrftoken='))
            ?.split('=')[1] || '';
    }

    const CAMPOS = {
        ticketNumeroOperacion: 'numero_operacion',
        ticketBanco:           'banco',
        ticketTitularNombre:   'titular_nombre',
        ticketTitularCuit:     'titular_cuit',
        ticketCuentaOrigen:    'cuenta_origen',
        ticketDestinatario:    'destinatario',
        ticketCuentaDestino:   'cuenta_destino',
        ticketSucursal:        'sucursal',
        ticketConcepto:        'concepto',
        ticketEstado:          'estado',
        ticketObservaciones:   'observaciones',
    };

    function limpiarModal() {
        Object.keys(CAMPOS).forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        document.getElementById('ticketFechaHora').value = '';
        document.getElementById('ticketMonto').value     = '';
        document.getElementById('ticketImagen').value    = '';
        const linkImg = document.getElementById('ticketImagenActualLink');
        linkImg.style.display = 'none';
        linkImg.href = '#';
        document.getElementById('ticketError').style.display = 'none';
        document.getElementById('ticketExito').style.display = 'none';
    }

    async function abrirModalTicket(depositoId, tipo, btn) {
        depositoActualId = depositoId;
        tipoActual        = tipo;
        botonActivador    = btn || null;
        limpiarModal();
        document.getElementById('ticketDepositoNum').textContent = '#' + depositoId;
        document.getElementById('ticketTipoLabel').textContent   = TIPO_LABELS[tipo] || tipo;

        try {
            const resp = await fetch(`${window.ticketDepositoUrl}?deposito_id=${depositoId}&tipo=${tipo}`);
            const data = await resp.json();
            if (data.existe) {
                Object.entries(CAMPOS).forEach(([id, campo]) => {
                    const el = document.getElementById(id);
                    if (el) el.value = data[campo] || '';
                });
                if (data.fecha_hora_ticket) {
                    document.getElementById('ticketFechaHora').value = data.fecha_hora_ticket.slice(0, 16);
                }
                if (data.monto_ticket !== null && data.monto_ticket !== undefined) {
                    document.getElementById('ticketMonto').value = data.monto_ticket;
                }
                if (data.imagen_url) {
                    const linkImg = document.getElementById('ticketImagenActualLink');
                    linkImg.href = data.imagen_url;
                    linkImg.style.display = 'block';
                }
            }
        } catch (e) {
            // Sin datos previos, se carga el modal vacío igual.
        }

        modalTicketInstance = new bootstrap.Modal(document.getElementById('modalTicket'));
        modalTicketInstance.show();
    }

    async function guardarTicket() {
        if (!depositoActualId || !tipoActual) return;
        const errEl = document.getElementById('ticketError');
        const okEl  = document.getElementById('ticketExito');
        const btn   = document.getElementById('btnGuardarTicket');

        errEl.style.display = 'none';
        okEl.style.display  = 'none';
        btn.disabled    = true;
        btn.textContent = 'Guardando...';

        const formData = new FormData();
        formData.append('deposito_id', depositoActualId);
        formData.append('tipo', tipoActual);
        Object.entries(CAMPOS).forEach(([id, campo]) => {
            formData.append(campo, document.getElementById(id).value.trim());
        });
        formData.append('fecha_hora_ticket', document.getElementById('ticketFechaHora').value);
        formData.append('monto_ticket', document.getElementById('ticketMonto').value);
        const archivo = document.getElementById('ticketImagen').files[0];
        if (archivo) formData.append('imagen', archivo);

        try {
            const resp = await fetch(window.ticketDepositoUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrf() },
                body: formData,
            });
            const data = await resp.json();

            if (data.success) {
                okEl.textContent = 'Ticket guardado correctamente.';
                okEl.style.display = '';
                if (botonActivador) {
                    botonActivador.classList.add('btn-ver-ticket-cargado');
                    botonActivador.textContent = botonActivador.dataset.labelCargado || 'Ticket cargado';
                }
                setTimeout(() => {
                    if (modalTicketInstance) modalTicketInstance.hide();
                }, 900);
            } else {
                errEl.textContent = data.error || 'Error al guardar el ticket.';
                errEl.style.display = '';
            }
        } catch (e) {
            errEl.textContent = 'Error de red al guardar el ticket.';
            errEl.style.display = '';
        }

        btn.disabled    = false;
        btn.textContent = 'Guardar ticket';
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.addEventListener('click', function (ev) {
            const btn = ev.target.closest('.btn-ver-ticket');
            if (btn) {
                abrirModalTicket(btn.dataset.depositoId, btn.dataset.tipo, btn);
            }
        });

        const btnGuardar = document.getElementById('btnGuardarTicket');
        if (btnGuardar) btnGuardar.addEventListener('click', guardarTicket);
    });
})();
