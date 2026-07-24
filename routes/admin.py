import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps
from PIL import Image, ImageOps
from extensions import db, csrf
from models import (Product, ProductImage, Category, Tag, Order, OrderItem, Coupon, UserCoupon,
                    DiscountRule, PrizeWheel, PrizeWheelSegment, PrizeSpin, CalendarEvent,
                    CustomizationGroup, CustomizationOption, User, StoreConfig, AdminEmail)
from sqlalchemy import func
from datetime import datetime, timedelta
from decimal import Decimal

MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

MESES_CORTOS_ES = {
    1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
}

def mes_anio(dt):
    return f"{MESES_ES[dt.month]} {dt.year}"

def mes_corto(dt):
    return MESES_CORTOS_ES[dt.month]

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('No tenés permisos de administrador.', 'danger')
            return redirect(url_for('shop.index'))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file):
    if file and allowed_file(file.filename):
        original_name = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        base_name = os.path.splitext(original_name)[0]
        filename = f"{timestamp}_{base_name}.jpg"
        upload_dir = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)

        try:
            with Image.open(file.stream) as img:
                img = ImageOps.exif_transpose(img)
                processed = ImageOps.fit(img, (1200, 1200), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                if processed.mode not in ('RGB', 'L'):
                    background = Image.new('RGB', processed.size, (255, 255, 255))
                    background.paste(processed, mask=processed.split()[-1] if processed.mode in ('RGBA', 'LA') else None)
                    processed = background
                elif processed.mode == 'L':
                    processed = processed.convert('RGB')
                processed.save(filepath, format='JPEG', quality=90, optimize=True)
            return f'/uploads/{filename}'
        except Exception:
            current_app.logger.exception('Error al procesar imagen de producto')
            return None
    return None


def delete_upload_file(url):
    if not url or not url.startswith('/uploads/'):
        return

    filename = os.path.basename(url)
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            current_app.logger.exception('Error al eliminar archivo de upload: %s', filepath)


def build_wheel_segment_text(tipo, valor, texto=''):
    value = float(valor or 0)
    if tipo == 'descuento_porcentaje':
        formatted = f'{value:.0f}'
        return f'{formatted}% descuento'
    if tipo == 'descuento_fijo':
        return f'${value:.0f} descuento'
    if tipo == 'producto_gratis':
        return 'Producto gratis'
    if tipo == 'sin_premio':
        return 'Seguí participando'
    return texto or 'Premio'


# --- DASHBOARD ---

@admin_bp.route('/')
@admin_required
def dashboard():
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    config_tienda = StoreConfig.get_or_create()

    ventas_mes = Order.query.filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])
    ).count()

    ingresos_mes = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])
    ).scalar()

    ingresos_envio_mes = db.session.query(func.coalesce(func.sum(Order.costo_envio), 0)).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.tipo_entrega == 'domicilio',
        Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])
    ).scalar()

    productos_vendidos_mes = db.session.query(func.coalesce(func.sum(OrderItem.cantidad), 0)).join(Order).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])
    ).scalar()

    clientes_nuevos_mes = User.query.filter(
        User.created_at >= datetime.combine(month_start, datetime.min.time()),
        User.created_at < datetime.combine(month_end, datetime.min.time()),
        User.is_admin == False
    ).count()

    pedidos_recientes = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    top_productos_mes = db.session.query(
        Product.nombre,
        func.sum(OrderItem.cantidad).label('total_vendido')
    ).join(OrderItem).join(Order).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])
    ).group_by(Product.nombre).order_by(func.sum(OrderItem.cantidad).desc()).limit(5).all()

    return render_template('admin/dashboard.html',
                           ventas_mes=ventas_mes, ingresos_mes=float(ingresos_mes),
                           productos_vendidos_mes=int(productos_vendidos_mes),
                           clientes_nuevos_mes=clientes_nuevos_mes,
                           pedidos_recientes=pedidos_recientes, top_productos=top_productos_mes,
                           envio_domicilio_costo=float(config_tienda.envio_domicilio_costo or 0),
                           ingresos_envio_mes=float(ingresos_envio_mes),
                           mes_actual=mes_anio(month_start))


@admin_bp.route('/dashboard/mensual')
@admin_required
def dashboard_mensual():
    today = datetime.utcnow().date()
    mesSeleccionado = request.args.get('mes', today.strftime('%Y-%m'))
    try:
        selected_date = datetime.strptime(mesSeleccionado, '%Y-%m').date()
    except ValueError:
        selected_date = today
    month_start = selected_date.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    status_filter = Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])

    ventas = Order.query.filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        status_filter
    ).count()

    ingresos = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        status_filter
    ).scalar()

    envio_ingresos = db.session.query(func.coalesce(func.sum(Order.costo_envio), 0)).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        Order.tipo_entrega == 'domicilio',
        status_filter
    ).scalar()

    productos_vendidos = db.session.query(func.coalesce(func.sum(OrderItem.cantidad), 0)).join(Order).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        status_filter
    ).scalar()

    clientes_nuevos = User.query.filter(
        User.created_at >= datetime.combine(month_start, datetime.min.time()),
        User.created_at < datetime.combine(month_end, datetime.min.time()),
        User.is_admin == False
    ).count()

    top_productos = db.session.query(
        Product.nombre,
        func.sum(OrderItem.cantidad).label('total')
    ).join(OrderItem).join(Order).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        status_filter
    ).group_by(Product.nombre).order_by(func.sum(OrderItem.cantidad).desc()).limit(10).all()

    ranking_clientes = db.session.query(
        User.nombre,
        func.count(Order.id).label('pedidos'),
        func.coalesce(func.sum(Order.total), 0).label('total_gastado')
    ).join(Order).filter(
        Order.created_at >= datetime.combine(month_start, datetime.min.time()),
        Order.created_at < datetime.combine(month_end, datetime.min.time()),
        status_filter
    ).group_by(User.id, User.nombre).order_by(func.sum(Order.total).desc()).limit(10).all()

    meses = []
    earliest = db.session.query(func.min(Order.created_at)).scalar()
    if earliest:
        start = earliest.replace(day=1)
        current = start
        while current <= datetime.utcnow():
            meses.append((current.strftime('%Y-%m'), mes_anio(current)))
            current = (current + timedelta(days=32)).replace(day=1)

    return render_template('admin/dashboard_mensual.html',
                           ventas=ventas, ingresos=float(ingresos),
                           envio_ingresos=float(envio_ingresos),
                           productos_vendidos=int(productos_vendidos),
                           clientes_nuevos=clientes_nuevos,
                           top_productos=top_productos,
                           ranking_clientes=ranking_clientes,
                           meses=meses, mes_seleccionado=mesSeleccionado,
                           mes_titulo=mes_anio(selected_date))


@admin_bp.route('/dashboard/anual')
@admin_required
def dashboard_anual():
    today = datetime.utcnow().date()
    anioSeleccionado = request.args.get('anio', str(today.year))
    try:
        anio = int(anioSeleccionado)
    except ValueError:
        anio = today.year

    anio_start = datetime(anio, 1, 1)
    anio_end = datetime(anio + 1, 1, 1)
    status_filter = Order.status.in_(['confirmado', 'entregado', 'senia_pagada', 'en_preparacion', 'listo'])

    ventas = Order.query.filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        status_filter
    ).count()

    ingresos = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        status_filter
    ).scalar()

    envio_ingresos = db.session.query(func.coalesce(func.sum(Order.costo_envio), 0)).filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        Order.tipo_entrega == 'domicilio',
        status_filter
    ).scalar()

    productos_vendidos = db.session.query(func.coalesce(func.sum(OrderItem.cantidad), 0)).join(Order).filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        status_filter
    ).scalar()

    clientes_nuevos = User.query.filter(
        User.created_at >= anio_start,
        User.created_at < anio_end,
        User.is_admin == False
    ).count()

    top_productos = db.session.query(
        Product.nombre,
        func.sum(OrderItem.cantidad).label('total')
    ).join(OrderItem).join(Order).filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        status_filter
    ).group_by(Product.nombre).order_by(func.sum(OrderItem.cantidad).desc()).limit(10).all()

    ranking_clientes = db.session.query(
        User.nombre,
        func.count(Order.id).label('pedidos'),
        func.coalesce(func.sum(Order.total), 0).label('total_gastado')
    ).join(Order).filter(
        Order.created_at >= anio_start,
        Order.created_at < anio_end,
        status_filter
    ).group_by(User.id, User.nombre).order_by(func.sum(Order.total).desc()).limit(10).all()

    resumen_mensual = []
    for m in range(1, 13):
        m_start = datetime(anio, m, 1)
        m_end = (m_start + timedelta(days=32)).replace(day=1)
        m_ventas = Order.query.filter(Order.created_at >= m_start, Order.created_at < m_end, status_filter).count()
        m_ingresos = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            Order.created_at >= m_start, Order.created_at < m_end, status_filter
        ).scalar()
        m_clientes = User.query.filter(
            User.created_at >= m_start, User.created_at < m_end, User.is_admin == False
        ).count()
        resumen_mensual.append({
            'mes': mes_corto(m_start),
            'ventas': m_ventas,
            'ingresos': float(m_ingresos),
            'clientes': m_clientes
        })

    anios_disponibles = []
    earliest = db.session.query(func.min(Order.created_at)).scalar()
    if earliest:
        for y in range(earliest.year, today.year + 1):
            anios_disponibles.append(y)

    return render_template('admin/dashboard_anual.html',
                           ventas=ventas, ingresos=float(ingresos),
                           envio_ingresos=float(envio_ingresos),
                           productos_vendidos=int(productos_vendidos),
                           clientes_nuevos=clientes_nuevos,
                           top_productos=top_productos,
                           ranking_clientes=ranking_clientes,
                           resumen_mensual=resumen_mensual,
                           anio_seleccionado=str(anio),
                           anios_disponibles=anios_disponibles)


@admin_bp.route('/configuracion/envio', methods=['POST'])
@admin_required
def update_shipping_config():
    config_tienda = StoreConfig.get_or_create()
    costo_envio = request.form.get('envio_domicilio_costo', 0, type=float)
    if costo_envio is None or costo_envio < 0:
        flash('El costo de envío debe ser un número mayor o igual a 0.', 'danger')
        return redirect(url_for('admin.dashboard'))

    config_tienda.envio_domicilio_costo = Decimal(str(costo_envio))
    db.session.commit()
    flash('Costo de envío a domicilio actualizado.', 'success')
    return redirect(url_for('admin.dashboard'))


# --- PRODUCTOS ---

@admin_bp.route('/productos')
@admin_required
def products():
    products = Product.query.order_by(Product.nombre).all()
    categories = Category.query.order_by(Category.nombre).all()
    return render_template('admin/productos.html', products=products, categories=categories)


@admin_bp.route('/productos/actualizar-precios', methods=['POST'])
@admin_required
def bulk_price_update():
    categoria_id = request.form.get('categoria_id', 0, type=int)
    tipo = request.form.get('tipo', 'porcentaje')
    valor = request.form.get('valor', 0, type=float)
    redondear = 'redondear' in request.form

    if valor <= 0:
        flash('El valor debe ser mayor a 0.', 'danger')
        return redirect(url_for('admin.products'))

    query = Product.query
    if categoria_id > 0:
        query = query.filter_by(category_id=categoria_id)

    products = query.all()
    if not products:
        flash('No hay productos en los filtros seleccionados.', 'warning')
        return redirect(url_for('admin.products'))

    actualizados = 0
    for p in products:
        if tipo == 'porcentaje':
            nuevo = float(p.precio) * (1 + valor / 100)
        else:
            nuevo = float(p.precio) + valor

        if redondear:
            nuevo = round(nuevo / 100) * 100

        p.precio = Decimal(str(round(nuevo, 2)))
        actualizados += 1

    db.session.commit()

    tipo_label = '%' if tipo == 'porcentaje' else '$'
    flash(f'{actualizados} producto(s) actualizado(s) con {tipo_label}{"%.2f" % valor}.', 'success')
    return redirect(url_for('admin.products'))


@admin_bp.route('/productos/nuevo', methods=['GET', 'POST'])
@admin_required
def product_new():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        precio = request.form.get('precio', type=float)
        category_id = request.form.get('category_id', type=int)
        es_personalizable = 'es_personalizable' in request.form
        destacado = 'destacado' in request.form
        visible_tienda = 'visible_tienda' in request.form
        tag_ids = request.form.getlist('tags', type=int)

        if not nombre or not precio:
            flash('Nombre y precio son obligatorios.', 'danger')
            categories = Category.query.filter_by(activo=True).all()
            tags = Tag.query.all()
            return render_template('admin/producto_form.html', categories=categories, tags=tags)

        product = Product(
            nombre=nombre, descripcion=descripcion, precio=Decimal(str(precio)),
            category_id=category_id if category_id else None,
            es_personalizable=es_personalizable,
            destacado=destacado,
            visible_tienda=visible_tienda
        )

        if tag_ids:
            product.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

        db.session.add(product)
        db.session.flush()

        # Guardar imágenes
        files = request.files.getlist('imagenes')
        for i, f in enumerate(files):
            url = save_image(f)
            if url:
                img = ProductImage(product_id=product.id, url=url, orden=i)
                db.session.add(img)

        db.session.commit()

        flash(f'Producto "{nombre}" creado.', 'success')
        if es_personalizable:
            return redirect(url_for('admin.product_customizations', product_id=product.id))
        return redirect(url_for('admin.products'))

    categories = Category.query.filter_by(activo=True).all()
    tags = Tag.query.all()
    return render_template('admin/producto_form.html', categories=categories, tags=tags)


@admin_bp.route('/productos/<int:product_id>/editar', methods=['GET', 'POST'])
@admin_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.nombre = request.form.get('nombre', '').strip()
        product.descripcion = request.form.get('descripcion', '').strip()
        product.precio = Decimal(str(request.form.get('precio', type=float)))
        product.category_id = request.form.get('category_id', type=int) or None
        product.es_personalizable = 'es_personalizable' in request.form
        product.destacado = 'destacado' in request.form
        product.visible_tienda = 'visible_tienda' in request.form
        product.activo = 'activo' in request.form
        product.stock_disponible = 'stock_disponible' in request.form

        tag_ids = request.form.getlist('tags', type=int)
        product.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

        # Agregar nuevas imágenes
        files = request.files.getlist('imagenes')
        nuevas_urls = []
        for f in files:
            url = save_image(f)
            if url:
                nuevas_urls.append(url)

        if nuevas_urls:
            existentes = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.orden).all()
            desplazamiento = len(nuevas_urls)
            for i, existente in enumerate(existentes):
                existente.orden = i + desplazamiento

            for i, url in enumerate(nuevas_urls):
                img = ProductImage(product_id=product.id, url=url, orden=i)
                db.session.add(img)

        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('admin.products'))

    categories = Category.query.filter_by(activo=True).all()
    tags = Tag.query.all()
    return render_template('admin/producto_form.html', product=product, categories=categories, tags=tags)


@admin_bp.route('/productos/<int:product_id>/eliminar', methods=['POST'])
@admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)

    tiene_pedidos = OrderItem.query.filter_by(product_id=product.id).first() is not None
    if tiene_pedidos:
        product.activo = False
        product.stock_disponible = False
        db.session.commit()
        flash('Producto desactivado porque tiene pedidos asociados.', 'warning')
        return redirect(url_for('admin.products'))

    image_urls = [img.url for img in product.images.all() if img.url]
    if product.imagen:
        image_urls.append(product.imagen)

    db.session.delete(product)
    db.session.commit()

    for url in image_urls:
        delete_upload_file(url)

    flash('Producto eliminado.', 'success')
    return redirect(url_for('admin.products'))


@admin_bp.route('/productos/imagen/<int:image_id>/eliminar', methods=['POST'])
@admin_required
def product_image_delete(image_id):
    img = ProductImage.query.get_or_404(image_id)
    product_id = img.product_id
    image_url = img.url
    db.session.delete(img)
    db.session.commit()
    delete_upload_file(image_url)
    flash('Imagen eliminada.', 'success')
    return redirect(url_for('admin.product_edit', product_id=product_id))


@admin_bp.route('/productos/imagen/<int:image_id>/principal', methods=['POST'])
@admin_required
def product_image_set_principal(image_id):
    img = ProductImage.query.get_or_404(image_id)
    product_id = img.product_id

    # Poner esta imagen con orden 0 y reordenar el resto
    all_images = ProductImage.query.filter_by(product_id=product_id).order_by(ProductImage.orden).all()
    orden = 1
    for other in all_images:
        if other.id == img.id:
            other.orden = 0
        else:
            other.orden = orden
            orden += 1

    db.session.commit()
    flash('Imagen principal actualizada.', 'success')
    return redirect(url_for('admin.product_edit', product_id=product_id))


# --- PERSONALIZACIONES ---

@admin_bp.route('/productos/<int:product_id>/personalizaciones', methods=['GET', 'POST'])
@admin_required
def product_customizations(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        nombre = request.form.get('group_nombre', '').strip()
        min_sel = request.form.get('min_selecciones', 0, type=int)
        max_sel = request.form.get('max_selecciones', 10, type=int)
        obligatorio = 'obligatorio' in request.form

        if nombre:
            group = CustomizationGroup(
                product_id=product.id, nombre=nombre,
                min_selecciones=min_sel, max_selecciones=max_sel,
                obligatorio=obligatorio
            )
            db.session.add(group)
            db.session.commit()
            flash(f'Grupo "{nombre}" creado.', 'success')

        return redirect(url_for('admin.product_customizations', product_id=product.id))

    groups = product.customization_groups.all()
    return render_template('admin/personalizaciones.html', product=product, groups=groups)


@admin_bp.route('/personalizaciones/grupo/<int:group_id>/opciones', methods=['POST'])
@admin_required
def add_customization_option(group_id):
    group = CustomizationGroup.query.get_or_404(group_id)
    nombre = request.form.get('option_nombre', '').strip()
    precio_extra = request.form.get('precio_extra', 0, type=float)

    if nombre:
        option = CustomizationOption(
            group_id=group.id, nombre=nombre,
            precio_extra=Decimal(str(precio_extra))
        )
        db.session.add(option)
        db.session.commit()
        flash(f'Opción "{nombre}" agregada.', 'success')

    return redirect(url_for('admin.product_customizations', product_id=group.product_id))


@admin_bp.route('/personalizaciones/grupo/<int:group_id>/eliminar', methods=['POST'])
@admin_required
def delete_customization_group(group_id):
    group = CustomizationGroup.query.get_or_404(group_id)
    pid = group.product_id
    db.session.delete(group)
    db.session.commit()
    flash('Grupo eliminado.', 'info')
    return redirect(url_for('admin.product_customizations', product_id=pid))


@admin_bp.route('/personalizaciones/opcion/<int:option_id>/eliminar', methods=['POST'])
@admin_required
def delete_customization_option(option_id):
    option = CustomizationOption.query.get_or_404(option_id)
    pid = option.group.product_id
    db.session.delete(option)
    db.session.commit()
    flash('Opción eliminada.', 'info')
    return redirect(url_for('admin.product_customizations', product_id=pid))


# --- CATEGORÍAS ---

@admin_bp.route('/categorias', methods=['GET', 'POST'])
@admin_required
def categories():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        orden = request.form.get('orden', 0, type=int)

        if nombre:
            imagen = None
            if 'imagen' in request.files:
                imagen = save_image(request.files['imagen'])
            cat = Category(nombre=nombre, descripcion=descripcion, orden=orden, imagen=imagen)
            db.session.add(cat)
            db.session.commit()
            flash(f'Categoría "{nombre}" creada.', 'success')

        return redirect(url_for('admin.categories'))

    cats = Category.query.order_by(Category.orden).all()
    return render_template('admin/categorias.html', categories=cats)


@admin_bp.route('/categorias/<int:cat_id>/editar', methods=['POST'])
@admin_required
def category_edit(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat.nombre = request.form.get('nombre', cat.nombre).strip()
    cat.descripcion = request.form.get('descripcion', '').strip()
    cat.orden = request.form.get('orden', cat.orden, type=int)
    cat.activo = 'activo' in request.form

    if 'imagen' in request.files and request.files['imagen'].filename:
        imagen = save_image(request.files['imagen'])
        if imagen:
            cat.imagen = imagen

    db.session.commit()
    flash('Categoría actualizada.', 'success')
    return redirect(url_for('admin.categories'))


@admin_bp.route('/categorias/<int:cat_id>/eliminar', methods=['POST'])
@admin_required
def category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat.activo = False
    db.session.commit()
    flash('Categoría desactivada.', 'info')
    return redirect(url_for('admin.categories'))


# --- ETIQUETAS ---

@admin_bp.route('/etiquetas', methods=['GET', 'POST'])
@admin_required
def tags():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        color = request.form.get('color', '#8B4513').strip()
        if nombre:
            tag = Tag(nombre=nombre, color=color)
            db.session.add(tag)
            db.session.commit()
            flash(f'Etiqueta "{nombre}" creada.', 'success')
        return redirect(url_for('admin.tags'))

    tags = Tag.query.order_by(Tag.nombre).all()
    return render_template('admin/etiquetas.html', tags=tags)


@admin_bp.route('/etiquetas/<int:tag_id>/eliminar', methods=['POST'])
@admin_required
def tag_delete(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    flash('Etiqueta eliminada.', 'info')
    return redirect(url_for('admin.tags'))


# --- PEDIDOS ---

@admin_bp.route('/pedidos')
@admin_required
def orders():
    status_filter = request.args.get('status', '')
    query = Order.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin/pedidos.html', orders=orders, status_filter=status_filter)


@admin_bp.route('/pedidos/<int:order_id>')
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/pedido_detalle.html', order=order)


@admin_bp.route('/pedidos/nuevo', methods=['GET', 'POST'])
@admin_required
def order_new():
    users = User.query.filter_by(is_admin=False).order_by(User.nombre).all()
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    config_tienda = StoreConfig.get_or_create()

    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        tipo_entrega = request.form.get('tipo_entrega', 'retiro')
        direccion_entrega = request.form.get('direccion_entrega', '').strip() or None
        notas = request.form.get('notas', '').strip()
        costo_envio = request.form.get('costo_envio', type=float) or 0
        status = request.form.get('status', 'confirmado')

        if not user_id:
            flash('Debés seleccionar un cliente.', 'danger')
            return render_template('admin/pedido_form.html', users=users, products=products, config_tienda=config_tienda)

        if tipo_entrega == 'domicilio' and not direccion_entrega:
            flash('Debés ingresar una dirección de entrega para envío a domicilio.', 'danger')
            return render_template('admin/pedido_form.html', users=users, products=products, config_tienda=config_tienda)

        if tipo_entrega == 'retiro':
            costo_envio = 0

        product_ids = request.form.getlist('product_id', type=int)
        cantidades = request.form.getlist('cantidad', type=int)
        items_data = []

        for product_id, cantidad in zip(product_ids, cantidades):
            if product_id and cantidad and cantidad > 0:
                product = Product.query.get(product_id)
                if product:
                    items_data.append((product, cantidad))

        if not items_data:
            flash('Debés agregar al menos un producto con cantidad mayor a cero.', 'danger')
            return render_template('admin/pedido_form.html', users=users, products=products, config_tienda=config_tienda)

        order = Order(
            user_id=user_id,
            codigo=Order.generate_code(),
            subtotal=0,
            descuento=0,
            total=0,
            senia=0,
            status=status,
            notas=notas,
            tipo_entrega=tipo_entrega,
            costo_envio=Decimal(str(costo_envio)),
            direccion_entrega=direccion_entrega
        )
        db.session.add(order)
        db.session.flush()

        subtotal = Decimal('0')
        for product, cantidad in items_data:
            precio_unitario = Decimal(str(product.precio))
            item_subtotal = precio_unitario * cantidad
            subtotal += item_subtotal
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=item_subtotal
            )
            db.session.add(order_item)

        order.subtotal = subtotal
        order.total = subtotal + order.costo_envio
        db.session.commit()

        flash('Pedido creado manualmente.', 'success')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    return render_template('admin/pedido_form.html', users=users, products=products, config_tienda=config_tienda)


@admin_bp.route('/pedidos/<int:order_id>/status', methods=['POST'])
@admin_required
@csrf.exempt
def order_update_status(order_id):
    current_app.logger.info(f'Actualizando estado del pedido {order_id}')
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status', '')
    # Detectar si es una petición AJAX
    is_ajax = request.form.get('ajax') == '1' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    current_app.logger.info(f'Estado nuevo: {new_status}, AJAX: {is_ajax}')

    valid_statuses = ['pendiente', 'senia_pagada', 'confirmado', 'en_preparacion', 'listo', 'entregado', 'cancelado']

    if new_status not in valid_statuses:
        current_app.logger.warning(f'Estado inválido: {new_status}')
        if is_ajax:
            return jsonify({'success': False, 'message': 'Estado inválido'}), 400
        flash('Estado inválido.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    order.status = new_status
    db.session.commit()
    current_app.logger.info(f'Estado actualizado exitosamente a: {new_status}')

    if is_ajax:
        return jsonify({'success': True, 'message': f'Estado actualizado a "{new_status}"', 'status': new_status})

    flash(f'Estado del pedido actualizado a "{new_status}".', 'success')
    return redirect(url_for('admin.order_detail', order_id=order.id))


@admin_bp.route('/pedidos/<int:order_id>/fecha-retiro', methods=['POST'])
@admin_required
def order_set_fecha_retiro(order_id):
    order = Order.query.get_or_404(order_id)
    fecha_str = request.form.get('fecha_retiro', '')

    if not fecha_str:
        flash('Debés seleccionar una fecha.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    try:
        fecha_retiro = datetime.fromisoformat(fecha_str)
    except ValueError:
        flash('Fecha inválida.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    order.fecha_retiro = fecha_retiro

    # Eliminar evento de calendario anterior para este pedido (si existe)
    CalendarEvent.query.filter_by(order_id=order.id).delete()

    tipo_label = 'Retiro' if order.tipo_entrega == 'retiro' else 'Domicilio'
    titulo = f'{order.user.nombre} - {tipo_label}'
    items_descripcion = '\n'.join(
        f'{item.cantidad} x {item.product.nombre}' for item in order.items
    )
    descripcion = f'{tipo_label}\n{items_descripcion}' if items_descripcion else tipo_label

    # Crear evento en el calendario
    evento = CalendarEvent(
        titulo=titulo,
        descripcion=descripcion,
        order_id=order.id,
        fecha_inicio=fecha_retiro,
        fecha_fin=fecha_retiro + timedelta(hours=1),
        color='#C4756E'
    )
    db.session.add(evento)
    db.session.commit()

    flash(f'Fecha de retiro asignada: {fecha_retiro.strftime("%d/%m/%Y %H:%M")} hs. Evento agregado al calendario.', 'success')
    return redirect(url_for('admin.order_detail', order_id=order.id))


# --- CUPONES ---

@admin_bp.route('/cupones')
@admin_required
def coupons():
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('admin/cupones.html', coupons=coupons)


@admin_bp.route('/cupones/nuevo', methods=['GET', 'POST'])
@admin_required
def coupon_new():
    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip().upper()
        descripcion = request.form.get('descripcion', '').strip()
        tipo = request.form.get('tipo', 'porcentaje')
        valor = request.form.get('valor', 0, type=float)
        minimo_compra = request.form.get('minimo_compra', 0, type=float)
        max_usos = request.form.get('max_usos', type=int)
        solo_primer_pedido = 'solo_primer_pedido' in request.form

        fecha_inicio = None
        fecha_fin = None
        fi = request.form.get('fecha_inicio', '')
        ff = request.form.get('fecha_fin', '')
        if fi:
            try:
                fecha_inicio = datetime.strptime(fi, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass
        if ff:
            try:
                fecha_fin = datetime.strptime(ff, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        user_emails = request.form.get('user_emails', '').strip()

        if not codigo:
            flash('El código es obligatorio.', 'danger')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('admin/cupon_form.html', users=users, coupon=None)

        coupon = Coupon(
            codigo=codigo, descripcion=descripcion, tipo=tipo,
            valor=Decimal(str(valor)), minimo_compra=Decimal(str(minimo_compra)),
            max_usos=max_usos, solo_primer_pedido=solo_primer_pedido,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
        )
        db.session.add(coupon)
        db.session.flush()

        # Asignar a usuarios específicos
        if user_emails:
            emails = [e.strip().lower() for e in user_emails.split(',')]
            for email in emails:
                user = User.query.filter_by(email=email).first()
                if user:
                    uc = UserCoupon(user_id=user.id, coupon_id=coupon.id, disponible=True)
                    db.session.add(uc)

        db.session.commit()
        flash(f'Cupón "{codigo}" creado.', 'success')
        return redirect(url_for('admin.coupons'))

    users = User.query.filter_by(is_admin=False).all()
    return render_template('admin/cupon_form.html', users=users, coupon=None)


@admin_bp.route('/cupones/<int:coupon_id>/toggle', methods=['POST'])
@admin_required
def coupon_toggle(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.activo = not coupon.activo
    db.session.commit()
    flash(f'Cupón {"activado" if coupon.activo else "desactivado"}.', 'info')
    return redirect(url_for('admin.coupons'))


@admin_bp.route('/cupones/<int:coupon_id>/editar', methods=['GET', 'POST'])
@admin_required
def coupon_edit(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    if request.method == 'POST':
        coupon.codigo = request.form.get('codigo', '').strip().upper()
        coupon.descripcion = request.form.get('descripcion', '').strip()
        coupon.tipo = request.form.get('tipo', 'porcentaje')
        coupon.valor = Decimal(str(request.form.get('valor', 0, type=float)))
        coupon.minimo_compra = Decimal(str(request.form.get('minimo_compra', 0, type=float)))
        coupon.max_usos = request.form.get('max_usos', type=int)
        coupon.solo_primer_pedido = 'solo_primer_pedido' in request.form

        fi = request.form.get('fecha_inicio', '')
        ff = request.form.get('fecha_fin', '')
        coupon.fecha_inicio = None
        coupon.fecha_fin = None
        if fi:
            try:
                coupon.fecha_inicio = datetime.strptime(fi, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass
        if ff:
            try:
                coupon.fecha_fin = datetime.strptime(ff, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        if not coupon.codigo:
            flash('El código es obligatorio.', 'danger')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('admin/cupon_form.html', users=users, coupon=coupon)

        db.session.commit()
        flash(f'Cupón "{coupon.codigo}" actualizado.', 'success')
        return redirect(url_for('admin.coupons'))

    users = User.query.filter_by(is_admin=False).all()
    return render_template('admin/cupon_form.html', users=users, coupon=coupon)


@admin_bp.route('/cupones/<int:coupon_id>/eliminar', methods=['POST'])
@admin_required
def coupon_delete(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)

    for order in coupon.orders.all():
        order.coupon_id = None

    for user_coupon in coupon.user_coupons.all():
        db.session.delete(user_coupon)

    db.session.delete(coupon)
    db.session.commit()
    flash('Cupón eliminado.', 'success')
    return redirect(url_for('admin.coupons'))


# --- REGLAS DE DESCUENTO ---

@admin_bp.route('/descuentos')
@admin_required
def discount_rules():
    rules = DiscountRule.query.all()
    return render_template('admin/descuentos.html', rules=rules)


@admin_bp.route('/descuentos/nuevo', methods=['GET', 'POST'])
@admin_required
def discount_rule_new():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        tipo = request.form.get('tipo', '')
        descuento_tipo = request.form.get('descuento_tipo', 'porcentaje')
        descuento_valor = request.form.get('descuento_valor', 0, type=float)

        condicion = {}
        if tipo == 'por_cantidad':
            condicion['min_cantidad'] = request.form.get('min_cantidad', 1, type=int)
            prod_id = request.form.get('producto_id', type=int)
            cat_id = request.form.get('categoria_id', type=int)
            if prod_id:
                condicion['producto_id'] = prod_id
            if cat_id:
                condicion['categoria_id'] = cat_id
        elif tipo == 'por_dia':
            condicion['dia_semana'] = request.form.get('dia_semana', '')

        rule = DiscountRule(
            nombre=nombre, tipo=tipo, condicion=condicion,
            descuento_tipo=descuento_tipo,
            descuento_valor=Decimal(str(descuento_valor))
        )
        db.session.add(rule)
        db.session.commit()
        flash('Regla de descuento creada.', 'success')
        return redirect(url_for('admin.discount_rules'))

    products = Product.query.filter_by(activo=True).all()
    categories = Category.query.filter_by(activo=True).all()
    return render_template('admin/descuento_form.html', products=products, categories=categories)


@admin_bp.route('/descuentos/<int:rule_id>/toggle', methods=['POST'])
@admin_required
def discount_rule_toggle(rule_id):
    rule = DiscountRule.query.get_or_404(rule_id)
    rule.activo = not rule.activo
    db.session.commit()
    flash(f'Regla {"activada" if rule.activo else "desactivada"}.', 'info')
    return redirect(url_for('admin.discount_rules'))


@admin_bp.route('/descuentos/<int:rule_id>/eliminar', methods=['POST'])
@admin_required
def discount_rule_delete(rule_id):
    rule = DiscountRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    flash('Regla eliminada.', 'info')
    return redirect(url_for('admin.discount_rules'))


# --- RUEDA DE PREMIOS ---

@admin_bp.route('/rueda')
@admin_required
def prize_wheel():
    wheel = PrizeWheel.query.first()
    segment_spin_counts = {}
    if wheel:
        segment_ids = [seg.id for seg in wheel.segments.all()]
        if segment_ids:
            counts = db.session.query(PrizeSpin.segment_id, func.count(PrizeSpin.id)).filter(
                PrizeSpin.segment_id.in_(segment_ids)
            ).group_by(PrizeSpin.segment_id).all()
            segment_spin_counts = {segment_id: count for segment_id, count in counts}
    return render_template('admin/rueda.html', wheel=wheel, segment_spin_counts=segment_spin_counts)


@admin_bp.route('/rueda/configurar', methods=['POST'])
@admin_required
def prize_wheel_config():
    wheel = PrizeWheel.query.first()
    if not wheel:
        wheel = PrizeWheel(nombre='Rueda de Premios')
        db.session.add(wheel)

    wheel.monto_minimo_activacion = Decimal(str(request.form.get('monto_minimo', 10000, type=float)))
    wheel.activa = 'activa' in request.form
    db.session.commit()
    flash('Configuración de la rueda actualizada.', 'success')
    return redirect(url_for('admin.prize_wheel'))


@admin_bp.route('/rueda/segmento', methods=['POST'])
@admin_required
def prize_wheel_add_segment():
    wheel = PrizeWheel.query.first()
    if not wheel:
        flash('Primero configurá la rueda.', 'warning')
        return redirect(url_for('admin.prize_wheel'))

    texto = request.form.get('texto', '').strip()
    tipo = request.form.get('tipo', 'sin_premio')
    valor = request.form.get('valor', 0, type=float)
    color = request.form.get('color', '#8B4513')
    probabilidad = request.form.get('probabilidad', 1, type=int)

    texto_final = build_wheel_segment_text(tipo, valor, texto)
    seg = PrizeWheelSegment(
        wheel_id=wheel.id, texto=texto_final, tipo=tipo,
        valor=Decimal(str(valor)), color=color, probabilidad=probabilidad
    )
    db.session.add(seg)
    db.session.commit()
    flash(f'Segmento "{texto_final}" agregado.', 'success')

    return redirect(url_for('admin.prize_wheel'))


@admin_bp.route('/rueda/segmento/<int:seg_id>/eliminar', methods=['POST'])
@admin_required
def prize_wheel_delete_segment(seg_id):
    seg = PrizeWheelSegment.query.get_or_404(seg_id)
    force_delete = request.form.get('force', '0') == '1'
    spins = PrizeSpin.query.filter_by(segment_id=seg.id).all()

    if spins and not force_delete:
        flash('Este segmento ya fue usado en giros anteriores. Marcalo como forzado para eliminarlo junto con los giros asociados.', 'warning')
        return redirect(url_for('admin.prize_wheel'))

    if spins:
        for spin in spins:
            db.session.delete(spin)

    db.session.delete(seg)
    db.session.commit()
    flash('Segmento eliminado.', 'info')
    return redirect(url_for('admin.prize_wheel'))


# --- CALENDARIO ---

@admin_bp.route('/calendario')
@admin_required
def calendar():
    return render_template('admin/calendario.html')


@admin_bp.route('/api/calendar/events')
@admin_required
def calendar_events():
    start = request.args.get('start', '')
    end = request.args.get('end', '')

    query = CalendarEvent.query

    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            query = query.filter(CalendarEvent.fecha_inicio >= start_dt)
        except ValueError:
            pass
    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            query = query.filter(CalendarEvent.fecha_inicio <= end_dt)
        except ValueError:
            pass

    events = query.all()
    result = []
    for ev in events:
        result.append({
            'id': ev.id,
            'title': ev.titulo,
            'start': ev.fecha_inicio.isoformat(),
            'end': ev.fecha_fin.isoformat() if ev.fecha_fin else None,
            'color': ev.color,
            'extendedProps': {
                'descripcion': ev.descripcion or '',
                'order_id': ev.order_id
            }
        })
    return jsonify(result)


@admin_bp.route('/api/calendar/events', methods=['POST'])
@admin_required
def calendar_event_create():
    data = request.get_json()
    titulo = data.get('title', '').strip()
    descripcion = data.get('descripcion', '').strip()
    fecha_inicio = data.get('start', '')
    fecha_fin = data.get('end', '')
    color = data.get('color', '#8B4513')
    order_id = data.get('order_id', type=int)

    if not titulo or not fecha_inicio:
        return jsonify({'error': 'Título y fecha son obligatorios'}), 400

    try:
        fi = datetime.fromisoformat(fecha_inicio)
    except ValueError:
        return jsonify({'error': 'Fecha inválida'}), 400

    ff = None
    if fecha_fin:
        try:
            ff = datetime.fromisoformat(fecha_fin)
        except ValueError:
            pass

    event = CalendarEvent(
        titulo=titulo, descripcion=descripcion,
        fecha_inicio=fi, fecha_fin=ff, color=color,
        order_id=order_id
    )
    db.session.add(event)
    db.session.commit()

    return jsonify({
        'id': event.id, 'title': event.titulo,
        'start': event.fecha_inicio.isoformat(),
        'end': event.fecha_fin.isoformat() if event.fecha_fin else None,
        'color': event.color
    }), 201


@admin_bp.route('/api/calendar/events/<int:event_id>', methods=['PUT'])
@admin_required
def calendar_event_update(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    data = request.get_json()

    if 'title' in data:
        event.titulo = data['title']
    if 'descripcion' in data:
        event.descripcion = data['descripcion']
    if 'start' in data:
        try:
            event.fecha_inicio = datetime.fromisoformat(data['start'])
        except ValueError:
            pass
    if 'end' in data:
        try:
            event.fecha_fin = datetime.fromisoformat(data['end'])
        except ValueError:
            pass
    if 'color' in data:
        event.color = data['color']

    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/calendar/events/<int:event_id>', methods=['DELETE'])
@admin_required
def calendar_event_delete(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify({'success': True})


# --- CLIENTES ---

@admin_bp.route('/clientes')
@admin_required
def clients():
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template('admin/clientes.html', users=users)


@admin_bp.route('/clientes/nuevo', methods=['POST'])
@admin_required
@csrf.exempt
def client_new():
    nombre = request.form.get('nombre', '').strip()
    email = request.form.get('email', '').strip().lower()
    whatsapp = request.form.get('whatsapp', '').strip()
    direccion = request.form.get('direccion', '').strip()
    password = request.form.get('password', '').strip()

    if not nombre or not email:
        flash('Nombre y email son obligatorios.', 'danger')
        return redirect(url_for('admin.clients'))

    if User.query.filter_by(email=email).first():
        flash(f'Ya existe un usuario con el email "{email}".', 'danger')
        return redirect(url_for('admin.clients'))

    username = email.split('@')[0]
    base_username = username
    suffix = 1
    while User.query.filter_by(username=username).first():
        username = f'{base_username}{suffix}'
        suffix += 1

    user = User(
        email=email,
        username=username,
        nombre=nombre,
        whatsapp=whatsapp or None,
        direccion=direccion or None,
        email_verificado=True
    )
    if password:
        user.set_password(password)

    db.session.add(user)
    db.session.commit()
    flash(f'Cliente "{nombre}" creado.', 'success')
    return redirect(url_for('admin.clients'))


@admin_bp.route('/clientes/<int:user_id>/editar', methods=['POST'])
@admin_required
@csrf.exempt
def client_edit(user_id):
    user = User.query.get_or_404(user_id)
    user.nombre = request.form.get('nombre', '').strip()
    user.whatsapp = request.form.get('whatsapp', '').strip() or None
    user.direccion = request.form.get('direccion', '').strip() or None
    user.notas = request.form.get('notas', '').strip() or None

    email = request.form.get('email', '').strip().lower()
    if email and email != user.email:
        if User.query.filter_by(email=email).first():
            flash(f'Ya existe otro usuario con el email "{email}".', 'danger')
            return redirect(url_for('admin.clients'))
        user.email = email

    password = request.form.get('password', '').strip()
    if password:
        user.set_password(password)

    db.session.commit()
    flash(f'Cliente "{user.nombre}" actualizado.', 'success')
    return redirect(url_for('admin.clients'))


@admin_bp.route('/clientes/<int:user_id>/toggle-bloqueo', methods=['POST'])
@admin_required
@csrf.exempt
def client_toggle_block(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('No podés bloquear a otro administrador.', 'danger')
        return redirect(url_for('admin.clients'))

    user.is_active_user = not user.is_active_user
    db.session.commit()
    estado = 'bloqueado' if not user.is_active_user else 'activado'
    flash(f'Cliente "{user.nombre}" {estado}.', 'info')
    return redirect(url_for('admin.clients'))


@admin_bp.route('/clientes/<int:user_id>/eliminar', methods=['POST'])
@admin_required
@csrf.exempt
def client_delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('No podés eliminar a otro administrador.', 'danger')
        return redirect(url_for('admin.clients'))

    if user.orders.count() > 0:
        flash(f'No se puede eliminar "{user.nombre}" porque tiene pedidos asociados. Bloquealo en su lugar.', 'danger')
        return redirect(url_for('admin.clients'))

    db.session.delete(user)
    db.session.commit()
    flash(f'Cliente "{user.nombre}" eliminado.', 'success')
    return redirect(url_for('admin.clients'))


# --- PERFIL ADMIN ---

@admin_bp.route('/perfil', methods=['GET', 'POST'])
@admin_required
def profile():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('La contraseña actual no es correcta.', 'danger')
            return redirect(url_for('admin.profile'))

        if not new_password or len(new_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('admin.profile'))

        if new_password != confirm_password:
            flash('Las contraseñas nuevas no coinciden.', 'danger')
            return redirect(url_for('admin.profile'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Contraseña actualizada correctamente.', 'success')
        return redirect(url_for('admin.profile'))

    return render_template('admin/perfil.html')


# --- ADMIN EMAILS (Google OAuth admins) ---

@admin_bp.route('/admin-emails', methods=['GET', 'POST'])
@admin_required
def admin_emails():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('El email es obligatorio.', 'danger')
            return redirect(url_for('admin.admin_emails'))

        if AdminEmail.query.filter_by(email=email).first():
            flash(f'"{email}" ya está en la lista.', 'warning')
            return redirect(url_for('admin.admin_emails'))

        ae = AdminEmail(email=email)
        db.session.add(ae)

        # Si ya existe un usuario con ese email, promoverlo a admin
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_admin = True

        db.session.commit()
        flash(f'"{email}" agregado como admin.', 'success')
        return redirect(url_for('admin.admin_emails'))

    emails = AdminEmail.query.order_by(AdminEmail.created_at.desc()).all()
    return render_template('admin/admin_emails.html', emails=emails)


@admin_bp.route('/admin-emails/<int:email_id>/eliminar', methods=['POST'])
@admin_required
def admin_email_delete(email_id):
    ae = AdminEmail.query.get_or_404(email_id)

    # Quitar is_admin al usuario con ese email si existe
    user = User.query.filter_by(email=ae.email).first()
    if user:
        user.is_admin = False

    db.session.delete(ae)
    db.session.commit()
    flash(f'"{ae.email}" eliminado de admins.', 'info')
    return redirect(url_for('admin.admin_emails'))
