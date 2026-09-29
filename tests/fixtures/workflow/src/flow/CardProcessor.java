package flow;

public class CardProcessor extends BaseProcessor {
    @Override
    public String process(int amount) {
        return format(amount + fee);
    }

    public String convert(int amount) {
        return format(amount);
    }

    public String convert(String amount) {
        return amount;
    }

    private void obsolete() {}
}
