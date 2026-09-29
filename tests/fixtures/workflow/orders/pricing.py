TAX = 2
UNUSED_RATE = 99


def subtotal(items):
    return sum(items)


def total(items):
    return subtotal(items) + TAX


def _old_discount(amount):
    return amount - 1
