from pkg.shapes import make, Ring
from pkg import shapes


def main():
    c = make(1)
    print(c.describe())
    r = Ring(2)
    r.area()
    shapes.make(3)


if __name__ == "__main__":
    main()
