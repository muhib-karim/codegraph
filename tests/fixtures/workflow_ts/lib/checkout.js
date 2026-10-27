import { grandTotal, runSteps } from '../src/index';
import { ReceiptView } from '../src/receipt';
import { MailSink } from './sinks.js';
import Audit from './sinks.js';
import { dispatch, attach as register } from './dispatch.mjs';
import { money } from './format.cjs';
import { legacyReceipt } from './legacy.cjs';

export function checkout(items) {
  const amount = grandTotal(items);
  const sink = new MailSink();
  const receipt = dispatch(sink, money(amount));
  const audit = new Audit();
  audit.record(receipt);
  return receipt;
}

export function configure() {
  return register(checkout);
}

export function main() {
  configure();
  const amount = runSteps(10);
  ReceiptView({ steps: [], amount });
  legacyReceipt(amount);
  return checkout([10, 20]);
}

main();
