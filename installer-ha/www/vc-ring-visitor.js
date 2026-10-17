/**
 * Suoneria chiamata videocitofono + annuncio TTS visitatore riconosciuto.
 * API globale: window.vcRingVisitor.start() | announce(nome) | stop()
 */
(function () {
  'use strict';

  var MAX_RING_MS = 30000;
  var PAUSE_MS = 1200;
  var RING_URL = '/local/minion.mp3';

  var audio = null;
  var loopTimer = null;
  var maxTimer = null;
  var active = false;
  var pausedForAnnounce = false;

  function clearTimers() {
    if (loopTimer) {
      clearTimeout(loopTimer);
      loopTimer = null;
    }
    if (maxTimer) {
      clearTimeout(maxTimer);
      maxTimer = null;
    }
  }

  function stopAudio() {
    if (!audio) return;
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (_) {}
    audio = null;
  }

  function stopLegacyRing() {
    try {
      if (window._vcRing) {
        window._vcRing.pause();
        window._vcRing.currentTime = 0;
        window._vcRing = null;
      }
      if (window._vcRingTimer) {
        clearTimeout(window._vcRingTimer);
        window._vcRingTimer = null;
      }
    } catch (_) {}
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      loopTimer = setTimeout(resolve, ms);
    });
  }

  var audioCtx = null;

  function playBeep() {
    return new Promise(function (resolve) {
      try {
        var Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) {
          resolve();
          return;
        }
        if (!audioCtx) audioCtx = new Ctx();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        var t = audioCtx.currentTime;
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.45);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(t);
        osc.stop(t + 0.5);
        osc.onended = function () {
          resolve();
        };
      } catch (_) {
        resolve();
      }
    });
  }

  function playOnce() {
    return new Promise(function (resolve) {
      stopAudio();
      audio = new Audio(RING_URL);
      audio.volume = 1.0;
      audio.loop = false;
      audio.onended = function () {
        resolve();
      };
      audio.onerror = function () {
        playBeep().then(resolve);
      };
      audio.play().catch(function () {
        playBeep().then(resolve);
      });
    });
  }

  async function ringLoop() {
    while (active && !pausedForAnnounce) {
      await playOnce();
      if (!active || pausedForAnnounce) break;
      await wait(PAUSE_MS);
    }
  }

  window.vcRingVisitor = {
    start: function () {
      this.stop();
      active = true;
      pausedForAnnounce = false;
      maxTimer = setTimeout(function () {
        window.vcRingVisitor.stop();
      }, MAX_RING_MS);
      ringLoop();
    },

    stop: function () {
      active = false;
      pausedForAnnounce = false;
      clearTimers();
      stopAudio();
      stopLegacyRing();
    },

    announce: function (nome) {
      pausedForAnnounce = true;
      stopAudio();
      var text = 'Visitatore identificato: ' + (nome || 'sconosciuto');
      var synth = window.speechSynthesis;
      if (!synth) {
        pausedForAnnounce = false;
        if (active) ringLoop();
        return;
      }
      var utter = new SpeechSynthesisUtterance(text);
      utter.lang = 'it-IT';
      utter.onend = function () {
        pausedForAnnounce = false;
        if (active) ringLoop();
      };
      utter.onerror = function () {
        pausedForAnnounce = false;
        if (active) ringLoop();
      };
      synth.cancel();
      synth.speak(utter);
    },
  };
})();
