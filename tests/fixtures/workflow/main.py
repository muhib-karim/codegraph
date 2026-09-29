from orders.service import checkout, configure


def main():
    configure()
    return checkout([10, 20])


if __name__ == "__main__":
    main()
