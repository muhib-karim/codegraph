// Notes only: total(items), checkout(), dispatch(sink, receipt), money() and MailSink.send.
export class Preview {
  total(items) {
    return 'total(items) + TAX_RATE, then checkout and money';
  }
}

export class Draft {
  send(receipt) {
    return `dispatch(sink, ${receipt}) via roundCents`;
  }
}
