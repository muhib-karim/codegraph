const RETRY_LIMIT = 3;

// dispatch(sink, receipt) cannot know the sink class statically.
export function dispatch(sink, receipt) {
  return sink.send(receipt);
}

export const attach = (callback) => callback;

export function notifyAll(sinks, receipt) {
  return sinks.map((s) => dispatch(s, receipt));
}
