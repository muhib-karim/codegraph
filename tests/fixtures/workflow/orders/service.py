from .pricing import total
from .sinks import MailSink, AuditSink


def dispatch(sink, receipt):
    return sink.send(receipt)


def checkout(items):
    amount = total(items)
    sink = MailSink()
    receipt = dispatch(sink, str(amount))
    audit = AuditSink()
    audit.record(receipt)
    return receipt


def attach(callback):
    return callback


def configure():
    return attach(checkout)
