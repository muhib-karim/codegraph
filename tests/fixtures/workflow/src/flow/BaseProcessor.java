package flow;

public abstract class BaseProcessor implements Processor {
    protected int fee = 2;

    protected String format(int amount) {
        return "receipt:" + amount;
    }
}
