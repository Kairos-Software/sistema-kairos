/* home.js — Grupo Kairos — SVG animado v4 (sin Three.js) */
(function () {
    'use strict';

    var ORANGE = '#E85C0D';
    var ORANGE_L = '#ff8c42';
    var BG = '#0a0a12';

    function ready(fn) {
        if (document.readyState === 'complete') { requestAnimationFrame(fn); }
        else { window.addEventListener('load', function () { requestAnimationFrame(fn); }); }
    }

    /* ── SVG Usuario ── */
    var svgUsers = `
    <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 320 165" style="display:block">
      <defs>
        <style>
          @keyframes spin-ring { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
          @keyframes spin-ring-rev { from { transform: rotate(0deg); } to { transform: rotate(-360deg); } }
          @keyframes float-fig { 0%,100%{ transform: translateY(0); } 50%{ transform: translateY(-5px); } }
          @keyframes pulse-glow { 0%,100%{ opacity:.55; } 50%{ opacity:1; } }
          @keyframes pulse-dot { 0%,100%{ transform: scale(1); opacity:1; } 50%{ transform: scale(1.5); opacity:.6; } }
          @keyframes dash-flow { to { stroke-dashoffset: -24; } }

          .ring-1 { transform-origin: 160px 95px; animation: spin-ring 9s linear infinite; }
          .ring-2 { transform-origin: 160px 95px; animation: spin-ring-rev 14s linear infinite; }
          .ring-3 { transform-origin: 160px 95px; animation: spin-ring 22s linear infinite; }
          .figure { transform-origin: 160px 95px; animation: float-fig 3.5s ease-in-out infinite; }
          .glow-ring { animation: pulse-glow 2.5s ease-in-out infinite; }
          .orbit-dot { animation: pulse-dot 2s ease-in-out infinite; }
          .data-line { stroke-dasharray: 6 6; animation: dash-flow 1.5s linear infinite; }
        </style>
      </defs>

      <!-- Fondo gradiente sutil -->
      <rect width="320" height="165" fill="${BG}" rx="14"/>
      <circle cx="160" cy="95" r="110" fill="none" stroke="${ORANGE}" stroke-width="0.3" opacity="0.08"/>

      <!-- Anillo externo decorativo (dashed) -->
      <g class="ring-3">
        <circle cx="160" cy="95" r="80" fill="none" stroke="${ORANGE}" stroke-width="0.5" stroke-dasharray="4 8" opacity="0.2"/>
      </g>

      <!-- Anillo orbital exterior -->
      <g class="ring-2">
        <circle cx="160" cy="95" r="68" fill="none" stroke="${ORANGE_L}" stroke-width="0.8" opacity="0.3"/>
        <circle cx="228" cy="95" r="2.5" fill="${ORANGE_L}" class="orbit-dot" style="transform-origin:228px 95px"/>
        <circle cx="92" cy="95" r="1.8" fill="${ORANGE_L}" opacity="0.5"/>
      </g>

      <!-- Anillo orbital interior -->
      <g class="ring-1">
        <circle cx="160" cy="95" r="52" fill="none" stroke="${ORANGE}" stroke-width="1" opacity="0.45"/>
        <circle cx="212" cy="95" r="3.5" fill="${ORANGE}" class="orbit-dot" style="animation-delay:-.8s;transform-origin:212px 95px"/>
        <circle cx="108" cy="95" r="2.2" fill="${ORANGE}" opacity="0.6" class="orbit-dot" style="animation-delay:-.4s;transform-origin:108px 95px"/>
      </g>

      <!-- Glow central bajo la figura -->
      <ellipse cx="160" cy="125" rx="28" ry="6" fill="${ORANGE}" class="glow-ring" opacity="0.25"/>

      <!-- Figura de usuario -->
      <g class="figure">
        <circle cx="160" cy="74" r="18" fill="#d8e0f5"/>
        <path d="M130 122 Q130 100 160 100 Q190 100 190 122" fill="#d8e0f5"/>
        <circle cx="160" cy="74" r="18" fill="none" stroke="${ORANGE}" stroke-width="2" opacity="0.7"/>
        <circle cx="160" cy="108" r="3" fill="${ORANGE}" opacity="0.8"/>
      </g>

      <!-- Líneas de datos ambientales -->
      <line x1="30" y1="50" x2="80" y2="50" stroke="${ORANGE}" stroke-width="0.6" class="data-line" opacity="0.3"/>
      <line x1="240" y1="140" x2="290" y2="140" stroke="${ORANGE}" stroke-width="0.6" class="data-line" opacity="0.3" style="animation-delay:-.7s"/>
      <line x1="20" y1="115" x2="55" y2="115" stroke="${ORANGE_L}" stroke-width="0.5" class="data-line" opacity="0.2" style="animation-delay:-.3s"/>
      <line x1="265" y1="55" x2="300" y2="55" stroke="${ORANGE_L}" stroke-width="0.5" class="data-line" opacity="0.2" style="animation-delay:-1s"/>

      <!-- Partículas estáticas de fondo -->
      <circle cx="45" cy="35" r="1.2" fill="${ORANGE_L}" opacity="0.25"/>
      <circle cx="275" cy="28" r="1" fill="${ORANGE}" opacity="0.2"/>
      <circle cx="290" cy="130" r="1.5" fill="${ORANGE_L}" opacity="0.3"/>
      <circle cx="30" cy="145" r="1" fill="${ORANGE}" opacity="0.2"/>
      <circle cx="300" cy="80" r="1.2" fill="${ORANGE_L}" opacity="0.2"/>
      <circle cx="22" cy="80" r="1" fill="${ORANGE}" opacity="0.2"/>
    </svg>`;

    /* ── SVG Clientes ── */
    var svgClients = `
    <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 320 165" style="display:block">
      <defs>
        <style>
          @keyframes bar-grow-1 { 0%,100%{ transform:scaleY(1);    } 50%{ transform:scaleY(1.15); } }
          @keyframes bar-grow-2 { 0%,100%{ transform:scaleY(1);    } 50%{ transform:scaleY(1.22); } }
          @keyframes bar-grow-3 { 0%,100%{ transform:scaleY(1);    } 50%{ transform:scaleY(1.1);  } }
          @keyframes bar-grow-4 { 0%,100%{ transform:scaleY(1);    } 50%{ transform:scaleY(1.28); } }
          @keyframes float-fig  { 0%,100%{ transform:translateY(0);} 50%{ transform:translateY(-5px); } }
          @keyframes glow-pulse { 0%,100%{ opacity:.2;  } 50%{ opacity:.5;  } }
          @keyframes dot-blink  { 0%,100%{ opacity:1;   } 50%{ opacity:.2;  } }
          @keyframes dot-blink2 { 0%,100%{ opacity:.7;  } 50%{ opacity:.15; } }
          @keyframes ping       { 0%{ r:4; opacity:.8; } 100%{ r:12; opacity:0; } }
          @keyframes trend-draw { from{ stroke-dashoffset:90; } to{ stroke-dashoffset:0; } }
          @keyframes map-scan   { 0%,100%{ opacity:.08; } 50%{ opacity:.18; } }

          .bar1{ transform-origin:62px  130px; animation:bar-grow-1 3.2s ease-in-out infinite;      }
          .bar2{ transform-origin:78px  130px; animation:bar-grow-2 3.2s ease-in-out infinite .5s;  }
          .bar3{ transform-origin:94px  130px; animation:bar-grow-3 3.2s ease-in-out infinite .9s;  }
          .bar4{ transform-origin:110px 130px; animation:bar-grow-4 3.2s ease-in-out infinite 1.3s; }
          .fig { transform-origin:220px 78px;  animation:float-fig  4s   ease-in-out infinite;      }
          .glow{ animation:glow-pulse 2.8s ease-in-out infinite;                                     }
          .bd  { animation:dot-blink  1.6s ease-in-out infinite;                                     }
          .bd2 { animation:dot-blink2 2.1s ease-in-out infinite .5s;                                }
          .bd3 { animation:dot-blink  1.9s ease-in-out infinite 1s;                                 }
          .ping{ animation:ping 2s ease-out infinite;                                                }
          .ping2{ animation:ping 2s ease-out infinite 1s;                                           }
          .trend{ stroke-dasharray:90; animation:trend-draw 1.8s ease-out forwards;                 }
          .mapscan{ animation:map-scan 4s ease-in-out infinite;                                      }
        </style>
      </defs>

      <rect width="320" height="165" fill="#0a0a12" rx="14"/>

      <!-- Mini mapa -->
      <rect x="148" y="22" width="152" height="122" rx="8" fill="#0d1428" stroke="#1e2a50" stroke-width="1"/>
      <line x1="148" y1="52"  x2="300" y2="52"  stroke="#1e2a50" stroke-width=".5"/>
      <line x1="148" y1="82"  x2="300" y2="82"  stroke="#1e2a50" stroke-width=".5"/>
      <line x1="148" y1="112" x2="300" y2="112" stroke="#1e2a50" stroke-width=".5"/>
      <line x1="186" y1="22"  x2="186" y2="144" stroke="#1e2a50" stroke-width=".5"/>
      <line x1="224" y1="22"  x2="224" y2="144" stroke="#1e2a50" stroke-width=".5"/>
      <line x1="262" y1="22"  x2="262" y2="144" stroke="#1e2a50" stroke-width=".5"/>

      <ellipse cx="180" cy="67" rx="18" ry="11" fill="#1a2a44" class="mapscan"/>
      <ellipse cx="215" cy="60" rx="12" ry="8"  fill="#1a2a44" class="mapscan" style="animation-delay:-.8s"/>
      <ellipse cx="248" cy="70" rx="20" ry="10" fill="#1a2a44" class="mapscan" style="animation-delay:-.4s"/>
      <ellipse cx="275" cy="95" rx="14" ry="9"  fill="#1a2a44" class="mapscan" style="animation-delay:-1.2s"/>
      <ellipse cx="195" cy="100" rx="10" ry="7" fill="#1a2a44" class="mapscan" style="animation-delay:-.6s"/>
      <ellipse cx="230" cy="110" rx="16" ry="8" fill="#1a2a44" class="mapscan" style="animation-delay:-1s"/>

      <circle class="ping"  cx="244" cy="64" r="4" fill="none" stroke="#E85C0D" stroke-width="1"/>
      <circle class="bd"    cx="244" cy="64" r="4" fill="#E85C0D"/>
      <circle class="ping2" cx="179" cy="60" r="3" fill="none" stroke="#4466cc" stroke-width="1"/>
      <circle class="bd2"   cx="179" cy="60" r="3" fill="#4466cc"/>
      <circle class="bd3"   cx="271" cy="92" r="3" fill="#E85C0D" opacity=".8"/>
      <circle class="bd2"   cx="198" cy="97" r="2.5" fill="#4466cc" opacity=".7"/>
      <circle               cx="228" cy="108" r="2" fill="#ff8c42" opacity=".6"/>

      <text x="224" y="138" text-anchor="middle" font-family="'Nunito',sans-serif" font-size="7.5" font-weight="700" fill="#2a3a60" letter-spacing="1.5">DISTRIBUCIÓN</text>

      <!-- Panel gráfico -->
      <rect x="20" y="22" width="118" height="122" rx="8" fill="#0d1428" stroke="#1e2a50" stroke-width="1"/>
      <line x1="30" y1="130" x2="128" y2="130" stroke="#2a3a60" stroke-width=".8"/>
      <line x1="30" y1="50"  x2="30"  y2="130" stroke="#2a3a60" stroke-width=".8"/>
      <line x1="30" y1="100" x2="128" y2="100" stroke="#1e2a50" stroke-width=".5" stroke-dasharray="3 4"/>
      <line x1="30" y1="75"  x2="128" y2="75"  stroke="#1e2a50" stroke-width=".5" stroke-dasharray="3 4"/>

      <g class="bar1"><rect x="38"  y="104" width="14" height="26" rx="2" fill="#2244aa" opacity=".8"/></g>
      <g class="bar2"><rect x="57"  y="90"  width="14" height="40" rx="2" fill="#3355cc" opacity=".9"/></g>
      <g class="bar3"><rect x="76"  y="97"  width="14" height="33" rx="2" fill="#E85C0D" opacity=".9"/></g>
      <g class="bar4"><rect x="95"  y="78"  width="14" height="52" rx="2" fill="#E85C0D"/></g>

      <polyline class="trend" points="45,102 64,88 83,95 102,76" fill="none" stroke="#ff8c42" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="102" cy="76" r="3.2" fill="#ff8c42" class="bd"/>

      <text x="79" y="145" text-anchor="middle" font-family="'Nunito',sans-serif" font-size="7.5" font-weight="700" fill="#2a3a60" letter-spacing="1.5">INGRESOS</text>

      <!-- Figura cliente -->
      <g class="fig">
        <ellipse cx="139" cy="130" rx="20" ry="5" fill="#E85C0D" opacity=".18" class="glow"/>
        <circle cx="139" cy="72" r="17" fill="#d8e0f5"/>
        <circle cx="139" cy="72" r="17" fill="none" stroke="#E85C0D" stroke-width="1.8" opacity=".8"/>
        <path d="M115 128 Q115 100 139 100 Q163 100 163 128" fill="#d8e0f5"/>
        <path d="M115 128 Q115 100 139 100 Q163 100 163 128" fill="none" stroke="#E85C0D" stroke-width="1.4" opacity=".65"/>
        <circle cx="139" cy="110" r="2.8" fill="#E85C0D"/>
      </g>
    </svg>`;

    /* ── SVG Cobranzas (monedas + billete + gráfico) ── */
    var svgCobranzas = `
    <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 320 165" style="display:block">
      <defs>
        <style>
          @keyframes float-coin { 0%,100%{ transform: translateY(0); } 50%{ transform: translateY(-6px); } }
          @keyframes pulse-bill { 0%,100%{ opacity:0.7; } 50%{ opacity:1; } }
          @keyframes spin-coin  { 0%{ transform: rotate(0deg); } 100%{ transform: rotate(360deg); } }
          @keyframes grow-bar   { 0%{ transform: scaleY(0.2); } 100%{ transform: scaleY(1); } }
          @keyframes dash-draw  { to{ stroke-dashoffset: 0; } }
          @keyframes shine      { 0%{ opacity:0; } 50%{ opacity:0.6; } 100%{ opacity:0; } }
          .coin1 { animation: float-coin 2.4s ease-in-out infinite; transform-origin: 90px 85px; }
          .coin2 { animation: float-coin 2.8s ease-in-out infinite 0.4s; transform-origin: 140px 100px; }
          .coin3 { animation: float-coin 2.2s ease-in-out infinite 0.8s; transform-origin: 190px 80px; }
          .bill  { animation: pulse-bill 2.6s ease-in-out infinite; }
          .spinner { transform-origin: 260px 95px; animation: spin-coin 12s linear infinite; }
          .bar1 { transform-origin: 38px 130px; animation: grow-bar 0.8s ease-out forwards; }
          .bar2 { transform-origin: 58px 130px; animation: grow-bar 0.8s ease-out 0.2s forwards; }
          .bar3 { transform-origin: 78px 130px; animation: grow-bar 0.8s ease-out 0.4s forwards; }
          .bar4 { transform-origin: 98px 130px; animation: grow-bar 0.8s ease-out 0.6s forwards; }
          .trend { stroke-dasharray: 90; animation: dash-draw 1.5s ease-out forwards; }
          .shine { animation: shine 2.2s ease-in-out infinite; }
        </style>
      </defs>

      <rect width="320" height="165" fill="${BG}" rx="14"/>
      <circle cx="160" cy="95" r="120" fill="none" stroke="${ORANGE}" stroke-width="0.3" opacity="0.08"/>

      <!-- Monedas flotantes -->
      <g class="coin1">
        <circle cx="90" cy="85" r="16" fill="#2a2a2a" stroke="${ORANGE}" stroke-width="1.2" opacity="0.9"/>
        <circle cx="90" cy="85" r="11" fill="none" stroke="${ORANGE_L}" stroke-width="0.8" opacity="0.6"/>
        <text x="90" y="89" text-anchor="middle" font-family="'Rajdhani',sans-serif" font-size="11" font-weight="700" fill="${ORANGE}">$</text>
      </g>
      <g class="coin2">
        <circle cx="140" cy="100" r="12" fill="#2a2a2a" stroke="${ORANGE}" stroke-width="1" opacity="0.8"/>
        <circle cx="140" cy="100" r="8" fill="none" stroke="${ORANGE_L}" stroke-width="0.6"/>
        <text x="140" y="103" text-anchor="middle" font-family="'Rajdhani',sans-serif" font-size="9" font-weight="700" fill="${ORANGE}">$</text>
      </g>
      <g class="coin3">
        <circle cx="190" cy="80" r="10" fill="#2a2a2a" stroke="${ORANGE}" stroke-width="0.8" opacity="0.7"/>
        <text x="190" y="83" text-anchor="middle" font-family="'Rajdhani',sans-serif" font-size="8" font-weight="700" fill="${ORANGE_L}">$</text>
      </g>

      <!-- Billete -->
      <g class="bill">
        <rect x="248" y="52" width="52" height="32" rx="4" fill="#2a2a2a" stroke="${ORANGE}" stroke-width="1"/>
        <rect x="254" y="58" width="40" height="20" rx="2" fill="none" stroke="${ORANGE_L}" stroke-width="0.6"/>
        <text x="274" y="72" text-anchor="middle" font-family="'Rajdhani',sans-serif" font-size="14" font-weight="700" fill="${ORANGE}">$</text>
        <line x1="254" y1="62" x2="294" y2="62" stroke="${ORANGE_L}" stroke-width="0.4" opacity="0.4"/>
        <line x1="254" y1="74" x2="294" y2="74" stroke="${ORANGE_L}" stroke-width="0.4" opacity="0.4"/>
      </g>

      <!-- Anillo orbitante -->
      <g class="spinner">
        <circle cx="260" cy="95" r="38" fill="none" stroke="${ORANGE}" stroke-width="0.6" stroke-dasharray="4 6" opacity="0.3"/>
        <circle cx="298" cy="95" r="4" fill="${ORANGE}" opacity="0.8"/>
      </g>

      <!-- Gráfico de barras -->
      <rect x="22" y="22" width="110" height="122" rx="6" fill="#0d1428" stroke="#1e2a50" stroke-width="0.8"/>
      <line x1="30" y1="130" x2="125" y2="130" stroke="#2a3a60" stroke-width="0.6"/>
      <line x1="30" y1="50"  x2="30"  y2="130" stroke="#2a3a60" stroke-width="0.6"/>

      <g class="bar1"><rect x="32" y="90" width="12" height="40" rx="2" fill="${ORANGE}" opacity="0.8"/></g>
      <g class="bar2"><rect x="48" y="75" width="12" height="55" rx="2" fill="${ORANGE}" opacity="0.9"/></g>
      <g class="bar3"><rect x="64" y="82" width="12" height="48" rx="2" fill="${ORANGE_L}" opacity="0.9"/></g>
      <g class="bar4"><rect x="80" y="60" width="12" height="70" rx="2" fill="${ORANGE}"/></g>

      <polyline class="trend" points="38,108 54,93 70,100 86,78" fill="none" stroke="${ORANGE_L}" stroke-width="1.6" stroke-linecap="round"/>
      <circle cx="86" cy="78" r="3" fill="${ORANGE_L}" class="shine"/>

      <text x="77" y="148" text-anchor="middle" font-family="'Nunito',sans-serif" font-size="7.5" font-weight="700" fill="#2a3a60" letter-spacing="1.5">COBRANZAS</text>

      <!-- Partículas decorativas -->
      <circle cx="30" cy="35" r="1.2" fill="${ORANGE_L}" opacity="0.3"/>
      <circle cx="280" cy="28" r="1" fill="${ORANGE}" opacity="0.25"/>
      <circle cx="310" cy="140" r="1.5" fill="${ORANGE_L}" opacity="0.3"/>
      <circle cx="18" cy="145" r="1" fill="${ORANGE}" opacity="0.2"/>
    </svg>`;

    ready(function () {
        var usersEl = document.getElementById('canvas-users');
        if (usersEl) { usersEl.innerHTML = svgUsers; }
        var clientsEl = document.getElementById('canvas-clients');
        if (clientsEl) { clientsEl.innerHTML = svgClients; }
        var cobranzasEl = document.getElementById('canvas-cobranzas');
        if (cobranzasEl) { cobranzasEl.innerHTML = svgCobranzas; }
    });

}());