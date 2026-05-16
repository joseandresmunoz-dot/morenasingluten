from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager
import secrets


# --- USUARIOS ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)  # Null si usa Google OAuth
    whatsapp = db.Column(db.String(20), nullable=True)
    direccion = db.Column(db.String(300), nullable=True)
    google_id = db.Column(db.String(256), nullable=True, unique=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    email_verificado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    coupons = db.relationship('UserCoupon', backref='user', lazy='dynamic')
    prize_spins = db.relationship('PrizeSpin', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def total_spent(self):
        from sqlalchemy import func
        result = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            Order.user_id == self.id,
            Order.status.in_(['confirmado', 'entregado'])
        ).scalar()
        return float(result)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --- PRODUCTOS ---

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    imagen = db.Column(db.String(300), nullable=True)
    orden = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)

    products = db.relationship('Product', backref='category', lazy='dynamic')


product_tags = db.Table('product_tags',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True)
)


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#8B4513')


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    imagen = db.Column(db.String(300), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    es_personalizable = db.Column(db.Boolean, default=False)
    stock_disponible = db.Column(db.Boolean, default=True)
    activo = db.Column(db.Boolean, default=True)
    destacado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tags = db.relationship('Tag', secondary=product_tags, backref=db.backref('products', lazy='dynamic'))
    customization_groups = db.relationship('CustomizationGroup', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    images = db.relationship('ProductImage', backref='product', lazy='dynamic', cascade='all, delete-orphan',
                             order_by='ProductImage.orden')

    @property
    def imagen_principal(self):
        """Devuelve la URL de la imagen principal (primera por orden) o el campo imagen legacy"""
        img = self.images.order_by(ProductImage.orden).first()
        if img:
            return img.url
        return self.imagen

    @property
    def todas_las_imagenes(self):
        """Devuelve lista de todas las imágenes ordenadas"""
        imgs = self.images.order_by(ProductImage.orden).all()
        if imgs:
            return imgs
        if self.imagen:
            return [type('Img', (), {'id': 0, 'url': self.imagen, 'orden': 0})()]
        return []


class ProductImage(db.Model):
    """Imágenes de un producto"""
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    url = db.Column(db.String(300), nullable=False)
    orden = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CustomizationGroup(db.Model):
    """Grupo de personalización para un producto (ej: 'Elegí tus facturas', 'Elegí sabores')"""
    __tablename__ = 'customization_groups'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    min_selecciones = db.Column(db.Integer, default=0)
    max_selecciones = db.Column(db.Integer, default=10)
    obligatorio = db.Column(db.Boolean, default=False)

    options = db.relationship('CustomizationOption', backref='group', lazy='dynamic', cascade='all, delete-orphan')


class CustomizationOption(db.Model):
    """Opción dentro de un grupo de personalización"""
    __tablename__ = 'customization_options'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('customization_groups.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    precio_extra = db.Column(db.Numeric(10, 2), default=0)
    activo = db.Column(db.Boolean, default=True)


# --- PEDIDOS ---

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    descuento = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    senia = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # 50%
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=True)
    status = db.Column(db.String(20), default='pendiente')
    # pendiente, senia_pagada, confirmado, en_preparacion, listo, entregado, cancelado
    notas = db.Column(db.Text, nullable=True)
    tipo_entrega = db.Column(db.String(20), nullable=False, default='retiro')
    costo_envio = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    direccion_entrega = db.Column(db.String(300), nullable=True)
    fecha_retiro = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')

    @staticmethod
    def generate_code():
        return 'MSG-' + secrets.token_hex(4).upper()


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    personalizacion = db.Column(db.JSON, nullable=True)  # Guardar opciones elegidas

    product = db.relationship('Product')


# --- CUPONES Y DESCUENTOS ---

class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(200), nullable=True)
    tipo = db.Column(db.String(20), nullable=False)
    # porcentaje, monto_fijo, envio_gratis
    valor = db.Column(db.Numeric(10, 2), default=0)
    minimo_compra = db.Column(db.Numeric(10, 2), default=0)
    max_usos = db.Column(db.Integer, nullable=True)  # None = ilimitado
    usos_actuales = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_inicio = db.Column(db.DateTime, nullable=True)
    fecha_fin = db.Column(db.DateTime, nullable=True)
    solo_primer_pedido = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relación con usuarios específicos
    user_coupons = db.relationship('UserCoupon', backref='coupon', lazy='dynamic')
    orders = db.relationship('Order', backref='coupon', lazy='dynamic')

    def is_valid(self, user=None, subtotal=0):
        now = datetime.utcnow()
        if not self.activo:
            return False, 'Este cupón no está activo.'
        if self.fecha_inicio and now < self.fecha_inicio:
            return False, 'Este cupón aún no está disponible.'
        if self.fecha_fin and now > self.fecha_fin:
            return False, 'Este cupón ha expirado.'
        if self.max_usos and self.usos_actuales >= self.max_usos:
            return False, 'Este cupón ya alcanzó el máximo de usos.'
        if subtotal < float(self.minimo_compra):
            return False, f'El mínimo de compra para este cupón es ${self.minimo_compra}.'
        if self.solo_primer_pedido and user:
            if user.orders.filter(Order.status != 'cancelado').count() > 0:
                return False, 'Este cupón es solo para el primer pedido.'
        # Verificar si es cupón para usuario específico
        if self.user_coupons.count() > 0 and user:
            uc = self.user_coupons.filter_by(user_id=user.id).first()
            if not uc:
                return False, 'Este cupón no está disponible para tu cuenta.'
            if uc.usado:
                return False, 'Ya usaste este cupón.'
            if not uc.disponible:
                return False, 'Este cupón estará disponible para tu próxima compra.'
        return True, 'Cupón válido.'

    def calculate_discount(self, subtotal):
        if self.tipo == 'porcentaje':
            return float(subtotal) * float(self.valor) / 100
        elif self.tipo == 'monto_fijo':
            return min(float(self.valor), float(subtotal))
        elif self.tipo == 'envio_gratis':
            return 0  # Se maneja aparte
        return 0


class UserCoupon(db.Model):
    """Cupones asignados a usuarios específicos"""
    __tablename__ = 'user_coupons'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=False)
    usado = db.Column(db.Boolean, default=False)
    disponible = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DiscountRule(db.Model):
    """Reglas de descuento automáticas"""
    __tablename__ = 'discount_rules'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    # por_cantidad, por_dia, por_categoria
    condicion = db.Column(db.JSON, nullable=False)
    # Ej: {"min_cantidad": 6, "producto_id": 1} o {"dia_semana": "martes"}
    descuento_tipo = db.Column(db.String(20), nullable=False)  # porcentaje, monto_fijo
    descuento_valor = db.Column(db.Numeric(10, 2), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StoreConfig(db.Model):
    __tablename__ = 'store_config'

    id = db.Column(db.Integer, primary_key=True)
    envio_domicilio_costo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_or_create():
        config = StoreConfig.query.first()
        if not config:
            config = StoreConfig(envio_domicilio_costo=0)
            db.session.add(config)
            db.session.commit()
        return config


# --- RUEDA DE PREMIOS ---

class PrizeWheel(db.Model):
    """Configuración de la rueda de premios"""
    __tablename__ = 'prize_wheel'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    monto_minimo_activacion = db.Column(db.Numeric(10, 2), nullable=False, default=10000)
    activa = db.Column(db.Boolean, default=True)
    token_expiracion_minutos = db.Column(db.Integer, default=30)

    segments = db.relationship('PrizeWheelSegment', backref='wheel', lazy='dynamic', cascade='all, delete-orphan')
    tokens = db.relationship('PrizeWheelToken', backref='wheel', lazy='dynamic', cascade='all, delete-orphan')


class PrizeWheelSegment(db.Model):
    """Segmentos de la rueda"""
    __tablename__ = 'prize_wheel_segments'

    id = db.Column(db.Integer, primary_key=True)
    wheel_id = db.Column(db.Integer, db.ForeignKey('prize_wheel.id'), nullable=False)
    texto = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    valor = db.Column(db.Numeric(10, 2), default=0)
    color = db.Column(db.String(7), default='#8B4513')
    probabilidad = db.Column(db.Integer, default=1)
    cantidad_disponible = db.Column(db.Integer, nullable=True)
    orden = db.Column(db.Integer, default=0)

    @property
    def probabilidad_porcentaje(self):
        """Calcula el porcentaje real de probabilidad basado en el total del wheel"""
        wheel = self.wheel
        if not wheel:
            return 0
        total = sum(s.probabilidad for s in wheel.segments.all())
        if total == 0:
            return 0
        return round((self.probabilidad / total) * 100, 1)

    @property
    def esta_disponible(self):
        """Verifica si el segmento tiene stock disponible"""
        if self.cantidad_disponible is None:
            return True
        return self.cantidad_disponible > 0


class PrizeWheelToken(db.Model):
    """Tokens de giro para evitar manipulaciones"""
    __tablename__ = 'prize_wheel_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wheel_id = db.Column(db.Integer, db.ForeignKey('prize_wheel.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    usado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    @property
    def es_valido(self):
        return not self.usado and datetime.utcnow() < self.expires_at


class PrizeSpin(db.Model):
    """Registro de giros de la rueda"""
    __tablename__ = 'prize_spins'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wheel_id = db.Column(db.Integer, db.ForeignKey('prize_wheel.id'), nullable=False)
    segment_id = db.Column(db.Integer, db.ForeignKey('prize_wheel_segments.id'), nullable=False)
    token_id = db.Column(db.Integer, db.ForeignKey('prize_wheel_tokens.id'), nullable=True)
    monto_acumulado = db.Column(db.Numeric(10, 2), nullable=False)
    premio_aplicado = db.Column(db.Boolean, default=False)
    coupon_generado_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    segment = db.relationship('PrizeWheelSegment')
    coupon_generado = db.relationship('Coupon')


# --- CALENDARIO ---

class CalendarEvent(db.Model):
    """Eventos del calendario del admin"""
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=True)
    color = db.Column(db.String(7), default='#8B4513')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship('Order', backref='calendar_events')
