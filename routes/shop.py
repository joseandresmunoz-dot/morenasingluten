from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from extensions import db
from models import (Product, Category, Tag, Order, OrderItem, Coupon, UserCoupon,
                    DiscountRule, PrizeWheel, PrizeWheelSegment, PrizeSpin, CustomizationGroup, StoreConfig)
from decimal import Decimal
import urllib.parse
import secrets
import random
from datetime import datetime, timedelta
from sqlalchemy import func

shop_bp = Blueprint('shop', __name__)


@shop_bp.route('/')
def index():
    categories = Category.query.filter_by(activo=True).order_by(Category.orden).all()
    featured = Product.query.filter_by(activo=True, visible_tienda=True, stock_disponible=True, destacado=True).limit(8).all()

    best_sellers = db.session.query(
        Product,
        func.coalesce(func.sum(OrderItem.cantidad), 0).label('total_vendido')
    ).outerjoin(OrderItem, OrderItem.product_id == Product.id).outerjoin(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Product.activo == True,
        Product.stock_disponible == True,
        db.or_(Order.id == None, Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo']))
    ).group_by(Product.id).order_by(
        func.coalesce(func.sum(OrderItem.cantidad), 0).desc(),
        Product.nombre.asc()
    ).limit(8).all()

    best_sellers = [row[0] for row in best_sellers if row[1] > 0]

    return render_template('shop/index.html', categories=categories, featured=featured, best_sellers=best_sellers)


@shop_bp.route('/api/productos/buscar')
def api_buscar_productos():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])

    products = Product.query.filter(
        Product.activo == True,
        Product.visible_tienda == True,
        Product.stock_disponible == True,
        db.or_(
            Product.nombre.ilike(f'%{q}%'),
            Product.tags.any(Tag.nombre.ilike(f'%{q}%')),
            Category.nombre.ilike(f'%{q}%')
        )
    ).outerjoin(Product.category).order_by(Product.nombre).limit(8).all()

    results = []
    for p in products:
        tags = [{'nombre': t.nombre, 'color': t.color} for t in p.tags]
        img = p.imagen_principal or ''
        results.append({
            'id': p.id,
            'nombre': p.nombre,
            'imagen': img,
            'precio': float(p.precio) if p.precio else 0,
            'tags': tags,
        })
    return jsonify(results)


@shop_bp.route('/productos')
def products():
    category_id = request.args.get('categoria', type=int)
    tag_id = request.args.get('etiqueta', type=int)
    buscar = request.args.get('buscar', '').strip()

    query = Product.query.filter_by(activo=True, visible_tienda=True, stock_disponible=True)

    if category_id:
        query = query.filter_by(category_id=category_id)
    if tag_id:
        query = query.filter(Product.tags.any(Tag.id == tag_id))
    if buscar:
        query = query.filter(Product.nombre.ilike(f'%{buscar}%'))

    products = query.order_by(Product.nombre).all()
    categories = Category.query.filter_by(activo=True).order_by(Category.orden).all()
    tags = Tag.query.all()

    return render_template('shop/productos.html', products=products, categories=categories,
                           tags=tags, selected_category=category_id, selected_tag=tag_id, buscar=buscar)


@shop_bp.route('/producto/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    customization_groups = []
    if product.es_personalizable:
        customization_groups = product.customization_groups.all()
    return render_template('shop/producto_detalle.html', product=product,
                           customization_groups=customization_groups)


# --- CARRITO (Session-based) ---

def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']


def save_cart(cart):
    session['cart'] = cart
    session.modified = True


@shop_bp.route('/carrito')
def cart():
    cart_items = get_cart()
    items_detail = []
    subtotal = Decimal('0')

    for item in cart_items:
        product = db.session.get(Product, item['product_id'])
        if product:
            item_subtotal = Decimal(str(item['precio'])) * item['cantidad']
            subtotal += item_subtotal
            items_detail.append({
                'cart_index': item.get('cart_index', 0),
                'product': product,
                'cantidad': item['cantidad'],
                'precio': Decimal(str(item['precio'])),
                'subtotal': item_subtotal,
                'personalizacion': item.get('personalizacion', {})
            })

    discount_rules = check_discount_rules(items_detail)
    descuento_reglas = sum(d['descuento'] for d in discount_rules)

    available_coupons = []
    if current_user.is_authenticated:
        now = datetime.utcnow()
        available_coupons = db.session.query(Coupon).join(UserCoupon).filter(
            UserCoupon.user_id == current_user.id,
            UserCoupon.usado == False,
            UserCoupon.disponible == True,
            Coupon.activo == True,
            db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
        ).all()

    return render_template('shop/carrito.html', items=items_detail, subtotal=subtotal,
                           discount_rules=discount_rules, descuento_reglas=descuento_reglas,
                           show_wheel=False, segments=[], available_coupons=available_coupons)


@shop_bp.route('/carrito/agregar', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    cantidad = request.form.get('cantidad', 1, type=int)

    if not product_id or cantidad < 1:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Producto inválido.'}), 400
        flash('Producto inválido.', 'danger')
        return redirect(request.referrer or url_for('shop.products'))

    product = db.session.get(Product, product_id)
    if not product or not product.activo:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Producto no disponible.'}), 400
        flash('Producto no disponible.', 'danger')
        return redirect(request.referrer or url_for('shop.products'))

    precio = float(product.precio)
    personalizacion = {}

    if product.es_personalizable:
        from models import CustomizationOption
        for group in product.customization_groups.all():
            preset_mode = request.form.get(f'preset_mode_{group.id}', 'custom')
            opciones = []

            if preset_mode == 'clasicas':
                # Preset: 2 Dulce de leche, 2 Crema Pastelera, 2 Membrillo
                preset_map = {'Dulce de leche': 2, 'Crema Pastelera': 2, 'Membrillo': 2}
                for option in group.options.filter_by(activo=True).all():
                    qty = preset_map.get(option.nombre, 0)
                    if qty > 0:
                        opciones.append({
                            'id': option.id,
                            'nombre': option.nombre,
                            'cantidad': qty,
                            'precio_extra': float(option.precio_extra)
                        })
                        precio += float(option.precio_extra) * qty
            else:
                for option in group.options.filter_by(activo=True).all():
                    qty_key = f'custom_{group.id}_qty_{option.id}'
                    qty = request.form.get(qty_key, 0, type=int)
                    if qty > 0:
                        opciones.append({
                            'id': option.id,
                            'nombre': option.nombre,
                            'cantidad': qty,
                            'precio_extra': float(option.precio_extra)
                        })
                        precio += float(option.precio_extra) * qty

            if opciones:
                personalizacion[group.nombre] = opciones

    cart = get_cart()
    cart.append({
        'cart_index': len(cart),
        'product_id': product_id,
        'cantidad': cantidad,
        'precio': precio,
        'personalizacion': personalizacion
    })
    save_cart(cart)

    message = f'¡{product.nombre} agregado al carrito!'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'cart_count': len(cart), 'message': message})

    flash(message, 'success')
    return redirect(request.referrer or url_for('shop.products'))


@shop_bp.route('/carrito/actualizar', methods=['POST'])
def update_cart():
    index = request.form.get('index', type=int)
    cantidad = request.form.get('cantidad', type=int)

    cart = get_cart()
    if index is not None and 0 <= index < len(cart) and cantidad and cantidad > 0:
        cart[index]['cantidad'] = cantidad
        save_cart(cart)
    return redirect(url_for('shop.cart'))


@shop_bp.route('/carrito/eliminar', methods=['POST'])
def remove_from_cart():
    index = request.form.get('index', type=int)
    cart = get_cart()
    if index is not None and 0 <= index < len(cart):
        cart.pop(index)
        for i, item in enumerate(cart):
            item['cart_index'] = i
        save_cart(cart)
    return redirect(url_for('shop.cart'))


@shop_bp.route('/carrito/vaciar', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    flash('Carrito vaciado.', 'info')
    return redirect(url_for('shop.products'))


# --- CUPONES ---

@shop_bp.route('/carrito/aplicar-cupon', methods=['POST'])
@login_required
def apply_coupon():
    coupon = None
    coupon_id = request.form.get('coupon_id', type=int)
    if coupon_id:
        coupon = db.session.get(Coupon, coupon_id)
    else:
        codigo = request.form.get('codigo', '').strip().upper()
        if not codigo:
            flash('Ingresá un código de cupón.', 'warning')
            return redirect(url_for('shop.cart'))
        coupon = Coupon.query.filter_by(codigo=codigo).first()

    if not coupon:
        flash('Cupón no encontrado.', 'danger')
        return redirect(url_for('shop.cart'))

    cart = get_cart()
    subtotal = sum(Decimal(str(item['precio'])) * item['cantidad'] for item in cart)

    valid, msg = coupon.is_valid(current_user, float(subtotal))
    if not valid:
        flash(msg, 'danger')
        return redirect(url_for('shop.cart'))

    session['coupon_id'] = coupon.id
    session['coupon_code'] = coupon.codigo
    flash(f'¡Cupón "{coupon.codigo}" aplicado!', 'success')
    return redirect(url_for('shop.cart'))


@shop_bp.route('/carrito/quitar-cupon', methods=['POST'])
def remove_coupon():
    session.pop('coupon_id', None)
    session.pop('coupon_code', None)
    flash('Cupón removido.', 'info')
    redirect_to = request.form.get('redirect', 'cart')
    if redirect_to == 'checkout':
        return redirect(url_for('shop.checkout'))
    return redirect(url_for('shop.cart'))


@shop_bp.route('/checkout/aplicar-cupon', methods=['POST'])
@login_required
def apply_coupon_checkout():
    coupon_id = request.form.get('coupon_id', type=int)
    if not coupon_id:
        flash('Seleccioná un cupón.', 'warning')
        return redirect(url_for('shop.checkout'))

    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        flash('Cupón no encontrado.', 'danger')
        return redirect(url_for('shop.checkout'))

    # Verificar que el cupón pertenezca al usuario y esté habilitado
    uc = UserCoupon.query.filter_by(user_id=current_user.id, coupon_id=coupon.id, usado=False, disponible=True).first()
    if not uc:
        flash('Este cupón no está disponible para tu cuenta.', 'danger')
        return redirect(url_for('shop.checkout'))

    cart = get_cart()
    subtotal = sum(Decimal(str(item['precio'])) * item['cantidad'] for item in cart)

    valid, msg = coupon.is_valid(current_user, float(subtotal))
    if not valid:
        flash(msg, 'danger')
        return redirect(url_for('shop.checkout'))

    session['coupon_id'] = coupon.id
    session['coupon_code'] = coupon.codigo
    flash(f'¡Cupón "{coupon.codigo}" aplicado!', 'success')
    return redirect(url_for('shop.checkout'))


# --- REGLAS DE DESCUENTO ---

def check_discount_rules(items_detail):
    rules = DiscountRule.query.filter_by(activo=True).all()
    applied = []
    now = datetime.utcnow()

    for rule in rules:
        cond = rule.condicion or {}

        if rule.tipo == 'por_cantidad':
            min_qty = cond.get('min_cantidad', 0)
            prod_id = cond.get('producto_id')
            cat_id = cond.get('categoria_id')
            for item in items_detail:
                match = False
                if prod_id and item['product'].id == prod_id and item['cantidad'] >= min_qty:
                    match = True
                elif cat_id and item['product'].category_id == cat_id and item['cantidad'] >= min_qty:
                    match = True
                elif not prod_id and not cat_id and item['cantidad'] >= min_qty:
                    match = True

                if match:
                    if rule.descuento_tipo == 'porcentaje':
                        desc = float(item['subtotal']) * float(rule.descuento_valor) / 100
                    else:
                        desc = float(rule.descuento_valor)
                    applied.append({'nombre': rule.nombre, 'descuento': desc})

        elif rule.tipo == 'por_dia':
            dia = cond.get('dia_semana', '').lower()
            dias_map = {
                'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5, 'domingo': 6
            }
            if dias_map.get(dia) == now.weekday():
                total = sum(float(i['subtotal']) for i in items_detail)
                if rule.descuento_tipo == 'porcentaje':
                    desc = total * float(rule.descuento_valor) / 100
                else:
                    desc = float(rule.descuento_valor)
                applied.append({'nombre': rule.nombre, 'descuento': desc})

    return applied


# --- CHECKOUT ---

@shop_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if not current_user.email_verificado and not current_user.google_id and not current_user.is_admin:
        flash('Necesitás verificar tu email antes de finalizar una compra.', 'warning')
        return redirect(url_for('auth.complete_profile'))

    if not current_user.whatsapp:
        flash('Completá tu número de WhatsApp antes de hacer un pedido.', 'info')
        return redirect(url_for('auth.complete_profile'))

    cart = get_cart()
    if not cart:
        flash('Tu carrito está vacío.', 'warning')
        return redirect(url_for('shop.products'))

    items_detail = []
    subtotal = Decimal('0')

    for item in cart:
        product = db.session.get(Product, item['product_id'])
        if product:
            item_subtotal = Decimal(str(item['precio'])) * item['cantidad']
            subtotal += item_subtotal
            items_detail.append({
                'product': product,
                'cantidad': item['cantidad'],
                'precio': Decimal(str(item['precio'])),
                'subtotal': item_subtotal,
                'personalizacion': item.get('personalizacion', {})
            })

    # Descuento por reglas
    discount_rules = check_discount_rules(items_detail)
    descuento_reglas = Decimal(str(sum(d['descuento'] for d in discount_rules)))

    # Verificar si el usuario califica para la rueda de premios en checkout
    show_wheel = False
    segments = []
    if current_user.is_authenticated and float(subtotal) > 0:
        wheel = PrizeWheel.query.filter_by(activa=True).first()
        if wheel:
            total_with_cart = current_user.total_spent + float(subtotal)
            min_amount = float(wheel.monto_minimo_activacion)

            if total_with_cart >= min_amount:
                expected_spins = int(total_with_cart / min_amount)
                actual_spins = PrizeSpin.query.filter(
                    PrizeSpin.user_id == current_user.id,
                    PrizeSpin.wheel_id == wheel.id,
                    PrizeSpin.segment_id != None
                ).count()

                if expected_spins > actual_spins and not session.get('wheel_just_spun'):
                    show_wheel = True

                if show_wheel:
                    segs = wheel.segments.order_by(PrizeWheelSegment.id).all()
                    segments = []
                    for s in segs:
                        if s.tipo == 'descuento_porcentaje':
                            texto_segmento = f'{float(s.valor):.0f}% descuento'
                        elif s.tipo == 'descuento_fijo':
                            texto_segmento = f'${float(s.valor):.0f} descuento'
                        elif s.tipo == 'producto_gratis':
                            texto_segmento = 'Producto gratis'
                        elif s.tipo == 'sin_premio':
                            texto_segmento = 'Seguí participando'
                        else:
                            texto_segmento = s.texto
                        segments.append({'texto': texto_segmento, 'color': s.color, 'id': s.id, 'probabilidad': s.probabilidad})

    # Descuento por cupón
    descuento_cupon = Decimal('0')
    coupon = None
    if 'coupon_id' in session:
        coupon = db.session.get(Coupon, session['coupon_id'])
        if coupon:
            descuento_cupon = Decimal(str(coupon.calculate_discount(float(subtotal))))

    config_tienda = StoreConfig.get_or_create()
    envio_costo_config = Decimal(str(config_tienda.envio_domicilio_costo or 0))
    tipo_entrega = 'retiro'
    costo_envio = Decimal('0')

    if request.method == 'POST':
        tipo_entrega = request.form.get('tipo_entrega', 'retiro').strip().lower()
        if tipo_entrega not in ['retiro', 'domicilio']:
            tipo_entrega = 'retiro'

    if tipo_entrega == 'domicilio':
        costo_envio = envio_costo_config

    descuento_total = descuento_reglas + descuento_cupon
    total = max(subtotal - descuento_total + costo_envio, Decimal('0'))
    senia = (total / 2).quantize(Decimal('0.01'))

    available_coupons = []
    if not coupon:
        now = datetime.utcnow()
        available_coupons = db.session.query(Coupon).join(UserCoupon).filter(
            UserCoupon.user_id == current_user.id,
            UserCoupon.usado == False,
            UserCoupon.disponible == True,
            Coupon.activo == True,
            db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
        ).all()

    if request.method == 'POST':
        notas = request.form.get('notas', '').strip()
        fecha_retiro_str = request.form.get('fecha_retiro', '')
        direccion_entrega = (request.form.get('direccion_entrega', '').strip() or current_user.direccion or '').strip()

        if tipo_entrega == 'domicilio' and not direccion_entrega:
            available_coupons_on_error = []
            if not coupon:
                now = datetime.utcnow()
                available_coupons_on_error = db.session.query(Coupon).join(UserCoupon).filter(
                    UserCoupon.user_id == current_user.id,
                    UserCoupon.usado == False,
                    Coupon.activo == True,
                    db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
                ).all()
            flash('Si elegís envío a domicilio, debés ingresar una dirección de entrega.', 'danger')
            return render_template('shop/checkout.html', items=items_detail, subtotal=subtotal,
                                   descuento_reglas=descuento_reglas, descuento_cupon=descuento_cupon,
                                   descuento_total=descuento_total, total=total, senia=senia,
                                   coupon=coupon, discount_rules=discount_rules,
                                   available_coupons=available_coupons_on_error,
                                   show_wheel=show_wheel, segments=segments,
                                   mp_alias=current_app.config['MERCADOPAGO_ALIAS'],
                                   mp_titular=current_app.config['MERCADOPAGO_TITULAR'],
                                   tipo_entrega=tipo_entrega, costo_envio=costo_envio,
                                   envio_domicilio_costo=envio_costo_config,
                                   direccion_entrega=direccion_entrega)

        if tipo_entrega == 'domicilio' and direccion_entrega != (current_user.direccion or ''):
            current_user.direccion = direccion_entrega

        fecha_retiro = None
        if fecha_retiro_str:
            try:
                fecha_retiro = datetime.strptime(fecha_retiro_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Formato de fecha inválido.', 'danger')
                return render_template('shop/checkout.html', items=items_detail, subtotal=subtotal,
                                       descuento_reglas=descuento_reglas, descuento_cupon=descuento_cupon,
                                       descuento_total=descuento_total, total=total, senia=senia,
                                       coupon=coupon, discount_rules=discount_rules,
                                       available_coupons=available_coupons_on_error if 'available_coupons_on_error' in locals() else available_coupons,
                                       show_wheel=show_wheel, segments=segments,
                                       mp_alias=current_app.config['MERCADOPAGO_ALIAS'],
                                       mp_titular=current_app.config['MERCADOPAGO_TITULAR'],
                                       tipo_entrega=tipo_entrega, costo_envio=costo_envio,
                                       envio_domicilio_costo=envio_costo_config,
                                       direccion_entrega=direccion_entrega)

        order = Order(
            user_id=current_user.id,
            codigo=Order.generate_code(),
            subtotal=subtotal,
            descuento=descuento_total,
            total=total,
            senia=senia,
            coupon_id=coupon.id if coupon else None,
            notas=notas,
            tipo_entrega=tipo_entrega,
            costo_envio=costo_envio,
            direccion_entrega=direccion_entrega if tipo_entrega == 'domicilio' else None,
            fecha_retiro=fecha_retiro,
            status='pendiente'
        )
        db.session.add(order)
        db.session.flush()

        for item in cart:
            product = db.session.get(Product, item['product_id'])
            if product:
                oi = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    cantidad=item['cantidad'],
                    precio_unitario=Decimal(str(item['precio'])),
                    subtotal=Decimal(str(item['precio'])) * item['cantidad'],
                    personalizacion=item.get('personalizacion', {})
                )
                db.session.add(oi)

        if coupon:
            coupon.usos_actuales += 1
            uc = UserCoupon.query.filter_by(user_id=current_user.id, coupon_id=coupon.id).first()
            if uc:
                uc.usado = True

        # Activar cupones generados por la rueda para la próxima compra
        pending_coupons = UserCoupon.query.filter_by(
            user_id=current_user.id,
            usado=False,
            disponible=False
        ).all()
        for pending in pending_coupons:
            pending.disponible = True

        db.session.commit()

        session.pop('cart', None)
        session.pop('coupon_id', None)
        session.pop('coupon_code', None)
        session.pop('wheel_just_spun', None)
        session['wheel_order_id'] = order.id

        return redirect(url_for('shop.order_confirmation', order_id=order.id))

    return render_template('shop/checkout.html', items=items_detail, subtotal=subtotal,
                           descuento_reglas=descuento_reglas, descuento_cupon=descuento_cupon,
                           descuento_total=descuento_total, total=total, senia=senia,
                           coupon=coupon, discount_rules=discount_rules,
                           available_coupons=available_coupons,
                           show_wheel=show_wheel, segments=segments,
                           mp_alias=current_app.config['MERCADOPAGO_ALIAS'],
                           mp_titular=current_app.config['MERCADOPAGO_TITULAR'],
                           tipo_entrega=tipo_entrega, costo_envio=costo_envio,
                           envio_domicilio_costo=envio_costo_config,
                           direccion_entrega=current_user.direccion or '')


@shop_bp.route('/pedido/<int:order_id>/confirmacion')
@login_required
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        flash('No tenés acceso a este pedido.', 'danger')
        return redirect(url_for('shop.index'))

    show_wheel = False
    segments = []
    if session.get('wheel_order_id') == order.id and not session.get('wheel_just_spun'):
        wheel = PrizeWheel.query.filter_by(activa=True).first()
        if wheel:
            total_with_order = current_user.total_spent + float(order.total)
            min_amount = float(wheel.monto_minimo_activacion)
            if total_with_order >= min_amount:
                expected_spins = int(total_with_order / min_amount)
                actual_spins = PrizeSpin.query.filter(
                    PrizeSpin.user_id == current_user.id,
                    PrizeSpin.wheel_id == wheel.id,
                    PrizeSpin.segment_id != None
                ).count()
                if expected_spins > actual_spins:
                    show_wheel = True
                    segs = wheel.segments.order_by(PrizeWheelSegment.id).all()
                    for s in segs:
                        if s.tipo == 'descuento_porcentaje':
                            texto_segmento = f'{float(s.valor):.0f}% descuento'
                        elif s.tipo == 'descuento_fijo':
                            texto_segmento = f'${float(s.valor):.0f} descuento'
                        elif s.tipo == 'producto_gratis':
                            texto_segmento = 'Producto gratis'
                        elif s.tipo == 'sin_premio':
                            texto_segmento = 'Seguí participando'
                        else:
                            texto_segmento = s.texto
                        segments.append({'texto': texto_segmento, 'color': s.color, 'id': s.id, 'probabilidad': s.probabilidad})

    whatsapp_msg = build_whatsapp_message(order)
    whatsapp_url = f"https://wa.me/{current_app.config['WHATSAPP_NUMBER']}?text={urllib.parse.quote(whatsapp_msg)}"

    return render_template('shop/confirmacion.html', order=order, whatsapp_url=whatsapp_url,
                           mp_alias=current_app.config['MERCADOPAGO_ALIAS'],
                           mp_titular=current_app.config['MERCADOPAGO_TITULAR'],
                           show_wheel=show_wheel, segments=segments)


@shop_bp.route('/mis-pedidos')
@login_required
def my_orders():
    orders = current_user.orders.order_by(Order.created_at.desc()).all()

    # Cupones disponibles del usuario (no usados y activos)
    now = datetime.utcnow()
    available_coupons = db.session.query(Coupon).join(UserCoupon).filter(
        UserCoupon.user_id == current_user.id,
        UserCoupon.usado == False,
        UserCoupon.disponible == True,
        Coupon.activo == True,
        db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
    ).all()

    return render_template('shop/mis_pedidos.html', orders=orders, available_coupons=available_coupons)


@shop_bp.route('/mis-cupones')
@login_required
def my_coupons():
    now = datetime.utcnow()
    # Cupones activos (no usados, habilitados y no vencidos)
    active_coupons = db.session.query(Coupon, UserCoupon).join(UserCoupon).filter(
        UserCoupon.user_id == current_user.id,
        UserCoupon.usado == False,
        UserCoupon.disponible == True,
        Coupon.activo == True,
        db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
    ).all()

    # Cupones pendientes para la próxima compra
    pending_coupons = db.session.query(Coupon, UserCoupon).join(UserCoupon).filter(
        UserCoupon.user_id == current_user.id,
        UserCoupon.usado == False,
        UserCoupon.disponible == False,
        Coupon.activo == True,
        db.or_(Coupon.fecha_fin == None, Coupon.fecha_fin > now)
    ).all()

    # Cupones usados o vencidos
    used_coupons = db.session.query(Coupon, UserCoupon).join(UserCoupon).filter(
        UserCoupon.user_id == current_user.id,
        db.or_(
            UserCoupon.usado == True,
            db.and_(Coupon.fecha_fin != None, Coupon.fecha_fin <= now)
        )
    ).all()

    return render_template('shop/mis_cupones.html', active_coupons=active_coupons,
                           pending_coupons=pending_coupons,
                           used_coupons=used_coupons, current_time=now)


def build_whatsapp_message(order):
    lines = [f"🧁 *Nuevo Pedido - Morena Sin Gluten*",
             f"📋 Código: {order.codigo}",
             f"👤 Cliente: {order.user.nombre}",
              f"📱 WhatsApp: {order.user.whatsapp}",
             f"📍 Localidad: {order.user.localidad or 'No especificada'}",
             f"📧 Email: {order.user.email}",
             "",
             "*Productos:*"]

    for item in order.items:
        lines.append(f"  • {item.product.nombre} x{item.cantidad} - ${item.subtotal}")
        if item.personalizacion:
            for grupo, opciones in item.personalizacion.items():
                parts = []
                for o in opciones:
                    qty = o.get('cantidad', 1)
                    parts.append(f"{o['nombre']} x{qty}" if qty > 1 else o['nombre'])
                lines.append(f"    _{grupo}: {', '.join(parts)}_")

    entrega = order.tipo_entrega or 'retiro'
    lines.append("")
    lines.append(f"🚚 Entrega: {entrega.title()}")
    if entrega == 'domicilio':
        if order.direccion_entrega:
            lines.append(f"📍 Dirección: {order.direccion_entrega}")
        lines.append("🕕 Entregas a domicilio a partir de las 18:00 hs")
    lines.append(f"💰 Subtotal: ${order.subtotal}")
    if order.descuento > 0:
        lines.append(f"🏷️ Descuento: -${order.descuento}")
    if order.costo_envio and order.costo_envio > 0:
        lines.append(f"🚛 Envío: ${order.costo_envio}")
    lines.append(f"💵 *Total: ${order.total}*")
    lines.append(f"💳 *Seña (50%): ${order.senia}*")
    if order.notas:
        lines.append(f"📝 Notas: {order.notas}")
    if order.fecha_retiro:
        lines.append(f"📅 Retiro: {order.fecha_retiro.strftime('%d/%m/%Y %H:%M')}")

    return '\n'.join(lines)


# --- RUEDA DE PREMIOS ---

@shop_bp.route('/api/prize-spin/apply', methods=['POST'])
@login_required
def apply_prize():
    try:
        wheel = PrizeWheel.query.filter_by(activa=True).first()
        if not wheel:
            return jsonify({'error': 'Rueda no disponible'}), 400

        existing_spin = PrizeSpin.query.filter_by(
            user_id=current_user.id,
            wheel_id=wheel.id,
            premio_aplicado=False
        ).first()

        segment = None
        if existing_spin and existing_spin.segment_id and existing_spin.segment is not None:
            spin = existing_spin
            segment = existing_spin.segment
        else:
            if existing_spin:
                db.session.delete(existing_spin)

            cart_items = get_cart()
            subtotal = sum(Decimal(str(item['precio'])) * item['cantidad'] for item in cart_items)
            total_for_spin = current_user.total_spent + float(subtotal)

            order_id_for_spin = session.get('wheel_order_id')
            if order_id_for_spin:
                order_for_spin = db.session.get(Order, order_id_for_spin)
                if order_for_spin and order_for_spin.user_id == current_user.id:
                    total_for_spin = current_user.total_spent + float(order_for_spin.total)

            min_amount = float(wheel.monto_minimo_activacion)
            expected_spins = int(total_for_spin / min_amount)
            actual_spins = PrizeSpin.query.filter(
                PrizeSpin.user_id == current_user.id,
                PrizeSpin.wheel_id == wheel.id,
                PrizeSpin.segment_id != None
            ).count()

            if expected_spins <= actual_spins:
                return jsonify({'error': 'No tienes giros disponibles'}), 400

            segs = wheel.segments.order_by(PrizeWheelSegment.id).all()
            if not segs:
                return jsonify({'error': 'No hay segmentos configurados'}), 400

            weighted = []
            for seg in segs:
                weighted.extend([seg] * seg.probabilidad)
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
                uc = UserCoupon(user_id=current_user.id, coupon_id=coupon.id, disponible=False)
                db.session.add(uc)

            spin = PrizeSpin(
                user_id=current_user.id,
                wheel_id=wheel.id,
                segment_id=selected.id,
                monto_acumulado=Decimal(str(total_for_spin)),
                coupon_generado_id=coupon_id
            )
            db.session.add(spin)
            segment = selected

        spin.premio_aplicado = True

        if segment is None:
            segment = spin.segment
        if segment is None:
            db.session.delete(spin)
            db.session.commit()
            return jsonify({'error': 'Error interno de la rueda de premios. Volvé a intentarlo.'}), 500

        prize_text = segment.texto
        if segment.tipo == 'descuento_porcentaje':
            prize_text = f'{float(segment.valor):.0f}% de descuento'
        elif segment.tipo == 'descuento_fijo':
            prize_text = f'${float(segment.valor):.2f} de descuento'
        elif segment.tipo == 'producto_gratis':
            prize_text = 'Producto gratis'
        elif segment.tipo == 'sin_premio':
            prize_text = 'Sin premio'

        result = {
            'texto': prize_text,
            'tipo': segment.tipo,
            'segment_id': spin.segment_id,
            'valor': float(segment.valor)
        }

        if spin.coupon_generado:
            result['cupon'] = spin.coupon_generado.codigo
            result['tiene_cupon'] = True
            if spin.coupon_generado.fecha_fin:
                result['vencimiento'] = spin.coupon_generado.fecha_fin.strftime('%d/%m/%Y')

        session['wheel_just_spun'] = True
        db.session.commit()
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
