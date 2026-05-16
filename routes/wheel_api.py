import math
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import PrizeWheel, PrizeWheelSegment, PrizeWheelToken, PrizeSpin, Coupon, UserCoupon, Order

wheel_api_bp = Blueprint('wheel_api', __name__)


def build_wheel_segment_text(tipo, valor, texto=''):
    """Build the display text for a wheel segment based on its type"""
    value = float(valor or 0)
    if tipo == 'descuento_porcentaje':
        return f'{value:.0f}% descuento'
    if tipo == 'descuento_fijo':
        return f'${value:.0f} descuento'
    if tipo == 'producto_gratis':
        return texto or 'Producto gratis'
    if tipo == 'sin_premio':
        return 'Seguí participando'
    return texto or 'Premio'


def get_or_create_wheel():
    wheel = PrizeWheel.query.first()
    if not wheel:
        wheel = PrizeWheel(nombre='Rueda de Premios', monto_minimo_activacion=10000)
        db.session.add(wheel)
        db.session.commit()
    return wheel


@wheel_api_bp.route('/status', methods=['GET'])
@login_required
def get_wheel_status():
    wheel = PrizeWheel.query.filter_by(activa=True).first()
    if not wheel:
        return jsonify({'disponible': False, 'mensaje': 'Rueda inactiva'})

    total_spent = float(current_user.total_spent or 0)
    min_amount = float(wheel.monto_minimo_activacion)

    expected_spins = int(total_spent / min_amount) if min_amount > 0 else 0

    actual_spins = PrizeSpin.query.filter(
        PrizeSpin.user_id == current_user.id,
        PrizeSpin.wheel_id == wheel.id,
        PrizeSpin.segment_id.isnot(None)
    ).count()

    giros_disponibles = max(0, expected_spins - actual_spins)

    active_token = PrizeWheelToken.query.filter(
        PrizeWheelToken.user_id == current_user.id,
        PrizeWheelToken.usado == False,
        PrizeWheelToken.expires_at > datetime.utcnow()
    ).first()

    token_info = None
    if active_token:
        token_info = {
            'token': active_token.token,
            'expires_at': active_token.expires_at.isoformat()
        }

    return jsonify({
        'disponible': giros_disponibles > 0,
        'giros_disponibles': giros_disponibles,
        'total_gastado': total_spent,
        'monto_necesario': min_amount,
        'proximo_giro_en': max(0, min_amount - (total_spent % min_amount)) if min_amount > 0 else 0,
        'token': token_info,
        'wheel_activa': wheel.activa
    })


@wheel_api_bp.route('/generar-token', methods=['POST'])
@login_required
def generate_spin_token():
    wheel = PrizeWheel.query.filter_by(activa=True).first()
    if not wheel:
        return jsonify({'error': 'Rueda inactiva'}), 400

    total_spent = float(current_user.total_spent or 0)
    min_amount = float(wheel.monto_minimo_activacion)

    expected_spins = int(total_spent / min_amount) if min_amount > 0 else 0

    actual_spins = PrizeSpin.query.filter(
        PrizeSpin.user_id == current_user.id,
        PrizeSpin.wheel_id == wheel.id,
        PrizeSpin.segment_id.isnot(None)
    ).count()

    if expected_spins <= actual_spins:
        return jsonify({'error': 'No tienes giros disponibles'}), 400

    existing_token = PrizeWheelToken.query.filter(
        PrizeWheelToken.user_id == current_user.id,
        PrizeWheelToken.usado == False,
        PrizeWheelToken.expires_at > datetime.utcnow()
    ).first()

    if existing_token:
        return jsonify({
            'token': existing_token.token,
            'expires_at': existing_token.expires_at.isoformat()
        })

    order_id = request.json.get('order_id') if request.is_json else None

    token = secrets.token_hex(32)
    expires = datetime.utcnow() + timedelta(minutes=wheel.token_expiracion_minutos or 30)

    wheel_token = PrizeWheelToken(
        token=token,
        user_id=current_user.id,
        wheel_id=wheel.id,
        order_id=order_id,
        expires_at=expires,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:255]
    )
    db.session.add(wheel_token)
    db.session.commit()

    return jsonify({
        'token': token,
        'expires_at': expires.isoformat()
    })


@wheel_api_bp.route('/spin', methods=['POST'])
@login_required
def spin_wheel():
    data = request.get_json() or {}
    token = data.get('token')

    if not token:
        return jsonify({'error': 'Token requerido'}), 400

    wheel_token = PrizeWheelToken.query.filter_by(
        token=token,
        user_id=current_user.id,
        usado=False
    ).first()

    if not wheel_token:
        return jsonify({'error': 'Token inválido o expirado'}), 400

    if not wheel_token.es_valido:
        return jsonify({'error': 'Token expirado'}), 400

    wheel = wheel_token.wheel
    if not wheel or not wheel.activa:
        return jsonify({'error': 'Rueda inactiva'}), 400

    total_spent = float(current_user.total_spent or 0)
    min_amount = float(wheel.monto_minimo_activacion)

    expected_spins = int(total_spent / min_amount) if min_amount > 0 else 0

    actual_spins = PrizeSpin.query.filter(
        PrizeSpin.user_id == current_user.id,
        PrizeSpin.wheel_id == wheel.id,
        PrizeSpin.segment_id.isnot(None)
    ).count()

    if expected_spins <= actual_spins:
        wheel_token.usado = True
        db.session.commit()
        return jsonify({'error': 'No tienes giros disponibles'}), 400

    segs = PrizeWheelSegment.query.filter_by(wheel_id=wheel.id).order_by(PrizeWheelSegment.orden, PrizeWheelSegment.id).all()

    if not segs:
        return jsonify({'error': 'No hay segmentos configurados'}), 400

    available_segs = [s for s in segs if s.esta_disponible]
    if not available_segs:
        available_segs = segs

    weighted = []
    for seg in available_segs:
        weighted.extend([seg] * seg.probabilidad)

    import random
    selected = random.choice(weighted)

    coupon_id = None
    if selected.tipo in ('descuento_porcentaje', 'descuento_fijo'):
        tipo = 'porcentaje' if selected.tipo == 'descuento_porcentaje' else 'monto_fijo'
        coupon = Coupon(
            codigo=f'PREMIO-{secrets.token_hex(3).upper()}',
            descripcion=f'Premio de la rueda: {selected.texto}',
            tipo=tipo,
            valor=selected.valor,
            max_usos=1,
            activo=True,
            fecha_fin=datetime.utcnow() + timedelta(days=7)
        )
        db.session.add(coupon)
        db.session.flush()
        coupon_id = coupon.id
        uc = UserCoupon(user_id=current_user.id, coupon_id=coupon.id, disponible=True)
        db.session.add(uc)

    spin = PrizeSpin(
        user_id=current_user.id,
        wheel_id=wheel.id,
        segment_id=selected.id,
        token_id=wheel_token.id,
        monto_acumulado=total_spent,
        coupon_generado_id=coupon_id
    )
    db.session.add(spin)

    wheel_token.usado = True

    if selected.cantidad_disponible is not None:
        selected.cantidad_disponible -= 1

    db.session.commit()

    prize_text = build_wheel_segment_text(selected.tipo, selected.valor, selected.texto)

    result = {
        'texto': prize_text,
        'tipo': selected.tipo,
        'segment_id': selected.id,
        'segmento_texto': selected.texto,
        'segmento_color': selected.color,
        'valor': float(selected.valor),
        'spin_id': spin.id
    }

    if spin.coupon_generado:
        result['cupon'] = spin.coupon_generado.codigo
        result['tiene_cupon'] = True
        if spin.coupon_generado.fecha_fin:
            result['vencimiento'] = spin.coupon_generado.fecha_fin.strftime('%d/%m/%Y')

    return jsonify(result)


@wheel_api_bp.route('/result/<int:spin_id>', methods=['GET'])
@login_required
def get_spin_result(spin_id):
    spin = PrizeSpin.query.filter_by(id=spin_id, user_id=current_user.id).first()
    if not spin:
        return jsonify({'error': 'Giro no encontrado'}), 404

    return jsonify({
        'id': spin.id,
        'segment_id': spin.segment_id,
        'texto': spin.segment.texto if spin.segment else None,
        'tipo': spin.segment.tipo if spin.segment else None,
        'valor': float(spin.segment.valor) if spin.segment else 0,
        'coupon': spin.coupon_generado.codigo if spin.coupon_generado else None,
        'premio_aplicado': spin.premio_aplicado,
        'created_at': spin.created_at.isoformat()
    })


@wheel_api_bp.route('/historial', methods=['GET'])
@login_required
def get_spin_history():
    spins = PrizeSpin.query.filter_by(user_id=current_user.id).order_by(
        PrizeSpin.created_at.desc()
    ).limit(20).all()

    return jsonify([{
        'id': s.id,
        'segmento': s.segment.texto if s.segment else None,
        'tipo': s.segment.tipo if s.segment else None,
        'coupon': s.coupon_generado.codigo if s.coupon_generado else None,
        'premio_aplicado': s.premio_aplicado,
        'created_at': s.created_at.isoformat()
    } for s in spins])


@wheel_api_bp.route('/segmentos', methods=['GET'])
def get_segments():
    wheel = PrizeWheel.query.filter_by(activa=True).first()
    if not wheel:
        return jsonify({'segmentos': []})

    segs = PrizeWheelSegment.query.filter_by(wheel_id=wheel.id).order_by(
        PrizeWheelSegment.orden, PrizeWheelSegment.id
    ).all()

    total_prob = sum(s.probabilidad for s in segs)

    return jsonify({
        'segmentos': [{
            'id': s.id,
            'texto': build_wheel_segment_text(s.tipo, s.valor, s.texto),
            'tipo': s.tipo,
            'valor': float(s.valor),
            'color': s.color,
            'angulo': round((s.probabilidad / total_prob) * 2 * math.pi, 4) if total_prob > 0 else 0,
            'disponible': s.esta_disponible,
            'orden': s.orden or 0
        } for s in segs]
    })