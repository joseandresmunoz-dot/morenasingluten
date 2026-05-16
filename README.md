# 🧁 Morena Sin Gluten - Tienda Online

Tienda online para pedidos de productos sin gluten con sistema de carrito, personalización de productos, cupones, rueda de premios y panel de administración.

## Requisitos

- Python 3.10+
- PostgreSQL
- Cuenta Google Cloud (para OAuth - opcional)

## Instalación

### 1. Crear base de datos PostgreSQL

```sql
CREATE DATABASE morena_sin_gluten;
CREATE USER morena WITH PASSWORD 'tu_password';
GRANT ALL PRIVILEGES ON DATABASE morena_sin_gluten TO morena;
```

### 2. Configurar entorno

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copiar `.env.example` a `.env` y editar:

```bash
cp .env.example .env
```

Completar con tus datos:
- `SECRET_KEY`: clave secreta para Flask
- `DATABASE_URL`: URL de conexión a PostgreSQL
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: credenciales de Google OAuth

### 4. Inicializar la base de datos

```bash
python seed.py
```

Esto crea:
- Usuario admin: `admin@morenasingluten.com` / `admin123`
- Categorías y productos de ejemplo
- Rueda de premios configurada

### 5. Ejecutar

```bash
python app.py
```

Abrir: http://localhost:5000

## Google OAuth (opcional)

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear proyecto → APIs y servicios → Credenciales
3. Crear ID de cliente OAuth 2.0
4. URI de redirección: `http://localhost:5000/auth/google/callback`
5. Copiar Client ID y Secret al `.env`

## Estructura

```
├── app.py                  # App principal Flask
├── config.py               # Configuración
├── extensions.py           # Extensiones Flask
├── models.py               # Modelos SQLAlchemy
├── seed.py                 # Datos iniciales
├── routes/
│   ├── auth.py             # Autenticación y Google OAuth
│   ├── shop.py             # Tienda, carrito, checkout
│   └── admin.py            # Panel de administración
├── templates/
│   ├── base.html           # Template base tienda
│   ├── auth/               # Login, registro, perfil
│   ├── shop/               # Tienda, productos, carrito
│   └── admin/              # Panel admin
└── static/
    ├── css/                # Estilos
    └── js/                 # JavaScript
```

## Funcionalidades

### Tienda
- Catálogo de productos con filtros (categoría, etiqueta, búsqueda)
- Productos personalizables (facturas, tortas, boxes)
- Carrito de compras con sesión
- Checkout con envío de pedido por WhatsApp
- Seña del 50% vía Mercado Pago (alias: lacocinaceliaco)
- Registro manual o con Google OAuth
- Cupones de descuento
- Descuentos automáticos por cantidad o día
- Rueda de premios por monto acumulado

### Panel Admin
- Dashboard con métricas de ventas
- CRUD de productos, categorías y etiquetas
- Gestión de personalizaciones por producto
- Gestión de pedidos con estados
- Sistema de cupones (%, $, envío gratis, por cliente)
- Reglas de descuento automáticas
- Rueda de premios configurable
- Calendario de pedidos (FullCalendar)
- Listado de clientes

## Datos de Pago

- **Alias Mercado Pago:** lacocinaceliaco
- **Titular:** Ana Carolina Iannovelli
- **WhatsApp:** +54 9 2966 355530
