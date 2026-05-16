"""
Script para inicializar la base de datos con un usuario admin
y datos de ejemplo para Morena Sin Gluten.

Uso: python seed.py
"""
from app import app
from extensions import db
from models import User, Category, Tag, Product, PrizeWheel, PrizeWheelSegment, CustomizationGroup, CustomizationOption
from decimal import Decimal

def seed():
    with app.app_context():
        # Crear tablas
        db.create_all()

        # Admin user
        if not User.query.filter_by(email='admin@morenasingluten.com').first():
            admin = User(
                email='admin@morenasingluten.com',
                username='admin@morenasingluten.com',
                nombre='Morena Admin',
                is_admin=True,
                whatsapp='+5492966355530'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print('✅ Usuario admin creado (admin@morenasingluten.com / admin123)')

        # Categorías
        cats_data = [
            ('Facturas', 'Facturas sin gluten frescas del día', 1),
            ('Tortas', 'Tortas artesanales para toda ocasión', 2),
            ('Panes', 'Panes frescos sin gluten', 3),
            ('Box / Combos', 'Combos y boxes personalizables', 4),
            ('Pastelería', 'Pastelería fina sin gluten', 5),
            ('Galletitas', 'Galletitas dulces y saladas', 6),
        ]

        cats = {}
        for nombre, desc, orden in cats_data:
            if not Category.query.filter_by(nombre=nombre).first():
                cat = Category(nombre=nombre, descripcion=desc, orden=orden)
                db.session.add(cat)
                db.session.flush()
                cats[nombre] = cat
                print(f'  📁 Categoría: {nombre}')
            else:
                cats[nombre] = Category.query.filter_by(nombre=nombre).first()

        # Etiquetas
        tags_data = [
            ('Sin TACC', '#4CAF50'),
            ('Vegano', '#8BC34A'),
            ('Sin Lácteos', '#FF9800'),
            ('Nuevo', '#E91E63'),
            ('Más Vendido', '#9C27B0'),
        ]

        tags = {}
        for nombre, color in tags_data:
            if not Tag.query.filter_by(nombre=nombre).first():
                tag = Tag(nombre=nombre, color=color)
                db.session.add(tag)
                db.session.flush()
                tags[nombre] = tag
                print(f'  🏷️ Etiqueta: {nombre}')
            else:
                tags[nombre] = Tag.query.filter_by(nombre=nombre).first()

        # Productos
        products_data = [
            ('Docena de Facturas', 'Docena de facturas sin gluten variadas', 5500, 'Facturas', True, ['Sin TACC', 'Más Vendido']),
            ('Media Docena de Facturas', 'Media docena de facturas sin gluten', 3000, 'Facturas', True, ['Sin TACC']),
            ('Torta de Chocolate', 'Torta de chocolate sin gluten, para 10 personas', 12000, 'Tortas', True, ['Sin TACC']),
            ('Torta de Vainilla', 'Torta de vainilla con crema, para 10 personas', 11000, 'Tortas', True, ['Sin TACC']),
            ('Pan de Campo', 'Pan de campo artesanal sin gluten', 3500, 'Panes', False, ['Sin TACC', 'Vegano']),
            ('Pan Lactal', 'Pan lactal sin gluten por unidad', 4000, 'Panes', False, ['Sin TACC']),
            ('Box Desayuno', 'Box desayuno completo personalizable', 9500, 'Box / Combos', True, ['Sin TACC', 'Nuevo']),
            ('Box Merienda', 'Box merienda con facturas y torta', 8000, 'Box / Combos', True, ['Sin TACC']),
            ('Alfajores x6', 'Alfajores de maicena sin gluten x6', 4500, 'Pastelería', False, ['Sin TACC', 'Más Vendido']),
            ('Galletitas de Avena', 'Galletitas de avena sin gluten x12', 3000, 'Galletitas', False, ['Sin TACC', 'Vegano']),
        ]

        for nombre, desc, precio, cat_name, personalizable, tag_names in products_data:
            if not Product.query.filter_by(nombre=nombre).first():
                product = Product(
                    nombre=nombre, descripcion=desc,
                    precio=Decimal(str(precio)),
                    category_id=cats[cat_name].id,
                    es_personalizable=personalizable
                )
                product.tags = [tags[t] for t in tag_names if t in tags]
                db.session.add(product)
                db.session.flush()
                print(f'  🧁 Producto: {nombre} - ${precio}')

                # Personalizaciones
                if personalizable and 'Facturas' in nombre:
                    group = CustomizationGroup(
                        product_id=product.id,
                        nombre='Elegí tus facturas',
                        min_selecciones=0,
                        max_selecciones=12 if 'Docena' in nombre else 6,
                        obligatorio=False
                    )
                    db.session.add(group)
                    db.session.flush()
                    for opt_name in ['Medialunas', 'Cañoncitos de crema', 'Vigilantes', 'Bolas de fraile', 'Tortitas negras', 'Cremona', 'Sacramento']:
                        db.session.add(CustomizationOption(group_id=group.id, nombre=opt_name, precio_extra=0))

                elif personalizable and 'Torta' in nombre:
                    # Grupo de relleno
                    group = CustomizationGroup(
                        product_id=product.id,
                        nombre='Relleno',
                        min_selecciones=1, max_selecciones=2,
                        obligatorio=True
                    )
                    db.session.add(group)
                    db.session.flush()
                    for opt_name, extra in [('Dulce de leche', 0), ('Crema pastelera', 0), ('Mousse de chocolate', 200), ('Frutas frescas', 500)]:
                        db.session.add(CustomizationOption(group_id=group.id, nombre=opt_name, precio_extra=Decimal(str(extra))))

                    # Grupo decoración
                    group2 = CustomizationGroup(
                        product_id=product.id,
                        nombre='Decoración',
                        min_selecciones=0, max_selecciones=3,
                        obligatorio=False
                    )
                    db.session.add(group2)
                    db.session.flush()
                    for opt_name, extra in [('Merengue', 0), ('Ganache de chocolate', 300), ('Fondant', 1500), ('Frutas decorativas', 500)]:
                        db.session.add(CustomizationOption(group_id=group2.id, nombre=opt_name, precio_extra=Decimal(str(extra))))

                elif personalizable and 'Box' in nombre:
                    group = CustomizationGroup(
                        product_id=product.id,
                        nombre='Armá tu box',
                        min_selecciones=3, max_selecciones=6,
                        obligatorio=True
                    )
                    db.session.add(group)
                    db.session.flush()
                    for opt_name, extra in [('Facturas x3', 0), ('Alfajores x2', 0), ('Galletitas', 0), ('Brownie', 300), ('Torta porción', 500), ('Pan de campo', 200), ('Mermelada artesanal', 400)]:
                        db.session.add(CustomizationOption(group_id=group.id, nombre=opt_name, precio_extra=Decimal(str(extra))))

        # Rueda de premios
        if not PrizeWheel.query.first():
            wheel = PrizeWheel(nombre='Rueda de Premios', monto_minimo_activacion=15000, activa=True)
            db.session.add(wheel)
            db.session.flush()

            segments = [
                ('10% OFF', 'descuento_porcentaje', 10, '#C4756E', 3),
                ('15% OFF', 'descuento_porcentaje', 15, '#8B4513', 2),
                ('$500 OFF', 'descuento_fijo', 500, '#4CAF50', 2),
                ('Seguí participando', 'sin_premio', 0, '#9E9E9E', 4),
                ('20% OFF', 'descuento_porcentaje', 20, '#E91E63', 1),
                ('$1000 OFF', 'descuento_fijo', 1000, '#FF9800', 1),
            ]
            for texto, tipo, valor, color, prob in segments:
                seg = PrizeWheelSegment(
                    wheel_id=wheel.id, texto=texto, tipo=tipo,
                    valor=Decimal(str(valor)), color=color, probabilidad=prob
                )
                db.session.add(seg)
            print('  🎡 Rueda de premios configurada')

        db.session.commit()
        print('\n✅ Base de datos inicializada correctamente!')
        print('🔑 Admin: admin@morenasingluten.com / admin123')
        print('🌐 Ejecutá: python app.py')


if __name__ == '__main__':
    seed()
