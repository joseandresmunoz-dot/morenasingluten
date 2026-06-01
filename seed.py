"""
Script para inicializar la base de datos con un usuario admin
y datos reales de Morena Sin Gluten.

Uso: python seed.py
"""
from app import app
from extensions import db
from models import User, Category, Tag, Product, ProductImage, PrizeWheel, PrizeWheelSegment, CustomizationGroup, CustomizationOption, StoreConfig
from decimal import Decimal


def seed():
    with app.app_context():
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

        # Store config
        if not StoreConfig.query.first():
            db.session.add(StoreConfig(envio_domicilio_costo=Decimal('4000.00')))
            print('  💰 Configuración de tienda creada')

        # Categorías
        cats_data = [
            ('Panificados', '', '/uploads/20260523193148915660_panificados.jpg', 0),
            ('Facturas', 'Facturas sin gluten frescas del día', '/uploads/20260523193430384373_factutras.jpg', 1),
            ('Tortas', 'Tortas artesanales para toda ocasión', '/uploads/20260523193236028559_tortas.jpg', 2),
            ('Alfajores', 'Alfajores varios', '/uploads/20260523193245459871_ALFAJORES.jpg', 3),
            ('Box / Combos', 'Combos y boxes personalizables', '/uploads/20260523193255860794_BOXCOMBOS.jpg', 4),
            ('Empanadas', 'Empanadas varios sabores', '/uploads/20260523193307564822_EMPANADAS.jpg', 5),
            ('Galletitas', 'Galletitas dulces', '/uploads/20260523193322979507_GALLETITAS.jpg', 6),
            ('Budines', 'Budines de varios sabores', '/uploads/20260523193159101437_BUDINES.jpg', 0),
            ('Canelones', 'Canelones varios sabores.\n3 unidades por porción', '/uploads/20260523193210174365_canelones.jpg', 0),
            ('Keto low carb', 'Productos sin azúcar, elaborado con harinas de almendra o de coco y materias primas de excelente calidad. Apto Diabetico', '/uploads/20260523192846529010_keto.jpg', 0),
            ('Pastas frescas', 'Variedades de pastas frescas', '/uploads/20260523192857932749_PASTASFRESCAS.jpg', 0),
            ('PIZZAS Y PREPIZZAS', 'Pizzas y prepizzas', '/uploads/20260523192906690431_pizzasprepizzas.jpg', 0),
            ('Sandwiches de miga', 'Sandwiches de miga de distintos sabores', '/uploads/20260523192915569448_SANDMIGA.jpg', 0),
            ('Sandwiches Varios', 'Sandwiches salados', '/uploads/20260523193054715580_SANDWICHES_VARIOS.jpg', 0),
            ('Tartas', 'Tartas dulces', '/uploads/20260523192816962841_TARTAS.jpg', 0),
        ]

        cats = {}
        for nombre, desc, imagen, orden in cats_data:
            if not Category.query.filter_by(nombre=nombre).first():
                cat = Category(nombre=nombre, descripcion=desc, imagen=imagen, orden=orden)
                db.session.add(cat)
                db.session.flush()
                cats[nombre] = cat
                print(f'  📁 Categoría: {nombre}')
            else:
                cats[nombre] = Category.query.filter_by(nombre=nombre).first()

        # Etiquetas
        tags_data = [
            ('Sin Gluten', '#df762a'),
            ('Sin TACC', '#4CAF50'),
            ('Sin Lácteos', '#FF9800'),
            ('Nuevo', '#E91E63'),
            ('Más Vendido', '#9C27B0'),
            ('Sin Azúcar', '#6f8ce2'),
            ('Diabeticos', '#30c412'),
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
            {
                'nombre': 'Pan Molde',
                'descripcion': '',
                'precio': 12000,
                'cat_name': 'Panificados',
                'personalizable': False,
                'destacado': True,
                'tags': ['Sin Gluten'],
                'imagen': '/uploads/20260523193731840911_PAN_MOLDE.jpg',
            },
            {
                'nombre': 'Facturas',
                'descripcion': 'Facturas surtidas, podes armar tu bandeja',
                'precio': 11500,
                'cat_name': 'Facturas',
                'personalizable': True,
                'destacado': True,
                'tags': ['Sin Gluten', 'Sin TACC', 'Más Vendido'],
                'imagen': '/uploads/20260523200018721313_FACTURASSURTIDAS.jpg',
            },
            {
                'nombre': 'Ravioles de Jamón y queso',
                'descripcion': 'Plancha de ravioles de jamon y queso por 16 uniades',
                'precio': 17000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523210802721963_RAVIOLES.jpg',
            },
            {
                'nombre': 'Ravioles de ricota y nuez',
                'descripcion': 'Plancha de ravioles de ricota y nuez por 16 unidades',
                'precio': 17000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523210854080104_RAVIOLES.jpg',
            },
            {
                'nombre': 'Ravioles de verduras',
                'descripcion': 'Plancha de ravioles de verduras por 16 unidades',
                'precio': 18000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523210952885628_RAVIOLES.jpg',
            },
            {
                'nombre': 'Sorrentinos de jamón y queso',
                'descripcion': 'Plancha de sorrentinos de jamón y queso',
                'precio': 17000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523211422914896_SORRENTINOS.jpg',
            },
            {
                'nombre': 'Sorrentinos de ricota y nuez',
                'descripcion': 'Plancha de sorrentinos de ricota y nuez por 12 unidades',
                'precio': 17000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523211503561477_SORRENTINOS.jpg',
            },
            {
                'nombre': 'Sorrentinos de verduras',
                'descripcion': 'Plancha de sorrentinos de verduras por 12 unidades',
                'precio': 18000,
                'cat_name': 'Pastas frescas',
                'personalizable': False,
                'destacado': False,
                'tags': ['Sin Gluten', 'Sin TACC'],
                'imagen': '/uploads/20260523211544624501_SORRENTINOS.jpg',
            },
        ]

        for pd in products_data:
            if not Product.query.filter_by(nombre=pd['nombre']).first():
                product = Product(
                    nombre=pd['nombre'],
                    descripcion=pd['descripcion'],
                    precio=Decimal(str(pd['precio'])),
                    category_id=cats[pd['cat_name']].id,
                    es_personalizable=pd['personalizable'],
                    destacado=pd['destacado'],
                )
                product.tags = [tags[t] for t in pd['tags'] if t in tags]
                db.session.add(product)
                db.session.flush()
                print(f'  🧁 Producto: {pd["nombre"]} - ${pd["precio"]}')

                # Product image
                img = ProductImage(product_id=product.id, url=pd['imagen'], orden=0)
                db.session.add(img)

                # Personalizaciones
                if pd['personalizable'] and pd['nombre'] == 'Facturas':
                    group = CustomizationGroup(
                        product_id=product.id,
                        nombre='Elegí tus facturas',
                        min_selecciones=6,
                        max_selecciones=6,
                        obligatorio=True,
                    )
                    db.session.add(group)
                    db.session.flush()
                    for opt_name, extra in [
                        ('Dulce de leche', 0),
                        ('Medialunas', 0),
                        ('Vigilantes', 0),
                        ('Membrillo', 0),
                        ('Crema Pastelera', 0),
                        ('Sacramentos', 2500),
                        ('Cuadrado de Jamón y queso', 3800),
                    ]:
                        db.session.add(CustomizationOption(
                            group_id=group.id, nombre=opt_name,
                            precio_extra=Decimal(str(extra))
                        ))

        # Rueda de premios
        if not PrizeWheel.query.first():
            wheel = PrizeWheel(
                nombre='Rueda de Premios',
                monto_minimo_activacion=Decimal('25000.00'),
                activa=False,
            )
            db.session.add(wheel)
            db.session.flush()

            segments = [
                ('10% descuento', 'descuento_porcentaje', 10, '#f4257e', 2),
                ('20% descuento', 'descuento_porcentaje', 20, '#aa14f0', 1),
                ('5% descuento', 'descuento_porcentaje', 5, '#15f919', 5),
                ('10% descuento', 'descuento_porcentaje', 10, '#8b4513', 1),
                ('20% descuento', 'descuento_porcentaje', 20, '#6bde54', 1),
                ('5% descuento', 'descuento_porcentaje', 5, '#dcf524', 5),
                ('5% descuento', 'descuento_porcentaje', 5, '#f59c5c', 5),
                ('Sin premio', 'sin_premio', 0, '#e56dee', 10),
                ('Sin premio', 'sin_premio', 0, '#3ddff5', 10),
                ('Sin premio', 'sin_premio', 0, '#35e9bc', 10),
                ('Sin premio', 'sin_premio', 0, '#9ef0ca', 10),
            ]
            for texto, tipo, valor, color, prob in segments:
                db.session.add(PrizeWheelSegment(
                    wheel_id=wheel.id, texto=texto, tipo=tipo,
                    valor=Decimal(str(valor)), color=color, probabilidad=prob,
                ))
            print('  🎡 Rueda de premios configurada')

        db.session.commit()
        print('\n✅ Base de datos inicializada correctamente!')
        print('🔑 Admin: admin@morenasingluten.com / admin123')
        print('🌐 Ejecutá: python app.py')


if __name__ == '__main__':
    seed()
