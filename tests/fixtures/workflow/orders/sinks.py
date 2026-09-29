class Sink:
    def send(self, receipt):
        raise NotImplementedError


class MailSink(Sink):
    def send(self, receipt):
        return receipt.upper()


class ArchiveSink(Sink):
    def send(self, receipt):
        return receipt.lower()


class AuditSink:
    def record(self, receipt):
        return len(receipt)
