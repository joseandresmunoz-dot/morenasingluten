// Morena Sin Gluten - Main JS

function showNotification(message, category = 'success') {
    const alert = document.createElement('div');
    alert.className = `alert alert-${category} alert-dismissible fade show position-fixed top-0 end-0 m-3 shadow`;
    alert.setAttribute('role', 'alert');
    alert.style.zIndex = 1080;
    alert.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    document.body.appendChild(alert);
    setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
    }, 5000);
}

function updateCartCount(count) {
    const cartLink = document.querySelector('a[href$="/carrito"]');
    if (cartLink) {
        let badge = cartLink.querySelector('.position-absolute.badge');
        if (!badge && count > 0) {
            badge = document.createElement('span');
            badge.className = 'position-absolute top-0 start-100 translate-middle badge rounded-pill bg-rosa';
            cartLink.appendChild(badge);
        }
        if (badge) {
            badge.textContent = count;
            if (count === 0) {
                badge.remove();
            }
        }
    }

    const floatingCart = document.querySelector('.floating-cart');
    const floatingBadge = document.querySelector('.floating-cart-badge');
    if (floatingCart && floatingBadge) {
        floatingBadge.textContent = count;
        if (count > 0) {
            floatingCart.classList.remove('d-none');
        } else {
            floatingCart.classList.add('d-none');
        }
    }
}

function initAjaxCartForms() {
    const ajaxCartForms = document.querySelectorAll('form[action$="/carrito/agregar"]');
    if (!ajaxCartForms.length) return;

    ajaxCartForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            const submitBtn = form.querySelector('[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            })
            .then(response => {
                if (response.headers.get('content-type')?.includes('application/json')) {
                    return response.json();
                }
                return response.text().then(text => { throw new Error(text || 'Error al agregar al carrito'); });
            })
            .then(data => {
                if (!data || data.success === false) {
                    throw new Error(data?.message || 'Error al agregar al carrito');
                }
                if (typeof data.cart_count === 'number') {
                    updateCartCount(data.cart_count);
                }
                showNotification(data.message || 'Producto agregado al carrito!', 'success');
            })
            .catch(error => {
                showNotification(error.message || 'Error al agregar al carrito', 'danger');
            })
            .finally(() => {
                if (submitBtn) submitBtn.disabled = false;
            });
        });
    });
}

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert:not(.alert-info):not(.alert-warning)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 5000);
    });

    initAjaxCartForms();
});
