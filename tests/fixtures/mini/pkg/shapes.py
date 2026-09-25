import math

UNUSED_CONST = 3
SCALE = 2


class Shape:
    def area(self):
        raise NotImplementedError

    def describe(self):
        return f"{self.area():.2f}"


class Circle(Shape):
    def __init__(self, r):
        self.r = r

    def area(self):
        return math.pi * self.r ** 2 * SCALE


class Ring(Circle):
    def area(self):
        return super().area() - 1


def _orphan():
    return 1


def make(r):
    def inner(x):
        return Circle(x)
    return inner(r)
