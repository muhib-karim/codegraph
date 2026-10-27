// Sinks deliver a receipt; dispatch() only sees the base contract.
export class Sink {
  send(receipt) {
    throw new Error('not implemented');
  }
}

export class MailSink extends Sink {
  send(receipt) {
    return this.format(receipt).toUpperCase();
  }

  format(receipt) {
    return `mail:${receipt}`;
  }
}

export class ArchiveSink extends Sink {
  send(receipt) {
    return receipt.toLowerCase();
  }
}

export default class AuditSink {
  record(receipt) {
    return receipt.length;
  }

  flush() {
    return 0;
  }
}
