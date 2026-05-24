/* ═══════════════════════════════════════════════
   SAJF Strategies — Bob Chat Widget
   ═══════════════════════════════════════════════ */

var bobHistory = [];
var bobWaiting = false;

function bobToggle() {
    document.getElementById('bob-bubble').classList.toggle('open');
    if (document.getElementById('bob-bubble').classList.contains('open')) {
        setTimeout(function() { document.getElementById('bob-input').focus(); }, 210);
    }
}

function bobKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); bobSend(); }
}

function bobAutoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 90) + 'px';
}

function bobSend() {
    if (bobWaiting) return;
    var input = document.getElementById('bob-input');
    var msg = input.value.trim();
    if (!msg) return;

    bobAddMessage('user', msg);
    bobHistory.push({ role: 'user', content: msg });
    input.value = '';
    input.style.height = 'auto';
    bobSetWaiting(true);

    fetch('/api/bob/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, history: bobHistory.slice(-10) })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var reply = data.reply || 'Entschuldigung, ich konnte keine Antwort generieren.';
        bobAddMessage('bot', reply);
        bobHistory.push({ role: 'assistant', content: reply });
    })
    .catch(function() {
        bobAddMessage('bot', 'Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.');
    })
    .finally(function() { bobSetWaiting(false); });
}

function bobAddMessage(role, text) {
    var el = document.createElement('div');
    el.className = 'bob-msg ' + role;
    el.textContent = text;
    var container = document.getElementById('bob-messages');
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

function bobSetWaiting(on) {
    bobWaiting = on;
    document.getElementById('bob-typing').style.display = on ? 'block' : 'none';
    document.getElementById('bob-send').disabled = on;
    var container = document.getElementById('bob-messages');
    container.scrollTop = container.scrollHeight;
}
