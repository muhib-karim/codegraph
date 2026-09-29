package flow;

public class Runner {
    static String execute(Processor processor) {
        return processor.process(10);
    }

    public static void main(String[] args) {
        CardProcessor card = new CardProcessor();
        card.convert(3);
        execute(card);
    }
}
