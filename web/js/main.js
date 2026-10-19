// Web shell: Ruffle (Flash emulator) + 7:5 fit + fullscreen + touch pad that sends real key events.
(() => {
  'use strict';
  const SWF = 'game.swf';
  const ASPECT = 350 / 250;
  const $ = (id) => document.getElementById(id);
  const game = $('game'), pad = $('pad'), start = $('start'), playBtn = $('play'), loading = $('loading');
  const APP = /SonicHeApp/.test(navigator.userAgent);   // inside the Android app (already full screen, landscape)
  const touch = APP || (matchMedia('(pointer: coarse)').matches && navigator.maxTouchPoints > 0);
  let player = null;

  function fit() {
    const w = innerWidth, h = innerHeight;
    const gw = Math.min(w, h * ASPECT);
    game.style.width = Math.floor(gw) + 'px';
    game.style.height = Math.floor(gw / ASPECT) + 'px';
    document.body.classList.toggle('portrait', h > w);
    $('rotate').hidden = APP || !(touch && h > w && !sessionStorage.rotateOk);
  }
  addEventListener('resize', fit);
  fit();

  // ---------- Ruffle ----------
  window.RufflePlayer = window.RufflePlayer || {};
  window.RufflePlayer.config = {
    publicPath: 'ruffle/', autoplay: 'on', unmuteOverlay: 'hidden', splashScreen: false,
    letterbox: 'on', quality: 'high', contextMenu: 'off', preloader: true,
    backgroundColor: '#000000', allowFullscreen: true, openUrlMode: 'deny',
    // Ruffle's own WebGL renderer: the wgpu one panics on GPUs with 256 vertex uniform vectors (many phones)
    preferredRenderer: 'webgl',
  };
  const ruffle = window.RufflePlayer.newest();
  playBtn.disabled = false;
  loading.textContent = '';

  async function boot() {
    start.hidden = true;
    if (touch) goFull();
    player = ruffle.createPlayer();
    game.appendChild(player);
    try { await player.ruffle().load({ url: SWF }); }
    catch (e) { start.hidden = false; loading.textContent = 'שגיאה בטעינת המשחק: ' + e.message; return; }
    player.focus();
  }
  playBtn.addEventListener('click', boot);
  $('rotate-ok').addEventListener('click', () => { sessionStorage.rotateOk = 1; fit(); });

  // ---------- fullscreen ----------
  function goFull() {
    const el = document.documentElement;
    if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen({ navigationUI: 'hide' }).catch(() => {});
  }
  $('btn-full').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen(); else goFull();
    player && player.focus();
  });
  document.addEventListener('fullscreenchange', () => document.body.classList.toggle('playing-fs', !!document.fullscreenElement));

  // ---------- touch pad ----------
  const KEYS = {
    left: ['ArrowLeft', 'ArrowLeft', 37], right: ['ArrowRight', 'ArrowRight', 39],
    down: ['ArrowDown', 'ArrowDown', 40], space: [' ', 'Space', 32], enter: ['Enter', 'Enter', 13],
  };
  function send(type, name) {
    const [key, code, keyCode] = KEYS[name];
    const ev = new KeyboardEvent(type, { key, code, keyCode, which: keyCode, bubbles: true, cancelable: true, composed: true });
    if (!player) return;
    // Ruffle only reads keys while the player has focus (a tapped HTML button takes it away)
    if (document.activeElement !== player) player.focus({ preventScroll: true });
    player.dispatchEvent(ev);
  }
  function showPad(on) { pad.hidden = !on; localStorage.pad = on ? 1 : 0; }
  showPad(localStorage.pad ? localStorage.pad === '1' : touch);
  $('btn-pad').addEventListener('click', () => { showPad(pad.hidden); player && player.focus(); });

  for (const b of pad.querySelectorAll('.key')) {
    const name = b.dataset.key;
    const ids = new Set();
    const down = (e) => {
      e.preventDefault();
      b.setPointerCapture(e.pointerId);
      if (!ids.size) { b.classList.add('on'); send('keydown', name); }
      ids.add(e.pointerId);
      if (navigator.vibrate) navigator.vibrate(8);
    };
    const up = (e) => {
      if (!ids.delete(e.pointerId) || ids.size) return;
      b.classList.remove('on'); send('keyup', name);
    };
    b.addEventListener('pointerdown', down);
    b.addEventListener('pointerup', up);
    b.addEventListener('pointercancel', up);
    b.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  if (APP) {
    $('btn-full').hidden = true;
    // Android back: pause in the game, leave the app from the start screen
    window.__appBack = () => {
      if (!start.hidden || !player) { window.App && App.exit(); return; }
      send('keydown', 'enter'); setTimeout(() => send('keyup', 'enter'), 120);
    };
  } else if ('serviceWorker' in navigator && !/^(localhost|127\.|192\.168\.)/.test(location.hostname)) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
})();
