package demo;

public class Dog extends Base implements Animal {
    private int legs = 4;
    private static int unusedField = 0;

    public Dog() { super(1); }

    @Override
    public String sound() { return bark(legs); }

    private String bark(int n) { return "woof" + n; }

    private String bark(int n, int m) { return "woof"; }

    private void neverCalled() {}

    public static void main(String[] args) {
        Dog d = new Dog();
        d.sound();
        Runnable r = Dog::helper;
    }

    static void helper() {}
}

class Base {
    Base(int x) {}
}
