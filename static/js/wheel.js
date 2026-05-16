const WHEEL_START_OFFSET = -Math.PI / 2;
const POINTER_ANGLE = Math.PI / 2;

function normalizeAngle(value) {
    const twoPi = 2 * Math.PI;
    return ((value % twoPi) + twoPi) % twoPi;
}

async function fetchWheelSegments() {
    const response = await fetch('/api/wheel/segmentos', { credentials: 'same-origin' });
    const data = await response.json();
    return data.segmentos || [];
}

async function generateWheelToken() {
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    const csrfToken = csrfInput ? csrfInput.value : '';
    const response = await fetch('/api/wheel/generar-token', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({})
    });
    if (!response.ok) return null;
    const data = await response.json();
    return data.token;
}

function buildSegmentRanges(segments) {
    let start = 0;
    const ranges = [];
    for (const seg of segments) {
        const angle = seg.angulo || ((2 * Math.PI) / Math.max(segments.length, 1));
        ranges.push({ start, end: start + angle });
        start += angle;
    }
    return ranges;
}

function drawWheel(ctx, cx, cy, radius, segments, segmentRanges, rotation, highlightIndex) {
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    const n = segments.length;
    if (n === 0) return;

    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 4, 0, 2 * Math.PI);
    ctx.shadowColor = 'rgba(0,0,0,0.3)';
    ctx.shadowBlur = 12;
    ctx.fillStyle = '#8B4513';
    ctx.fill();
    ctx.restore();

    for (let i = 0; i < n; i++) {
        const range = segmentRanges[i] || { start: i * ((2 * Math.PI) / n), end: (i + 1) * ((2 * Math.PI) / n) };
        const sa = WHEEL_START_OFFSET + rotation + range.start;
        const ea = WHEEL_START_OFFSET + rotation + range.end;

        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, sa, ea); ctx.closePath();

        if (segments[i].disponible === false) {
            ctx.fillStyle = '#d0d0d0';
        } else {
            ctx.fillStyle = segments[i].color;
        }
        ctx.fill();
        ctx.strokeStyle = '#FFF8F0'; ctx.lineWidth = 2; ctx.stroke();

        if (highlightIndex === i) {
            ctx.save();
            ctx.strokeStyle = '#111';
            ctx.lineWidth = 4;
            ctx.shadowColor = 'rgba(0,0,0,0.25)';
            ctx.shadowBlur = 6;
            ctx.beginPath(); ctx.moveTo(cx, cy);
            ctx.arc(cx, cy, radius, sa, ea); ctx.closePath();
            ctx.stroke();
            ctx.restore();
        }

        ctx.save(); ctx.translate(cx, cy); ctx.rotate(sa + (ea - sa) / 2);
        ctx.textAlign = 'right'; ctx.fillStyle = '#fff';
        ctx.font = 'bold 11px Poppins, sans-serif';
        ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 3;
        const text = segments[i].texto, maxW = radius - 25;
        if (ctx.measureText(text).width > maxW) {
            const words = text.split(' '); let l1 = '', l2 = '';
            for (const w of words) {
                if (ctx.measureText(l1 + ' ' + w).width < maxW) l1 += (l1 ? ' ' : '') + w;
                else l2 += (l2 ? ' ' : '') + w;
            }
            ctx.fillText(l1, radius - 15, -4);
            ctx.fillText(l2, radius - 15, 10);
        } else {
            ctx.fillText(text, radius - 15, 4);
        }
        ctx.restore();
    }

    ctx.beginPath(); ctx.arc(cx, cy, 22, 0, 2 * Math.PI);
    ctx.fillStyle = '#C4756E'; ctx.fill();
    ctx.strokeStyle = '#FFF8F0'; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = '#fff'; ctx.font = 'bold 18px Poppins, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('🧁', cx, cy);

    const pointerLen = radius + 4;
    const pointerBase = radius - 12;
    const tip = {
        x: cx + Math.cos(POINTER_ANGLE) * pointerLen,
        y: cy + Math.sin(POINTER_ANGLE) * pointerLen
    };
    const left = {
        x: cx + Math.cos(POINTER_ANGLE - 0.12) * pointerBase,
        y: cy + Math.sin(POINTER_ANGLE - 0.12) * pointerBase
    };
    const right = {
        x: cx + Math.cos(POINTER_ANGLE + 0.12) * pointerBase,
        y: cy + Math.sin(POINTER_ANGLE + 0.12) * pointerBase
    };
    ctx.save();
    ctx.fillStyle = '#111';
    ctx.beginPath();
    ctx.moveTo(tip.x, tip.y);
    ctx.lineTo(left.x, left.y);
    ctx.lineTo(right.x, right.y);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
}

function getPrizeMessage(data) {
    if (data.tipo === 'descuento_porcentaje')
        return `🎉 ¡Ganaste un cupón de ${parseFloat(data.valor).toFixed(0)}% de descuento!`;
    if (data.tipo === 'descuento_fijo')
        return `🎉 ¡Ganaste un cupón de $${parseFloat(data.valor).toFixed(2)} de descuento!`;
    if (data.tipo === 'producto_gratis')
        return '🎉 ¡Ganaste un producto gratis!';
    if (data.tipo === 'sin_premio')
        return '😅 No ganaste premio esta vez.';
    return data.texto || '¡Ganaste!';
}
